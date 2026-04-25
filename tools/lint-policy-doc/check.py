#!/usr/bin/env python3
"""Aether ADR-0009 (retrieval-augmented utterance audit reach) rot guard.

Mirror of `tools/lint-memory-doc/check.py`,
`tools/lint-presence-doc/check.py`, etc. Keeps
`docs/adr/ADR-0009-retrieval-augmented-utterance-audit-reach.md`
honest: the ADR claims specific symbols, fields, and constants exist
in code. When any disappears (rename, delete, typo), this linter
fails.

Not a prose parser. The `ANCHORS` manifest below is the contract
between the ADR and the code; an ADR-0009 follow-up that adds /
removes / renames an anchor MUST update this manifest in the same PR.

Run:

  python tools/lint-policy-doc/check.py          # validate
  python tools/lint-policy-doc/check.py --json   # machine-readable

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
    # ---- L1 TurnRequest split (ADR-0009 §Decision 5, Path A) ----
    ("file",   "packages/l1-interaction/src/turn.rs", None, "L1: turn module"),
    ("symbol", "packages/l1-interaction/src/turn.rs", "pub struct TurnRequest", "L1: TurnRequest"),
    ("symbol", "packages/l1-interaction/src/turn.rs", "pub original_utterance: String", "L1: original_utterance field"),
    ("symbol", "packages/l1-interaction/src/turn.rs", "pub model_input_utterance: String", "L1: model_input_utterance field"),
    ("symbol", "packages/l1-interaction/src/turn.rs", "pub retrieval_provenance:", "L1: retrieval_provenance field on TurnRequest"),

    # ---- L5 audit row schema bump v1 → v2 (ADR-0009 §Decision 6) ----
    ("file",   "packages/l5-policy/src/audit.rs", None, "L5: audit module"),
    ("symbol", "packages/l5-policy/src/audit.rs", "pub struct AuditRecordEvent", "L5: AuditRecordEvent"),
    ("symbol", "packages/l5-policy/src/audit.rs", "pub schema_version: u32", "L5: schema_version field"),
    ("symbol", "packages/l5-policy/src/audit.rs", "pub original_utterance: Option<String>", "L5: original_utterance v2 field"),
    ("symbol", "packages/l5-policy/src/audit.rs", "pub retrieval_provenance: Option<RetrievalProvenance>", "L5: retrieval_provenance v2 field"),
    ("symbol", "packages/l5-policy/src/audit.rs", "pub struct RetrievalProvenance", "L5: RetrievalProvenance struct"),
    ("symbol", "packages/l5-policy/src/audit.rs", "pub struct RetrievedMemoryRef", "L5: RetrievedMemoryRef struct"),
    ("symbol", "packages/l5-policy/src/audit.rs", "pub struct AuditExtras", "L5: AuditExtras struct"),
    ("symbol", "packages/l5-policy/src/audit.rs", "pub const AUDIT_SCHEMA_VERSION_V1", "L5: v1 constant"),
    ("symbol", "packages/l5-policy/src/audit.rs", "pub const AUDIT_SCHEMA_VERSION_V2", "L5: v2 constant"),
    ("symbol", "packages/l5-policy/src/audit.rs", "fn default_schema_version_v1", "L5: serde-default resolver"),

    # ---- L5 ActionRequest plumbing for audit_extras (ADR-0009 §Decision 2) ----
    ("symbol", "packages/l5-policy/src/policy_engine.rs", "pub audit_extras: Option<crate::audit::AuditExtras>", "L5: ActionRequest.audit_extras"),

    # ---- L5 engine writer stamps v2 fields (ADR-0009 §Decision 6) ----
    ("string", "packages/l5-policy/src/engine.rs", "AUDIT_SCHEMA_VERSION_V2", "L5: writer stamps v2"),

    # ---- L5 audit_seal canonical payload covers v2 fields ----
    ("string", "packages/l5-policy/src/audit_seal.rs", "schema_version", "L5: HMAC covers schema_version"),
    ("string", "packages/l5-policy/src/audit_seal.rs", "original_utterance", "L5: HMAC covers original_utterance"),
    ("string", "packages/l5-policy/src/audit_seal.rs", "retrieval_provenance", "L5: HMAC covers retrieval_provenance"),

    # ---- Shell wires ADR-0009 fields through submit_turn (ADR-0009 §Decision 4) ----
    ("symbol", "apps/desktop/src-tauri/src/commands.rs", "fn retrieval_provenance_for", "Shell: provenance projector helper"),
    ("string", "apps/desktop/src-tauri/src/commands.rs", "retrieval_provenance: Some(retrieval_provenance_for", "Shell: stamps provenance on conversation TurnRequest"),

    # ---- Frontend: version-aware AuditList rendering ----
    ("file",   "apps/desktop/src/components/TrustDrawer.tsx", None, "Frontend: TrustDrawer"),
    ("symbol", "apps/desktop/src/components/TrustDrawer.tsx", "AUDIT_SCHEMA_VERSION_V1", "Frontend: v1 constant"),
    ("symbol", "apps/desktop/src/components/TrustDrawer.tsx", "AUDIT_SCHEMA_VERSION_V2", "Frontend: v2 constant"),
    ("symbol", "apps/desktop/src/components/TrustDrawer.tsx", "function AuditRow", "Frontend: AuditRow renderer"),
    ("string", "apps/desktop/src/components/TrustDrawer.tsx", "schema_version", "Frontend: AuditList consumes schema_version"),
    ("string", "apps/desktop/src/components/TrustDrawer.tsx", "original_utterance", "Frontend: AuditList renders original_utterance"),
    ("string", "apps/desktop/src/components/TrustDrawer.tsx", "retrieval_provenance", "Frontend: AuditList renders provenance summary"),
    ("string", "apps/desktop/src/components/TrustDrawer.tsx", "pre-ADR-0009", "Frontend: v1 schema badge copy"),

    # ---- Frontend: TS types for the projected audit row ----
    ("string", "apps/desktop/src/lib/types.ts", "TrustRetrievalProvenance", "Frontend: TS provenance shape"),
    ("string", "apps/desktop/src/lib/types.ts", "TrustRetrievalHit", "Frontend: TS hit shape"),

    # ---- ADR doc itself ----
    ("file",   "docs/adr/ADR-0009-retrieval-augmented-utterance-audit-reach.md", None, "ADR-0009 doc"),
]


DOC_PATH = Path("docs/adr/ADR-0009-retrieval-augmented-utterance-audit-reach.md")
STATUS_RE = re.compile(r"\*\*Status:\*\*\s+\*\*(?P<status>Accepted|Proposed|Superseded)\*\*")


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
            "ADR-0009 doc is missing — this linter is useless without it.",
        )
    text = doc_path.read_text(encoding="utf-8")
    m = STATUS_RE.search(text)
    if not m:
        return None, Failure(
            "doc", str(doc_path), None, "header",
            "could not find `**Status:** **Accepted|Proposed|Superseded**` line.",
        )
    return m.group("status"), None


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
            "expected substring not found in file — the ADR claims it exists. "
            "Either restore the symbol/string in code, or update the doc AND "
            "the ANCHORS manifest in tools/lint-policy-doc/check.py.",
        )
    return None


def _collect(repo_root: Path) -> tuple[str | None, list[Failure]]:
    failures: list[Failure] = []
    status, doc_fail = _check_status_line(repo_root / DOC_PATH)
    if doc_fail is not None:
        failures.append(doc_fail)

    for kind, rel, needle, section in ANCHORS:
        f = _check_anchor(repo_root, kind, rel, needle, section)
        if f is not None:
            failures.append(f)

    return status, failures


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check ADR-0009 anchors against code.",
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

    status, failures = _collect(repo_root)

    if args.json:
        print(json.dumps(
            {
                "ok":           not failures,
                "doc":          str(DOC_PATH),
                "doc_status":   status,
                "anchor_count": len(ANCHORS),
                "failures":     [f.to_dict() for f in failures],
            },
            indent=2,
        ))
    else:
        if failures:
            print("policy-doc rot-guard (ADR-0009): FAIL")
            for f in failures:
                print(f)
            print(
                f"\n{len(failures)} failure(s). "
                "See tools/lint-policy-doc/ANCHORS for how to resolve."
            )
        else:
            print("policy-doc rot-guard (ADR-0009): OK")
            print(
                f"  doc: {DOC_PATH} (Status: {status})"
                f"  checked {len(ANCHORS)} anchors across "
                f"{len({a[1] for a in ANCHORS})} files."
            )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
