"""Run the Doctrine §8 selftest pass against an existing Phase 0 batch.

Companion to phase0_baseline.py — once a baseline image lands on disk
this wraps the multimodal-vision evaluation step. Runs against the
local Qwen2-VL backend by default (sanctioned bare-metal Phase 2 path),
falling back to OpenAI gpt-4o-mini when explicitly requested.

Usage (live, runs Qwen2-VL on the GPU):

    PERSONA_REFGEN_SELFTEST_LIVE=1 \\
    PERSONA_REFGEN_SELFTEST_BACKEND=qwen2vl \\
        python tools/persona-reference-gen/phase0_evaluate.py \\
            --persona aurora --batch 2026-05-02-phase0

Stub mode (no env var) is honoured — every candidate scores 8/yes/yes
deterministically. Useful for verifying the runner glue without a GPU.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from output_schema import (  # noqa: E402  — sys.path mutation above
    SelfTestRow,
    read_manifest,
)
from selftest import (  # noqa: E402
    is_live_mode,
    score_candidate,
    write_selftest_jsonl,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _persona_anchor_path(slug: str) -> Path:
    return _REPO_ROOT / "personas" / slug / "avatar" / "anchor.png"


def _output_dir(slug: str, batch_id: str) -> Path:
    return _REPO_ROOT / "personas" / slug / "_pipeline" / "step1_references" / batch_id


def evaluate_batch(
    persona_slug: str,
    batch_id: str,
    *,
    vlm_backend: str | None = None,
) -> list[SelfTestRow]:
    """Score every candidate in a batch and write selftest.jsonl. Returns
    the rows emitted so callers can summarise inline."""
    out_dir = _output_dir(persona_slug, batch_id)
    manifest_path = out_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"no manifest at {manifest_path}")

    manifest = read_manifest(manifest_path)
    anchor_path = _persona_anchor_path(persona_slug)
    if not anchor_path.exists():
        raise FileNotFoundError(
            f"anchor not found at {anchor_path}; selftest needs an "
            "identity reference for the identity_match axis."
        )

    prompts_by_id = {p.prompt_id: p for p in manifest.prompts}
    rows: list[SelfTestRow] = []
    for candidate in manifest.candidates:
        spec = prompts_by_id[candidate.prompt_id]
        cand_path = out_dir / candidate.image_path
        row = score_candidate(
            cand_path,
            anchor_path,
            prompt_id=candidate.prompt_id,
            candidate_index=candidate.candidate_index,
            prompt_text=spec.prompt_text,
            persona_slug=persona_slug,
            vlm_backend=vlm_backend,
        )
        rows.append(row)

    write_selftest_jsonl(rows, out_dir)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="phase0-evaluate",
        description=(
            "Run the Doctrine §8 multimodal-vision self-test pass on a "
            "completed Phase 0 batch. Defaults to Qwen2-VL (local), can "
            "be overridden via --backend or PERSONA_REFGEN_SELFTEST_BACKEND."
        ),
    )
    parser.add_argument("--persona", default="aurora")
    parser.add_argument("--batch", required=True)
    parser.add_argument(
        "--backend",
        choices=["openai", "qwen2vl"],
        default="qwen2vl",
        help="VLM backend (default qwen2vl — bare-metal sanctioned path)",
    )
    args = parser.parse_args(argv)

    rows = evaluate_batch(args.persona, args.batch, vlm_backend=args.backend)
    mode = "LIVE" if is_live_mode() else "STUB"
    print(
        f"[phase0-evaluate] persona={args.persona} batch={args.batch} "
        f"mode={mode} backend={args.backend} candidates={len(rows)}"
    )
    flagged = sum(1 for r in rows if r.verdict == "flag")
    print(f"  pass: {len(rows) - flagged}   flag: {flagged}")
    for row in rows:
        print(
            f"  - {row.prompt_id} c{row.candidate_index}: "
            f"verdict={row.verdict} photoreal={row.photoreal_score} "
            f"framing={row.framing_match} identity={row.identity_match}"
        )
        if row.notes:
            print(f"      notes: {row.notes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
