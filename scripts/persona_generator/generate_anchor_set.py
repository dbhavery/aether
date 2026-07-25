"""Generate the 4-image anchor set for a persona via fal.ai flux-pro.

Usage:
    python scripts/persona_generator/generate_anchor_set.py [<persona_id> ...]

Reads each persona's avatar/README.md, extracts the 4 prompts (anchor,
portrait, profile_left, profile_right), submits them to fal.ai
flux-pro/v1.1-ultra at 16:9 aspect ratio, downloads the results to:

    personas/<id>/avatar/anchor.png
    personas/<id>/avatar/portrait.png
    personas/<id>/avatar/profile_left.png
    personas/<id>/avatar/profile_right.png

Also saves raw JPG copies to anchor_set_raw_2026-04-28/ for re-cropping
without quality loss, matching Aurora's pack convention. Appends a
generation log block to avatar/README.md with model + request_id + URL
for each image.

If a persona's profile_right prompt is described as "Same as profile_left,
head turned 30 degrees left" (the common abbreviated form), the script
derives profile_right by string-mutating profile_left.

Skips persona if anchor.png already exists unless --force is passed.

Cost: ~$0.05 per call * 4 = $0.20 per persona, ~$1.60 for the 8 pending.
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

import fal_client


_REPO_ROOT = Path(__file__).resolve().parents[2]

PENDING_PERSONAS = [
    "marcus_chen",
    "sara_reyes",
    "james_whitfield",
    "nadia_volkov",
    "priya_iyer",
    "ray_castellano",
    "hannah_park",
    "tomas_andrade",
]

_MODEL = "fal-ai/flux-pro/v1.1-ultra"
_ASPECT = "16:9"
_PROMPT_HEADING_RE = re.compile(r"^## Prompt: `(?P<file>[a-z_]+\.png)`", re.MULTILINE)
_TEXT_BLOCK_RE = re.compile(r"```text\n(?P<prompt>.+?)\n```", re.DOTALL)
_ASSET_NAMES = ["anchor.png", "portrait.png", "profile_left.png", "profile_right.png"]


def extract_prompts(readme_path: Path) -> dict[str, str]:
    text = readme_path.read_text(encoding="utf-8")
    # Walk through ## Prompt: `X.png` headings in order and pair each
    # with the next ```text...``` block that appears before the next
    # ## heading (any kind). Allows prose between heading and code.
    found: dict[str, str] = {}
    headings = list(_PROMPT_HEADING_RE.finditer(text))
    for i, m in enumerate(headings):
        asset = m.group("file")
        section_end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        # Look for next "## " (any) AFTER this heading but stop at section_end.
        next_anyheading = re.search(r"^## ", text[m.end():section_end], re.MULTILINE)
        local_end = m.end() + next_anyheading.start() if next_anyheading else section_end
        block = _TEXT_BLOCK_RE.search(text, m.end(), local_end)
        if block:
            found[asset] = block.group("prompt").strip()
    if "profile_left.png" in found and "profile_right.png" not in found:
        # Derive profile_right by mutating profile_left's head-turn direction.
        left = found["profile_left.png"]
        right = re.sub(
            r"head turned 30 degrees right \(showing (?:her|his) left 3/4\)",
            "head turned 30 degrees left (showing the right 3/4)",
            left,
        )
        if right == left:
            # Fallback substitution patterns.
            right = left.replace("3/4 left", "3/4 right")
        found["profile_right.png"] = right
    missing = [a for a in _ASSET_NAMES if a not in found]
    if missing:
        raise SystemExit(f"missing prompt blocks in {readme_path}: {missing}")
    return found


def download(url: str, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as resp, out.open("wb") as f:
        f.write(resp.read())


def generate_one(persona_id: str, *, force: bool = False) -> None:
    avatar_dir = _REPO_ROOT / "personas" / persona_id / "avatar"
    raw_dir = avatar_dir / "anchor_set_raw_2026-04-28"
    readme = avatar_dir / "README.md"

    if not readme.exists():
        print(f"[{persona_id}] no avatar/README.md — skipping")
        return

    if (avatar_dir / "anchor.png").exists() and not force:
        print(f"[{persona_id}] anchor.png exists — pass --force to regenerate")
        return

    prompts = extract_prompts(readme)
    print(f"[{persona_id}] extracted {len(prompts)} prompts; submitting to fal.ai …")

    log_blocks: list[str] = []
    for asset in _ASSET_NAMES:
        prompt = prompts[asset]
        print(f"  - {asset}: submitting …")
        result = fal_client.subscribe(
            _MODEL,
            arguments={
                "prompt": prompt,
                "aspect_ratio": _ASPECT,
                "num_images": 1,
                "enable_safety_checker": False,
                "output_format": "jpeg",
            },
            with_logs=False,
        )
        if "images" not in result or not result["images"]:
            raise SystemExit(f"[{persona_id}] no images in fal.ai response for {asset}")
        url = result["images"][0]["url"]
        request_id = result.get("request_id", "?")

        raw_path = raw_dir / asset.replace(".png", "_raw.jpg")
        png_path = avatar_dir / asset
        download(url, raw_path)
        # Save a PNG copy alongside the raw JPG so the loader's expected
        # filename exists. Pillow round-trip preserves the 2752×1536 raw output.
        from PIL import Image  # type: ignore[import-not-found]

        img = Image.open(raw_path).convert("RGB")
        img.save(png_path, format="PNG", optimize=True)
        print(f"    wrote {png_path.name} ({png_path.stat().st_size} bytes) + raw")

        log_blocks.append(
            f"\n### {asset} — generated {date.today().isoformat()}\n"
            f"- backend: `fal.ai`\n"
            f"- model: `{_MODEL}`\n"
            f"- aspect_ratio: `{_ASPECT}`\n"
            f"- request_id: `{request_id}`\n"
            f"- source URL: {url}\n"
            f"- raw output: kept at `anchor_set_raw_2026-04-28/{raw_path.name}`\n"
        )

    # Append generation logs to README.md (additive, do not overwrite the
    # prompt briefs above).
    with readme.open("a", encoding="utf-8") as f:
        f.write(
            f"\n---\n\n## Generation log — {date.today().isoformat()}\n"
            "Generated end-to-end via "
            "scripts/persona_generator/generate_anchor_set.py.\n"
        )
        for block in log_blocks:
            f.write(block)

    print(f"[{persona_id}] done.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("personas", nargs="*", help="persona ids; default = all PENDING")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    targets = args.personas if args.personas else PENDING_PERSONAS
    unknown = set(args.personas) - set(PENDING_PERSONAS) if args.personas else set()
    if unknown:
        raise SystemExit(f"unknown persona(s): {sorted(unknown)}")

    for pid in targets:
        try:
            generate_one(pid, force=args.force)
        except Exception as exc:
            print(f"[{pid}] FAILED: {exc}")

    print("\nAll done.")


if __name__ == "__main__":
    main()
