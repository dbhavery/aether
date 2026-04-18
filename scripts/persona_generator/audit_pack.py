"""Thin CLI wrapper around `src.personas.audit.audit_pack`.

Usage:
    python scripts/persona_generator/audit_pack.py <persona_id>
    python scripts/persona_generator/audit_pack.py --all

Behaves as a combined schema + licensing check:

    1. Loads the pack using the same path the backend loader uses
       (`src.personas.scan_personas`). A schema-level failure causes a
       non-zero exit before the licensing audit runs.
    2. If schema passes, runs `audit_pack()` from `src.personas.audit`.

Exit code 0 = clean (safe to ship). Exit code 1 = one or more issues.
Exit code 2 = CLI usage error or schema validation failure.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
# Ensure `src` package is importable whether this script is run from
# the repo root or anywhere else.
sys.path.insert(0, str(_REPO_ROOT))


def _import_backend():
    """Late import so usage --help works without the src dependencies."""
    from src.personas.audit import audit_pack as run_audit
    from src.personas.loader import PersonaValidationError, scan_personas

    return run_audit, scan_personas, PersonaValidationError


def _load_packs() -> dict:
    _, scan_personas, _ = _import_backend()
    bundled = _REPO_ROOT / "personas"
    # Use an empty user dir so we only audit bundled packs.
    user = Path("/nonexistent-aether-audit-user-dir")
    return scan_personas(bundled, user)


def audit(persona_id: str) -> int:
    """Audit one pack. Return the number of issues (0 = clean)."""
    run_audit, _, PersonaValidationError = _import_backend()
    try:
        packs = _load_packs()
    except PersonaValidationError as exc:
        print(f"[{persona_id}] SCHEMA VALIDATION FAILED:\n{exc}", file=sys.stderr)
        return -1  # sentinel — caller exits 2

    pack = packs.get(persona_id)
    if pack is None:
        print(
            f"[{persona_id}] pack not loaded (loader rejected it or folder missing) — "
            f"loaded: {sorted(packs)}",
            file=sys.stderr,
        )
        return -1

    issues = run_audit(pack)
    if not issues:
        print(f"{persona_id}: 0 issue(s) — clean")
        return 0
    print(f"{persona_id}: {len(issues)} issue(s):")
    for issue in issues:
        print(f"  - {issue}")
    return len(issues)


def audit_all() -> int:
    """Audit every bundled pack. Return total issue count."""
    run_audit, _, PersonaValidationError = _import_backend()
    try:
        packs = _load_packs()
    except PersonaValidationError as exc:
        print(f"SCHEMA VALIDATION FAILED: {exc}", file=sys.stderr)
        return -1

    if not packs:
        print("no packs loaded", file=sys.stderr)
        return 0

    total = 0
    for persona_id, pack in sorted(packs.items()):
        issues = run_audit(pack)
        if not issues:
            print(f"{persona_id}: 0 issue(s) — clean")
            continue
        print(f"{persona_id}: {len(issues)} issue(s):")
        for issue in issues:
            print(f"  - {issue}")
        total += len(issues)
    return total


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("persona_id", nargs="?", help="Persona id to audit")
    group.add_argument("--all", action="store_true", help="Audit every bundled pack")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    if args.all:
        total = audit_all()
    else:
        total = audit(args.persona_id)

    if total < 0:
        return 2  # schema validation failure
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
