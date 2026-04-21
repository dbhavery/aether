# P3 — Documented deferrals: ts-rs id codegen + remote vision privacy (2026-05-03)

**Status:** Docs only. No code change. No commits other than this report
+ the next handoff.

## Why these are listed but not built

The 2026-05-02 handoff and the 2026-05-03 session prompt both call out
two follow-ups that look small from a distance but become land-mines if
landed prematurely. This report records the rationale so future sessions
don't keep re-deciding the same questions.

---

## Deferral 1 — `ts-rs`-style codegen for vision provider ids

### Current situation

- TS side: `apps/desktop/src/lib/visionProviders.ts` holds the canonical
  `VISION_PROVIDER_REGISTRY` (id + shortLabel). All five downstream TS
  consumers (mediaTurns dedup, ActiveVisionRoute, visionRouteSummary,
  Transcript footer dedup, badge derivation) read from the registry.
  TS dedup is complete.
- Rust side: each vision adapter declares its own `id()` independently
  (`OllamaVisionProvider::id() = "ollama-vision"`,
  `LlamaCppVisionProvider::id() = "llamacpp-vision"`).
- The two sides agree by convention only; a typo on either side would
  go undetected at compile time.

### Decision

Defer until a third vision adapter is on the table. Rationale:

1. With two adapters the duplicated surface is two strings. The
   existing TS registry tests assert both known ids, so a TS typo
   fails CI. A Rust typo would only fail at runtime when the
   provider returns the wrong id — uncomfortable but not severe.
2. Single-source codegen pays back when there are three+ sources
   to keep in lockstep. With two, the codegen scaffolding (build
   script, ts-rs / specta config, generated-file checked-in vs
   regenerated, CI freshness check) costs more than the bug it
   prevents.
3. The third adapter is the point at which the cost curve flips.
   Any time a third adapter is being scoped, treat the codegen as
   prerequisite work, not a follow-up.

### Likely approach when the time comes

Two options worth weighing then, not now:

- **`ts-rs` (or `specta`) with a shared Rust enum.** Define
  `VisionProviderId { OllamaVision, LlamaCppVision, Foo }` once in
  Rust, derive serde + ts-rs, emit a generated TS const into
  `apps/desktop/src/lib/generated/`. CI re-runs codegen and fails on
  drift. Pros: fully type-safe, no manual sync. Cons: adds a build
  dependency and a pre-commit hook.
- **JSON schema source-of-truth.** A single
  `packages/contracts/vision_providers.json` file consumed by both
  sides via codegen / build script. Pros: language-neutral, easy
  diff review. Cons: two codegen pipelines instead of one.

Recommend `ts-rs` if a third adapter lands first; recommend the JSON
schema approach if non-Rust workspace members start consuming the
same vocabulary.

---

## Deferral 2 — Remote-vision privacy posture

### Current situation

- Both shipped vision providers (Ollama, llama.cpp) are local-only.
  Image bytes never leave the host.
- `vision_provider.json` is a transient config; image bytes are
  never persisted (durable-memory privacy posture for images is
  "transient only" — see hard constraint in the 2026-05-03 prompt).
- No remote / cloud vision adapter exists. The Trust drawer surface
  is sized for local-only assumptions today.

### Decision

Defer remote-vision privacy work until a remote adapter is the next
piece of vision-track work. Rationale: the privacy posture is a
contract between the user, the adapter, and the audit/UI surface —
designing it without a concrete adapter to gate against produces a
spec that won't match the eventual reality.

### Key questions to answer at that time

When the third (remote) adapter starts, the posture work needs to
answer at least these:

1. **Data retention.** What does the remote provider promise about
   request/response retention? How is that surfaced to the user?
2. **Host allowlist.** Which hostnames can a remote vision adapter
   reach? Where is the allowlist stored, who edits it, and how is it
   audited?
3. **Per-provider consent labelling.** Does the user's media
   permission grant cover remote calls automatically, or does each
   remote provider require its own opt-in tier? Strong default: it
   does not — a fresh per-provider consent gesture is required.
4. **Configuration surface.** Where in the UI does the user set
   their remote-vision posture? `vision_provider.json` is
   additive-default-safe today; widening it for remote keys must
   keep that property.
5. **Audit semantics.** Should `AuditRecordEvent` carry an explicit
   "remote endpoint contacted" field, or is the existing capability
   row sufficient when the resource scope encodes the host?
6. **Image-on-the-wire.** Today image bytes are transient in memory.
   What's the wire format for a remote call (data URL, multipart,
   pre-signed upload)? What guarantees does the adapter give about
   not retaining the on-the-wire copy?
7. **User-visible labelling.** The Trust drawer and transcript
   footer currently show provider id + model. Should remote
   providers carry a stronger "calls out to the internet" badge so
   users can tell at a glance which turns left the host?

These belong in a single spec that lands alongside (or just before)
the remote adapter, not as a series of small drive-bys.

---

## Hard-constraint compliance

- No push.
- No code change in this report.
- No L5 / persistence / streaming changes.
- No new providers.
