#!/usr/bin/env python3
"""Aether Presence V1 architecture-doc rot guard.

Mirror of `tools/lint-voice-doc/check.py`. Keeps
`docs/PRESENCE-V1-ARCHITECTURE.md` honest: the doc claims specific
files, symbols, and string constants (telemetry kinds, event
channels, config filenames, command names) exist in code. When any
disappears (rename, delete, typo), this linter fails.

Not a prose parser. The manifest below is the contract between the
doc and the code; a Presence-V1 PR that adds / removes / renames an
anchor MUST update this manifest in the same PR.

Run:

  python tools/lint-presence-doc/check.py          # validate
  python tools/lint-presence-doc/check.py --json   # machine-readable

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
    # ---- §1 end-to-end flow: poll loop + shell wiring ----
    ("file",   "apps/desktop/src-tauri/src/main.rs", None, "§1 end-to-end flow"),
    ("symbol", "apps/desktop/src-tauri/src/main.rs", "async fn run_presence_loop", "§1 end-to-end flow"),
    ("symbol", "apps/desktop/src-tauri/src/main.rs", "PRESENCE_POLL_MS", "§1 poll rate"),

    # ---- §1 idle probe (OS-specific, shell-side) ----
    ("file",   "apps/desktop/src-tauri/src/idle_probe.rs", None, "§1 idle probe"),
    ("symbol", "apps/desktop/src-tauri/src/idle_probe.rs", "trait IdleProbe", "§1 idle probe"),
    ("symbol", "apps/desktop/src-tauri/src/idle_probe.rs", "WindowsIdleProbe", "§1 idle probe (Windows)"),
    ("symbol", "apps/desktop/src-tauri/src/idle_probe.rs", "UnsupportedIdleProbe", "§9 macOS/Linux stub"),

    # ---- §2 user-attention axis (L3) ----
    ("file",   "packages/l3-presence/src/attention.rs", None, "§2 user-attention axis"),
    ("symbol", "packages/l3-presence/src/attention.rs", "enum UserAttention", "§2 user-attention enum"),
    ("symbol", "packages/l3-presence/src/attention.rs", "struct AttentionThresholds", "§2 thresholds"),
    ("symbol", "packages/l3-presence/src/attention.rs", "struct AttentionSnapshot", "§2 attention snapshot"),
    ("symbol", "packages/l3-presence/src/attention.rs", "struct AttentionEvent", "§2 attention event"),
    ("symbol", "packages/l3-presence/src/attention.rs", "struct UserAttentionController", "§2 attention controller"),

    # ---- §2 assistant-posture axis (L3) ----
    ("file",   "packages/l3-presence/src/controller.rs", None, "§2 assistant-posture axis"),
    ("symbol", "packages/l3-presence/src/controller.rs", "enum PresenceState", "§2 posture states"),
    ("symbol", "packages/l3-presence/src/controller.rs", "struct PresenceSnapshot", "§2 posture snapshot"),
    ("symbol", "packages/l3-presence/src/controller.rs", "trait PresenceController", "§2 posture controller"),
    ("symbol", "packages/l3-presence/src/controller.rs", "InMemoryPresenceController", "§2 in-memory impl"),
    ("symbol", "packages/l3-presence/src/controller.rs", "TRANSITION_LOG_CAP", "§2 bounded ring cap"),

    # ---- §2 L3 crate-level discipline ----
    ("file",   "packages/l3-presence/src/lib.rs", None, "§8 L3 safety posture"),
    ("string", "packages/l3-presence/src/lib.rs", "deny(unsafe_code)", "§8 no unsafe in L3"),

    # ---- §2 shell-side presence-history ring ----
    ("symbol", "apps/desktop/src-tauri/src/state.rs", "struct PresenceHistoryEntry", "§2 shell ring row"),
    ("symbol", "apps/desktop/src-tauri/src/state.rs", "push_presence_history", "§2 ring push"),
    ("symbol", "apps/desktop/src-tauri/src/state.rs", "presence_history_recent", "§2 ring snapshot"),
    ("symbol", "apps/desktop/src-tauri/src/state.rs", "PRESENCE_HISTORY_CAPACITY", "§2 ring capacity"),

    # ---- §3 presence.json contract ----
    ("file",   "apps/desktop/src-tauri/src/presence_config.rs", None, "§3 config module"),
    ("string", "apps/desktop/src-tauri/src/presence_config.rs", "presence.json", "§3 filename"),
    ("symbol", "apps/desktop/src-tauri/src/presence_config.rs", "DEFAULT_IDLE_AFTER_S", "§3 idle default"),
    ("symbol", "apps/desktop/src-tauri/src/presence_config.rs", "DEFAULT_AWAY_AFTER_S", "§3 away default"),
    ("symbol", "apps/desktop/src-tauri/src/state.rs", "attach_presence_config_file", "§3 boot wiring"),
    ("symbol", "apps/desktop/src-tauri/src/state.rs", "set_presence_config", "§3 hot-swap setter"),

    # ---- §5 telemetry kind + event bus channel ----
    ("string", "apps/desktop/src-tauri/src/state.rs", "presence_state_changed", "§5 telemetry kind"),
    ("string", "apps/desktop/src-tauri/src/commands.rs", "presence:attention", "§5 event-bus channel"),

    # ---- §6 UI — Tauri commands bridging to the UI layer ----
    ("file",   "apps/desktop/src-tauri/src/commands.rs", None, "§6 commands module"),
    ("symbol", "apps/desktop/src-tauri/src/commands.rs", "fn presence_current", "§6 posture command"),
    ("symbol", "apps/desktop/src-tauri/src/commands.rs", "fn presence_status", "§6 attention command"),
    ("symbol", "apps/desktop/src-tauri/src/commands.rs", "fn presence_recent_history", "§6 history command"),

    # ---- §6 UI — Settings + Trust drawer ----
    ("file",   "apps/desktop/src/components/SettingsDrawer.tsx", None, "§6 Settings UI"),
    ("file",   "apps/desktop/src/components/TrustDrawer.tsx",    None, "§6 Trust drawer"),

    # ---- §9 / §12 runtime renderer scaffold (T1.4) ----
    ("file",   "packages/l3-presence/src/runtime.rs", None, "§9 / §12 runtime renderer scaffold"),
    ("symbol", "packages/l3-presence/src/runtime.rs", "trait Renderer", "§9 renderer trait"),
    ("symbol", "packages/l3-presence/src/runtime.rs", "struct LogStubRenderer", "§9 stub renderer"),
    ("symbol", "packages/l3-presence/src/runtime.rs", "struct MotionClipLibraryHandle", "§9 library handle"),
    ("symbol", "packages/l3-presence/src/runtime.rs", "struct AudioStreamHandle", "§9 audio handle"),
    ("symbol", "packages/l3-presence/src/runtime.rs", "struct MotionClipId", "§9 clip id"),
    ("symbol", "packages/l3-presence/src/runtime.rs", "enum RendererEvent", "§9 renderer event vocabulary"),
    ("symbol", "packages/l3-presence/src/runtime.rs", "struct RenderingPresenceController", "§9 wired controller"),
    ("symbol", "packages/l3-presence/src/runtime.rs", "RENDERER_EVENT_LOG_CAP", "§9 bounded ring cap"),
]


DOC_PATH = Path("docs/PRESENCE-V1-ARCHITECTURE.md")
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
            "the ANCHORS manifest in tools/lint-presence-doc/check.py.",
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
        description="Check Presence V1 architecture doc anchors against code.",
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
            print("presence-doc rot-guard: FAIL")
            for f in failures:
                print(f)
            print(
                f"\n{len(failures)} failure(s). "
                "See tools/lint-presence-doc/README.md for how to resolve."
            )
        else:
            print("presence-doc rot-guard: OK")
            print(
                f"  doc: {DOC_PATH} (Status: Current as of {doc_date})"
                f"  checked {len(ANCHORS)} anchors across "
                f"{len({a[1] for a in ANCHORS})} files."
            )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
