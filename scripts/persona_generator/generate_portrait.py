"""Generate the base portrait.png for a persona pack.

Usage:
    python scripts/persona_generator/generate_portrait.py <persona_id> [--force]

Writes `personas/<persona_id>/avatar/portrait.png` at exactly 1024x1024
using the per-persona prompt template from `prompts.py`. Appends a
reproducibility note to `avatar/README.md` so the exact prompt + model
used is captured for future regeneration.

Skips if the target file already exists unless --force is passed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Support running as a script or as a module.
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _backends import generate_square_image  # type: ignore[no-redef]
    from prompts import PERSONA_PROMPTS, build_portrait_prompt  # type: ignore[no-redef]
else:  # pragma: no cover — used when someone imports the module path
    from ._backends import generate_square_image
    from .prompts import PERSONA_PROMPTS, build_portrait_prompt


_REPO_ROOT = Path(__file__).resolve().parents[2]
_PORTRAIT_SIZE = 1024


def generate(persona_id: str, *, force: bool = False) -> Path:
    """Generate the portrait for `persona_id`; return the output path."""
    if persona_id not in PERSONA_PROMPTS:
        raise SystemExit(
            f"unknown persona '{persona_id}' — known: {sorted(PERSONA_PROMPTS)}"
        )
    spec = PERSONA_PROMPTS[persona_id]
    prompt = build_portrait_prompt(spec)

    out_dir = _REPO_ROOT / "personas" / persona_id / "avatar"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "portrait.png"

    if out_path.exists() and not force:
        print(f"[{persona_id}] portrait.png already exists — pass --force to regenerate")
        return out_path

    print(f"[{persona_id}] generating portrait ({_PORTRAIT_SIZE}x{_PORTRAIT_SIZE}) …")
    result = generate_square_image(prompt, out_path, size=_PORTRAIT_SIZE)
    print(f"[{persona_id}] wrote {out_path} via {result.backend}:{result.model}")

    _append_readme(out_dir, persona_id, "portrait.png", result.backend, result.model, prompt)
    return out_path


def _append_readme(
    avatar_dir: Path,
    persona_id: str,
    filename: str,
    backend: str,
    model: str,
    prompt: str,
) -> None:
    """Append the generation recipe for a file to avatar/README.md."""
    readme = avatar_dir / "README.md"
    header = (
        f"# Avatar assets for persona '{persona_id}'\n\n"
        "Each section below records exactly how one asset was generated.\n"
        "Add a new section any time an asset is regenerated — do not\n"
        "overwrite history. Schema: `docs/PERSONA-SCHEMA.md`.\n"
    )
    if not readme.exists():
        readme.write_text(header, encoding="utf-8")

    block = (
        f"\n## `{filename}`\n"
        f"- backend: `{backend}`\n"
        f"- model: `{model}`\n"
        f"- prompt:\n\n"
        "```text\n"
        f"{prompt}\n"
        "```\n"
    )
    with readme.open("a", encoding="utf-8") as fh:
        fh.write(block)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("persona_id", help="Persona id (aurora | caelum | luma | ...)")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate even if portrait.png already exists",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    generate(args.persona_id, force=args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
