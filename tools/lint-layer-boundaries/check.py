#!/usr/bin/env python3
"""Aether layer-boundary linter.

Enforces the intra-workspace dependency rules declared in
`ARCHITECTURE.md` and `CLAUDE.md` §1.4:

  - L5 (policy) is the non-bypassable gate. Sibling engines (L1, L2, L3,
    L4, L6, L7) MAY depend on `aether-l5-policy`. L5 MUST NOT depend on
    any sibling engine crate.
  - Sibling engines do NOT depend on each other directly. Coordination
    goes through `packages/event-bus`, shared types, or typed L5 / L6
    outputs.
  - Shared-infra crates (`event-bus`, `storage`, `media-engine`,
    `telemetry`) do NOT depend on any engine crate.
  - L5 may depend on shared-infra crates (it currently depends on
    `event-bus`, `storage`, `telemetry`).

Mechanism:

  1. Shell out to `cargo metadata --format-version 1 --no-deps` to get
     the authoritative list of workspace members + their declared deps.
  2. Build a directed graph of workspace-internal edges only. External
     crates (thiserror, serde, tokio, ...) are ignored — `cargo-deny`
     covers those separately.
  3. Check every edge against a per-crate allowlist. Flag every edge
     that does not appear in the allowlist.
  4. Exit 0 if all edges are allowed; exit 1 with a report otherwise.

Usage:

  python tools/lint-layer-boundaries/check.py          # validate
  python tools/lint-layer-boundaries/check.py --json   # machine-readable

Run from the repo root, or set `AETHER_REPO_ROOT` to point at the repo.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable


# Every workspace crate that this linter cares about. Non-listed crates
# are ignored (e.g. TS packages, future tools/* binaries).
ENGINE_CRATES: frozenset[str] = frozenset(
    {
        "aether-l1-interaction",
        "aether-l2-memory",
        "aether-l3-presence",
        "aether-l4-router",
        "aether-l5-policy",
        "aether-l6-persona",
        "aether-l7-trust",
    }
)

SHARED_INFRA_CRATES: frozenset[str] = frozenset(
    {
        "aether-event-bus",
        "aether-storage",
        "aether-media-engine",
        "aether-telemetry",
    }
)

KNOWN_WORKSPACE_CRATES: frozenset[str] = ENGINE_CRATES | SHARED_INFRA_CRATES


# Allowed intra-workspace edges. Format:
#   ALLOWED[src] = frozenset of crate names that `src` is permitted to
#                  depend on (directly, in `[dependencies]` or
#                  `[dev-dependencies]`).
#
# Rationale for each entry lives in the planning doctrine:
#   - Engines may depend on aether-l5-policy (the non-bypassable gate).
#   - L2 may additionally depend on aether-storage (memory kernel
#     persistence). Confirmed by L2 interface pack.
#   - L5 may depend on shared infra (event-bus, storage, telemetry).
#     L5 must NOT depend on any sibling engine.
#   - Shared-infra crates are leaves; they do not depend on any
#     workspace crate. (They may still depend on other shared infra
#     if that ever becomes useful — not today.)
ALLOWED: dict[str, frozenset[str]] = {
    # ------ engines ------
    "aether-l1-interaction": frozenset({"aether-l5-policy"}),
    "aether-l2-memory":      frozenset({"aether-l5-policy", "aether-storage"}),
    "aether-l3-presence":    frozenset(),
    "aether-l4-router":      frozenset({"aether-l5-policy"}),
    "aether-l5-policy":      frozenset(
        {"aether-event-bus", "aether-storage", "aether-telemetry"}
    ),
    "aether-l6-persona":     frozenset({"aether-l5-policy"}),
    "aether-l7-trust":       frozenset({"aether-l5-policy"}),
    # ------ shared infra ------
    "aether-event-bus":      frozenset(),
    "aether-storage":        frozenset(),
    "aether-media-engine":   frozenset(),
    "aether-telemetry":      frozenset(),
}


class Violation:
    __slots__ = ("source", "target", "kind", "reason")

    def __init__(self, source: str, target: str, kind: str, reason: str) -> None:
        self.source = source
        self.target = target
        self.kind = kind  # "dependencies" | "dev-dependencies" | "build-dependencies"
        self.reason = reason

    def to_dict(self) -> dict[str, str]:
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
            "reason": self.reason,
        }

    def __str__(self) -> str:
        return (
            f"  {self.source} -> {self.target}  [{self.kind}]\n"
            f"      {self.reason}"
        )


def _repo_root() -> Path:
    env = os.environ.get("AETHER_REPO_ROOT")
    if env:
        return Path(env)
    # Walk up from this script's location until we see a Cargo.toml that
    # declares `[workspace]`.
    here = Path(__file__).resolve()
    for parent in (here, *here.parents):
        cargo = parent / "Cargo.toml"
        if cargo.is_file() and "[workspace]" in cargo.read_text(encoding="utf-8"):
            return parent
    raise RuntimeError(
        "Could not locate workspace root. Run this script from the Aether repo "
        "or set AETHER_REPO_ROOT."
    )


def _run_cargo_metadata(repo_root: Path) -> dict:
    cmd = [
        "cargo",
        "metadata",
        "--format-version",
        "1",
        "--no-deps",
        "--manifest-path",
        str(repo_root / "Cargo.toml"),
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, check=True
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            "`cargo` not found on PATH. Install a Rust toolchain via rustup."
        ) from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            "cargo metadata failed:\n" + (e.stderr or e.stdout or "")
        ) from e
    return json.loads(proc.stdout)


def _collect_violations(metadata: dict) -> list[Violation]:
    violations: list[Violation] = []

    # `workspace_members` strings vary across Cargo versions:
    #   old (pre-1.77):  "aether-l5-policy 0.0.1 (path+file:///.../l5-policy)"
    #   new (1.77+):     "path+file:///.../packages/l5-policy#aether-l5-policy@0.0.1"
    # Handle both.
    workspace_names: set[str] = set()
    for m in metadata.get("workspace_members", []):
        if "#" in m and "@" in m:
            # new format: path+...#name@version
            after_hash = m.split("#", 1)[1]
            name = after_hash.split("@", 1)[0]
        else:
            # old format: name version (...)
            name = m.split(" ", 1)[0]
        workspace_names.add(name)

    for pkg in metadata.get("packages", []):
        name: str = pkg.get("name", "")
        if name not in workspace_names:
            continue
        if name not in ALLOWED:
            # Not a crate we police (e.g. ts-side packages, tooling).
            continue

        allowed_targets = ALLOWED[name]

        for dep in pkg.get("dependencies", []):
            target = dep.get("name", "")
            if target not in KNOWN_WORKSPACE_CRATES:
                continue  # external crate; not our concern
            kind_raw = dep.get("kind")
            # kind: null -> normal, "dev" -> dev-dependencies,
            # "build" -> build-dependencies.
            if kind_raw is None:
                kind = "dependencies"
            elif kind_raw == "dev":
                kind = "dev-dependencies"
            elif kind_raw == "build":
                kind = "build-dependencies"
            else:
                kind = f"kind={kind_raw}"

            if target in allowed_targets:
                continue

            reason = _reason_for(name, target)
            violations.append(Violation(name, target, kind, reason))

    return violations


def _reason_for(src: str, target: str) -> str:
    """Explain why this edge is forbidden."""
    if src == "aether-l5-policy" and target in ENGINE_CRATES - {"aether-l5-policy"}:
        return (
            "L5 is the non-bypassable policy gate. It MUST NOT depend on any "
            "sibling engine crate (ARCHITECTURE.md, "
            "CLAUDE.md §1.4)."
        )
    if src in ENGINE_CRATES and target in ENGINE_CRATES and target != "aether-l5-policy":
        return (
            "Sibling engine crates do not import each other. Route through the "
            "event bus, shared types, or typed L5 / L6 outputs instead "
            "(CLAUDE.md §1.4)."
        )
    if src in SHARED_INFRA_CRATES and target in ENGINE_CRATES:
        return (
            "Shared-infra crates must not depend on engine crates — the arrow "
            "runs the other way (ARCHITECTURE.md)."
        )
    if target not in KNOWN_WORKSPACE_CRATES:
        return "Unexpected non-workspace target."
    return (
        f"'{src}' is not permitted to depend on '{target}'. Update the ALLOWED "
        "table in tools/lint-layer-boundaries/check.py if this edge is doctrinal; "
        "otherwise reshape the import to go through shared types or the event bus."
    )


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check Aether layer-boundary rules against cargo metadata."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON report on stdout",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        repo_root = _repo_root()
        metadata = _run_cargo_metadata(repo_root)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    violations = _collect_violations(metadata)

    if args.json:
        print(
            json.dumps(
                {
                    "ok": not violations,
                    "violations": [v.to_dict() for v in violations],
                },
                indent=2,
            )
        )
    else:
        if violations:
            print("layer-boundary violations detected:")
            for v in violations:
                print(v)
            print(
                f"\n{len(violations)} violation(s). See "
                "tools/lint-layer-boundaries/README.md for how to resolve."
            )
        else:
            print("layer-boundary check: OK (0 violations)")
            print(
                f"  checked {len(ALLOWED)} workspace crates; "
                f"engines {len(ENGINE_CRATES)}, shared infra {len(SHARED_INFRA_CRATES)}."
            )

    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
