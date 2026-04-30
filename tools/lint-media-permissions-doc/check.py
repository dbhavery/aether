#!/usr/bin/env python3
"""Aether Media-Permissions architecture-doc rot guard.

Mirror of `tools/lint-presence-doc/check.py` and
`tools/lint-voice-doc/check.py`. Keeps
`docs/MEDIA-PERMISSIONS.md` honest: the doc claims specific
files, symbols, string constants (capability names, command names,
wire-format labels, env vars), and UI components exist in code.
When any disappears (rename, delete, typo), this linter fails.

Not a prose parser. The manifest below is the contract between the
doc and the code; a media-permissions PR that adds / removes /
renames an anchor MUST update this manifest in the same PR.

Run:

  python tools/lint-media-permissions-doc/check.py          # validate
  python tools/lint-media-permissions-doc/check.py --json   # machine-readable

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
    # ---- Model: tri-state per device, two devices ----
    ("file",   "apps/desktop/src-tauri/src/media_permissions.rs", None, "Model: media-permissions module"),
    ("symbol", "apps/desktop/src-tauri/src/media_permissions.rs", "pub enum PermissionState", "Model: tri-state enum"),
    ("symbol", "apps/desktop/src-tauri/src/media_permissions.rs", "pub enum MediaKind", "Model: device discriminant"),
    ("symbol", "apps/desktop/src-tauri/src/media_permissions.rs", "pub enum CaptureGate", "Model: gate evaluation result"),
    ("symbol", "apps/desktop/src-tauri/src/media_permissions.rs", "pub struct MediaPermissions", "Model: persisted shape"),
    ("symbol", "apps/desktop/src-tauri/src/media_permissions.rs", "fn from_wire", "Model: wire-format parse"),
    ("symbol", "apps/desktop/src-tauri/src/media_permissions.rs", "fn evaluate", "Model: gate evaluator"),
    ("symbol", "apps/desktop/src-tauri/src/media_permissions.rs", "pub fn load_or_default", "Model: tolerant loader"),
    ("symbol", "apps/desktop/src-tauri/src/media_permissions.rs", "pub fn save", "Model: atomic save"),
    # ---- Model: wire-format labels (lowercase strings) ----
    ("string", "apps/desktop/src-tauri/src/media_permissions.rs", "\"allow\"", "Model: wire label allow"),
    ("string", "apps/desktop/src-tauri/src/media_permissions.rs", "\"ask\"", "Model: wire label ask"),
    ("string", "apps/desktop/src-tauri/src/media_permissions.rs", "\"deny\"", "Model: wire label deny"),
    ("string", "apps/desktop/src-tauri/src/media_permissions.rs", "\"camera\"", "Model: device label camera"),
    ("string", "apps/desktop/src-tauri/src/media_permissions.rs", "\"screen\"", "Model: device label screen"),

    # ---- Persistence: media_permissions.json beside session memory ----
    ("string", "apps/desktop/src-tauri/src/state.rs", "media_permissions.json", "Persistence: filename"),
    ("symbol", "apps/desktop/src-tauri/src/state.rs", "pub fn media_permissions", "Persistence: AppState getter"),
    ("symbol", "apps/desktop/src-tauri/src/state.rs", "pub fn set_media_permission", "Persistence: AppState setter"),
    ("symbol", "apps/desktop/src-tauri/src/state.rs", "pub fn evaluate_media_permission", "Enforcement: AppState gate evaluator"),

    # ---- Tauri command surface ----
    ("file",   "apps/desktop/src-tauri/src/commands.rs", None, "Tauri commands module"),
    ("symbol", "apps/desktop/src-tauri/src/commands.rs", "pub fn get_media_permissions", "Command: get_media_permissions"),
    ("symbol", "apps/desktop/src-tauri/src/commands.rs", "pub fn set_media_permission", "Command: set_media_permission"),
    ("symbol", "apps/desktop/src-tauri/src/commands.rs", "pub fn analyze_frame", "Command: analyze_frame (P3 single-frame path)"),
    ("symbol", "apps/desktop/src-tauri/src/commands.rs", "pub fn vision_status", "Command: vision_status"),
    ("symbol", "apps/desktop/src-tauri/src/commands.rs", "pub struct FrameAnalysisOutcome", "Command: analyze_frame result shape"),

    # ---- Command handler registration in main.rs ----
    ("symbol", "apps/desktop/src-tauri/src/main.rs", "commands::get_media_permissions", "main.rs: get_media_permissions registered"),
    ("symbol", "apps/desktop/src-tauri/src/main.rs", "commands::set_media_permission", "main.rs: set_media_permission registered"),
    ("symbol", "apps/desktop/src-tauri/src/main.rs", "commands::analyze_frame", "main.rs: analyze_frame registered"),
    ("symbol", "apps/desktop/src-tauri/src/main.rs", "commands::vision_status", "main.rs: vision_status registered"),

    # ---- L5 capability gate for vision routing ----
    ("symbol", "packages/l5-policy/src/capability.rs", "MediaCamera", "L5 capability: MediaCamera"),
    ("symbol", "packages/l5-policy/src/capability.rs", "MediaScreenCapture", "L5 capability: MediaScreenCapture"),

    # ---- Tauri capability allowlist (default-deny) ----
    ("file",   "apps/desktop/src-tauri/capabilities/default.json", None, "Tauri capability allowlist (default-deny)"),
    ("string", "apps/desktop/src-tauri/capabilities/default.json", "core:default", "Allowlist: core:default"),
    ("string", "apps/desktop/src-tauri/capabilities/default.json", "core:window:default", "Allowlist: core:window:default"),
    ("string", "apps/desktop/src-tauri/capabilities/default.json", "core:event:default", "Allowlist: core:event:default"),
    ("string", "apps/desktop/src-tauri/capabilities/default.json", "core:app:default", "Allowlist: core:app:default"),

    # ---- Vision provider env vars (opt-in) ----
    ("string", "packages/l4-router/src/providers/ollama_vision.rs", "AETHER_OLLAMA_VISION_MODEL", "Env var: vision model selector"),
    ("string", "packages/l4-router/src/providers/ollama_vision.rs", "AETHER_OLLAMA_VISION_BASE_URL", "Env var: vision daemon endpoint"),
    ("string", "packages/l4-router/src/providers/ollama_vision.rs", "AETHER_OLLAMA_VISION_TIMEOUT_MS", "Env var: vision timeout"),

    # ---- Frontend mirrors and UI ----
    ("file",   "apps/desktop/src/lib/types.ts", None, "Frontend: TS type mirrors"),
    ("file",   "apps/desktop/src/components/VisionBadge.tsx", None, "Frontend: VisionBadge component"),
]


DOC_PATH = Path("docs/MEDIA-PERMISSIONS.md")
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
            "the ANCHORS manifest in tools/lint-media-permissions-doc/check.py.",
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
        description="Check Media-Permissions architecture doc anchors against code.",
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
            print("media-permissions-doc rot-guard: FAIL")
            for f in failures:
                print(f)
            print(
                f"\n{len(failures)} failure(s). "
                "See tools/lint-media-permissions-doc/README.md for how to resolve."
            )
        else:
            print("media-permissions-doc rot-guard: OK")
            print(
                f"  doc: {DOC_PATH} (Status: Current as of {doc_date})"
                f"  checked {len(ANCHORS)} anchors across "
                f"{len({a[1] for a in ANCHORS})} files."
            )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
