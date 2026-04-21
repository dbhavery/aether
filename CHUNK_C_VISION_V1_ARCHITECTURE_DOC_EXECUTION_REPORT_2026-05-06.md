# Chunk C — VISION-V1-ARCHITECTURE.md — execution report (2026-05-06)

**Status:** Shipped, committed `d93d7f0` on `dev`. Push not authorized.

## Goal

Capture the Vision v1 slice — local-only single-frame assistant —
in a single architecture reference so future tracks (remote vision,
microphone, voice/STT/TTS) have a stable shape to design against.
Today the architecture is documented across ten+ execution reports
and this week's handoffs; without a digest, future sessions reload
the same context every time.

## Surfaces touched

- `docs/VISION-V1-ARCHITECTURE.md` (new, 350 lines).

## Sections

1. **End-to-end flow** — annotated ASCII pipeline from
   `permission → capture → analyze_frame → L4 → provider →
   memory/audit/telemetry/transcript/UI` with every layer's
   responsibility named.
2. **Providers** — Ollama and llama.cpp config knobs, env vars,
   feature flags, healthcheck behavior, model discovery endpoints,
   and the deliberate non-unification of `LlamaCppConfigError` /
   `OllamaConfigError`.
3. **`vision_provider.json` contract** — additive default-safe
   read, unknown-field tolerance, dropped-on-rewrite limitation,
   single-writer rule, malformed fallback. References the
   schema-tolerance test set.
4. **Provider / model selection rules** — active-provider fallback,
   per-provider model preservation across swaps, persisted entries
   for unregistered providers, first-launch seeding, TTL cache
   semantics, manual `↻` refresh.
5. **Frame validation** — both enforcement points
   (`validate_frame_data_url` shell-side and
   `maybe_apply_vision` mirror) with the rule list and the
   debug-vs-WARN log distinction.
6. **Telemetry kinds** — table of the five vision kinds with
   audit-row presence column.
7. **UI surfaces** — VisionBadge, ActiveVisionRoute, transcript
   footer, Trust drawer history/audit, all reading from the
   shared `VISION_PROVIDER_REGISTRY`.
8. **Hard constraints** — seven invariants every Vision-v1 PR must
   honor (local-only, transient bytes, additive config, no
   provider info in audit, no streaming, distinct provider
   errors, no raw payload telemetry).
9. **Open questions for future tracks** — pointer to remote
   adapter privacy work, mic/voice mirror plan, codegen trigger
   conditions.
10. **Reference reports** — index of justifying execution reports
    so a curious reader can dig in.

## What was deliberately left out

- **Sequence diagrams.** The ASCII flow is enough for the audience
  (future me + collaborators); a graphical diagram would rot.
- **Code excerpts.** The doc names files and functions; readers
  can grep. Excerpts go stale faster than prose.
- **Performance notes.** Vision v1 doesn't have a perf SLO yet;
  noting "TBD" would be noise.
- **Roadmap.** This is a snapshot, not a plan. Roadmap belongs in
  the active handoff.

## Hard-constraint compliance

- **No code change.**
- **No release / distribution / signing work.**
- **No new providers.**
- **No new test deps.**
- **No mic/voice/STT/TTS work.**

## How to keep this current

The doc names a "Status: Current as of 2026-05-05" line at the top.
When future PRs change a behavior the doc claims, update the doc in
the same PR. If we routinely forget, fold it into a CI check that
fails when `docs/VISION-V1-ARCHITECTURE.md` hasn't been touched in
the same commit as files it references.
