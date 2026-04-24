#!/usr/bin/env python3
"""Windows-native fallback for ``scripts/current_status.sh``.

Same contract: print a one-screen snapshot of the repo — live git
state plus the subsystem-status / check-matrix / risks sections of
the latest ``HANDOFF_*.md``. Standalone, stdlib-only.

Usage::

    python scripts/current_status.py            # latest handoff
    python scripts/current_status.py 2026-05-17 # filter by date prefix
    python scripts/current_status.py --list     # list handoffs

The bash flavour is kept for Unix / WSL / git-bash; this mirror exists
because Don runs PowerShell often and the behaviour needs to be
identical regardless of shell. See Risk B in
``HANDOFF_2026-05-17_SESSION_END_ULTRA_LONG_SETUP.md``.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str]) -> str:
    try:
        out = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
        )
        return out.stdout.strip()
    except FileNotFoundError:
        return ""


def _repo_root() -> Path:
    out = _run(["git", "rev-parse", "--show-toplevel"])
    if not out:
        sys.stderr.write("error: not inside a git repo\n")
        sys.exit(2)
    return Path(out)


def _section_matching(parts: list[str], needles: list[str]) -> tuple[str, str] | None:
    for p in parts[1:]:
        head, _, body = p.partition("\n")
        head_lc = head.lower()
        if any(n in head_lc for n in needles):
            return head.strip(), body.rstrip()
    return None


def _render(title: str, pair: tuple[str, str] | None) -> None:
    if pair is None:
        return
    head, body = pair
    print(f"----- {title}: {head} -----")
    lines = body.splitlines()
    capped: list[str] = []
    for ln in lines:
        capped.append(ln)
        if len(capped) >= 60:
            capped.append("… (truncated — see full handoff)")
            break
    print("\n".join(capped).rstrip())
    print()


def _last_commit_time(path: Path) -> int:
    """Return the unix timestamp of the last commit touching ``path``.

    Falls back to ``0`` for untracked files so they sort last. Using
    commit time (not filename date) prevents future-dated filenames
    from masquerading as "newest" — see
    MILESTONE_1_RETROSPECTIVE_2026-04-23.md §3 item 1.
    """
    out = _run(["git", "log", "-1", "--format=%ct", "--", path.name])
    try:
        return int(out)
    except ValueError:
        return 0


def _handoffs_newest_first(root: Path, pattern: str) -> list[Path]:
    """List handoff paths ordered by last-commit-time, newest first.

    Untracked handoffs (commit time ``0``) keep a stable filename
    tiebreak so a fresh working-copy file still appears first if it
    was just written.
    """
    files = list(root.glob(pattern))
    files.sort(key=lambda p: (_last_commit_time(p), p.name), reverse=True)
    return files


def main(argv: list[str]) -> int:
    root = _repo_root()
    if len(argv) > 1 and argv[1] == "--list":
        for p in _handoffs_newest_first(root, "HANDOFF_*.md"):
            print(p.name)
        return 0

    filt = argv[1] if len(argv) > 1 else ""
    pattern = f"HANDOFF_*{filt}*.md" if filt else "HANDOFF_*.md"
    matches = _handoffs_newest_first(root, pattern)
    if not matches:
        sys.stderr.write(f"error: no handoff matched: {filt or '<latest>'}\n")
        sys.stderr.write("try: python scripts/current_status.py --list\n")
        return 2
    handoff = matches[0]

    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]) or "?"
    tip = _run(["git", "log", "-1", "--oneline"]) or "?"
    ahead = _run(["git", "rev-list", "--count", "@{u}..HEAD"]) or "?"
    dirty_raw = _run(["git", "status", "--porcelain"])
    if not dirty_raw:
        tree = "clean"
    else:
        tree = f"dirty ({len(dirty_raw.splitlines())} paths)"

    print("=" * 64)
    print(f"Aether — live status (from {handoff.name})")
    print("=" * 64)
    print(f"branch:        {branch}")
    print(f"tip:           {tip}")
    print(f"ahead of @{{u}}: {ahead}")
    print(f"working tree:  {tree}")
    print()

    text = handoff.read_text(encoding="utf-8", errors="replace")
    parts = re.split(r"(?m)^## ", text)

    _render(
        "Subsystem status",
        _section_matching(parts, ["subsystem status", "subsystem snapshot"]),
    )
    _render(
        "Check matrix",
        _section_matching(parts, ["check matrix"]),
    )
    _render(
        "Risks / alerts",
        _section_matching(parts, ["risks", "alerts"]),
    )

    print("=" * 64)
    print("Source of truth reminder: repo beats prompt (Decision #32).")
    print(
        "If anything above conflicts with git log / the code, trust the"
    )
    print(
        "repo and update the handoff. Do NOT restate stale status in a"
    )
    print("fresh prompt — run this script instead.")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
