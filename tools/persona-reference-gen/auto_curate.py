"""Auto-curation helper — translate selftest verdicts into curation rows.

When the Doctrine §8 self-test pass has run and Don hasn't manually
curated yet, this writes a `curation.jsonl` with sensible defaults
derived from the selftest verdict:

  selftest verdict "pass"  → curation verdict "keep"
  selftest verdict "flag"  → curation verdict "reject"
  no selftest row          → curation "pending" (skipped)

Lets `dataset_builder.build_dataset` produce a useful training set
without waiting for a human curator. Don's manual curation, when it
happens, overwrites the auto rows because `curation.jsonl` is
latest-wins per (prompt_id, candidate_index).

Notes are tagged with `auto-curate:` prefix so a later review can
distinguish auto rows from Don's manual rows by note content alone.

Usage:

    python tools/persona-reference-gen/auto_curate.py \\
        --persona aurora \\
        --batch 2026-05-02-framing-probe

Idempotent: re-running on a batch with existing curation rows
preserves them — the auto rows only fill gaps.
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
    CurationEntry,
    SelfTestRow,
    read_manifest,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]


def _utc_now() -> str:
    return _dt.datetime.now(tz=_dt.UTC).isoformat(timespec="seconds")


def _batch_dir(persona_slug: str, batch_id: str) -> Path:
    return _REPO_ROOT / "personas" / persona_slug / "_pipeline" / "step1_references" / batch_id


def _load_curation(path: Path) -> dict[tuple[str, int], CurationEntry]:
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


def _load_selftest(path: Path) -> dict[tuple[str, int], SelfTestRow]:
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


def auto_curate_batch(
    persona_slug: str,
    batch_id: str,
    *,
    repo_root: Path | None = None,
    overwrite_existing: bool = False,
) -> dict[str, int]:
    """Write auto-curation rows to curation.jsonl based on selftest verdicts.

    Returns a counts dict with keys `kept`, `rejected`, `skipped_existing`,
    `skipped_no_selftest`.
    """
    repo_root = repo_root or _REPO_ROOT
    out_dir = (
        repo_root / "personas" / persona_slug / "_pipeline" / "step1_references" / batch_id
    )
    manifest_path = out_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"no manifest at {manifest_path}")

    manifest = read_manifest(manifest_path)
    curation_path = out_dir / "curation.jsonl"
    selftest_path = out_dir / "selftest.jsonl"

    existing = _load_curation(curation_path)
    selftest = _load_selftest(selftest_path)

    counts = {
        "kept": 0,
        "rejected": 0,
        "skipped_existing": 0,
        "skipped_no_selftest": 0,
    }

    new_lines: list[str] = []
    for c in manifest.candidates:
        key = (c.prompt_id, c.candidate_index)
        if key in existing and not overwrite_existing:
            counts["skipped_existing"] += 1
            continue
        st = selftest.get(key)
        if st is None:
            counts["skipped_no_selftest"] += 1
            continue
        if st.verdict == "pass":
            verdict = "keep"
            counts["kept"] += 1
        else:
            verdict = "reject"
            counts["rejected"] += 1
        entry = CurationEntry(
            prompt_id=c.prompt_id,
            candidate_index=c.candidate_index,
            verdict=verdict,  # type: ignore[arg-type]
            timestamp=_utc_now(),
            note=(
                f"auto-curate: derived from selftest verdict={st.verdict} "
                f"photoreal={st.photoreal_score} framing={st.framing_match} "
                f"identity={st.identity_match}"
            ),
        )
        new_lines.append(entry.to_jsonl())

    if new_lines:
        with curation_path.open("a", encoding="utf-8") as f:
            for line in new_lines:
                f.write(line + "\n")
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="auto-curate",
        description=(
            "Translate selftest.jsonl verdicts into curation.jsonl rows. "
            "Lets dataset_builder consume a batch even before Don manually "
            "curates. Don's later manual rows take precedence (latest-wins)."
        ),
    )
    parser.add_argument("--persona", required=True)
    parser.add_argument("--batch", required=True)
    parser.add_argument(
        "--overwrite-existing",
        action="store_true",
        help="rewrite even if curation.jsonl already has rows for a candidate",
    )
    args = parser.parse_args(argv)

    counts = auto_curate_batch(
        args.persona,
        args.batch,
        overwrite_existing=args.overwrite_existing,
    )
    print(
        f"[auto-curate] persona={args.persona} batch={args.batch} "
        f"kept={counts['kept']} rejected={counts['rejected']} "
        f"skipped_existing={counts['skipped_existing']} "
        f"skipped_no_selftest={counts['skipped_no_selftest']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
