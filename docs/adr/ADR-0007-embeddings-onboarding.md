# ADR-0007: Embeddings onboarding — tier-aware readiness, pull UX, and backfill

- **Status:** Accepted (Don, 2026-04-24, with external reviewer concurrence on the nine-block discuss outputs).
- **Date:** 2026-04-24
- **Deciders:** Don (owner). Nine-block discuss session 2026-04-24 locked every decision below. Claude captures.
- **Supersedes:** `docs/adr/ADR-0003-model-defaults-supersession.md` Decision 2 only — embedding-model default is now tier-parameterised under the ADR-0006 hardware tier model rather than globally singular. ADR-0003 Decision 1 (gemma4:e4b LLM pin) remains in force pending a future LLM tier-manifest ADR. ADR-0003's Mini-Run 0 *methodology* (research-driven default re-evaluation) remains valid and is not superseded.
- **Superseded by:** nothing.
- **Related:** `docs/adr/ADR-0005-retrieval-wiring.md` (wired the path that this ADR now onboards), `docs/adr/ADR-0003-model-defaults-supersession.md` (model pins — become tier-parameterised here), `docs/adr/ADR-0006-hardware-tier-model.md` (defines the tier axis this ADR consumes), `docs/MEMORY-V2-ARCHITECTURE.md` §§10–11.

## Context

ADR-0005 landed the retrieval wiring: `submit_turn` invokes `run_retrieval_context`, composes a block, augments the prompt. The feature is live whenever `memory.json::embeddings.enabled = true`.

Today that flag can only be flipped by hand-editing `memory.json`. No UI surface, no readiness indication, no model-pull guidance, no handling of pre-existing Durable rows that were written before embeddings were on. This ADR fixes that.

Nine design questions were worked through in the 2026-04-24 discuss session. Each is captured below as a numbered decision.

## Decisions

### 1. Readiness posture: best-effort + surfaced warning. (Block 1.)

When `embeddings.enabled = true` but the probe says not-ready, turns still proceed — memory-only, no retrieval block injected. A visible indicator surfaces the state with a structured reason. This matches the posture for presence / vision / speech: auxiliary modalities degrade gracefully, they do not block the primary turn flow. Retrieval is quality-additive grounding; its absence is a quality tax, not a correctness failure.

Rejected: hard-block (too annoying on a daily-use tool, Ollama restarts would halt conversations); fully-silent (today's behaviour — user can't tell whether retrieval fired).

### 2. Probe definition: reachable + model-listed. (Block 2.)

The readiness probe hits `GET /api/tags`, parses with `aether_l4_router::ollama_vision::parse_tags_response` (already `pub` — reused, not reimplemented), and checks whether the configured tier's embedding model is in the returned list. Ready iff both.

Cheap (sub-millisecond), covers the two realistic failure modes (daemon down + model not pulled), reuses existing code.

Rejected: `/api/tags` only (blind to missing model — the most common first-time failure); full `embed("ping")` probe (1-3s cold-start tax on every session start, catches only exotic failures that the best-effort posture already handles).

### 3. Probe cadence: event-driven, symmetric. (Block 3.)

Probes run at:

- App boot (session start).
- After any mutation to `memory.json::embeddings.enabled` or `embeddings.provider`.
- After any `tier_changed` event from ADR-0006 (tier change may change the target embedding model).

In addition, every invocation of `run_retrieval_context` updates `AppState.retrieval_readiness` based on its own outcome — failure → not-ready with reason, success → ready. The indicator reflects last-known ground truth from real traffic.

No background polling. No per-turn preflight (the orchestrator is itself the signal source).

Rejected: per-turn preflight (adds latency to every turn); session-start-only (indicator stuck at stale state after Ollama crashes mid-session); periodic background poll (tokio tick task cost, tuning interval, another moving part).

### 4. Model-pull UX: CLI-instruction (A) now; in-app pull (B) deferred. (Block 4.)

When the probe returns `model_installed = false`, the indicator's reason text is:

> Embedding model `<model-name>` is not installed. Run `ollama pull <model-name>` in a terminal (~<size> download) and Aether will activate retrieval automatically.

No button. The text itself is selectable. Model name and approximate size come from the tier's model manifest.

Deferred to future run: an in-app `[Pull model]` button that spawns an `ollama pull` subprocess, streams progress, handles cancel. The infrastructure (subprocess wiring, progress parsing, error classification) is a real ~300-LOC feature that saves a context-switch. Revisit when Aether has users who aren't fluent in terminals.

Rejected: auto-pull on enable (paternalistic — flipping a checkbox should not initiate a 1.2 GB network operation).

### 5. Backfill scope: opt-in `[Backfill now]` with hardware-aware estimate. (Block 5.)

When the probe is ready AND there are un-embedded rows in any embed-eligible domain (Durable / Projects / Artifacts), the indicator shows:

> `N` existing items not indexed for retrieval. `[Backfill now (~estimate)]`

The estimate comes from the tier's embedding latency profile (see Decision 7) multiplied by `N`. The button triggers a background job that walks the un-embedded rows and calls the existing `maybe_embed_on_write`-equivalent for each. Progress is streamed via Tauri events; cancel is supported.

Button is hidden when `N = 0` (new users with no pre-flag history never see a pointless zero-row button).

Rejected: no-backfill default (breaks the whole "Aether remembers prior context" value prop — existing history would be invisible to retrieval forever); auto-backfill on enable (paternalism again — minutes of background CPU should not be a side effect of a checkbox); lazy per-turn backfill (invisible progress, per-turn latency tax, debugging hell).

Future refinement (not shipped now): granular scope ("Backfill last 30 days only"). Worth adding only if full backfill becomes painful at real user scale.

### 6. Indicator surface: Trust drawer section + attention badge on drawer icon + toast on transition. (Block 6.)

Three surfaces, composed:

- **Trust drawer `RetrievalTab`** (or new section in existing tab): structured state (ready / not-ready + reason), model name + size, backfill button when applicable, pull-instruction copy when applicable. Settings-drawer-quality UX: always available on demand, never blocking.
- **Attention badge on the drawer icon** (small dot, standard IDE/app pattern): visible when state is not-ready, clears when ready. Solves "drawer is closed, something changed" without chrome noise.
- **Toast on state transition**: quiet, transient (~4 seconds), appears on ready → not-ready (so user knows their last turn degraded) and on completion of pull / backfill. Appears never while state is steady.

Rejected: chrome pill (always-visible, conflicts with minimal aesthetic); Settings-only (contradicts Decision 1's "surfaced" — burying it defeats the purpose); toast-only (missed toast = missed signal, no fallback).

### 7. Tier-parameterised model manifest. (Formally supersedes ADR-0003 Decision 2 — see header.)

ADR-0003 pinned `bge-m3` as *the* embedding default. Under ADR-0006, there are three tiers, but the selection rule is *quality-first*, not *tier-first*: tier defines the search space within which the model is chosen; the smallest model that meets the constant retrieval-quality bar wins. If no model in the tier's search space passes the bar, retrieval does not ship at that tier (mirrors the avatar-medium principle in ADR-0006 Decision 1: tiers vary the medium to preserve the bar, never lower the bar to fit the medium). One model rarely fits all hardware; this is why tiers exist. But quality is the ceiling, not a knob.

| Tier | Default embedding model | Approx. size | Approx. cold-start | Approx. per-row embed latency |
| --- | --- | --- | --- | --- |
| **Spark** | `bge-small-en-v1.5` (or equivalent small, CPU-viable) | ~130 MB | <1 s | ~100-200 ms CPU |
| **Flame** | `bge-m3` (ADR-0003 default preserved at this tier) | ~1.2 GB | 1-3 s cold, <200 ms warm | ~50-100 ms GPU, ~300 ms CPU |
| **Forge** | `bge-m3` (same — bigger variants don't buy enough for personal scale) | ~1.2 GB | 1-3 s cold, <100 ms warm | ~30-50 ms GPU |

The `RetrievalConfig` shape in `memory.json` does not need to change — `embeddings.provider` string continues to name the model. What changes: the *default* value is resolved from `tier.json` at read time, so a new install picks the right model for its hardware without hand-editing. Explicit user override remains available (advanced users who want bge-m3 on a Spark machine can set it manually; we don't second-guess).

These numbers feed the backfill estimate (Decision 5) and the pull-size copy (Decision 4). Final per-tier latency figures may shift once on-hardware validation runs (see implementation plan); the *manifest concept* is the binding decision, the numbers are best estimates.

### 8. Disk-space preflight. (Not previously in the nine blocks — added during drafting.)

Before the indicator shows any CLI-pull instruction or backfill button, check available disk space on the app data directory via `fs::available_space`:

- Need ≥ `model_size * 1.5` free for a pull (model file + working space + safety margin).
- If below threshold, indicator state is `not_ready_low_disk`, reason surfaces the missing amount ("Need ~1.8 GB free; have ~800 MB").
- No pull or backfill offered until disk is freed.

Simple, cross-platform, avoids the "download half a model and crash" failure mode.

### 9. Hardware detection signal wiring. (From Block 7 + ADR-0006 interaction.)

This ADR does *not* redo hardware detection — it consumes the outputs of ADR-0006:

- Reads `tier.json::selected_tier` to resolve the target model.
- Reads `tier.json::hardware_snapshot.ollama_gpu_loaded` to choose between CPU / GPU latency estimates for the backfill.
- Subscribes to `tier_changed` events to re-probe.

No new hardware-detection code lives here.

## Run 3 implementation plan (tier-aware)

Two implementation sessions, with on-hardware validation as the first step:

**Session A — tier + readiness + CLI-pull path (backend-heavy):**

1. On-hardware validation. `ollama pull <tier-appropriate model>`, flip flag, submit two turns, verify retrieval actually fires end-to-end on real hardware. 10-15 minutes. Outcome feeds the latency numbers in Decision 7 (may tune estimates).
2. ADR-0006 implementation: hardware detection module, `tier.json`, tier Tauri commands. (Decisions 1-7 of ADR-0006.)
3. `AppState.retrieval_readiness` state machine; `embeddings_readiness` Tauri command returning structured reason; boot + settings-change probes; symmetric update from `run_retrieval_context`. (Decisions 1-3 of this ADR.)
4. Disk-space preflight wiring. (Decision 8.)
5. Tests + rot guard.

**Session B — onboarding UX + backfill:**

6. Trust drawer `RetrievalTab` section + attention badge + toast infrastructure. (Decision 6.)
7. CLI-pull instruction copy in "not ready (model not installed)" state. (Decision 4.)
8. Backfill Tauri command + progress events + cancel. (Decision 5 backend.)
9. Backfill UI wiring (button + progress + cancel). (Decision 5 frontend.)
10. Frontend TS types mirrored from Rust (lesson from `dcc89f7`: don't let them drift).
11. E2E test, execution report, handoff.

**Explicitly out of scope for Run 3 (deferred to future runs):**

- In-app `[Pull model]` button (Decision 4 deferred).
- Background safety-net poll (Decision 3 explicit).
- Hard-block posture mode (Decision 1 explicit).
- Per-retrieval telemetry shape (needs its own ADR; depends on History tab UX).
- L1 audit cleanup for retrieval-augmented utterance (Risk G from HANDOFF_2026-04-24, needs its own cross-layer ADR).
- Granular backfill scope (Decision 5 future refinement).
- Avatar / TTS / vision tier manifests (future ADRs).

## Alternatives considered

Each of the nine blocks rejected alternatives; see individual decision sections above for specifics. No global alternatives worth calling out — the block-by-block discuss session surfaced the real tradeoffs.

## Consequences

**Positive.**

- `embeddings.enabled` becomes a flag users can actually flip and trust.
- Retrieval state is visible, not silent.
- Existing users' history becomes reachable by retrieval after an informed, user-initiated backfill.
- Tier model integrates cleanly — Aether doesn't guess which model to pull, it reads `tier.json`.
- Patterns established here (user-initiated infra work, hardware-aware estimates, best-effort graceful degradation) generalise to future onboarding ADRs for TTS / vision / avatar.

**Negative.**

- Trust drawer gains a new section — incremental UI surface. Well-scoped but adds frontend + TS types.
- Backfill is a new background-job pattern. Must be robust (cancel, resume-on-restart-if-not-complete, progress accuracy). Proportional test coverage required.
- Deferring the in-app pull (Decision 4) preserves manual-install friction until that deferred work lands.

**Neutral.**

- Model pins become tier-parameterised; ADR-0003 no longer the single source of model truth. This is managed via clear cross-reference, not by revoking ADR-0003.

## Open items (NOT decided here)

- Exact Spark-tier embedding model (candidate: `bge-small-en-v1.5` — final choice pending hardware validation).
- Backfill job concurrency (one at a time vs N-parallel). Default: serial, simple, add parallelism if measured backfill times exceed patience threshold.
- Backfill resumability across app restart (if user closes app mid-backfill, does it resume or does the button reappear?). Default: reappear; explicit resume is v2.
- Indicator reason text copy — draft in implementation, review during Session B.

---

(end of ADR-0007)
