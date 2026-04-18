"""Persona pack loader — scans disk, validates against the schema, returns packs.

Validation rules enforced here mirror `docs/PERSONA-SCHEMA.md` §5. Any change
there must be reflected here and in `audit.py`.

Failure policy (important):
  * For **bundled** packs, a validation failure raises `PersonaValidationError`.
    Bundled packs ship with the product; broken ones are engineering bugs and
    should halt startup so we catch them in CI, not in the field.
  * For **user** packs, a validation failure is logged as a warning and the
    pack is skipped. User-authored packs must not crash the app.
"""

from __future__ import annotations

import wave
from pathlib import Path

import yaml
from loguru import logger
from pydantic import ValidationError

from src.personas.models import PersonaManifest, PersonaMetadata, PersonaPack


class PersonaValidationError(Exception):
    """Raised when a bundled persona pack fails validation.

    User pack failures are logged and skipped — they do not raise.
    """


# Validation thresholds from PERSONA-SCHEMA.md §5.
_MIN_REFERENCE_WAV_SECONDS = 5.0
_MAX_REFERENCE_WAV_SECONDS = 60.0
_MIN_PORTRAIT_DIMENSION = 512
_PORTRAIT_ASPECT_TOLERANCE = 0.10  # ±10% from square

_REQUIRED_STATE_IMAGES = ("idle", "listening", "thinking", "speaking")


def scan_personas(bundled_dir: Path, user_dir: Path) -> dict[str, PersonaPack]:
    """Scan both persona directories and return validated packs keyed by id.

    User packs with an `id` matching a bundled pack override the bundled one
    (logged at INFO level so it's visible during dev). Packs whose folder name
    starts with `_` are treated as reference/example scaffolds and skipped.

    Args:
        bundled_dir: Ship-included persona root (e.g. ``personas/`` in repo).
        user_dir: User override root (e.g. ``%APPDATA%/aether/personas/``).

    Returns:
        Mapping ``{persona_id: PersonaPack}``. Empty if both dirs are empty or
        missing.

    Raises:
        PersonaValidationError: A bundled pack failed validation. User pack
            failures are logged and skipped.
    """
    packs: dict[str, PersonaPack] = {}

    # Bundled first. A failure here is a shipping bug.
    for pack in _scan_directory(bundled_dir, is_user_dir=False):
        packs[pack.id] = pack

    # Then user overrides.
    for pack in _scan_directory(user_dir, is_user_dir=True):
        if pack.id in packs:
            logger.info(
                f"personas: user pack '{pack.id}' overrides bundled pack "
                f"(bundled={packs[pack.id].root_dir}, user={pack.root_dir})"
            )
        packs[pack.id] = pack

    logger.info(f"personas: loaded {len(packs)} pack(s) — {sorted(packs)}")
    return packs


def _scan_directory(root: Path, *, is_user_dir: bool) -> list[PersonaPack]:
    """Iterate direct subdirectories of `root` and validate each as a pack.

    Private helper — callers should use `scan_personas`.
    """
    if not root.exists():
        logger.debug(f"personas: scan skipped — {root} does not exist")
        return []
    if not root.is_dir():
        logger.warning(f"personas: scan skipped — {root} is not a directory")
        return []

    packs: list[PersonaPack] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.startswith("_"):
            logger.debug(f"personas: skipping reference pack {entry.name}")
            continue
        try:
            packs.append(_load_pack(entry, is_user_pack=is_user_dir))
        except PersonaValidationError as exc:
            if is_user_dir:
                logger.warning(f"personas: skipping user pack '{entry.name}' — {exc}")
            else:
                # Re-raise for bundled packs. Ship-blocker.
                raise
    return packs


def _load_pack(pack_dir: Path, *, is_user_pack: bool) -> PersonaPack:
    """Load, validate, and assemble a single persona pack from disk."""
    manifest = _load_manifest(pack_dir)
    metadata = _load_metadata(pack_dir)

    # Cross-file rule: folder name must match manifest id (schema §5).
    if manifest.id != pack_dir.name:
        raise PersonaValidationError(
            f"persona id '{manifest.id}' does not match folder name '{pack_dir.name}' "
            f"(see PERSONA-SCHEMA.md §5)"
        )

    _check_required_files(pack_dir)
    _validate_reference_wav(pack_dir / "voice" / "reference.wav")
    _validate_portrait(pack_dir / "avatar" / "portrait.png")

    return PersonaPack(
        manifest=manifest,
        metadata=metadata,
        root_dir=pack_dir,
        is_user_pack=is_user_pack,
    )


def _load_manifest(pack_dir: Path) -> PersonaManifest:
    path = pack_dir / "persona.yaml"
    raw = _read_yaml(path)
    try:
        return PersonaManifest.model_validate(raw)
    except ValidationError as exc:
        raise PersonaValidationError(
            f"{path} is invalid against PERSONA-SCHEMA.md §2:\n{exc}"
        ) from exc


def _load_metadata(pack_dir: Path) -> PersonaMetadata:
    path = pack_dir / "metadata.yaml"
    raw = _read_yaml(path)
    try:
        return PersonaMetadata.model_validate(raw)
    except ValidationError as exc:
        raise PersonaValidationError(
            f"{path} is invalid against PERSONA-SCHEMA.md §4:\n{exc}"
        ) from exc


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        raise PersonaValidationError(f"missing required file: {path}")
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise PersonaValidationError(f"{path} is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise PersonaValidationError(
            f"{path} must parse to a mapping, got {type(data).__name__}"
        )
    return data


def _check_required_files(pack_dir: Path) -> None:
    """Verify every REQUIRED asset listed in PERSONA-SCHEMA.md §1 exists."""
    required = [
        pack_dir / "persona.yaml",
        pack_dir / "metadata.yaml",
        pack_dir / "avatar" / "portrait.png",
        pack_dir / "voice" / "reference.wav",
        pack_dir / "voice" / "sample.wav",
    ]
    required.extend(pack_dir / "avatar" / "states" / f"{name}.png" for name in _REQUIRED_STATE_IMAGES)

    missing = [p for p in required if not p.exists()]
    if missing:
        rel = [str(p.relative_to(pack_dir)) for p in missing]
        raise PersonaValidationError(
            f"pack '{pack_dir.name}' missing required files: {rel} "
            f"(see PERSONA-SCHEMA.md §1)"
        )


def _validate_reference_wav(path: Path) -> None:
    """Enforce schema §5: 5s <= reference.wav duration <= 60s."""
    try:
        with wave.open(str(path), "rb") as wav:
            frames = wav.getnframes()
            rate = wav.getframerate()
    except wave.Error as exc:
        raise PersonaValidationError(f"{path} is not a valid WAV file: {exc}") from exc
    except OSError as exc:
        raise PersonaValidationError(f"{path} could not be read: {exc}") from exc

    if rate <= 0:
        raise PersonaValidationError(f"{path} reports sample rate {rate}")
    duration = frames / rate
    if duration < _MIN_REFERENCE_WAV_SECONDS:
        raise PersonaValidationError(
            f"{path} is {duration:.2f}s — minimum is {_MIN_REFERENCE_WAV_SECONDS:.0f}s "
            f"(see PERSONA-SCHEMA.md §5)"
        )
    if duration > _MAX_REFERENCE_WAV_SECONDS:
        raise PersonaValidationError(
            f"{path} is {duration:.2f}s — maximum is {_MAX_REFERENCE_WAV_SECONDS:.0f}s "
            f"(see PERSONA-SCHEMA.md §5)"
        )


def _validate_portrait(path: Path) -> None:
    """Enforce schema §5: portrait.png >= 512x512 and near-square (±10%).

    We parse the PNG header directly to avoid adding Pillow as a hard dep for
    something the loader can read from raw bytes. PNG spec: first 8 bytes
    magic, then an IHDR chunk whose data starts with big-endian u32 width,
    u32 height.
    """
    try:
        with path.open("rb") as f:
            header = f.read(24)
    except OSError as exc:
        raise PersonaValidationError(f"{path} could not be read: {exc}") from exc

    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise PersonaValidationError(f"{path} is not a valid PNG (bad magic)")
    if header[12:16] != b"IHDR":
        raise PersonaValidationError(f"{path} has unexpected PNG structure (missing IHDR)")

    width = int.from_bytes(header[16:20], "big")
    height = int.from_bytes(header[20:24], "big")

    if width < _MIN_PORTRAIT_DIMENSION or height < _MIN_PORTRAIT_DIMENSION:
        raise PersonaValidationError(
            f"{path} is {width}x{height} — minimum is "
            f"{_MIN_PORTRAIT_DIMENSION}x{_MIN_PORTRAIT_DIMENSION} (see PERSONA-SCHEMA.md §5)"
        )

    longer, shorter = max(width, height), min(width, height)
    # Guard: longer==0 is impossible here (both >= MIN), but keeps future edits safe.
    aspect_skew = (longer - shorter) / longer if longer else 0.0
    if aspect_skew > _PORTRAIT_ASPECT_TOLERANCE:
        raise PersonaValidationError(
            f"{path} aspect skew {aspect_skew:.2%} exceeds "
            f"{_PORTRAIT_ASPECT_TOLERANCE:.0%} tolerance — portrait must be near-square "
            f"(see PERSONA-SCHEMA.md §5)"
        )


__all__ = ["PersonaValidationError", "scan_personas"]
