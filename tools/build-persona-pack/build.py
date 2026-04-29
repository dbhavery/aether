"""Build a single persona pack zip + SHA-256 + manifest entry.

Usage:
    python tools/build-persona-pack/build.py <persona_id> [--version 1.0.0] \
        [--out dist/personas]

Reads `personas/<persona_id>/` and produces:
    dist/personas/<persona_id>-<version>.zip
    dist/personas/<persona_id>-<version>.sha256
    dist/personas/<persona_id>-<version>.manifest.json

The zip contains the canonical persona dir minus generation scratch:
    persona.yaml
    metadata.yaml
    avatar/anchor.png
    avatar/portrait.png
    avatar/profile_left.png
    avatar/profile_right.png
    voice/reference.wav
    voice/sample.wav
    voice/voice.yaml
    voice/SOURCE.md

The zip explicitly EXCLUDES:
    avatar/anchor_set_raw_2026-04-28/  (raw JPGs; preserved in repo only)
    avatar/_archived_2026-04-28_first_pass/  (archived first-pass; repo only)
    avatar/README.md  (generation log; useful in repo, not in pack)

Manifest entry shape per ADR-0012 §5:
    {
      "slug": "<persona_id>",
      "version": "<version>",
      "display_name": "...",
      "archetype": "...",
      "size_bytes": <int>,
      "shared_deps": [],
      "asset_url": "TODO — release pipeline fills this",
      "sha256": "<hex>"
    }

Manifest signing (Ed25519) is a separate later step done by the
release-signing tool (`infra/persona-manifest/`). This script
produces the unsigned manifest entry only.

See file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0012-persona-delivery-download-on-demand.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


# Files that ship inside the pack zip. Order is deterministic for
# reproducible-build hashing. Schema version is locked here; bump
# when a new asset becomes part of the contract.
_PACK_INCLUDES = [
    "persona.yaml",
    "metadata.yaml",
    "avatar/anchor.png",
    "avatar/portrait.png",
    "avatar/profile_left.png",
    "avatar/profile_right.png",
    "voice/reference.wav",
    "voice/sample.wav",
    "voice/voice.yaml",
    "voice/SOURCE.md",
]


def _read_yaml_field(yaml_path: Path, field: str) -> str:
    """Tiny YAML extractor — pulls a top-level scalar string field
    without depending on PyYAML. Good enough for `display_name`,
    `archetype`. Returns "" if not found."""
    if not yaml_path.exists():
        return ""
    text = yaml_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{field}:"):
            value = stripped[len(field) + 1 :].strip()
            return value.strip('"').strip("'")
    return ""


def _read_archetype(persona_dir: Path) -> str:
    """`archetype` is nested under `personality:` in persona.yaml.
    Read the raw text and grab the indented value."""
    yaml_path = persona_dir / "persona.yaml"
    if not yaml_path.exists():
        return ""
    in_personality = False
    for line in yaml_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("personality:"):
            in_personality = True
            continue
        if in_personality:
            stripped = line.strip()
            if stripped.startswith("archetype:"):
                return stripped[len("archetype:") :].strip().strip('"').strip("'")
            if line and not line.startswith(" "):
                # Left the personality block.
                return ""
    return ""


def build_pack(
    persona_id: str,
    *,
    version: str = "1.0.0",
    out_dir: Path | None = None,
) -> tuple[Path, Path, Path]:
    persona_dir = _REPO_ROOT / "personas" / persona_id
    if not persona_dir.is_dir():
        raise SystemExit(f"persona dir not found: {persona_dir}")

    out_dir = out_dir or _REPO_ROOT / "dist" / "personas"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Verify all required files exist before opening the zip.
    missing = [
        rel
        for rel in _PACK_INCLUDES
        if not (persona_dir / rel).exists()
    ]
    if missing:
        raise SystemExit(
            f"[{persona_id}] missing required pack files:\n  "
            + "\n  ".join(missing)
        )

    zip_path = out_dir / f"{persona_id}-{version}.zip"
    print(f"[{persona_id}] writing {zip_path} …")
    # Use ZIP_DEFLATED at level 6 for repeatable output. Sort entries
    # by name so two builds of the same source produce the same bytes.
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for rel in sorted(_PACK_INCLUDES):
            src = persona_dir / rel
            arcname = f"{persona_id}/{rel}"
            zf.write(src, arcname=arcname)

    # SHA-256 of the zip bytes.
    sha256 = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    sha_path = out_dir / f"{persona_id}-{version}.sha256"
    sha_path.write_text(f"{sha256}  {zip_path.name}\n", encoding="utf-8")

    # Manifest entry (asset_url is a placeholder filled by the release pipeline).
    display_name = _read_yaml_field(persona_dir / "persona.yaml", "display_name") or persona_id
    archetype = _read_archetype(persona_dir) or "unknown"
    manifest_entry = {
        "slug": persona_id,
        "version": version,
        "display_name": display_name,
        "archetype": archetype,
        "size_bytes": zip_path.stat().st_size,
        "shared_deps": [],
        "asset_url": f"TODO://{persona_id}-{version}.zip",
        "sha256": sha256,
    }
    manifest_path = out_dir / f"{persona_id}-{version}.manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_entry, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(
        f"[{persona_id}] zip={zip_path.stat().st_size} bytes, "
        f"sha256={sha256[:16]}…, archetype={archetype}"
    )
    return zip_path, sha_path, manifest_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("personas", nargs="*",
                        help="persona ids; default = all 9 in personas/")
    parser.add_argument("--version", default="1.0.0")
    parser.add_argument("--out", type=Path, default=None,
                        help="override output dir; default = dist/personas/")
    args = parser.parse_args()

    if args.personas:
        targets = args.personas
    else:
        # Discover persona dirs that are ready to ship: must have
        # persona.yaml AND the new-schema anchor.png. This excludes
        # legacy first-pass-only dirs (_example, caelum, luma) that
        # never received the anchor-set redesign.
        personas_root = _REPO_ROOT / "personas"
        targets = sorted(
            d.name for d in personas_root.iterdir()
            if d.is_dir()
            and (d / "persona.yaml").exists()
            and (d / "avatar" / "anchor.png").exists()
        )
        if not targets:
            raise SystemExit("no shippable personas found in personas/ (need persona.yaml + avatar/anchor.png)")

    failures: list[str] = []
    for pid in targets:
        try:
            build_pack(pid, version=args.version, out_dir=args.out)
        except SystemExit as exc:
            print(f"[{pid}] FAILED: {exc}", file=sys.stderr)
            failures.append(pid)

    print(f"\nBuilt {len(targets) - len(failures)}/{len(targets)} packs.")
    if failures:
        raise SystemExit(f"failed: {failures}")


if __name__ == "__main__":
    main()
