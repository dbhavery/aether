"""Don-in-loop curation CLI for a reference-image batch.

Reads a batch manifest and walks Don through each candidate, capturing a
`keep | reject | reprompt` verdict + optional note. Output is appended to
`curation.jsonl` (latest-wins per `prompt_id`).

Per ADR-0015 §"Architecture": "the module produces a candidate batch; Don
approves/rejects/re-prompts." This is the minimum viable curation surface;
a GUI is a follow-up.

Doctrine §8 (visual self-test) is **not yet wired** — when implemented, the
curator should pre-attach a multimodal-vision verdict alongside each
candidate so Don sees the agent's self-test before being asked. Tracked in
README §"What's stubbed".

Usage:
    python tools/persona-reference-gen/curate.py --persona aurora --batch 2026-05-18a
    # Optional: --auto-keep to mark every candidate keep (smoke / non-interactive).
    # Optional: --report-only to print the current curation state without prompting.
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


def _prompt_user(
    candidate_index: int,
    prompt_id: str,
    image_rel_path: str,
) -> tuple[CurationVerdict, str]:
    """Interactive prompt. Returns (verdict, note)."""
    print()
    print(f"  candidate: prompt_id={prompt_id} idx={candidate_index}")
    print(f"  image:     {image_rel_path}")
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
    args = parser.parse_args(argv)

    out_dir = _batch_dir(args.persona, args.batch)
    manifest_path = out_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"ERROR: manifest not found at {manifest_path}", file=sys.stderr)
        return 2
    manifest = read_manifest(manifest_path)
    curation_path = out_dir / "curation.jsonl"
    curation = _load_existing_curation(curation_path)

    print(
        f"[{manifest.persona_slug}] batch {manifest.batch_id}: "
        f"{len(manifest.candidates)} candidates"
    )

    if args.report_only:
        _summarize(manifest, curation)
        return 0

    for c in manifest.candidates:
        existing = curation.get((c.prompt_id, c.candidate_index))
        if existing and existing.verdict != "pending":
            continue
        if args.auto_keep:
            verdict: CurationVerdict = "keep"
            note = "auto-keep"
        else:
            verdict, note = _prompt_user(c.candidate_index, c.prompt_id, c.image_path)
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
