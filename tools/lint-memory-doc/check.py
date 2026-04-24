#!/usr/bin/env python3
"""Aether Memory V2 architecture-doc rot guard.

Mirror of `tools/lint-presence-doc/check.py` and
`tools/lint-quality-doc/check.py`. Keeps
`docs/MEMORY-V2-ARCHITECTURE.md` honest: the doc claims specific
files, symbols, and string constants (domain labels, telemetry
kinds, capability names, embed-eligible domain set, retention
sweep entry point) exist in code. When any disappears (rename,
delete, typo), this linter fails.

Not a prose parser. The manifest below is the contract between the
doc and the code; a Memory V2 PR that adds / removes / renames an
anchor MUST update this manifest in the same PR.

Run:

  python tools/lint-memory-doc/check.py          # validate
  python tools/lint-memory-doc/check.py --json   # machine-readable

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
    # ---- §1 six-domain taxonomy (ADR-0001 relocation) ----
    ("file",   "packages/l2-memory/src/domain.rs", None, "§1 domain taxonomy"),
    ("symbol", "packages/l2-memory/src/domain.rs", "pub enum MemoryDomain", "§1 MemoryDomain enum"),
    ("symbol", "packages/l2-memory/src/domain.rs", "pub const ALL", "§1 ALL constant"),
    ("string", "packages/l2-memory/src/domain.rs", "Session", "§1 domain Session"),
    ("string", "packages/l2-memory/src/domain.rs", "Durable", "§1 domain Durable"),
    ("string", "packages/l2-memory/src/domain.rs", "Facts", "§1 domain Facts"),
    ("string", "packages/l2-memory/src/domain.rs", "Projects", "§1 domain Projects"),
    ("string", "packages/l2-memory/src/domain.rs", "Preferences", "§1 domain Preferences"),
    ("string", "packages/l2-memory/src/domain.rs", "Artifacts", "§1 domain Artifacts"),

    # ---- §3 memory.json policy surface ----
    ("file",   "apps/desktop/src-tauri/src/memory_config.rs", None, "§3 policy surface"),
    ("symbol", "apps/desktop/src-tauri/src/memory_config.rs", "pub struct MemoryConfig", "§3 MemoryConfig"),
    ("symbol", "apps/desktop/src-tauri/src/memory_config.rs", "pub enum MemoryRisk", "§3 MemoryRisk tri-state"),
    ("symbol", "apps/desktop/src-tauri/src/memory_config.rs", "pub struct EmbeddingsConfig", "§3 embeddings policy"),
    ("symbol", "apps/desktop/src-tauri/src/memory_config.rs", "fn retention_for", "§3 retention resolver"),
    ("symbol", "apps/desktop/src-tauri/src/memory_config.rs", "fn risk_for", "§3 risk resolver"),
    ("string", "apps/desktop/src-tauri/src/memory_config.rs", "memory.json", "§3 filename"),

    # ---- §4 L5 capability wiring ----
    ("symbol", "packages/l5-policy/src/capability.rs", "MemoryWrite", "§4 capability MemoryWrite"),
    ("symbol", "packages/l5-policy/src/capability.rs", "MemoryRead", "§4 capability MemoryRead"),
    ("symbol", "packages/l5-policy/src/capability.rs", "MemoryForget", "§4 capability MemoryForget"),
    ("symbol", "packages/l5-policy/src/capability.rs", "MemoryEdit", "§4 capability MemoryEdit"),
    ("symbol", "packages/l5-policy/src/capability.rs", "MemoryEmbed", "§4 capability MemoryEmbed (step 6)"),

    # ---- §5 telemetry kinds ----
    ("file",   "apps/desktop/src-tauri/src/memory_service.rs", None, "§5 memory service"),
    ("string", "apps/desktop/src-tauri/src/memory_service.rs", "memory_written", "§5 telemetry: written"),
    ("string", "apps/desktop/src-tauri/src/memory_service.rs", "memory_forgotten", "§5 telemetry: forgotten"),
    ("string", "apps/desktop/src-tauri/src/memory_service.rs", "memory_write_asked", "§5 telemetry: write_asked"),
    ("string", "apps/desktop/src-tauri/src/memory_service.rs", "memory_write_denied", "§5 telemetry: write_denied"),
    ("string", "apps/desktop/src-tauri/src/memory_service.rs", "memory_edited", "§5 telemetry: edited"),
    ("string", "apps/desktop/src-tauri/src/memory_service.rs", "memory_retrieval", "§5 telemetry: retrieval"),
    ("string", "apps/desktop/src-tauri/src/memory_service.rs", "memory_embedded", "§5 telemetry: embedded (step 6)"),

    # ---- memory_service shell API ----
    ("symbol", "apps/desktop/src-tauri/src/memory_service.rs", "fn memory_write", "memory_service: write"),
    ("symbol", "apps/desktop/src-tauri/src/memory_service.rs", "fn memory_write_after_approval", "memory_service: post-approval write"),
    ("symbol", "apps/desktop/src-tauri/src/memory_service.rs", "fn memory_forget", "memory_service: forget"),
    ("symbol", "apps/desktop/src-tauri/src/memory_service.rs", "fn memory_forget_item", "memory_service: per-item forget"),
    ("symbol", "apps/desktop/src-tauri/src/memory_service.rs", "fn memory_edit", "memory_service: edit"),
    ("symbol", "apps/desktop/src-tauri/src/memory_service.rs", "fn memory_read_audit_tick", "memory_service: read audit"),
    ("symbol", "apps/desktop/src-tauri/src/memory_service.rs", "fn run_retention_sweep", "§10 step 5 sweep entry"),
    ("symbol", "apps/desktop/src-tauri/src/memory_service.rs", "fn maybe_embed_on_write", "§10 step 6 embed hook"),

    # ---- §6 UI — Trust drawer Memory tab ----
    ("file",   "apps/desktop/src/components/MemoryTab.tsx", None, "§6 Memory tab"),
    ("file",   "apps/desktop/src/components/TrustDrawer.tsx", None, "§6 Trust drawer"),
    ("file",   "apps/desktop/src/components/SettingsDrawer.tsx", None, "§6 Settings (memory section)"),

    # ---- §10 step 4 — SessionMemoryStore surface (remove/update) ----
    ("file",   "packages/l2-memory/src/session.rs", None, "§10 step 4 session store"),
    ("symbol", "packages/l2-memory/src/session.rs", "trait SessionMemoryStore", "§10 session store trait"),
    ("symbol", "packages/l2-memory/src/session.rs", "fn remove", "§10 step 4 remove"),
    ("symbol", "packages/l2-memory/src/session.rs", "fn update", "§10 step 4 update"),

    # ---- §10 step 5 — retention sweep ----
    ("symbol", "packages/l2-memory/src/session.rs", "fn prune_before", "§10 step 5 prune_before"),
    ("symbol", "packages/l2-memory/src/session.rs", "fn list_sessions", "§10 step 5 list_sessions"),
    ("file",   "apps/desktop/src-tauri/src/main.rs", None, "§10 step 5 sweep wiring"),
    ("symbol", "apps/desktop/src-tauri/src/main.rs", "RETENTION_SWEEP_INTERVAL_MS", "§10 step 5 tick constant"),
    ("symbol", "apps/desktop/src-tauri/src/main.rs", "async fn run_retention_sweep_loop", "§10 step 5 tick loop"),

    # ---- §10 step 6 — embeddings (opt-in) ----
    ("file",   "packages/l2-memory/src/embeddings.rs", None, "§10 step 6 embeddings module"),
    ("symbol", "packages/l2-memory/src/embeddings.rs", "trait EmbeddingStore", "§10 step 6 store trait"),
    ("symbol", "packages/l2-memory/src/embeddings.rs", "trait EmbeddingProvider", "§10 step 6 provider trait"),
    ("symbol", "packages/l2-memory/src/embeddings.rs", "pub struct FlatFileEmbeddingStore", "§10 step 6 flat-file impl"),
    ("symbol", "packages/l2-memory/src/embeddings.rs", "pub struct OllamaEmbeddingProvider", "§10 step 6 Ollama provider"),
    ("symbol", "packages/l2-memory/src/embeddings.rs", "pub const EMBED_ELIGIBLE_DOMAINS", "§10 step 6 eligible domains"),
    ("string", "packages/l2-memory/src/embeddings.rs", "DEFAULT_OLLAMA_EMBED_MODEL", "§10 step 6 default model const"),
    ("string", "packages/l2-memory/src/embeddings.rs", "AETHER_EMBED_OLLAMA_MODEL", "§10 step 6 model env var"),
    ("string", "packages/l2-memory/src/embeddings.rs", "AETHER_EMBED_OLLAMA_BASE_URL", "§10 step 6 base URL env var"),

    # ---- ADR-0004 — Durable-domain store (Milestone 2 Run 1) ----
    ("file",   "packages/storage/migrations/0005_durable_log.sql", None, "ADR-0004: Durable table migration"),
    ("string", "packages/l2-memory/src/sqlite_session.rs", "DURABLE_TABLE", "ADR-0004: Durable table name const"),
    ("string", "packages/l2-memory/src/sqlite_session.rs", "DEFAULT_TABLE", "ADR-0004: Default table name const"),
    ("symbol", "packages/l2-memory/src/sqlite_session.rs", "pub fn with_table", "ADR-0004: parameterized constructor"),
    ("symbol", "packages/l2-memory/src/sqlite_session.rs", "pub fn open_session_and_durable", "ADR-0004: paired opener"),
    ("symbol", "packages/l2-memory/src/sqlite_session.rs", "pub struct SessionAndDurableStores", "ADR-0004: paired-opener return"),
    ("symbol", "apps/desktop/src-tauri/src/state.rs", "pub fn memory_for_domain", "ADR-0004: domain router"),
    ("symbol", "apps/desktop/src-tauri/src/state.rs", "pub const DOMAINS_WITH_STORE", "ADR-0004: stored-domain set"),
    ("symbol", "apps/desktop/src-tauri/src/state.rs", "pub durable_memory", "ADR-0004: Durable lane on AppState"),

    # ---- ADRs ----
    ("file",   "docs/adr/ADR-0001-memory-domain-reconciliation.md", None, "ADR-0001: domain relocation"),
    ("file",   "docs/adr/ADR-0002-embeddings-provider-and-vector-backend.md", None, "ADR-0002: embeddings defaults"),
    ("file",   "docs/adr/ADR-0004-durable-store-shape.md", None, "ADR-0004: Durable-store shape"),
]


DOC_PATH = Path("docs/MEMORY-V2-ARCHITECTURE.md")
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
            "the ANCHORS manifest in tools/lint-memory-doc/check.py.",
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
        description="Check Memory V2 architecture doc anchors against code.",
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
            print("memory-doc rot-guard: FAIL")
            for f in failures:
                print(f)
            print(
                f"\n{len(failures)} failure(s). "
                "See tools/lint-memory-doc/README.md for how to resolve."
            )
        else:
            print("memory-doc rot-guard: OK")
            print(
                f"  doc: {DOC_PATH} (Status: Current as of {doc_date})"
                f"  checked {len(ANCHORS)} anchors across "
                f"{len({a[1] for a in ANCHORS})} files."
            )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
