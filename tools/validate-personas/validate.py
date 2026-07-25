"""Strict-consumer validation for persona packs.

Usage:
    python tools/validate-personas/validate.py [<persona_id> ...]

Walks each persona's canonical source dir under `personas/<slug>/` and
verifies it would load cleanly through a strict downstream consumer
(e.g., the L6 persona engine after install). Catches drift between
metadata.yaml claims and actual asset files BEFORE the build pipeline
zips a broken pack.

Checks per persona:
  1. `persona.yaml` exists and has `id`, `display_name`, `tagline`,
     `personality.archetype`.
  2. `metadata.yaml` exists and has `schema_version`, `assets` block.
  3. All 4 anchor-set PNGs exist and are non-empty.
  4. All 2 voice WAVs exist with valid headers (wave.open succeeds)
     and report 24 kHz mono 16-bit PCM at expected durations:
     reference.wav = 20.0 s, sample.wav = 4.0 s.
  5. `voice/voice.yaml` and `voice/SOURCE.md` exist.
  6. `metadata.yaml` does NOT mention "PENDING" (graduated).

Returns nonzero exit on any failure; suitable for CI gating.
"""

from __future__ import annotations

import argparse
import sys
import wave
from dataclasses import dataclass, field
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]

_REQUIRED_ANCHOR_FILES = [
    "avatar/anchor.png",
    "avatar/portrait.png",
    "avatar/profile_left.png",
    "avatar/profile_right.png",
]
_REQUIRED_VOICE_FILES = [
    "voice/voice.yaml",
    "voice/SOURCE.md",
]
_VOICE_DURATION_TOLERANCE_SEC = 0.2
_EXPECTED_VOICE_DURATIONS = {
    "voice/reference.wav": 20.0,
    "voice/sample.wav": 4.0,
}
_EXPECTED_VOICE_RATE = 24000
_EXPECTED_VOICE_CHANNELS = 1


@dataclass
class ValidationResult:
    persona_id: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _check_yaml_field(path: Path, field: str) -> str | None:
    """Returns the value or None if not found. Top-level scalar only."""
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{field}:"):
            value = stripped[len(field) + 1 :].strip().strip('"').strip("'")
            return value
    return None


def _check_nested_field(path: Path, parent: str, child: str) -> str | None:
    """Read a single-level-nested scalar field."""
    if not path.exists():
        return None
    in_block = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{parent}:"):
            in_block = True
            continue
        if in_block:
            stripped = line.strip()
            if stripped.startswith(f"{child}:"):
                return stripped[len(child) + 1 :].strip().strip('"').strip("'")
            if line and not line.startswith(" "):
                return None
    return None


def validate_one(persona_id: str) -> ValidationResult:
    res = ValidationResult(persona_id=persona_id)
    pdir = _REPO_ROOT / "personas" / persona_id
    if not pdir.is_dir():
        res.errors.append(f"persona dir does not exist: {pdir}")
        return res

    persona_yaml = pdir / "persona.yaml"
    metadata_yaml = pdir / "metadata.yaml"

    # 1. persona.yaml content
    if not persona_yaml.exists():
        res.errors.append("persona.yaml missing")
    else:
        for field in ("id", "display_name", "tagline"):
            v = _check_yaml_field(persona_yaml, field)
            if not v:
                res.errors.append(f"persona.yaml: missing or empty `{field}`")
        archetype = _check_nested_field(persona_yaml, "personality", "archetype")
        if not archetype:
            res.errors.append(
                "persona.yaml: missing `personality.archetype` (required by L6 persona engine)"
            )
        # id should match dir name
        decl_id = _check_yaml_field(persona_yaml, "id")
        if decl_id and decl_id != persona_id:
            res.errors.append(
                f"persona.yaml id={decl_id!r} does not match dir name {persona_id!r}"
            )

    # 2. metadata.yaml content + no PENDING
    if not metadata_yaml.exists():
        res.errors.append("metadata.yaml missing")
    else:
        text = metadata_yaml.read_text(encoding="utf-8")
        if "schema_version:" not in text:
            res.errors.append("metadata.yaml: missing `schema_version`")
        if "assets:" not in text:
            res.errors.append("metadata.yaml: missing `assets` block")
        if "PENDING" in text:
            res.errors.append(
                "metadata.yaml: still contains `PENDING` marker — pack not graduated"
            )

    # 3. anchor-set PNGs
    for rel in _REQUIRED_ANCHOR_FILES:
        p = pdir / rel
        if not p.exists():
            res.errors.append(f"missing {rel}")
        elif p.stat().st_size < 1024:
            res.errors.append(f"{rel} is suspiciously small ({p.stat().st_size} bytes)")

    # 4. voice WAVs
    for rel, expected_sec in _EXPECTED_VOICE_DURATIONS.items():
        p = pdir / rel
        if not p.exists():
            res.errors.append(f"missing {rel}")
            continue
        try:
            with wave.open(str(p), "rb") as w:
                rate = w.getframerate()
                ch = w.getnchannels()
                frames = w.getnframes()
        except Exception as exc:
            res.errors.append(f"{rel}: WAV header invalid — {exc}")
            continue
        if rate != _EXPECTED_VOICE_RATE:
            res.errors.append(f"{rel}: expected {_EXPECTED_VOICE_RATE} Hz, got {rate}")
        if ch != _EXPECTED_VOICE_CHANNELS:
            res.errors.append(f"{rel}: expected mono ({_EXPECTED_VOICE_CHANNELS} ch), got {ch}")
        actual_sec = frames / rate if rate else 0
        if abs(actual_sec - expected_sec) > _VOICE_DURATION_TOLERANCE_SEC:
            res.errors.append(
                f"{rel}: duration {actual_sec:.2f}s out of tolerance "
                f"({expected_sec}s ± {_VOICE_DURATION_TOLERANCE_SEC}s)"
            )

    # 5. voice docs
    for rel in _REQUIRED_VOICE_FILES:
        p = pdir / rel
        if not p.exists():
            res.errors.append(f"missing {rel}")

    # Soft warnings — non-fatal but worth flagging.
    voice_yaml = pdir / "voice" / "voice.yaml"
    if voice_yaml.exists() and "reference_wav:" not in voice_yaml.read_text(encoding="utf-8"):
        res.warnings.append("voice/voice.yaml: missing `reference_wav` field")

    return res


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("personas", nargs="*",
                        help="persona ids; default = discover all v0-cast dirs")
    parser.add_argument("--strict", action="store_true",
                        help="fail on warnings as well as errors")
    args = parser.parse_args()

    if args.personas:
        targets = args.personas
    else:
        personas_root = _REPO_ROOT / "personas"
        targets = sorted(
            d.name for d in personas_root.iterdir()
            if d.is_dir()
            and (d / "persona.yaml").exists()
            and (d / "avatar" / "anchor.png").exists()
        )

    results = [validate_one(pid) for pid in targets]
    failed = [r for r in results if r.errors]
    warned = [r for r in results if r.warnings]

    for r in results:
        status = "FAIL" if r.errors else ("WARN" if r.warnings else "PASS")
        print(f"[{status}] {r.persona_id}")
        for e in r.errors:
            print(f"    error: {e}")
        for w in r.warnings:
            print(f"    warn:  {w}")

    print(
        f"\n{len(targets)} personas validated: "
        f"{len(targets) - len(failed)} pass, "
        f"{len(failed)} fail, "
        f"{len(warned)} with warnings"
    )

    if failed or (args.strict and warned):
        sys.exit(1)


if __name__ == "__main__":
    main()
