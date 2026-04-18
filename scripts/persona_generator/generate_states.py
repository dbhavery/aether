"""Generate the four state images for a persona pack.

Usage:
    python scripts/persona_generator/generate_states.py <persona_id> [--force] [--state NAME]

Writes `personas/<persona_id>/avatar/states/{idle,listening,thinking,speaking}.png`
using per-state expression modifiers layered on the base persona prompt
(see `prompts.py`). Each state is generated as a fresh 1024x1024 portrait
— we deliberately do NOT inpaint the base portrait, because inpaint
stability at this resolution across the APIs we have is poor.

The identity-preserving pipeline is LivePortrait, which runs at animation
time and takes `portrait.png` as the identity anchor. These state images
are references for LivePortrait's expression library only.

Skips states whose output file already exists unless --force is passed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _backends import generate_square_image  # type: ignore[no-redef]
    from generate_portrait import _append_readme  # type: ignore[no-redef]
    from prompts import PERSONA_PROMPTS, build_state_prompt  # type: ignore[no-redef]
else:  # pragma: no cover
    from ._backends import generate_square_image
    from .generate_portrait import _append_readme
    from .prompts import PERSONA_PROMPTS, build_state_prompt


_REPO_ROOT = Path(__file__).resolve().parents[2]
_STATES = ("idle", "listening", "thinking", "speaking")
_STATE_SIZE = 1024


def generate(
    persona_id: str, *, force: bool = False, only: str | None = None
) -> list[Path]:
    if persona_id not in PERSONA_PROMPTS:
        raise SystemExit(
            f"unknown persona '{persona_id}' — known: {sorted(PERSONA_PROMPTS)}"
        )
    spec = PERSONA_PROMPTS[persona_id]

    states = (only,) if only else _STATES
    if only and only not in _STATES:
        raise SystemExit(f"unknown state '{only}' — expected one of {_STATES}")

    avatar_dir = _REPO_ROOT / "personas" / persona_id / "avatar"
    states_dir = avatar_dir / "states"
    states_dir.mkdir(parents=True, exist_ok=True)

    produced: list[Path] = []
    for state in states:
        out_path = states_dir / f"{state}.png"
        if out_path.exists() and not force:
            print(f"[{persona_id}] states/{state}.png exists — skipping (pass --force)")
            continue

        prompt = build_state_prompt(spec, state)
        print(f"[{persona_id}] generating states/{state}.png …")
        result = generate_square_image(prompt, out_path, size=_STATE_SIZE)
        print(
            f"[{persona_id}] wrote {out_path} via {result.backend}:{result.model}"
        )
        _append_readme(
            avatar_dir,
            persona_id,
            f"states/{state}.png",
            result.backend,
            result.model,
            prompt,
        )
        produced.append(out_path)
    return produced


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("persona_id", help="Persona id (aurora | caelum | luma | ...)")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--state",
        choices=_STATES,
        help="Regenerate only this state instead of all four",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    generate(args.persona_id, force=args.force, only=args.state)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
