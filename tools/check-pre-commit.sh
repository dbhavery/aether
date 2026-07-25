#!/usr/bin/env bash
# tools/check-pre-commit.sh
#
# Local mirror of CI's BLOCKING lint jobs. Run this before every commit
# (manually or via the pre-commit hook installed by tools/setup-hooks.sh).
#
# Mirrors:
#   - .github/workflows/ci.yml `rust` job step `cargo fmt --check`
#   - .github/workflows/ci.yml `legacy-python` job step `ruff check src/ tests/`
#
# Why this exists: CI was silently red on every push for multiple sessions
# because agents wrote code that compiled + tested cleanly locally but
# failed `cargo fmt --check` or `ruff check`. The fixes are trivial; the
# missed signal was costly. This script collapses those CI checks into a
# single fast local run so the failure surfaces in <10s instead of after
# a 1-minute CI cycle.
#
# Exits non-zero on any failure. Quiet on success.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

FAIL=0

# ---------------------------------------------------------------------------
# Locate cargo. Prefers PATH; falls back to default rustup install location
# on Windows ($USERPROFILE/.cargo/bin) and Unix ($HOME/.cargo/bin).
# ---------------------------------------------------------------------------
find_cargo() {
    if command -v cargo >/dev/null 2>&1; then
        echo cargo
        return
    fi
    for candidate in \
        "$HOME/.cargo/bin/cargo" \
        "$HOME/.cargo/bin/cargo.exe" \
        "${USERPROFILE:-}/.cargo/bin/cargo.exe"; do
        if [ -x "$candidate" ]; then
            echo "$candidate"
            return
        fi
    done
    echo ""
}

# ---------------------------------------------------------------------------
# Locate ruff. Prefers PATH; checks Python user-scripts location on Windows.
# ---------------------------------------------------------------------------
find_ruff() {
    if command -v ruff >/dev/null 2>&1; then
        echo ruff
        return
    fi
    for candidate in \
        "$HOME/.local/bin/ruff" \
        "$HOME/AppData/Local/Programs/Python/Python313/Scripts/ruff.exe" \
        "$HOME/AppData/Local/Programs/Python/Python312/Scripts/ruff.exe" \
        "${USERPROFILE:-}/AppData/Local/Programs/Python/Python313/Scripts/ruff.exe" \
        "${USERPROFILE:-}/AppData/Local/Programs/Python/Python312/Scripts/ruff.exe"; do
        if [ -x "$candidate" ]; then
            echo "$candidate"
            return
        fi
    done
    echo ""
}

CARGO=$(find_cargo)
RUFF=$(find_ruff)

# ---------------------------------------------------------------------------
# Rust: cargo fmt --check
# ---------------------------------------------------------------------------
if [ -z "$CARGO" ]; then
    echo "[pre-commit] WARN: cargo not found; install via https://rustup.rs/"
    echo "[pre-commit]       skipping cargo fmt check (CI will still run it)"
    FAIL=1
else
    echo "[pre-commit] cargo fmt --all -- --check"
    if ! "$CARGO" fmt --all -- --check; then
        echo "[pre-commit] FAIL: cargo fmt found drift; run: $CARGO fmt --all"
        FAIL=1
    fi
fi

# ---------------------------------------------------------------------------
# Python: ruff check src/ tests/
# Only runs if there are tracked Python files under src/ or tests/.
# ---------------------------------------------------------------------------
if [ -d src ] || [ -d tests ]; then
    if [ -z "$RUFF" ]; then
        echo "[pre-commit] WARN: ruff not found; install via 'pip install ruff'"
        echo "[pre-commit]       skipping python lint (CI will still run it)"
        FAIL=1
    else
        echo "[pre-commit] ruff check src/ tests/"
        if ! "$RUFF" check src/ tests/; then
            echo "[pre-commit] FAIL: ruff found issues; run: $RUFF check src/ tests/ --fix"
            FAIL=1
        fi
    fi
fi

if [ "$FAIL" -ne 0 ]; then
    echo "[pre-commit] one or more checks failed; commit blocked"
    exit 1
fi

echo "[pre-commit] all checks passed"
exit 0
