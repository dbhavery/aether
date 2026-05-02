"""Don-in-loop curation CLI for a reference-image batch.

Reads a batch manifest and walks Don through each candidate, capturing a
`keep | reject | reprompt` verdict + optional note. Output is appended to
`curation.jsonl` (latest-wins per `prompt_id`).

Per ADR-0015 §"Architecture": "the module produces a candidate batch; Don
approves/rejects/re-prompts." This is the minimum viable curation surface;
a GUI is a follow-up.

Doctrine §8 integration: when a `selftest.jsonl` sibling file is present,
candidates flagged by the multimodal-vision pass are hidden from the
default curation walk — Don's time isn't spent on candidates the agent
already identified as defective. Override with `--include-flagged`.
Self-test scores + notes are surfaced inline so Don sees the agent's
verdict before being asked for his own.

Usage:
    python tools/persona-reference-gen/curate.py --persona aurora --batch 2026-05-18a
    # Optional: --auto-keep to mark every candidate keep (smoke / non-interactive).
    # Optional: --report-only to print the current curation state without prompting.
    # Optional: --include-flagged to surface Doctrine §8-flagged candidates.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from output_schema import (  # noqa: E402
    BatchManifest,
    CurationEntry,
    CurationVerdict,
    SelfTestRow,
    read_manifest,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]


def _utc_now() -> str:
    return _dt.datetime.now(tz=_dt.UTC).isoformat(timespec="seconds")


def _batch_dir(persona_slug: str, batch_id: str) -> Path:
    return _REPO_ROOT / "personas" / persona_slug / "_pipeline" / "step1_references" / batch_id


def _load_existing_curation(path: Path) -> dict[tuple[str, int], CurationEntry]:
    """Load latest-wins per (prompt_id, candidate_index) from curation.jsonl."""
    if not path.exists():
        return {}
    out: dict[tuple[str, int], CurationEntry] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        e = CurationEntry.from_jsonl(line)
        out[(e.prompt_id, e.candidate_index)] = e
    return out


def _append_verdict(path: Path, entry: CurationEntry) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(entry.to_jsonl() + "\n")


def _load_selftest(path: Path) -> dict[tuple[str, int], SelfTestRow]:
    """Latest-wins per (prompt_id, candidate_index). Empty dict if absent."""
    if not path.exists():
        return {}
    out: dict[tuple[str, int], SelfTestRow] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = SelfTestRow.from_jsonl(line)
        out[(row.prompt_id, row.candidate_index)] = row
    return out


def _prompt_user(
    candidate_index: int,
    prompt_id: str,
    image_rel_path: str,
    selftest_row: SelfTestRow | None = None,
) -> tuple[CurationVerdict, str]:
    """Interactive prompt. Returns (verdict, note).

    When `selftest_row` is provided, surface the agent's Doctrine §8
    verdict + notes inline so Don sees the agent's read before judging.
    """
    print()
    print(f"  candidate: prompt_id={prompt_id} idx={candidate_index}")
    print(f"  image:     {image_rel_path}")
    if selftest_row is not None:
        print(
            f"  selftest:  verdict={selftest_row.verdict} "
            f"photoreal={selftest_row.photoreal_score} "
            f"framing={selftest_row.framing_match} "
            f"identity={selftest_row.identity_match}"
        )
        if selftest_row.notes:
            print(f"  notes:     {selftest_row.notes}")
    while True:
        raw = input("  verdict [k=keep / r=reject / p=reprompt / s=skip] > ").strip().lower()
        if raw in {"k", "keep"}:
            verdict: CurationVerdict = "keep"
            break
        if raw in {"r", "reject"}:
            verdict = "reject"
            break
        if raw in {"p", "reprompt"}:
            verdict = "reprompt"
            break
        if raw in {"s", "skip", ""}:
            verdict = "pending"
            break
        print("  unrecognized — try k / r / p / s")
    note = input("  note (optional, enter to skip) > ").strip()
    return verdict, note


def _summarize(manifest: BatchManifest, curation: dict[tuple[str, int], CurationEntry]) -> None:
    counts: dict[str, int] = {"keep": 0, "reject": 0, "reprompt": 0, "pending": 0}
    for c in manifest.candidates:
        e = curation.get((c.prompt_id, c.candidate_index))
        v = e.verdict if e else "pending"
        counts[v] = counts.get(v, 0) + 1
    print()
    print("  curation summary:")
    for k in ("keep", "reject", "reprompt", "pending"):
        print(f"    {k:>9}: {counts[k]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="persona-reference-gen-curate",
        description="Walk Don through a batch's candidates and record verdicts.",
    )
    parser.add_argument("--persona", required=True)
    parser.add_argument("--batch", required=True)
    parser.add_argument(
        "--auto-keep",
        action="store_true",
        help="non-interactive: mark every candidate keep (smoke / scripted use)",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="print curation summary; do not prompt",
    )
    parser.add_argument(
        "--include-flagged",
        action="store_true",
        help=(
            "surface candidates flagged by the Doctrine §8 self-test "
            "(default: skip them)"
        ),
    )
    args = parser.parse_args(argv)

    out_dir = _batch_dir(args.persona, args.batch)
    manifest_path = out_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"ERROR: manifest not found at {manifest_path}", file=sys.stderr)
        return 2
    manifest = read_manifest(manifest_path)
    curation_path = out_dir / "curation.jsonl"
    curation = _load_existing_curation(curation_path)
    selftest_path = out_dir / "selftest.jsonl"
    selftest = _load_selftest(selftest_path)

    print(
        f"[{manifest.persona_slug}] batch {manifest.batch_id}: "
        f"{len(manifest.candidates)} candidates"
    )
    if selftest:
        flagged = sum(1 for r in selftest.values() if r.verdict == "flag")
        if flagged:
            visibility = "surfaced" if args.include_flagged else "hidden"
            print(f"  selftest: {flagged} flagged ({visibility})")

    if args.report_only:
        _summarize(manifest, curation)
        return 0

    for c in manifest.candidates:
        existing = curation.get((c.prompt_id, c.candidate_index))
        if existing and existing.verdict != "pending":
            continue
        st_row = selftest.get((c.prompt_id, c.candidate_index))
        if (
            st_row is not None
            and st_row.verdict == "flag"
            and not args.include_flagged
        ):
            continue
        if args.auto_keep:
            verdict: CurationVerdict = "keep"
            note = "auto-keep"
        else:
            verdict, note = _prompt_user(
                c.candidate_index, c.prompt_id, c.image_path, selftest_row=st_row
            )
        if verdict == "pending":
            continue  # treat skip as no verdict written
        entry = CurationEntry(
            prompt_id=c.prompt_id,
            candidate_index=c.candidate_index,
            verdict=verdict,
            timestamp=_utc_now(),
            note=note,
        )
        _append_verdict(curation_path, entry)
        curation[(c.prompt_id, c.candidate_index)] = entry

    _summarize(manifest, curation)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
