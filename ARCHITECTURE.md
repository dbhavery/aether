# Aether — Architecture

Aether is an AI companion that runs on your machine. It has one architectural invariant: **every action that touches the world first clears a policy gate.** No exceptions, no fast paths, no "admin mode." The gate is the ground floor. Everything else grows on top of it.

This document explains how the ground floor was built and what sits on it.

---

## The thesis

Most AI assistants assume the language model is the product. Aether doesn't. The model is a service. The *relationship* — memory, presence, trust, timing — is the product. Policy is what keeps the relationship intact over years of use.

Three commitments follow from that:

- **Local-first.** Your data, your memory, your persona state live on your machine. Remote calls are deliberate and visible.
- **Policy is load-bearing.** Grants, audit, degraded modes, cost caps, BYOK — all enforced by one engine that nothing else can reach around.
- **Companion, not chatbot.** Long-lived relationship. Not single-session Q&A.

Those commitments shape every other choice below.

---

## The seven layers

Aether is organized into seven independent engines, each with an explicit contract. Nothing is a god object. Nothing is optional. The table reads top to bottom; the call arrow goes the other way.

| Layer | Name | Owns |
|-------|------|------|
| L1 | Interaction | Turn FSM, reflex classifier, STT/TTS, timing budgets |
| L2 | Memory | Local memory kernel, embeddings, provenance tags |
| L3 | Presence | Avatar scheduler, behavior frames, rendering surface |
| L4 | Router | Model and tool router, 7-tier tier abstraction, provider adapters |
| L5 | **Policy** | Authorization gate, audit log, grants, BYOK accounting |
| L6 | Persona | YAML/profile → compiled artifacts (prompts, voice, stance) |
| L7 | Trust UX | Onboarding, approvals, posture banners, incident UX |

Shared infrastructure (`event-bus`, `storage`, `telemetry`, `media-engine`) sits underneath. Sibling engines do not import each other; they coordinate through typed contracts and the event bus. Every side-effectful call routes through L5.

The layer boundary is enforced by a linter that runs in CI (`tools/lint-layer-boundaries/`). A PR that adds a forbidden edge cannot merge.

---

## One turn, end to end

Here is what happens when a user says something to Aether:

```
user utterance
      │
      ▼
 ┌────────────┐
 │  L1 turn   │  Idle → AwaitingPolicyApproval
 │  FSM       │
 └──────┬─────┘
        │  ActionRequest { capability, resource, persona, … }
        ▼
 ┌────────────┐
 │  L5 policy │  5-stage evaluator:
 │  engine    │    1. pre-gates (degraded mode? hardcoded block?)
 │            │    2. feature    (capability in active preset?)
 │            │    3. mode       (Deny / DraftOnly short-circuit)
 │            │    4. resource   (does a grant cover this scope?)
 │            │    5. duration   (issue or reuse, Once / Task / Session)
 │            │
 │            │  Every Allow writes an audit row BEFORE returning.
 │            │  The row is hash-chained and HMAC-sealed.
 └──────┬─────┘
        │  Decision::{Allow | Ask | Deny | DraftOnly | NeedsUpgrade}
        ▼
 ┌────────────┐     ┌────────────┐
 │  L1 branch │ ──► │  L4 router │  tier = persona.preferred_tier
 │  on        │     │  adapter   │  (reflex / local-* / remote-*)
 │  Decision  │     └──────┬─────┘
 └──────┬─────┘            │
        │                  ▼
        │           provider response
        │                  │
        ▼                  ▼
    TurnResult  ◄─  RouteOutcome
```

The L1 turn state machine has 19 canonical states. The current vertical slice uses five of them. Every transition is monotonic per `turn_id` and carries a `change_id`, a monotonic `seq`, and a `source_layer` tag. You can reconstruct any past turn by reading the audit log.

---

## The policy gate

L5 is the part of Aether that would be boring in any other system and is load-bearing here.

A policy decision is a typed value, not a boolean:

```rust
pub enum Decision {
    Allow       { grant_ref, audit_id },
    Ask         { ticket, audit_id },
    DraftOnly   { source, audit_id, reason },
    Deny        { reason, audit_id },
    NeedsUpgrade{ capability_path, audit_id, suggested_preset },
}
```

Five decisions cover the space. `Allow` means the caller may proceed. `Ask` means a human approval ticket was issued and the caller must wait. `DraftOnly` means produce the draft but do not commit side effects. `Deny` means refuse with a typed reason. `NeedsUpgrade` means the capability exists at a higher preset the user hasn't enabled.

Every one of those decisions carries an `audit_id`. The audit row is written synchronously, *before* the decision returns. If the audit write fails, the decision becomes `Deny { reason: AuditWriteFailed }`. Deny-by-default is the degraded posture; a broken audit log cannot silently authorize anything.

### The five stages

An `ActionRequest` walks five stages in order. Any stage may short-circuit.

1. **Pre-gates.** Degraded modes (`SafeMode`, `AuditBroken`, `LedgerCorrupt`, `MinimumTrust`) deny everything. Hardcoded blocks (e.g. `rm -rf /`) reject at the door.
2. **Feature.** Is this capability in the currently active preset? If not, return `NeedsUpgrade` pointing at a preset that would enable it.
3. **Action/resource.** Does an existing grant cover `(capability, resource, persona)`? If yes, reuse.
4. **Mode.** The capability's approval mode (`Auto`, `Ask`, `TaskScoped`, `Deny`, `DraftOnly`) decides what happens when no grant covers.
5. **Duration.** Grants get `Once`, `TaskScoped(TaskId)`, `Session`, or `Persistent { ttl }`. TTL expiry is one of the eight locked re-evaluation triggers.

### Grants

A grant authorizes a `(capability, resource_pattern, persona, duration)` tuple. Once issued, subsequent `evaluate` calls whose request falls inside the grant's pattern return `Allow` without re-running all five stages — **unless** one of the eight locked re-evaluation triggers fires:

`CapabilityDiffers`, `ResourceOutsidePattern`, `PersonaSwapped`, `RemoteEscalationUncovered`, `ProvenanceElevated`, `CostThresholdHit`, `GrantOrEmergencyRevoked`, `TtlExpired`.

Those triggers are not a loose guideline. They are enumerated, each produces a re-evaluation, and each has a test.

### The audit chain

`policy_audit_log` is append-only by SQL trigger. Every row stores:

- `prev_hash` — the prior row's event hash (genesis constant for row 1).
- `event_hash` — SHA-256 of `(prev_hash || canonical_payload)`.
- `record_hmac` — HMAC-SHA256 over `event_hash` with a per-install key.
- `key_id` — which key signed this row.

A singleton `policy_audit_chain_head` points at the current tip. `SqliteAuditStore::verify_chain` walks the log in insertion order, recomputes every hash and HMAC, compares the final computed tip to the stored head, and returns a typed error naming the first offending row on mismatch.

What this catches: local DB mutation (editing a payload), row splicing (inserting or deleting in the middle), chain-tip rollback. What it does not catch: key compromise (a future wave adds OS-keyring integration), host-level compromise, or third-party attestation (a future wave adds asymmetric checkpoint signatures).

The key lives in the `AETHER_AUDIT_HMAC_KEY_HEX` environment variable if set, otherwise in a 32-byte file at `<db>.hmac.key` generated by `OsRng` on first run. This is preview-grade key management. It is documented as such.

---

## Persona, compiled

L6 turns a small typed profile — name, description, tone, verbosity, stance, humor — into seven downstream artifacts:

- `CompiledPrompts` — system prompt + reflex templates.
- `CompiledRoutingRules` — preferred and maximum router tier.
- `CompiledBehaviorMap` — intensities for focus, warmth, playfulness, caution (consumed by L3).
- `CompiledMemoryHints` — salience weights (consumed by L2).
- `CompiledToolAllowList` — a *hint*; L5 still decides.
- `CompiledVoiceConfig` — voice id, speaking rate.
- `PersonaCompiledPolicyDefaults` — proposed per-capability approval modes that L5 merges under its preset precedence.

Compilation is deterministic. Same profile in, structurally identical `CompiledPersona` out. No model calls. Rules are `match` statements you can read in one sitting.

Crucially, the compiled persona proposes policy; it does not decide policy. Every generated system prompt carries the line *"all side-effectful actions require L5 authorization. You do not bypass that gate."* Persona is not an escape hatch.

---

## The router

L4 maps a seven-tier abstraction onto concrete provider adapters.

```
Reflex           ── templated reply, no LLM
LocalTiny        ── smallest local model
LocalSmall       ── balanced local model
LocalFull        ── full-size local model
RemoteStandard   ── frontier provider, default tier
RemotePremium    ── frontier provider, premium
RemoteDeepResearch── long-horizon frontier
```

Tier selection is data. A compiled persona declares `preferred_tier` and `max_tier`. The L1→L4 adapter reads those at construction time. Changing a persona from `Cautious` to `Bold` shifts the demo from `local-full` to `remote-standard` without a recompile of L1 or L4.

Remote escalation is one of the eight re-evaluation triggers. If a turn starts local and the router later wants to escalate, L5 re-evaluates under the remote tier — including the privacy-posture gate that blocks private-tagged context from crossing to a remote provider without explicit waiver.

---

## What this costs

Architecture has a price. Aether's is:

- **Every action is slower by one synchronous policy evaluate and one synchronous audit write.** Wave 3 measured the evaluator at sub-millisecond on in-memory backends. SQLite-backed mode adds storage-bound latency.
- **Grants accumulate.** A long session with a Bold persona generates many session-scoped grants. Revoke, TTL, and persona-swap each clear them, but the steady-state ledger is larger than a "just call the tool" design.
- **A broken audit log takes the system down.** Deny-by-default is correct but it is also unforgiving. Operations needs to treat `verify_chain` failure as a paging event.
- **Every new capability is a schema change.** Capabilities are typed enums, not strings. Adding one means editing `Capability` in `l5-policy`, adding preset defaults, writing tests, and — if it is side-effectful — a hardcoded block entry. Deliberate friction.

None of these are bugs. They are the shape of a system that takes authorization seriously.

---

## What Aether is not

Stated plainly so expectations calibrate:

- Not a chatbot UI.
- Not a plugin framework for LLMs.
- Not a LangChain competitor. Chains are a runtime concept; Aether is a layered architecture.
- Not a hosted service.
- Not ready to use. The OSS preview ships the spine and the first real slice of L5. Almost everything user-facing is not.

If you want a runnable assistant today, this is the wrong project. If you want to shape how a local-first companion should be built, you are welcome.

---

## Reading order

Start here, in this order:

1. This document — the seven-layer architecture and the non-bypassable gate. Sits above everything else.
2. `docs/PRODUCT-PLAN.md` — hard rules for the product family.
3. `docs/ARCHITECTURE-V2.md` — how the layers fit, expanded from this overview.
4. `packages/l5-policy/src/lib.rs` → `engine.rs` → `tests/engine_slice.rs` — the richest code in the repo.
5. `packages/l5-policy/src/audit_seal.rs` — the audit chain + HMAC implementation.
6. `apps/l1-cli/src/main.rs` — the working end-to-end demo.
7. The wave execution reports — honest accounts of what landed, with deferrals named.

`docs/REPO_TOUR.md` is a fifteen-minute guided walk if you prefer a narrated path.

---

## Provenance

The design predates the code by several months. Every architectural decision — the seven layers, the non-bypassable gate, the 19-state turn FSM, the eight re-evaluation triggers, the `Decision` variants — was argued and locked before a line of Rust was written, and the resulting decisions are captured in this document and the ADR log under `docs/adr/`. Those are the authoritative reference when the code and the docs disagree.

If something in the code contradicts this document, trust the code and file an issue. If the code looks buggy, trust the doctrine and file an issue.

---

**License:** MIT. **Author:** Donald Havery. **Contact:** see `SUPPORT.md`.
