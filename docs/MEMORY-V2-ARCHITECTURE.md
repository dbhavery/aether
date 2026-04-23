# Memory v2 — architecture reference

> **Status:** Current as of 2026-04-23.
> **Scope:** Evolution of the current session-memory kernel into a
> structured, user-visible memory system with clear retention rules,
> per-item trust provenance, and a UX that lets the user see and
> control what Aether remembers about them and their projects.
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

## 0. What "memory" is (and isn't) in Aether

Memory is everything Aether persists about the user's conversations
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

- **Reflections** / "what Aether thinks about you" — out of scope;
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
user goes when they want to know **what Aether knows about them**,
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
  (Likely `bge-small` or `nomic-embed-text` via Ollama.) Lock in
  Memory V2 step 4.
- Vector index backend — SQLite + rusqlite extensions? A separate
  sqlite-vec file? Out of scope for design-only doc; decide at
  implementation time.

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
  memory between two of their own Aether installs over a private
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
   Iterates every known session via `SessionMemoryStore::list_sessions`
   and evicts rows older than `MemoryConfig::retention_for(domain)`
   via `SessionMemoryStore::prune_before`. Emits one aggregated
   `memory_forgotten` telemetry row per domain that evicted ≥1
   row, and one L5 audit row per sweep invocation via
   `MemoryForget`. Today only the Session domain has a backing
   store; other domains' retention policies persist in
   `memory.json` for the future domain-typed durable store and
   are skipped with a trace note. `run_retention_sweep` is in
   `memory_service.rs`.
6. ✅ **Embeddings (opt-in).** Behind the `embeddings` cargo
   feature on `aether-l2-memory`. Default provider: Ollama
   `nomic-embed-text` (see ADR-0002 for the full decision set).
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
- `planning/plans/L2_memory_kernel_system_design.md` and
  `planning/plans/implementation_prep/sqlite_schema_pack.md` —
  planning-phase references; this doc supersedes them for v2.
- `tools/lint-vision-doc/check.py` — rot-guard shape to copy for
  Memory V2 step 7.
