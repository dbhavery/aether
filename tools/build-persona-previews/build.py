"""Build the bundled Tier-1 preview bundle for each persona.

Usage:
    python tools/build-persona-previews/build.py [<persona_id> ...] \
        [--out apps/desktop/src-tauri/resources/personas/previews]

For each persona, derives a lightweight preview bundle from the
canonical full-asset source at `personas/<slug>/`:

    <out>/<slug>/preview.webp        — 256×256 WebP, ≤ 100 KB
    <out>/<slug>/preview_voice.opus  — Opus 24 kbps mono, 3 s, ≤ 30 KB
    <out>/<slug>/preview.yaml        — display_name, tagline, archetype

Total bundle target: ≤ 130 KB per persona × 9 = ~1.2 MB.

These bundles are baked into the desktop installer per
ADR-0012 §3 Tier 1, so the onboarding wizard can show all 9 cast
cards offline. Re-derive from source whenever a persona's portrait
or sample is regenerated.

Runtime dependencies: PIL (Pillow) for WebP, ffmpeg on PATH for Opus.

See file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0012-persona-delivery-download-on-demand.md
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image  # type: ignore[import-not-found]


_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUT = (
    _REPO_ROOT / "apps" / "desktop" / "public" / "personas-previews"
)

# Tier-1 budget per persona (target, not enforced — log if exceeded).
_TARGET_WEBP_BYTES = 100 * 1024
_TARGET_OPUS_BYTES = 30 * 1024
_PREVIEW_SIZE = 256
_PREVIEW_VOICE_SECONDS = 3.0


def _ensure_ffmpeg() -> None:
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not found on PATH — install ffmpeg first")


def _read_field(yaml_path: Path, field: str) -> str:
    """Tiny YAML scalar reader (top-level only). Returns "" if absent."""
    if not yaml_path.exists():
        return ""
    for line in yaml_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{field}:"):
            return stripped[len(field) + 1 :].strip().strip('"').strip("'")
    return ""


def _read_archetype(persona_yaml: Path) -> str:
    """Read `personality.archetype` (nested one level)."""
    if not persona_yaml.exists():
        return ""
    in_block = False
    for line in persona_yaml.read_text(encoding="utf-8").splitlines():
        if line.startswith("personality:"):
            in_block = True
            continue
        if in_block:
            stripped = line.strip()
            if stripped.startswith("archetype:"):
                return stripped[len("archetype:") :].strip().strip('"').strip("'")
            if line and not line.startswith(" "):
                return ""
    return ""


def _build_webp(portrait_png: Path, out_webp: Path) -> None:
    """Center-crop the 16:9 portrait to a square then resize to 256² WebP."""
    img = Image.open(portrait_png).convert("RGB")
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    img = img.resize((_PREVIEW_SIZE, _PREVIEW_SIZE), Image.LANCZOS)
    out_webp.parent.mkdir(parents=True, exist_ok=True)
    # Quality 78 keeps faces sharp at 256² without blowing the budget.
    img.save(out_webp, format="WEBP", quality=78, method=6)


def _build_opus(sample_wav: Path, out_opus: Path) -> None:
    """Trim the sample to 3 seconds, encode as Opus 24 kbps mono."""
    out_opus.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(sample_wav),
        "-t", str(_PREVIEW_VOICE_SECONDS),
        "-ac", "1",  # mono
        "-c:a", "libopus",
        "-b:a", "24k",
        "-application", "voip",  # tuned for speech, not music
        str(out_opus),
    ]
    subprocess.run(cmd, check=True)


def _build_preview_yaml(persona_dir: Path, out_yaml: Path) -> None:
    persona_yaml = persona_dir / "persona.yaml"
    display_name = _read_field(persona_yaml, "display_name")
    tagline = _read_field(persona_yaml, "tagline")
    archetype = _read_archetype(persona_yaml)

    # Pull the slug from the directory.
    slug = persona_dir.name

    out_yaml.parent.mkdir(parents=True, exist_ok=True)
    out_yaml.write_text(
        f"""schema_version: 1

# Lightweight preview metadata bundled into the desktop installer.
# Derived from personas/{slug}/persona.yaml at release-build time
# by tools/build-persona-previews/build.py. Do not hand-edit.

slug: "{slug}"
display_name: {_quote(display_name)}
tagline: {_quote(tagline)}
archetype: "{archetype}"
""",
        encoding="utf-8",
    )


def _quote(s: str) -> str:
    """YAML-quote a string defensively. Wraps in double quotes,
    escaping internal double quotes."""
    if s == "":
        return '""'
    if any(c in s for c in ('"', "\\")):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return f'"{s}"'


def build_one(persona_id: str, out_root: Path) -> None:
    persona_dir = _REPO_ROOT / "personas" / persona_id
    if not persona_dir.is_dir():
        raise SystemExit(f"persona dir not found: {persona_dir}")

    portrait = persona_dir / "avatar" / "portrait.png"
    sample_wav = persona_dir / "voice" / "sample.wav"

    if not portrait.exists():
        raise SystemExit(f"[{persona_id}] missing avatar/portrait.png")
    if not sample_wav.exists():
        raise SystemExit(f"[{persona_id}] missing voice/sample.wav")

    out_dir = out_root / persona_id

    print(f"[{persona_id}] building preview bundle …")
    webp_out = out_dir / "preview.webp"
    opus_out = out_dir / "preview_voice.opus"
    yaml_out = out_dir / "preview.yaml"

    _build_webp(portrait, webp_out)
    _build_opus(sample_wav, opus_out)
    _build_preview_yaml(persona_dir, yaml_out)

    webp_bytes = webp_out.stat().st_size
    opus_bytes = opus_out.stat().st_size
    yaml_bytes = yaml_out.stat().st_size
    total = webp_bytes + opus_bytes + yaml_bytes

    print(
        f"[{persona_id}] webp={webp_bytes} opus={opus_bytes} "
        f"yaml={yaml_bytes} total={total} bytes"
    )
    if webp_bytes > _TARGET_WEBP_BYTES:
        print(f"[{persona_id}] WARN webp exceeds 100 KB target")
    if opus_bytes > _TARGET_OPUS_BYTES:
        print(f"[{persona_id}] WARN opus exceeds 30 KB target")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("personas", nargs="*",
                        help="persona ids; default = all 9 cast members")
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT,
                        help=f"output dir (default: {_DEFAULT_OUT.relative_to(_REPO_ROOT)})")
    args = parser.parse_args()

    _ensure_ffmpeg()

    if args.personas:
        targets = args.personas
    else:
        # Require anchor.png to filter to the v0 cast (same rule as
        # tools/build-persona-pack/). Excludes legacy first-pass-only
        # dirs caelum + luma, which were cut from the 9-cast.
        personas_root = _REPO_ROOT / "personas"
        targets = sorted(
            d.name for d in personas_root.iterdir()
            if d.is_dir()
            and (d / "persona.yaml").exists()
            and (d / "avatar" / "anchor.png").exists()
            and (d / "avatar" / "portrait.png").exists()
            and (d / "voice" / "sample.wav").exists()
        )
        if not targets:
            raise SystemExit("no shippable personas found (need anchor.png + portrait.png + sample.wav)")

    args.out.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    grand_total = 0
    for pid in targets:
        try:
            build_one(pid, args.out)
            for f in (args.out / pid).iterdir():
                grand_total += f.stat().st_size
        except (SystemExit, subprocess.CalledProcessError) as exc:
            print(f"[{pid}] FAILED: {exc}", file=sys.stderr)
            failures.append(pid)

    # Emit an index.json so the frontend can fetch a single file
    # instead of N separate preview.yaml files. Sorted slug order
    # for deterministic builds.
    import json

    index_entries: list[dict] = []
    for pid in sorted(set(targets) - set(failures)):
        persona_yaml = _REPO_ROOT / "personas" / pid / "persona.yaml"
        index_entries.append({
            "slug": pid,
            "display_name": _read_field(persona_yaml, "display_name"),
            "tagline": _read_field(persona_yaml, "tagline"),
            "archetype": _read_archetype(persona_yaml),
            "preview_webp": f"{pid}/preview.webp",
            "preview_voice_opus": f"{pid}/preview_voice.opus",
        })
    index_path = args.out / "index.json"
    index_path.write_text(
        json.dumps({"schema_version": 1, "personas": index_entries},
                   indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"\nWrote {index_path} ({len(index_entries)} entries)")

    print(
        f"Built {len(targets) - len(failures)}/{len(targets)} preview "
        f"bundles. Grand total bundled bytes: {grand_total} "
        f"({grand_total / 1024 / 1024:.2f} MB)."
    )
    if failures:
        raise SystemExit(f"failed: {failures}")


if __name__ == "__main__":
    main()
