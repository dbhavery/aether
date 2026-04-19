# L1 — Interaction Timing & Reflex Router

**Status:** draft
**Last updated:** 2026-04-18
**Layer type:** must-own (doctrine §1.1, §1.4, §1.7)
**Depends on:** L2 (memory hits feed reflex), L4 (router consults timing), L3 (presence state-linked), L5 (policy gates tool calls).
**Blocked by:** none for design; blocked by event bus implementation for build.

---

## Purpose

Own the felt timing of every interaction. This layer is the product's social pulse — the reflex path, the acknowledgment phrase pool, the timing contracts, and the turn-state machine that guarantees Aether never feels "thinking-quiet."

## Why must-own

Close-enough SaaS cannot hit the 250 ms / 800 ms / 2000 ms / 4000 ms contracts because cloud-hop latency dominates. The companion-grade standard requires deterministic local acknowledgment before any deliberation. This is the single biggest differentiator vs. ChatGPT-voice / Gemini Live and cannot be borrowed.

## Boundaries

**Owns:**
- Turn-state machine (listening / thinking / acknowledging / speaking / idle / waiting).
- Reflex classifier (direct-local / ack-and-wait / search / tool-plan / remote-escalation / safety-deflect / memory-write).
- Acknowledgment phrase pool + selection policy (persona-driven, non-repetitive, context-aware).
- Timing contracts & budget enforcement; fires ack automatically if deliberative path exceeds reflex budget.
- Turn-boundary detection (VAD-aware barge-in and interruption).
- `intent_hint`, `ack_phrase`, `route_decision` event emission.

**Does not own:**
- The underlying LLMs (L4 owns routing; model selection is swappable).
- TTS synthesis (Media engine; borrowable runtime).
- Visible avatar behavior (L3 consumes interaction state).
- Tool execution (L5 gates; L4 routes).
- Memory retrieval mechanics (L2).

## Dependencies

- **L2 memory kernel** — needs `memory_hit` events within 150 ms of `partial_transcript` to inform reflex.
- **L4 model router** — receives reflex output, returns `route_decision`.
- **L5 policy** — blocking gate before any tool plan leaves reflex.
- **Media engine** — consumes ack phrases, emits VAD/transcript events.
- **Event bus** — typed Rust-side coordinator; this layer is the bus's heaviest consumer.

## Borrowable vs custom

| Piece | Decision |
|---|---|
| Reflex classifier | **Custom.** Small local model (distilled Gemma 4 2B variant or classifier head) + rule layer. Non-negotiable. |
| Ack phrase pool | **Custom.** Phrase library is a doctrine surface, not a library call. |
| Turn state machine | **Custom (Rust).** Determinism + low-latency. |
| VAD | **Borrow** (Silero or WebRTC VAD) behind our interface. |
| Barge-in logic | **Custom.** Couples VAD + TTS interruption + viseme rollback. |

## Key risks

1. **Cascade silence.** If reflex classifier stalls, whole product feels dead. Mitigation: hard 150 ms reflex timeout → automatic ack phrase fires.
2. **Ack phrase repetition.** Single largest uncanny/cringe risk. Mitigation: persona-scoped rotating pool + recency penalty + context-conditioned selection.
3. **Interruption race conditions.** User speaks while TTS mid-phrase. Mitigation: event-sourced state machine with replayable audit trail.
4. **Reflex classifier false-positive direct-local.** Wrong answer delivered fast is worse than right answer slow. Mitigation: confidence threshold → escalate rather than answer.

## Sequencing

1. **P0 (OSS Preview)** — hand-coded reflex rules + fixed ack pool + simple state machine (Python/TS acceptable here). Goal: demonstrate the feel.
2. **P1 (Pro Phase 0)** — port state machine to Rust event bus; typed events; basic barge-in.
3. **P2 (Pro Phase 1)** — distilled classifier model; persona-driven ack pool; timing SLA instrumentation.
4. **P3 (Pro Phase 2)** — full contract enforcement (auto-ack on budget breach); deliberative-path cancellation; Isabelle phrase customization.
5. **P4 (Pro Phase 3+)** — context-conditioned phrase selection; mood/presence-linked pacing.

## Acceptance criteria

- 95th-percentile time-to-first-acknowledgment under 800 ms measured end-to-end (mic-cut to audible ack).
- Zero silent turns (every turn emits an ack or a direct answer within 800 ms).
- Ack phrase repetition rate <5% over 100 consecutive turns (same persona).
- Barge-in latency <150 ms (user speech start → TTS mute).
- Deliberative cancellation honored: interrupted request does not emit a late answer.
- Replayable event log for every turn.

## Open decisions for executing agent

- Choice of reflex classifier model (distilled Gemma 4 variant vs. classifier head vs. rule-only for P0).
- Exact ms budgets (feed into OPEN_QUESTIONS evaluation metrics).
- Whether P0 ships in Rust or is allowed to be Python/TS as tactical shortcut.

## Reference specs

- `file:///C:/Users/dbhav/Projects/aether-planning/09_realtime_interaction.md`
- `file:///C:/Users/dbhav/Projects/aether-planning/08_system_architecture.md`
- `file:///C:/Users/dbhav/Projects/aether-planning/01_product_doctrine.md`
