#!/usr/bin/env python3
"""Aether Quality-Eval V1 architecture-doc rot guard.

Mirror of `tools/lint-presence-doc/check.py`. Keeps
`docs/QUALITY-EVAL-V1-ARCHITECTURE.md` honest: the doc claims
specific files, symbols, and string constants (env var names,
expectation kinds, backend tokens, scenario JSONL field names)
exist in code. When any disappears (rename, delete, typo), this
linter fails.

Not a prose parser. The manifest below is the contract between the
doc and the code; a Quality-Eval PR that adds / removes / renames
an anchor MUST update this manifest in the same PR.

Run:

  python tools/lint-quality-doc/check.py          # validate
  python tools/lint-quality-doc/check.py --json   # machine-readable

Run from the repo root, or set `AETHER_REPO_ROOT` to point at the
repo.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Iterable


# ---------------------------------------------------------------------------
# Anchor manifest
# ---------------------------------------------------------------------------

ANCHORS: list[tuple[str, str, str | None, str]] = [
    # ---- §3 minimum viable harness — entry point + components ----
    ("file",   "tools/evals/__main__.py", None, "§3 CLI entry point"),
    ("symbol", "tools/evals/__main__.py", "class Scenario", "§3 scenario dataclass"),
    ("symbol", "tools/evals/__main__.py", "class ScenarioResult", "§3 scenario result dataclass"),
    ("symbol", "tools/evals/__main__.py", "def _iter_scenarios", "§3 JSONL loader"),
    ("symbol", "tools/evals/__main__.py", "def _last_user_prompt", "§3 prompt extractor"),
    ("symbol", "tools/evals/__main__.py", "def _ollama_env", "§3.1 Ollama env snapshot"),
    ("symbol", "tools/evals/__main__.py", "def _ollama_generate", "§3.1 live backend call"),
    ("symbol", "tools/evals/__main__.py", "def _capture_filename", "§3.2 capture filename"),
    ("symbol", "tools/evals/__main__.py", "def _write_capture_json", "§3.2 capture JSON writer"),
    ("symbol", "tools/evals/__main__.py", "def _load_replay_capture", "§3.2 replay loader"),
    ("symbol", "tools/evals/__main__.py", "def _resolve_actual", "§3 actual resolver"),
    ("symbol", "tools/evals/__main__.py", "def _run_scenario", "§3 scenario runner"),
    ("symbol", "tools/evals/__main__.py", "def main", "§3 CLI main"),

    # ---- §2.1 expectation DSL ----
    ("file",   "tools/evals/expectations.py", None, "§2.1 expectation DSL"),
    ("symbol", "tools/evals/expectations.py", "EVALUATED_KINDS", "§2.1 kinds registry"),
    ("symbol", "tools/evals/expectations.py", "class ExpectationResult", "§2.1 result dataclass"),
    ("symbol", "tools/evals/expectations.py", "def evaluate_expectation", "§2.1 DSL dispatcher"),

    # ---- §3 report rendering ----
    ("file",   "tools/evals/report.py", None, "§3 markdown report"),
    ("symbol", "tools/evals/report.py", "def build_markdown_report", "§3 report renderer"),

    # ---- §3.2 capture + replay unit tests ----
    ("file",   "tools/evals/test_capture_replay.py", None, "§3.2 capture/replay tests"),

    # ---- §6 step 5 — session-log replay importer ----
    ("file",   "tools/evals/session_log_import.py", None, "§6 (5) session-log importer"),
    ("symbol", "tools/evals/session_log_import.py", "class SessionTurn", "§6 (5) session turn row"),
    ("symbol", "tools/evals/session_log_import.py", "class ImportReport", "§6 (5) import report"),
    ("symbol", "tools/evals/session_log_import.py", "def _parse_session_log", "§6 (5) JSONL parser"),
    ("symbol", "tools/evals/session_log_import.py", "def _pair_user_assistant", "§6 (5) pair walker"),
    ("symbol", "tools/evals/session_log_import.py", "def _extract_scenarios", "§6 (5) scenario extractor"),
    ("symbol", "tools/evals/session_log_import.py", "def match_scenario", "§6 (5) match classifier"),
    ("symbol", "tools/evals/session_log_import.py", "def import_session_log", "§6 (5) programmatic entry"),
    ("symbol", "tools/evals/session_log_import.py", "def main", "§6 (5) CLI entry"),
    ("file",   "tools/evals/test_session_log_import.py", None, "§6 (5) importer tests"),

    # ---- §2.1 scenario JSONL fields (as emitted by the schema) ----
    ("string", "tools/evals/__main__.py", '"id"', "§2.1 scenario id field"),
    ("string", "tools/evals/__main__.py", '"domain"', "§2.1 scenario domain field"),
    ("string", "tools/evals/__main__.py", '"turns"', "§2.1 scenario turns field"),
    ("string", "tools/evals/__main__.py", '"actual"', "§2.1 scenario actual field"),
    ("string", "tools/evals/__main__.py", '"expectations"', "§2.1 scenario expectations field"),

    # ---- §2.1 expectation kinds (each implemented kind string) ----
    ("string", "tools/evals/expectations.py", '"forbids"', "§2.1 expectation kind: forbids"),
    ("string", "tools/evals/expectations.py", '"requires"', "§2.1 expectation kind: requires"),
    ("string", "tools/evals/expectations.py", '"length"', "§2.1 expectation kind: length"),
    ("string", "tools/evals/expectations.py", '"tone"', "§2.1 expectation kind: tone"),
    ("string", "tools/evals/expectations.py", "patterns", "§2.1 expectation patterns key"),

    # ---- §3.1 live backend env var names ----
    ("string", "tools/evals/__main__.py", "AETHER_EVAL_OLLAMA_BASE_URL", "§3.1 Ollama base URL env"),
    ("string", "tools/evals/__main__.py", "AETHER_EVAL_OLLAMA_MODEL", "§3.1 Ollama model env"),
    ("string", "tools/evals/__main__.py", "AETHER_EVAL_OLLAMA_TIMEOUT_S", "§3.1 Ollama timeout env"),

    # ---- §3 backend mode tokens ----
    ("string", "tools/evals/__main__.py", '"dry-run"', "§3 backend: dry-run"),
    ("string", "tools/evals/__main__.py", '"ollama"', "§3.1 backend: ollama"),
    ("string", "tools/evals/__main__.py", '"replay"', "§3.2 backend: replay"),
    ("string", "tools/evals/session_log_import.py", '"session-log"', "§6 (5) backend: session-log"),

    # ---- §2.1 scenario directories (one scenario per domain) ----
    ("file",   "tools/evals/scenarios/chat_realism/first_turn.jsonl", None, "§2.1 chat_realism scenario"),
    ("file",   "tools/evals/scenarios/memory_appropriateness/honors_forget.jsonl", None, "§2.1 memory_appropriateness scenario"),
    ("file",   "tools/evals/scenarios/presence_aware_behavior/respects_away_state.jsonl", None, "§2.1 presence_aware_behavior scenario"),
    ("file",   "tools/evals/scenarios/tool_use_judgment/prefers_text_answer.jsonl", None, "§2.1 tool_use_judgment scenario"),
    ("file",   "tools/evals/scenarios/vision_response_quality/describes_actual_scene.jsonl", None, "§2.1 vision_response_quality scenario"),
    ("file",   "tools/evals/scenarios/voice_transcription/domain_vocab.jsonl", None, "§2.1 voice_transcription scenario"),

    # ---- §2.3 adversarial probes (one per domain) ----
    ("file",   "tools/evals/adversarial/chat_realism/robot_tells.jsonl", None, "§2.3 chat_realism adversarial"),
    ("file",   "tools/evals/adversarial/memory_appropriateness/refuses_forget_regression.jsonl", None, "§2.3 memory_appropriateness adversarial"),
    ("file",   "tools/evals/adversarial/presence_aware_behavior/interrupts_away_regression.jsonl", None, "§2.3 presence_aware_behavior adversarial"),
    ("file",   "tools/evals/adversarial/tool_use_judgment/tool_happy_regression.jsonl", None, "§2.3 tool_use_judgment adversarial"),
    ("file",   "tools/evals/adversarial/vision_response_quality/hallucinated_scene_regression.jsonl", None, "§2.3 vision_response_quality adversarial"),
    ("file",   "tools/evals/adversarial/voice_transcription/dropped_proper_noun_regression.jsonl", None, "§2.3 voice_transcription adversarial"),

    # ---- §3 README (how to add a scenario / run the suite) ----
    ("file",   "tools/evals/README.md", None, "§3 user-facing README"),
]


DOC_PATH = Path("docs/QUALITY-EVAL-V1-ARCHITECTURE.md")
STATUS_RE = re.compile(r"\*\*Status:\*\*\s+Current as of\s+(\d{4}-\d{2}-\d{2})")


class Failure:
    __slots__ = ("kind", "path", "needle", "section", "reason")

    def __init__(self, kind: str, path: str, needle: str | None, section: str, reason: str) -> None:
        self.kind = kind
        self.path = path
        self.needle = needle
        self.section = section
        self.reason = reason

    def to_dict(self) -> dict[str, str | None]:
        return {
            "kind":    self.kind,
            "path":    self.path,
            "needle":  self.needle,
            "section": self.section,
            "reason":  self.reason,
        }

    def __str__(self) -> str:
        head = f"  [{self.kind}] {self.path}"
        if self.needle is not None:
            head += f"  needle={self.needle!r}"
        return f"{head}\n      ({self.section}) {self.reason}"


def _repo_root() -> Path:
    env = os.environ.get("AETHER_REPO_ROOT")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for parent in (here, *here.parents):
        cargo = parent / "Cargo.toml"
        if cargo.is_file() and "[workspace]" in cargo.read_text(encoding="utf-8"):
            return parent
    raise RuntimeError(
        "Could not locate workspace root. Run this script from the Aether repo "
        "or set AETHER_REPO_ROOT."
    )


def _check_status_line(doc_path: Path) -> tuple[str | None, Failure | None]:
    if not doc_path.is_file():
        return None, Failure(
            "doc", str(doc_path), None, "header",
            "architecture doc is missing — this linter is useless without it.",
        )
    text = doc_path.read_text(encoding="utf-8")
    m = STATUS_RE.search(text)
    if not m:
        return None, Failure(
            "doc", str(doc_path), None, "header",
            "could not find `**Status:** Current as of YYYY-MM-DD.` line near the top.",
        )
    return m.group(1), None


def _check_anchor(repo_root: Path, kind: str, rel: str, needle: str | None, section: str) -> Failure | None:
    path = repo_root / rel
    if kind == "file":
        if not path.is_file():
            return Failure(kind, rel, None, section, "file does not exist.")
        return None
    if not path.is_file():
        return Failure(
            kind, rel, needle, section,
            "host file for this anchor does not exist.",
        )
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return Failure(
            kind, rel, needle, section,
            "host file is not UTF-8; cannot check anchor.",
        )
    if needle is None:
        return Failure(
            kind, rel, needle, section,
            f"anchor kind {kind!r} requires a needle.",
        )
    if needle not in content:
        return Failure(
            kind, rel, needle, section,
            "expected substring not found in file — the doc claims it exists. "
            "Either restore the symbol/string in code, or update the doc AND "
            "the ANCHORS manifest in tools/lint-quality-doc/check.py.",
        )
    return None


def _collect(repo_root: Path) -> tuple[str | None, list[Failure]]:
    failures: list[Failure] = []
    doc_date, doc_fail = _check_status_line(repo_root / DOC_PATH)
    if doc_fail is not None:
        failures.append(doc_fail)

    for kind, rel, needle, section in ANCHORS:
        f = _check_anchor(repo_root, kind, rel, needle, section)
        if f is not None:
            failures.append(f)

    return doc_date, failures


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check Quality-Eval V1 architecture doc anchors against code.",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="emit machine-readable JSON report on stdout",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    doc_date, failures = _collect(repo_root)

    if args.json:
        print(json.dumps(
            {
                "ok":               not failures,
                "doc":              str(DOC_PATH),
                "doc_status_date":  doc_date,
                "anchor_count":     len(ANCHORS),
                "failures":         [f.to_dict() for f in failures],
            },
            indent=2,
        ))
    else:
        if failures:
            print("quality-doc rot-guard: FAIL")
            for f in failures:
                print(f)
            print(
                f"\n{len(failures)} failure(s). "
                "See tools/lint-quality-doc/README.md for how to resolve."
            )
        else:
            print("quality-doc rot-guard: OK")
            print(
                f"  doc: {DOC_PATH} (Status: Current as of {doc_date})"
                f"  checked {len(ANCHORS)} anchors across "
                f"{len({a[1] for a in ANCHORS})} files."
            )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
