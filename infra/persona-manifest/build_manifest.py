"""Build the master persona manifest from per-persona pack outputs.

Usage:
    # After running tools/build-persona-pack/build.py
    python infra/persona-manifest/build_manifest.py \
        [--in dist/personas] \
        [--out dist/persona-manifest.json] \
        [--base-url https://github.com/dbhavery/aether/releases/download]

Reads all `<slug>-<version>.manifest.json` entries from `--in`,
combines them into a single `dist/persona-manifest.json`, fills the
`asset_url` placeholders if `--base-url` is provided, and writes the
result.

**This script does NOT sign the manifest.** Ed25519 signing requires
Don's offline release key and is performed by a separate
`sign_manifest.py` (not yet built; awaiting key setup). The manifest
produced here carries `signature: null` until signed.

Output schema (per ADR-0012 §5):
    {
      "schema_version": 1,
      "generated": "<ISO-8601>",
      "manifest_version": "<semver>",
      "signature": null,
      "personas": [<entry>, <entry>, ...]
    }

Each entry shape comes from `tools/build-persona-pack/build.py`:
    {
      "slug": "...",
      "version": "...",
      "display_name": "...",
      "archetype": "...",
      "size_bytes": <int>,
      "shared_deps": [],
      "asset_url": "https://.../<slug>-<version>.zip",
      "sha256": "<hex>"
    }

See file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0012-persona-delivery-download-on-demand.md
for the full delivery-pipeline rationale.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_IN = _REPO_ROOT / "dist" / "personas"
_DEFAULT_OUT = _REPO_ROOT / "dist" / "persona-manifest.json"


def build_manifest(
    in_dir: Path,
    out_path: Path,
    *,
    base_url: str | None = None,
    manifest_version: str = "1.0.0",
) -> Path:
    if not in_dir.is_dir():
        raise SystemExit(f"input dir not found: {in_dir} (run build-persona-pack first)")

    entries: list[dict] = []
    for path in sorted(in_dir.glob("*.manifest.json")):
        entry = json.loads(path.read_text(encoding="utf-8"))
        # Fill asset_url if a base URL was provided AND the existing
        # value is the placeholder. Never overwrite a real URL.
        if base_url:
            existing = entry.get("asset_url", "")
            if existing.startswith("TODO://") or existing == "":
                slug = entry["slug"]
                version = entry["version"]
                # Match the GitHub Releases convention from ADR-0012 §5 v0.
                entry["asset_url"] = (
                    f"{base_url.rstrip('/')}/persona-{slug}-{version}/{slug}-{version}.zip"
                )
        entries.append(entry)

    if not entries:
        raise SystemExit(f"no per-persona manifest entries found in {in_dir}")

    manifest = {
        "schema_version": 1,
        "manifest_version": manifest_version,
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(),
        "signature": None,  # filled by sign_manifest.py later
        "personas": entries,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(
        f"wrote {out_path}\n"
        f"  schema_version={manifest['schema_version']}, "
        f"manifest_version={manifest['manifest_version']}, "
        f"personas={len(entries)}, signature=null"
    )
    if any(e["asset_url"].startswith("TODO://") for e in entries):
        unfilled = [e["slug"] for e in entries if e["asset_url"].startswith("TODO://")]
        print(
            f"  WARN {len(unfilled)} entries still carry TODO:// asset_url placeholders: "
            f"{unfilled}\n"
            "  Pass --base-url to fill, or hand-edit before signing."
        )
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="in_dir", type=Path, default=_DEFAULT_IN,
                        help=f"per-persona manifest dir (default: {_DEFAULT_IN.relative_to(_REPO_ROOT)})")
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT,
                        help=f"master manifest path (default: {_DEFAULT_OUT.relative_to(_REPO_ROOT)})")
    parser.add_argument("--base-url",
                        help="base URL to fill asset_url placeholders, e.g. "
                             "https://github.com/dbhavery/aether/releases/download")
    parser.add_argument("--manifest-version", default="1.0.0",
                        help="semver tag for this manifest revision")
    args = parser.parse_args()

    build_manifest(
        args.in_dir,
        args.out,
        base_url=args.base_url,
        manifest_version=args.manifest_version,
    )


if __name__ == "__main__":
    main()
