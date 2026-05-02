"""Cross-persona pipeline status reporter.

Walks `personas/<slug>/_pipeline/step1_references/` for every persona,
summarises batches + curation state + selftest verdicts. Read-only.
GPU-free. Useful for "where's everyone in the pipeline" at session
start.

Output is markdown so it pastes cleanly into HANDOFFs.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
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


def _summarise_batch(batch_dir: Path) -> dict[str, object]:
    """Return a one-batch summary dict. Catches missing-manifest cleanly."""
    summary: dict[str, object] = {
        "batch_id": batch_dir.name,
        "manifest_present": False,
        "candidates": 0,
        "verdict_counts": {},
        "selftest_counts": {},
        "backend": None,
        "model": None,
    }
    manifest_path = batch_dir / "manifest.json"
    if not manifest_path.exists():
        return summary

    summary["manifest_present"] = True
    try:
        manifest = read_manifest(manifest_path)
    except (ValueError, KeyError, TypeError) as exc:
        summary["error"] = f"manifest unreadable: {exc}"
        return summary

    summary["backend"] = manifest.backend
    summary["model"] = manifest.backend_model_id
    summary["candidates"] = len(manifest.candidates)

    curation = _load_curation(batch_dir / "curation.jsonl")
    selftest = _load_selftest(batch_dir / "selftest.jsonl")

    verdict_counts: dict[str, int] = defaultdict(int)
    for c in manifest.candidates:
        e = curation.get((c.prompt_id, c.candidate_index))
        verdict = e.verdict if e else "pending"
        verdict_counts[verdict] += 1
    summary["verdict_counts"] = dict(verdict_counts)

    selftest_counts: dict[str, int] = defaultdict(int)
    for c in manifest.candidates:
        row = selftest.get((c.prompt_id, c.candidate_index))
        if row is None:
            selftest_counts["unscored"] += 1
        else:
            selftest_counts[row.verdict] += 1
    summary["selftest_counts"] = dict(selftest_counts)
    return summary


def _persona_lora_present(persona_slug: str, repo_root: Path) -> bool:
    """Best-effort: is there a trained LoRA on disk for this persona?

    Looks in `personas/<slug>/loras/` for any `.safetensors` file.
    """
    lora_dir = repo_root / "personas" / persona_slug / "loras"
    if not lora_dir.exists():
        return False
    return any(lora_dir.glob("*.safetensors"))


def collect(repo_root: Path | None = None) -> list[dict[str, object]]:
    """Walk every persona's pipeline dir and return per-persona reports."""
    repo_root = repo_root or _REPO_ROOT
    personas_root = repo_root / "personas"
    if not personas_root.exists():
        return []

    reports: list[dict[str, object]] = []
    for persona_dir in sorted(personas_root.iterdir()):
        if not persona_dir.is_dir():
            continue
        if persona_dir.name.startswith("_"):
            continue
        persona_report: dict[str, object] = {
            "persona_slug": persona_dir.name,
            "anchor_present": (persona_dir / "avatar" / "anchor.png").exists(),
            "lora_present": _persona_lora_present(persona_dir.name, repo_root),
            "batches": [],
        }
        step1_root = persona_dir / "_pipeline" / "step1_references"
        if step1_root.exists():
            for batch_dir in sorted(p for p in step1_root.iterdir() if p.is_dir()):
                persona_report["batches"].append(_summarise_batch(batch_dir))
        reports.append(persona_report)
    return reports


def render_markdown(reports: list[dict[str, object]]) -> str:
    """Markdown summary suitable for pasting into a HANDOFF."""
    lines: list[str] = []
    lines.append("# Persona Pipeline Status")
    lines.append("")
    lines.append(f"**Personas tracked:** {len(reports)}")
    lines.append("")

    for r in reports:
        slug = r["persona_slug"]
        anchor = "yes" if r["anchor_present"] else "**no**"
        lora = "yes" if r["lora_present"] else "no"
        batches = r["batches"]
        lines.append(f"## {slug}")
        lines.append("")
        lines.append(f"- anchor.png present: {anchor}")
        lines.append(f"- LoRA on disk: {lora}")
        lines.append(f"- Step 1 batches: {len(batches)}")
        if batches:
            lines.append("")
            lines.append(
                "| batch | backend | candidates | verdicts | selftest |"
            )
            lines.append("|---|---|---|---|---|")
            for b in batches:
                if not b.get("manifest_present"):
                    lines.append(
                        f"| {b['batch_id']} | (no manifest) | — | — | — |"
                    )
                    continue
                vc = b.get("verdict_counts") or {}
                sc = b.get("selftest_counts") or {}
                vc_str = ", ".join(f"{k}:{v}" for k, v in sorted(vc.items())) or "—"
                sc_str = ", ".join(f"{k}:{v}" for k, v in sorted(sc.items())) or "—"
                lines.append(
                    f"| {b['batch_id']} | {b.get('backend') or '?'} | "
                    f"{b.get('candidates', 0)} | {vc_str} | {sc_str} |"
                )
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pipeline-status",
        description=(
            "Cross-persona pipeline status. Walks every persona's "
            "_pipeline/step1_references/ + summarises curation + selftest "
            "state. Read-only."
        ),
    )
    parser.add_argument(
        "--persona",
        default=None,
        help="restrict report to a single persona slug",
    )
    args = parser.parse_args(argv)

    reports = collect()
    if args.persona is not None:
        reports = [r for r in reports if r["persona_slug"] == args.persona]
    print(render_markdown(reports))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
