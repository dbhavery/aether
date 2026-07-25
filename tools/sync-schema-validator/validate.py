"""T2.1 sync-schema validator — runs the §4.7 test matrix.

Exit code 0 = all scenarios pass. Non-zero = at least one mismatch.

Run from repo root:
    python tools/sync-schema-validator/validate.py
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Callable, List

# Make `engine` importable when run from repo root or from tool dir.
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from engine import (  # noqa: E402
    Approval,
    CostContribution,
    Grant,
    MemoryItem,
    PersonaPointer,
    envelope_compatible,
    merge_cost_counters,
    resolve_approval,
    resolve_grant,
    resolve_memory_item,
    resolve_persona_pointer,
)


# ---------- scenario harness ----------


@dataclass
class Scenario:
    name: str
    run: Callable[[], bool]


_RESULTS: List[tuple] = []


def assert_eq(label: str, got, expected) -> bool:
    ok = got == expected
    _RESULTS.append((label, ok, got, expected))
    return ok


# ---------- §4.7 scenarios ----------


def scenario_concurrent_memory_edit() -> bool:
    a = MemoryItem("m1", "edit-A", False, 5, "deviceA")
    b = MemoryItem("m1", "edit-B", False, 5, "deviceB")
    winner = resolve_memory_item(a, b)
    # Tiebreak: lexicographic device_id wins → deviceA.
    return assert_eq(
        "concurrent_memory_edit -> lexicographic deviceA wins",
        winner,
        a,
    )


def scenario_edit_vs_tombstone() -> bool:
    a = MemoryItem("m1", "edit-A", False, 5, "deviceA")
    b = MemoryItem("m1", "", True, 4, "deviceB")  # lower clock but tombstoned
    winner = resolve_memory_item(a, b)
    return assert_eq(
        "edit_vs_tombstone -> tombstone wins despite lower clock",
        winner,
        b,
    )


def scenario_double_tombstone() -> bool:
    a = MemoryItem("m1", "", True, 5, "deviceA")
    b = MemoryItem("m1", "", True, 7, "deviceB")
    winner = resolve_memory_item(a, b)
    return assert_eq(
        "double_tombstone -> idempotent, higher clock wins",
        winner,
        b,
    )


def scenario_grant_revoke_vs_extend() -> bool:
    a = Grant("g1", "browser.read", revoked=True, logical_clock=5, device_id="deviceA")
    b = Grant("g1", "browser.read", revoked=False, logical_clock=6, device_id="deviceB")
    winner = resolve_grant(a, b)
    return assert_eq(
        "grant_revoke_vs_extend -> revoke wins despite lower clock",
        winner,
        a,
    )


def scenario_approval_double_response() -> bool:
    a = Approval("t1", response="allow", logical_clock=5, device_id="deviceA")
    b = Approval("t1", response="deny", logical_clock=5, device_id="deviceB")
    winner, superseded = resolve_approval(a, b)
    ok1 = assert_eq("approval_double -> deviceA wins (lex)", winner, a)
    ok2 = assert_eq("approval_double -> deviceB superseded", superseded, "deviceB")
    return ok1 and ok2


def scenario_cost_counter_merge() -> bool:
    contribs = (
        CostContribution("deviceA", tokens=1000, cents=100),  # $1.00
        CostContribution("deviceB", tokens=2500, cents=250),  # $2.50
    )
    merged = merge_cost_counters(contribs)
    ok1 = assert_eq("cost_merge -> total_cents", merged.total_cents, 350)
    ok2 = assert_eq("cost_merge -> total_tokens", merged.total_tokens, 3500)
    return ok1 and ok2


def scenario_cost_counter_monotonic() -> bool:
    # deviceA reports twice; only the higher value should be kept.
    contribs = (
        CostContribution("deviceA", tokens=1000, cents=100),
        CostContribution("deviceA", tokens=500, cents=50),  # stale; should not regress
        CostContribution("deviceB", tokens=2000, cents=200),
    )
    merged = merge_cost_counters(contribs)
    ok1 = assert_eq("cost_monotonic -> total_cents", merged.total_cents, 300)
    ok2 = assert_eq("cost_monotonic -> total_tokens", merged.total_tokens, 3000)
    return ok1 and ok2


def scenario_cap_cross_by_sum() -> bool:
    contribs = (
        CostContribution("deviceA", tokens=0, cents=150),  # $1.50
        CostContribution("deviceB", tokens=0, cents=180),  # $1.80
    )
    merged = merge_cost_counters(contribs)
    cap_cents = 300
    cap_hit = merged.total_cents > cap_cents
    return assert_eq("cap_cross_by_sum -> cap hit", cap_hit, True)


def scenario_persona_swap_race() -> bool:
    a = PersonaPointer("marcus", logical_clock=5, device_id="deviceA")
    b = PersonaPointer("sara", logical_clock=5, device_id="deviceB")
    winner = resolve_persona_pointer(a, b)
    return assert_eq(
        "persona_swap_race -> lex deviceA wins",
        winner,
        a,
    )


def scenario_schema_version_mismatch() -> bool:
    return assert_eq(
        "schema_version_mismatch -> sync rejected",
        envelope_compatible(7, 6),
        False,
    )


def scenario_schema_version_match() -> bool:
    return assert_eq(
        "schema_version_match -> sync proceeds",
        envelope_compatible(7, 7),
        True,
    )


# ---------- runner ----------


SCENARIOS: List[Scenario] = [
    Scenario("concurrent_memory_edit", scenario_concurrent_memory_edit),
    Scenario("edit_vs_tombstone", scenario_edit_vs_tombstone),
    Scenario("double_tombstone", scenario_double_tombstone),
    Scenario("grant_revoke_vs_extend", scenario_grant_revoke_vs_extend),
    Scenario("approval_double_response", scenario_approval_double_response),
    Scenario("cost_counter_merge", scenario_cost_counter_merge),
    Scenario("cost_counter_monotonic", scenario_cost_counter_monotonic),
    Scenario("cap_cross_by_sum", scenario_cap_cross_by_sum),
    Scenario("persona_swap_race", scenario_persona_swap_race),
    Scenario("schema_version_mismatch", scenario_schema_version_mismatch),
    Scenario("schema_version_match", scenario_schema_version_match),
]


def main() -> int:
    print("T2.1 sync-schema-validator — running %d scenarios" % len(SCENARIOS))
    print("-" * 60)

    n_pass = 0
    n_fail = 0
    for s in SCENARIOS:
        ok = s.run()
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {s.name}")
        if ok:
            n_pass += 1
        else:
            n_fail += 1

    print("-" * 60)
    print("Assertion details:")
    for label, ok, got, expected in _RESULTS:
        if ok:
            print(f"  ok    {label}")
        else:
            print(f"  FAIL  {label}")
            print(f"        got      = {got!r}")
            print(f"        expected = {expected!r}")

    print("-" * 60)
    print(f"Scenarios: {n_pass} passed, {n_fail} failed")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
