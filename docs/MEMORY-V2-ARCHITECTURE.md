# Memory v2 — architecture reference

> **Status:** Current as of 2026-04-23.
> **Scope:** Evolution of the current session-memory kernel into a
> structured, user-visible memory system with clear retention rules,
> per-item trust provenance, and a UX that lets the user see and
> control what Companion remembers about them and their projects.
> **Out of scope for v2:** long-horizon autonomous memory curation
> (the assistant deciding on its own what to remember), vector
> search over the open web, cross-user memory, remote memory
> synchronization, and any "personality drift from memory" feature
> that re-tunes the persona pack.

This doc mirrors `docs/VISION-V1-ARCHITECTURE.md`,
`docs/VOICE-V1-ARCHITECTURE.md`, and
`docs/PRESENCE-V1-ARCHITECTURE.md` section by section. When Memory
v2 ships, this doc moves from "design-only" to "current" and a
rot-guard manifest is added under `tools/lint-memory-doc/`.

---

## 0. What "memory" is (and isn't) in Companion

Memory is everything Companion persists about the user's conversations
and projects beyond the current turn. It is NOT:

- a search engine over external documents,
- a RAG pipeline for arbitrary file systems,
- a durable log of raw media,
- a behavior model that re-weights the persona pack.

It IS:

- a structured store of conversation turns with role + timestamp,
- a set of **explicit "fact slots"** the user can populate (via
  conversation or the Settings UI) — "I'm Don", "I'm working on
  the `aether` repo", "always use Pacific time",
- a set of **project-scoped notes** that accumulate with the user's
  consent,
- retrieval primitives the turn engine uses to ground responses,
- a Trust/Audit surface so users can see, edit, and forget memory
  items individually or by class.

Memory v1 (the currently-shipped kernel) already carries turns and
a five-domain schema. Memory v2 hardens the contract, makes the
surface visible to the user, adds explicit consent gates around
persistence, and wires Trust/Audit properly.

### Design parity with Vision / Voice / Presence

| Aspect                | Vision V1           | Voice V1              | Presence V1          | Memory V2                                     |
| --------------------- | ------------------- | --------------------- | -------------------- | --------------------------------------------- |
| Capture model         | single frame        | single utterance      | window + idle signal | single turn (text) + explicit fact slots      |
| Consent model         | tri-state per-device | single tri-state     | Settings toggle      | **per-domain defaults + per-item controls**   |
| Payload persistence   | transient bytes     | transient bytes       | coarse transitions   | **durable text + embeddings (opt-in)**        |
| L5 audit              | per capture         | per utterance         | none                 | **per write + per read-at-retrieval**         |
| Retention             | N/A                 | N/A                   | bounded ring         | **per-domain TTL, user-controllable**          |
| User control surface  | Settings tri-state  | Settings tri-state    | Settings toggle      | **Settings + dedicated "Memory" drawer**      |

Memory is the only subsystem that both **persists** and **retrieves**,
so its audit posture is correspondingly the richest: both writes and
reads can be inspected after the fact.

---

## 1. Memory domains (v2 freeze)

Six domains, same vocabulary L2 already uses but with v2-locked
definitions and defaults. Each domain has its own retention
default, privacy class, and Trust-drawer lane.

| Domain          | Contains                                                  | Default retention | Privacy class  |
| --------------- | --------------------------------------------------------- | ----------------- | -------------- |
| **Session**     | Turn-by-turn conversation within one session              | until session end | standard       |
| **Durable**     | Recent conversation across sessions (rolling window)      | 30 days           | standard       |
| **Facts**       | Explicit user-provided facts ("my name is…", "I use…")   | until forgotten   | user-sensitive |
| **Projects**    | Named project scopes + associated notes / references      | until forgotten   | standard       |
| **Preferences** | Per-user tuning (timezone, style, interaction defaults)   | until forgotten   | standard       |
| **Artifacts**   | References to files, URLs, code snippets the user pinned  | until forgotten   | user-sensitive |

Domains NOT present in v2 (deferred):

- **Reflections** / "what Companion thinks about you" — out of scope;
  re-introducing any form of auto-inferred user model requires a
  separate design round.
- **Global web** — out of scope; no automatic web ingestion.

---

## 2. End-to-end flow

```
[user turn OR Settings UI write]
  │
  ▼
[MemoryKernel — packages/l2-memory/src/kernel.rs]
  │ classify item into a domain + privacy class
  │ apply per-domain write policy:
  │   - standard items write directly (current L5 gate already allows)
  │   - user-sensitive items require an explicit consent moment
  │ stamp provenance (source = conversation | settings | tool | import)
  │ assign MemoryId
  │
  ▼
[L5 policy gate]
  │ records AuditRecordEvent { capability: MemoryWrite, scope: <domain> }
  │ enforces domain-level risk class:
  │   standard -> Auto
  │   user-sensitive -> Ask (default)
  │
  ▼
[Storage]
  │ SQLite via DurableSessionStore for text + metadata
  │ (optional) embeddings for Durable / Projects / Artifacts
  │ NO raw media bytes — vision/voice payloads stay transient
  │
  ▼
[Retrieval path — turn engine calls MemoryKernel::recent_window]
  │ also gated by L5 (capability: MemoryRead, scope: <domain>)
  │ rate-limited + cached; retrieval audit rows are sampled, not
  │   per-call, to avoid drowning the History surface
  │
  ▼
[Trust drawer "Memory" tab]
  │ per-domain lanes, per-item rows with:
  │   timestamp · domain · privacy class · source · content preview
  │ actions: forget item | forget-all-in-domain | edit fact
```

Critical rule: **nothing from vision or voice payloads enters
memory as raw bytes.** A vision turn may produce a transcript line
like "Analyzed the current screen; saw a terminal running cargo
test" — that text is indistinguishable from any other assistant
turn in memory. The image itself is never stored. Same for audio.

---

## 3. `memory.json` contract

Path: `<app_data>/memory.json`. Contains the **user-owned
memory-system policy**, not the memory items themselves (those
live in SQLite).

Shape:

```json
{
  "retention_days": {
    "session": null,
    "durable": 30,
    "facts": null,
    "projects": null,
    "preferences": null,
    "artifacts": null
  },
  "default_risk": {
    "facts": "ask",
    "artifacts": "ask",
    "durable": "auto",
    "session": "auto",
    "preferences": "auto",
    "projects": "auto"
  },
  "embeddings": {
    "enabled": false,
    "provider": null
  }
}
```

Contract (identical shape to every other config):

- **Additive** — new domains or fields may be added.
- **Default-safe on read** — missing keys resolve to sensible
  defaults; unknown fields ignored; malformed JSON falls back to
  defaults with a WARN naming the path.
- **Unknown fields dropped on rewrite** — documented limitation.
- **Single-writer through `MemoryPolicyRegistry`** (new v2 type).
- **Atomic writes.**

`retention_days = null` means "keep until the user explicitly
forgets". A numeric value is a rolling TTL enforced by a background
sweep at boot and on a low-rate periodic tick.

`embeddings.enabled = false` by default — v2 ships without
auto-embedding. Turning it on requires picking a local embedding
provider (future step).

---

## 4. Consent and audit posture

### Writes

- **Standard-class domains** (Session, Durable, Preferences,
  Projects by default): write policy is `Auto`. L5 audit row is
  still produced (capability `MemoryWrite`, scope = domain), but
  no user prompt.
- **User-sensitive domains** (Facts, Artifacts by default): write
  policy is `Ask`. The shell surfaces the classic approval modal
  before the write lands. Audit row records the user's decision.

### Reads

The turn engine calls `MemoryKernel::recent_window` on every turn
to ground the model. Producing an audit row per read would drown
the Trust drawer. Instead:

- **Reads are audited by sampling** — one audit row per ~100
  reads per domain per session, plus one at the end of every
  retrieval-heavy operation (tool call that triggered a retrieval
  burst).
- **Per-session read counts are exposed** in the Memory tab so the
  user can see "256 Session reads, 12 Durable reads, 0 Facts
  reads this session".

Rationale: memory reads are not user-facing actions but they
aren't invisible either. Sampling + session counters is the middle
ground: the audit surface stays legible, and a user who wants to
see every read can export the full log via a dedicated Trust
drawer action.

---

## 5. Telemetry kinds (memory-related)

Memory emits exactly **six** kinds. All live under the existing
`TelemetryEntry` type used by vision and voice; the TS allow-list
(future: `apps/desktop/src/lib/memoryTurns.ts`) mirrors the list
and is unit-tested for parity.

| kind                  | when                                                   | in audit?         |
| --------------------- | ------------------------------------------------------ | ----------------- |
| `memory_written`      | item persisted                                         | yes (every write) |
| `memory_forgotten`    | user deleted item or retention sweep evicted it        | yes (every delete) |
| `memory_write_asked`  | user-sensitive write required approval and got it      | yes               |
| `memory_write_denied` | user-sensitive write required approval and was denied  | yes               |
| `memory_edited`       | user edited a fact item in place                       | yes               |
| `memory_retrieval`    | retrieval sample (every ~100th retrieval per domain)   | yes (sampled)     |

No raw content in telemetry — only `MemoryId`, domain, privacy
class, and (for retrieval) count. The Memory tab reads the
structured content directly from the SQLite store.

---

## 6. UI surfaces

All read from a future source-of-truth
(`apps/desktop/src/lib/memory.ts`).

| Surface                             | What it shows                                                                 |
| ----------------------------------- | ----------------------------------------------------------------------------- |
| `TrustDrawer` History tab           | existing turn history (unchanged)                                             |
| `TrustDrawer` **Memory tab (NEW)**  | per-domain lanes, per-item rows, forget/edit actions, retention indicators   |
| `TrustDrawer` Audit tab             | memory-related audit rows labelled with capability + scope                    |
| `Transcript` footer chip            | "This turn used 3 memory items" (collapsed), expandable to show ids           |
| `Settings` → Memory section (NEW)   | per-domain retention, per-domain default risk, embeddings enable, forget-all |

The "Memory tab" is the headline v2 surface. It's the place the
user goes when they want to know **what Companion knows about them**,
in a form that reads like notes, not logs.

---

## 7. Interaction with the other modalities

- **Vision v1** produces a textual description of what was seen.
  That description goes into Session (and may roll into Durable).
  The underlying image bytes never enter memory.
- **Voice v1** produces a transcript that becomes a normal user
  turn. The audio bytes never enter memory.
- **Presence v1** does NOT write to memory. Presence state is
  transient and bounded by design.
- **Projects domain** is the bridge between conversation and
  long-term context. When the user names a project explicitly
  ("let's work on `aether`"), subsequent durable writes get
  tagged with that project and can be retrieved as a coherent
  scope.

---

## 8. Hard constraints (operative for every Memory-v2 PR)

1. **No raw-media persistence.** Image bytes, audio bytes: never
   into memory.
2. **Additive config evolution.** `memory.json` fields must be
   default-safe on read AND tolerate being absent from a rewrite.
3. **User-sensitive domains default to Ask.** A future PR that
   flips Facts/Artifacts to Auto is a policy decision that must
   go through a design update.
4. **Retention sweeps run only at boot + low-rate background.**
   No per-turn retention enforcement — that's fragile and
   surprising.
5. **Embeddings are opt-in and local-only by default.** Remote
   embedding providers are their own track, scoped separately.
6. **Trust-drawer Memory tab is read + forget + edit, not write.**
   Users don't "author" memory through the Trust drawer; they
   author it through conversation or explicit Settings edits for
   preferences.
7. **No auto-summarization that rewrites memory.** Memory items
   are preserved verbatim; summaries live in a separate
   Reflections domain (not in v2).
8. **No cross-user memory.** One user per install, full stop.
9. **No L5 audit-event shape changes.** Memory v2 uses the
   existing `AuditRecordEvent` with new capability enums
   (`MemoryWrite`, `MemoryRead`, `MemoryForget`, `MemoryEdit`).
   Any new enum variants ship in L5 via an additive change,
   tested in L5 crates before any L2 code depends on them.

---

## 9. Open questions for future tracks

### Embeddings

- Which local embedding provider is the reference candidate?
  Locked in ADR-0003 (supersedes ADR-0002 Decision 1): **BGE-M3**
  via Ollama (`bge-m3:latest`).
  **Updated 2026-04-24:** ADR-0007 D7 reframes this as
  *tier-parameterised* — Spark uses `nomic-embed-text` (substitution
  for `bge-small-en-v1.5` per DECISIONS_LOG D-001), Flame and Forge
  use `bge-m3`. See `docs/adr/ADR-0007-embeddings-onboarding.md`.
  **Updated 2026-04-25:** the original `bge-small-en-v1.5` is now
  loadable via the HuggingFace provider (`hf:BAAI/bge-small-en-v1.5`,
  see `docs/HF_EMBEDDER.md` and DECISIONS_LOG D-014). The
  `nomic-embed-text` substitution remains the zero-dependency
  default; users who install `sentence-transformers` may opt back
  into the original ADR-0007 D7 model.
- **Input sanitization (added 2026-04-25, DECISIONS_LOG D-016).**
  All embedding input is sanitized to strip the U+FFFD REPLACEMENT
  CHARACTER before reaching the embedding provider, replaced with
  ASCII space. bge-m3 over Ollama returns NaN-vector embeddings for
  inputs containing U+FFFD (Phase 3A surfaced this on 6 of 848
  synthetic-corpus rows; cosine over a NaN vector is NaN and
  silently breaks retrieval ranking). Sanitization is implemented
  as a default method on `EmbeddingProvider::embed` so every
  present and future provider (Ollama, Stub, Hf, future
  candle-native) inherits it without per-impl boilerplate. Scope
  intentionally limited to U+FFFD — other zero-width / noncharacter
  codepoints are not stripped without a demonstrated failure.
- Vector index backend — SQLite + rusqlite extensions? A separate
  sqlite-vec file? Out of scope for design-only doc; decide at
  implementation time.

### Embedding backfill (added 2026-04-24)

When `embeddings.enabled` flips to `true` on a profile that already
has Durable / Projects / Artifacts content, those rows lack
embedding rows and are invisible to retrieval. The backfill
orchestrator (`apps/desktop/src-tauri/src/backfill.rs`,
ADR-0007 D5) walks every embed-eligible domain and re-embeds each
row.

Today's behaviour:
- User-initiated only (button in Trust drawer Retrieval tab).
- Synchronous Tauri command — blocks the IPC thread for the
  duration. Acceptable for personal scale (<1000 rows on bge-m3 ≈
  3 min; on nomic-embed-text ≈ 27 sec — measured on Don's 3090 Ti
  workstation 2026-04-24).
- Skip-already-embedded fast path (added 2026-04-25): the worker
  asks `EmbeddingStore::embedded_ids(domain)` for the set of memory
  ids already vectorised, then skips matching rows during the walk.
  Skipped rows count into `BackfillProgress::skipped_already_embedded`
  rather than `completed`, so the UI can render "skipped X" without
  inflating the indexed count. Stores that don't override the trait
  default return an empty set; the worker falls back to brute-force
  re-embed (`upsert` is idempotent — strictly safe, just wasteful).
- Per-row pacing pause (default 50 ms) defends against the rapid-
  fire Ollama HTTP 500 surfaced in validation Block 9. The skip
  path bypasses pacing — there's no embed call to throttle.
- Cancel via shared atomic; observed at every row boundary,
  including during the skip walk.
- L5 `Capability::RetrievalContext` gated.

### Project boundaries

- How is a project "opened" conversationally — by the user naming
  it explicitly, or also by pattern matching on paths / URLs? v2
  lands with explicit-only; pattern matching is a later polish
  pass.

### Forget semantics

- Hard forget vs soft forget (tombstone). v2 uses hard forget:
  the row is deleted, the forget telemetry event is kept. A
  "restore last forget" undo is a later UX polish.

### Cross-device sync

- Out of scope for v2. A future track may let the user sync
  memory between two of their own Companion installs over a private
  channel; that's a new capability with its own design doc.

### L3 presence × memory retention

- Should memory retention be aware of presence (e.g. pause TTL
  sweeps when the user is away)? Probably not; TTLs are user
  intent, not activity-dependent. Revisit if telemetry shows
  churn.

---

## 10. Implementation sequencing (recommended)

When Memory v2 moves from design to build, land in this order.
Each step is a session of work.

1. ✅ **L5 capability additions.** Added `MemoryWrite`, `MemoryRead`,
   `MemoryForget`, `MemoryEdit` to the `Capability` enum behind
   additive, L5-first tests. No L2 consumers yet.
2. ✅ **Memory policy surface.** `memory.json`, `MemoryPolicyRegistry`,
   Settings UI section, Tauri commands for policy read/write.
3. ✅ **Per-domain write/read plumbing.** Wired the new capabilities
   into L2's existing write/read paths; user-sensitive domains
   route through the Ask flow.
4. ✅ **Memory tab in Trust drawer.** Read + forget + edit UI. Per-
   item retention indicators. Forget-all-in-domain action.
5. ✅ **Retention sweep.** Boot-time pass + hourly background tick
   (`RETENTION_SWEEP_INTERVAL_MS` = 1 hour, `apps/desktop/src-tauri/src/main.rs`).
   Iterates every domain in `AppState::DOMAINS_WITH_STORE` and
   evicts rows older than `MemoryConfig::retention_for(domain)` via
   `SessionMemoryStore::prune_before` on the correct lane
   (resolved via `AppState::memory_for_domain`). Emits one
   aggregated `memory_forgotten` telemetry row per domain that
   evicted ≥1 row, and one L5 audit row per sweep invocation via
   `MemoryForget`.
   **Coverage post-ADR-0004 (2026-04-24):** Session +
   **Durable**. Remaining four domains (Facts / Projects /
   Preferences / Artifacts) persist their retention policies in
   `memory.json` but are trace-skipped; ADR-0005 closes that gap.
   `run_retention_sweep` is in `memory_service.rs`.
6. ✅ **Embeddings (opt-in).** Behind the `embeddings` cargo
   feature on `aether-l2-memory`. Default provider: Ollama
   `bge-m3` (ADR-0003 supersedes ADR-0002 Decision 1; other
   ADR-0002 decisions — trait shape, flat-file store, capability,
   domain eligibility — unchanged).
   `memory.json::embeddings.enabled` defaults to `false`; when
   on, Durable/Projects/Artifacts writes produce an embedding
   via `maybe_embed_on_write` (best-effort; provider failure
   does not block the primary write). L5 audits via the new
   `MemoryEmbed` capability. Telemetry kind `memory_embedded`.
   See `packages/l2-memory/src/embeddings.rs`.
7. ✅ **Rot guard.** `tools/lint-memory-doc/` mirrors the
   vision / voice / presence / quality rot guards. 60 anchors
   across 12 files; this doc flipped to "Current" in the same
   change.
8. ✅ **Retrieval wiring (ADR-0005, Milestone 2 Run 2).** The
   turn pipeline now consults embeddings during real turns when
   `memory.json::embeddings.enabled = true`. Flow:
   `submit_turn` → `run_retrieval_context` (embed → query_nearest
   → fetch_one → rank, 5-second wall-clock bailout) →
   `format_retrieval_block` → `augment_utterance` → the router
   forwards the augmented string to the provider. Top-K is
   configurable via the new `memory.json::retrieval.max_items`
   field (default 5; `0` disables injection without flipping
   embeddings off). The original user text is preserved through
   a parallel channel (`user_record_raw`,
   `PendingTurn::original_utterance`) so memory records and the
   transcript never drift from what the user actually typed. L5
   gate: `Capability::RetrievalContext` — one audit row per
   retrieval invocation, even when embeddings are off. See
   `apps/desktop/src-tauri/src/retrieval.rs` and
   `docs/adr/ADR-0005-retrieval-wiring.md`.

   **Audit-row schema v2 (ADR-0009, Accepted 2026-04-25, commit
   `b577105`).** ADR-0005 left `TurnRequest` with a single
   `utterance` field carrying the augmented string, which then
   reached the L5 audit row. ADR-0009 cleaned that up:
   `TurnRequest` now carries `original_utterance` (audit truth —
   what the user typed) and `model_input_utterance`
   (reproducibility truth — what the router saw). The L5
   `AuditRecordEvent` is bumped to `schema_version = 2` and
   gains optional `original_utterance: Option<String>` plus
   `retrieval_provenance: Option<RetrievalProvenance>` fields;
   pre-2026-04-25 rows on disk deserialize implicitly as v1 via
   `serde(default)`. The frontend `AuditRow` component renders
   v1 with a "pre-ADR-0009" schema badge and v2 with the user's
   text as the headline plus a collapsed retrieval-summary
   disclosure. See `docs/adr/ADR-0009-retrieval-augmented-utterance-audit-reach.md`
   (decision D-001).

---

## 11. How this doc stays honest

`tools/lint-memory-doc/check.py` carries an anchor manifest tying
this doc to concrete files, symbols, and string constants across
`packages/l2-memory`, `packages/l5-policy`,
`apps/desktop/src-tauri`, and the frontend Trust / Settings
drawers. When code and doc diverge — a rename, a deletion, a typo
— the linter fails. The manifest and this doc MUST be updated in
the same PR when anchors change.

Rot guards verify doc/code consistency only. Behavioural
correctness lives in the Rust unit tests (`cargo test -p
aether-l2-memory --features embeddings`, `-p aether-l5-policy`,
shell `cargo test --all-features`) and the Vitest component
tests. Per `docs/GLOSSARY.md` §6, rot guards and acceptance
criteria are deliberately distinct surfaces.

---

## 12. Reference

- `docs/VISION-V1-ARCHITECTURE.md` — permission + telemetry pattern.
- `docs/VOICE-V1-ARCHITECTURE.md` — sibling track.
- `docs/PRESENCE-V1-ARCHITECTURE.md` — sibling track; the "observation
  vs policy-gated action" distinction is shared.
- `packages/l2-memory/src/` — existing L2 code: `kernel.rs`,
  `session.rs`, `sqlite_session.rs`. v2 extends rather than
  replaces.
- `docs/adr/ADR-0001-memory-domain-reconciliation.md` —
  the memory-domain decision record; this doc supersedes the
  earlier planning-phase references for v2.
- `tools/lint-vision-doc/check.py` — rot-guard shape to copy for
  Memory V2 step 7.
