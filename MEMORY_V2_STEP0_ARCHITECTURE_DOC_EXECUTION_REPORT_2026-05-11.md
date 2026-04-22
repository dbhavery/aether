# Memory V2 Step 0 — architecture doc (design only) — execution report (2026-05-11)

**Status:** Shipped locally on `dev`. Push not authorized.
**Scope:** Documentation only. No code.

## Goal

Kick off the Memory V2 track with a design-only architecture doc
that builds on the existing L2 kernel and freezes the v2-lock
contract: six memory domains, per-domain retention + consent,
explicit write/read audit, a dedicated Trust-drawer "Memory" tab,
and a rule that raw media bytes never enter memory.

## Surfaces touched

- `docs/MEMORY-V2-ARCHITECTURE.md` (new, ~330 lines).

## Design decisions captured

### Scope — what memory is and isn't

- **IS:** structured store of conversation turns + explicit fact
  slots + project notes + retrieval primitives + Trust/Audit
  surface.
- **IS NOT:** RAG over open web, durable log of raw media, behavior
  model that retunes the persona, autonomous curation system.

### Six domains locked in v2

| Domain      | Default retention       | Default risk |
| ----------- | ----------------------- | ------------ |
| Session     | until session end       | Auto         |
| Durable     | 30-day rolling window   | Auto         |
| Facts       | until explicitly forgotten | Ask       |
| Projects    | until forgotten         | Auto         |
| Preferences | until forgotten         | Auto         |
| Artifacts   | until forgotten         | Ask          |

**Deferred:** Reflections domain (auto-inferred user model) and a
Global-web domain — both require their own design rounds.

### Audit posture — richest of all modalities

Memory both persists AND retrieves, so its audit surface covers
both sides:

- **Writes:** one audit row per write. Standard-class domains
  auto-allow; user-sensitive domains (Facts, Artifacts) default to
  Ask with a classic approval modal.
- **Reads:** **sampled audit, every ~100 per domain per session**.
  Per-session read counts exposed in the Memory tab so the user
  can see retrieval volume at a glance.

Rationale: a per-read audit row would drown the Trust drawer; a
fully-silent read path would hide behavior. Sampling + counters is
the middle.

### Six telemetry kinds

`memory_written`, `memory_forgotten`, `memory_write_asked`,
`memory_write_denied`, `memory_edited`, `memory_retrieval`
(sampled). No raw content in telemetry — only `MemoryId`, domain,
privacy class, and counts.

### No raw-media persistence — hard rule

Vision v1 transcripts become memory items ("Analyzed the current
screen; saw..."). Voice v1 transcribed text becomes a user turn.
The underlying image / audio bytes NEVER enter memory. Enforced by
the existing transient-payload contract on both sides; Memory v2
restates it because it's the constraint most likely to drift.

### `memory.json` contract

Per-domain retention (null = keep forever), per-domain default
risk, embeddings disabled by default. Same additive-default-safe
shape as every other config.

### Memory tab — the headline v2 surface

The Trust drawer gains a new "Memory" tab with per-domain lanes,
per-item rows, forget/edit actions, retention indicators. This is
the place the user goes when they want to know **what Aether knows
about them**, in a form that reads like notes, not logs.

## Seven-step implementation sequencing captured in §10

1. L5 capability additions (`MemoryWrite`, `MemoryRead`,
   `MemoryForget`, `MemoryEdit`) — additive, L5-first, tested
   before any L2 consumer.
2. Memory policy surface (`memory.json`, `MemoryPolicyRegistry`,
   Settings UI, Tauri commands).
3. Per-domain write/read plumbing in L2.
4. Memory tab in Trust drawer.
5. Retention sweep at boot + low-rate background tick.
6. Embeddings (opt-in), local-only by default.
7. Rot guard (`tools/lint-memory-doc/`), flip doc to "current".

## Hard-constraint compliance

- No code change.
- No new commands.
- No new capabilities yet (additions planned for step 1).
- No L5 `AuditRecordEvent` shape changes — only new capability
  enum variants, added additively in step 1.
- No mic / voice / vision runtime work.
- No new dependencies.

## Tests

Docs-only. Focused checks:

- `cargo fmt --all -- --check` — clean
- `python tools/lint-layer-boundaries/check.py` — 0 violations
- `python tools/lint-vision-doc/check.py` — OK

## Parity with Vision / Voice / Presence patterns

- Additive-default-safe config: yes.
- Telemetry list locked at doc-level, expected TS parity: yes.
- Raw-payload transience: yes.
- Per-domain audit: yes (stronger than vision/voice, which audit
  per capture).
- Consent surface: **per-domain default risk + per-item controls**
  — more granular than the vision/voice tri-state because memory
  has more shapes of "sensitive".

## What is deliberately NOT in this slice

- No L5 capability additions — step 1.
- No `memory.json` — step 2.
- No Memory tab UI — step 4.
- No retention sweep — step 5.
- No embedding pipeline — step 6.
- No rot guard — step 7.

## Open questions parked for later

- Which local embedding provider is the reference candidate
  (`bge-small`? `nomic-embed-text`?). Lock in step 6.
- Vector index backend — SQLite extension, sqlite-vec, or a
  separate file? Decide at implementation time.
- Project boundary detection — explicit-only in v2; pattern
  matching a later polish pass.
- Forget semantics — v2 uses hard forget. A "restore last forget"
  undo is deferred.

## Deliberate deferrals flagged in §9

- Cross-device memory sync — new capability, own doc.
- Reflections domain (auto-inferred user model) — new design round.
- Presence-aware retention — probably not desirable; revisit if
  telemetry shows churn.
