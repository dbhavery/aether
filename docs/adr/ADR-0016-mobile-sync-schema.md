# ADR-0016: Mobile companion sync schema

- **Status:** **Accepted (full — body + 10 OQs).** Body accepted 2026-04-29; OQ-1 through OQ-10 accepted 2026-04-30 under Don's follow-up delegation ("1–5 are your decisions now"). Locked decisions captured in §10 of this ADR.
- **Date:** 2026-04-29 (drafted + body accepted), 2026-04-30 (OQs accepted).
- **Deciders:** Don (delegated to parallel-tracks coordinator). Body locked under doctrine §6 (single product) + body delegation; OQs locked under follow-up delegation 2026-04-30.
- **Supersedes:** nothing.
- **Superseded by:** nothing yet.
- **Related:**
  - `ARCHITECTURE.md` — the event surface this design extends and the primary store it extends additively.
  - `docs/adr/ADR-0004-durable-store-shape.md` — the durable store this design extends.
  - `docs/adr/ADR-0001-memory-domain-reconciliation.md` — memory is user-keyed (load-bearing for §3).
  - `docs/adr/ADR-0012-persona-delivery-download-on-demand.md` — one persona on disk; pack files do not sync.
  - Avatar runtime architecture — motion library + lip-sync are device-local.

## Context

Pro Phase 4 (browser + file workflow tools, T1.3) is about to commit the action-approval framework and audit-replay surfaces to a single-device shape. Sync decisions made *after* P4 lands cost a multi-layer migration. Made *before* P4 lands, they cost an extra column or two on tables already being designed.

Doctrine §6 retires the "ship a slice now, full product later" thesis: Companion ships once, complete. Mobile is therefore not a separate product — it is a *surface* of the same Companion. The desktop and the phone are the same agent, presented in two windows. Continuity across devices is a UX requirement (§4 — UX outranks implementation convenience), not a feature add-on.

Even if Don ultimately decides mobile never ships, the additive cost of reserving the schema is a few nullable columns. The cost of retrofitting later is months. This ADR locks the cheap-now / expensive-later tradeoff in favor of cheap-now.

## Decision

Adopt the mobile-sync architecture (T2.1). The lockable subset:

### 1. Topology — two-master with desktop as audit canonical

- Both desktop and mobile write locally. Neither is a thin client.
- The `policy_audit_log` chain has **one canonical instance** on desktop. Mobile keeps its own `mobile_audit.db` for offline integrity, then merges into desktop's chain via wrapping records on reconnect.
- L5's append-only invariants hold: the canonical chain is never forked.

### 2. Per-domain sync rules

| Surface | Behavior |
|---|---|
| `memory_items` (all six MemoryDomains per ADR-0001) | Bidirectional. LWW by Lamport clock. Tombstone precedence. |
| `memory_tombstones` | Bidirectional. Idempotent set-union semantics. |
| `policy_grants` | Bidirectional. Revoke-precedence; otherwise LWW by Lamport. |
| `policy_audit_log` | Mobile → desktop chain merge via wrapping records. Desktop is canonical. |
| `cost_counters` | PN-counter CRDT keyed by `device_id`; sums across devices. |
| `persona_profiles` (active pointer) | Single pointer, LWW by Lamport. Each device installs the pack independently per ADR-0012. |
| `approval_requests` | First-response-wins by Lamport. Losing device sees stale-prompt dismissal. |
| `interaction_sessions`, `routing_decisions`, `degraded_mode_events` | Append-only, device-tagged. Sync for history visibility, not for active-session migration. |
| `memory_embeddings_ref`, `compiled_persona_artifacts`, `byok_credentials_meta` (key material), persona pack files, in-flight turn state, media streams, viseme ticks | **Do not sync.** Each device runs locally. |

### 3. Schema additions are additive

Columns added to syncable mutable tables: `device_id`, `origin_seq`, `logical_clock`, `last_modified_at`, `tombstoned`. All have safe defaults; existing single-device installs remain valid.

New metadata tables: `sync_devices`, `sync_state`, `sync_outbox`, `cost_counter_contributions`. Detailed DDL in `T2.1_mobile_sync_schema.md` §3.

### 4. Identity / persona continuity

Per ADR-0012 + ADR-0001:
- The user's memory is one corpus across devices.
- The active persona is one pointer, synced.
- Each device downloads its own pack and compiles its own artifacts for its own hardware tier.
- Voice / face / motion library are device-local.

### 5. Transport

- LAN-first: mDNS discovery + long-lived TLS WebSocket directly between devices.
- Off-LAN relay deferred to a follow-on (open question §9 OQ-6 in the design doc).
- Pairing requires user-present consent on both devices (QR code + numeric confirmation).

### 6. Conflict-resolution validation

A synthetic event-stream validator at `tools/sync-schema-validator/` exercises the conflict-resolution rules (LWW, tombstone precedence, revoke precedence, first-response-wins, PN-counter convergence, etc.) on fixture inputs. Self-test gate per doctrine §8 — design changes that touch sync rules must run the validator green before reaching Don.

## Rationale

1. **Mobile cannot be a thin client.** Offline-with-no-laptop is a real use case; thin-client violates §4 (UX outranks implementation convenience).
2. **One global conflict-resolution rule is wrong.** Memory edits, grant revocation, cost summation, audit append, and approval responses have different semantics. Use the right tool per domain.
3. **Audit chain cannot fork.** L5's append-only HMAC chain is the legal record. Two divergent chains is unrecoverable. One chain with a merge protocol is solvable.
4. **Reserving schema is cheap; retrofitting is expensive.** Even if mobile never ships, the additive cost is negligible. If mobile ships in 18 months, the desktop is already wire-compatible.
5. **Doctrine §6 makes mobile a surface, not a product.** No mobile-only release. Mobile is the same Companion in another window.

## Consequences

### Positive

- P4 (T1.3 — browser + file workflow tools) can be designed sync-aware from the first commit. Approval rows, audit rows, and grant rows all carry `device_id` and `logical_clock` from day one.
- Memory domain reconciliation (T1.1, ADR-0001 follow-up) is unaffected — sync rules are domain-agnostic.
- Persona delivery (ADR-0012) holds without modification — pack files don't sync; the active-pointer does.
- Avatar runtime holds without modification — motion library + lip-sync are device-local.
- Cost-counter PN-CRDT prevents the "phone-while-offline burn the budget" failure mode.

### Negative / costs paid

- Every syncable mutable table grows by ~5 columns. Negligible disk; minor migration cost.
- Embedding re-derivation on receive doubles the embedding workload across two devices. Acceptable; embedding cost is the price of cross-device reach.
- Audit chain merge protocol is non-trivial to implement; budget ~2 weeks of L5 work when mobile ships.
- Mobile `mobile_audit.db` keeps growing as a forensic shard until pruned (open question §9 OQ-8). Mitigation: pruning rule deferred to follow-up.

### Trade-offs deliberately taken

- **No live cross-device session migration in v1.** Turns are atomic and device-local. Future work.
- **No off-LAN relay in v1.** LAN-first only. Most "phone with no laptop" cases are home/work LAN. Relay is a future feature.
- **Embeddings are device-local.** Each device runs its own embedding model and its own vector store. Sharing vectors would couple devices to one vendor; this design lets each device pick its own backend (open question in `sqlite_schema_pack.md` §11 OQ-1).

## Empirical Validation (deferred)

This ADR is design-only. Real validation arrives when:
1. The sync engine ships and round-trips a memory edit between two devices.
2. The audit chain merge protocol survives a corrupt-mobile-shard fault injection.
3. The PN-counter merge correctly accumulates spend across two simulated devices.
4. The synthetic-event-stream validator at `tools/sync-schema-validator/` runs green.
5. A real mobile app exists. (Currently no mobile app — this is the schema reservation.)

Until those checkpoints land, this ADR is the design contract for the work, not proof the work landed.

## Alternatives considered and rejected

- **Read-only mobile (thin client).** Rejected: fails offline UX (§4); re-creates WhatsApp Web UX problem; pushes every action through a network round-trip, undermining L1's timing contracts.
- **One global LWW rule across all surfaces.** Rejected: loses cost-counter sums; allows tombstones to be undone by stale edits; allows revokes to be undone by stale extensions.
- **One global CRDT (e.g. Automerge for everything).** Rejected: audit chain is fundamentally append-only and HMAC-chained, not CRDT-shaped; cost counters are a simple PN-counter, not justifying a heavyweight CRDT runtime; memory edits are infrequent enough that field-level merge is over-engineered.
- **Cloud-hosted "Companion sync."** Rejected: no central server in the threat model; relay is a dumb pipe (deferred), not a backend.

## Follow-ups

- T1.3 (Pro Phase 4 — browser + file workflow tools) integrates `device_id` + `logical_clock` columns from the first commit on approval / audit rows.
- T1.1 (MemoryDomain reconciliation) — once Don picks the option, update §3 of the design doc to reflect the final domain set. Sync rules are domain-agnostic; the enumeration may change.
- A follow-on ADR locks pairing UX (open question §9 OQ-7).
- A follow-on ADR locks the off-LAN relay protocol (open question §9 OQ-6) when Don decides to ship it.
- Coordinator-gated package proposals when mobile ships: `packages/sync-engine/`, `packages/device-identity/`, `apps/mobile/`.

## 10. Open questions — RESOLVED 2026-04-30

Per Don's follow-up delegation, the 10 OQs surfaced by the T2.1 design draft are locked at the recommended defaults. Summary:

| # | Decision | Rationale |
|---|---|---|
| OQ-1 | **Defensive design** with full schema reservation. Mobile may or may not ship; schema columns are nullable from day one so retrofit cost stays trivial. | Cheap-now / expensive-later tradeoff already locked by ADR body. |
| OQ-2 | **Live cross-device session migration is out-of-scope for v1.** Sessions are device-local; sync is for history visibility. | Scope discipline; revisit in v2 if user research demands it. |
| OQ-3 | **Soft toast + 5-second auto-dismiss** when a stale approval modal is invalidated by a winning approval on the other device. | Least-disruptive UX; no hard close. |
| OQ-4 | **Yes, add `cost_caps_local` per device.** Schema-side reservation now; implementation deferred. | Defensive; cheap to reserve. |
| OQ-5 | **5-minute persona-swap timeout** with `persona_swap_rollback` audit event. User retries on whichever device they're on. | Avoids ambiguous "did the swap commit?" state. |
| OQ-6 | **LAN-only transport in v1.** Off-LAN relay (companion.dbhavery.dev worker) is a v2 feature. | Most user cases are at home/work LAN. Relay adds infra cost + threat surface. |
| OQ-7 | **QR-code + numeric confirmation** device pairing. Desktop displays QR; phone scans + shows confirmation code; user reads code on desktop; both devices commit. Audit row on both. | Strong identity binding without typing 64-char hex. |
| OQ-8 | **Audit shard pruning after desktop confirms `audit_chain_head` includes mobile's last row + 30-day cooldown.** | Safe by default; never prunes before desktop has fully ingested. |
| OQ-9 | **Never auto-migrate desktop on a wire-breaking release while a still-supported mobile version exists.** Add `compatible_mobile_version` field to release metadata. | Avoids locking mobile-only users out of their own data. |
| OQ-10 | **This ADR is the locked surface.** `T2.1_mobile_sync_schema.md` is the rationale doc; updates to *decisions* go through new ADRs. | Standard ADR/rationale split. |

These resolutions move the T2.1 open questions from "deferred" to "accepted defaults"; this ADR is now the rationale source.

## References

- `ARCHITECTURE.md` — the event surface and store this design extends.
- `docs/adr/ADR-0001-memory-domain-reconciliation.md`
- `docs/adr/ADR-0004-durable-store-shape.md`
- `docs/adr/ADR-0012-persona-delivery-download-on-demand.md`
