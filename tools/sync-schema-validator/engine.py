"""Conflict-resolution rule implementations for T2.1 mobile sync schema.

Pure-functional. No I/O. No external deps. Stdlib only.

Each function takes "states" (dataclass-shaped dicts) from two devices
and returns the post-merge state. Rules per
`docs/adr/ADR-0016-mobile-sync-schema.md`.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, Optional, Tuple


# ---------- shared types ----------


@dataclass(frozen=True)
class MemoryItem:
    item_id: str
    content: str
    tombstoned: bool
    logical_clock: int
    device_id: str


@dataclass(frozen=True)
class Grant:
    grant_id: str
    capability: str
    revoked: bool
    logical_clock: int
    device_id: str


@dataclass(frozen=True)
class Approval:
    ticket_id: str
    response: Optional[str]  # "allow" | "deny" | None
    logical_clock: int
    device_id: str


@dataclass(frozen=True)
class CostContribution:
    device_id: str
    tokens: int
    cents: int


@dataclass(frozen=True)
class PersonaPointer:
    persona_id: str
    logical_clock: int
    device_id: str


# ---------- §4.1: memory_items — LWW by Lamport, tombstone precedence ----------


def resolve_memory_item(a: MemoryItem, b: MemoryItem) -> MemoryItem:
    if a.item_id != b.item_id:
        raise ValueError("resolve_memory_item: differing item_id")

    # Rule 1: tombstone wins.
    if a.tombstoned and not b.tombstoned:
        return a
    if b.tombstoned and not a.tombstoned:
        return b
    # Both tombstoned or neither tombstoned → continue.

    # Rule 2: higher logical_clock wins.
    if a.logical_clock > b.logical_clock:
        return a
    if b.logical_clock > a.logical_clock:
        return b

    # Rule 3: tiebreak — lexicographic device_id.
    return a if a.device_id < b.device_id else b


# ---------- §4.2: policy_grants — revoke precedence; else LWW ----------


def resolve_grant(a: Grant, b: Grant) -> Grant:
    if a.grant_id != b.grant_id:
        raise ValueError("resolve_grant: differing grant_id")

    if a.revoked and not b.revoked:
        return a
    if b.revoked and not a.revoked:
        return b

    if a.logical_clock > b.logical_clock:
        return a
    if b.logical_clock > a.logical_clock:
        return b

    return a if a.device_id < b.device_id else b


# ---------- §4.3: approval_requests — first-response-wins by Lamport ----------


def resolve_approval(a: Approval, b: Approval) -> Tuple[Approval, Optional[str]]:
    """Return (winner, superseded_device_id_or_None)."""
    if a.ticket_id != b.ticket_id:
        raise ValueError("resolve_approval: differing ticket_id")

    if a.response is None and b.response is None:
        # Neither responded; arbitrary winner, no supersede.
        return (a, None) if a.device_id <= b.device_id else (b, None)
    if a.response is not None and b.response is None:
        return a, None
    if b.response is not None and a.response is None:
        return b, None

    # Both responded. Earlier Lamport wins; tiebreak lexicographic.
    if a.logical_clock < b.logical_clock:
        return a, b.device_id
    if b.logical_clock < a.logical_clock:
        return b, a.device_id

    if a.device_id < b.device_id:
        return a, b.device_id
    return b, a.device_id


# ---------- §4.4: cost_counters — PN-counter CRDT (sum across devices) ----------


@dataclass(frozen=True)
class MergedCost:
    total_tokens: int
    total_cents: int
    per_device: Tuple[CostContribution, ...]


def merge_cost_counters(
    contributions: Tuple[CostContribution, ...],
) -> MergedCost:
    """Per device_id, take the highest contribution (PN-counter monotonic).

    Two devices each report their own running totals; the merged view is
    the sum. Within a single device, the highest reported total wins
    (monotonic counter — never goes backward).
    """
    by_device: Dict[str, CostContribution] = {}
    for c in contributions:
        prev = by_device.get(c.device_id)
        if prev is None:
            by_device[c.device_id] = c
        else:
            # Monotonic per device.
            by_device[c.device_id] = CostContribution(
                device_id=c.device_id,
                tokens=max(prev.tokens, c.tokens),
                cents=max(prev.cents, c.cents),
            )

    total_tokens = sum(c.tokens for c in by_device.values())
    total_cents = sum(c.cents for c in by_device.values())

    return MergedCost(
        total_tokens=total_tokens,
        total_cents=total_cents,
        per_device=tuple(sorted(by_device.values(), key=lambda c: c.device_id)),
    )


# ---------- §4.5: persona pointer — LWW by Lamport ----------


def resolve_persona_pointer(a: PersonaPointer, b: PersonaPointer) -> PersonaPointer:
    if a.logical_clock > b.logical_clock:
        return a
    if b.logical_clock > a.logical_clock:
        return b
    return a if a.device_id < b.device_id else b


# ---------- envelope schema-version handshake (§6.4) ----------


def envelope_compatible(local_version: int, peer_version: int) -> bool:
    """Sync only proceeds when both sides are at the same schema_version."""
    return local_version == peer_version
