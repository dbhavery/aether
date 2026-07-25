#!/usr/bin/env bash
# tools/setup-hooks.sh
#
# One-time setup: point this clone's git hooks at tools/git-hooks/.
# Idempotent — safe to run multiple times.
#
# Why core.hooksPath instead of copying into .git/hooks: the hooks then
# travel with the repo. New clones run `bash tools/setup-hooks.sh` once
# and immediately get the same hooks every other contributor uses.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

git config core.hooksPath tools/git-hooks

# Ensure the hook scripts are executable. Windows checkouts may not preserve
# the +x bit; we set it explicitly via git's index attribute.
chmod +x tools/git-hooks/* 2>/dev/null || true
chmod +x tools/check-pre-commit.sh 2>/dev/null || true

echo "[setup-hooks] core.hooksPath set to tools/git-hooks"
echo "[setup-hooks] pre-commit will now run tools/check-pre-commit.sh"
echo "[setup-hooks] disable with: git config --unset core.hooksPath"
