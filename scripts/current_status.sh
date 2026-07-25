#!/usr/bin/env bash
# scripts/current_status.sh
#
# Prints a one-screen snapshot of the repo: live git state plus
# subsystem status / check matrix / risks from the latest session
# handoff. Mitigates the "stale prompt" drift pattern described in
# HANDOFF_2026-05-17_SESSION_END_ULTRA_LONG_SETUP.md Risk B.
#
# Usage:
#   ./scripts/current_status.sh            # latest handoff
#   ./scripts/current_status.sh 2026-05-17 # filter by date prefix
#   ./scripts/current_status.sh --list     # list handoffs
#
# Contract:
# - Non-destructive, read-only. No git writes, no env mutation.
# - Delegates section parsing to scripts/current_status.py so the
#   bash and Python surfaces print the same snapshot.

set -u

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [[ -z "$ROOT" ]]; then
  echo "error: not inside a git repo" >&2
  exit 2
fi
cd "$ROOT" || exit 2

PY="${PYTHON_CMD:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
  PY="python"
fi
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "error: neither python3 nor python on PATH" >&2
  exit 2
fi

exec "$PY" "$ROOT/scripts/current_status.py" "$@"
