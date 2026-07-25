"""End-to-end release runner for persona packs.

Usage:
    python tools/release-personas.py [--version 1.0.0] \
        [--base-url https://github.com/dbhavery/aether/releases/download] \
        [--skip-previews] [--skip-validate]

Runs the full release pipeline in order:
    1. tools/validate-personas/validate.py   (strict pre-flight gate)
    2. tools/build-persona-pack/build.py     (Tier-2 zip + sha256 + entry)
    3. tools/build-persona-previews/build.py (Tier-1 bundled previews)
    4. infra/persona-manifest/build_manifest.py (master manifest)

Stops on first failure. The signing step (Ed25519 of the master
manifest) is NOT included — it requires Don's offline release key
and is performed by a separate sign_manifest.py (not yet built).

After this runs successfully, the artefacts to upload are:
    dist/personas/*.zip                  (Tier-2 downloads, per-persona)
    dist/persona-manifest.json           (master manifest, unsigned)
    apps/desktop/src-tauri/resources/personas/previews/*  (committed)

The desktop installer build picks up the previews from the
src-tauri resources path automatically at compile time.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]


def run(label: str, argv: list[str]) -> None:
    print(f"\n=== {label} ===")
    print(f"$ {' '.join(argv)}")
    proc = subprocess.run(argv, cwd=_REPO_ROOT)
    if proc.returncode != 0:
        sys.exit(f"FAILED: {label} exited with code {proc.returncode}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="1.0.0",
                        help="version tag for the persona packs and manifest")
    parser.add_argument("--base-url",
                        default="https://github.com/dbhavery/aether/releases/download",
                        help="base URL for asset_url placeholders in the manifest")
    parser.add_argument("--skip-previews", action="store_true",
                        help="skip the Tier-1 preview bundle rebuild")
    parser.add_argument("--skip-validate", action="store_true",
                        help="skip pre-flight validation (NOT recommended for release)")
    args = parser.parse_args()

    py = sys.executable

    if not args.skip_validate:
        run(
            "Validate persona source dirs",
            [py, "tools/validate-personas/validate.py", "--strict"],
        )

    run(
        "Build Tier-2 persona packs (zip + sha256 + per-pack manifest)",
        [py, "tools/build-persona-pack/build.py", "--version", args.version],
    )

    if not args.skip_previews:
        run(
            "Build Tier-1 bundled previews",
            [py, "tools/build-persona-previews/build.py"],
        )

    run(
        "Aggregate master persona manifest (unsigned)",
        [
            py, "infra/persona-manifest/build_manifest.py",
            "--manifest-version", args.version,
            "--base-url", args.base_url,
        ],
    )

    print("\n=== Release pipeline complete ===")
    print(f"  Tier-2 artefacts:  dist/personas/*-{args.version}.zip")
    print(f"  Master manifest:   dist/persona-manifest.json (UNSIGNED)")
    print(f"  Tier-1 previews:   apps/desktop/src-tauri/resources/personas/previews/")
    print()
    print("Next step: sign dist/persona-manifest.json with Don's offline")
    print("Ed25519 release key (sign_manifest.py — not yet implemented).")
    print("Until then the manifest is not trustworthy in production.")


if __name__ == "__main__":
    main()
