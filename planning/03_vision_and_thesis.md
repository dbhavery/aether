# 03 — Vision and Thesis

The product vision and the three theses (core / experience / strategic) that govern Companion's design.

> **Updated 2026-05-18** to reflect doctrine §5/§6/§7/§8 (`01_product_doctrine.md`):
> - **§5** photoreal full-body characters from the start — no headshot intermediate;
> - **§6** Companion ships once, when complete — no interim wedge product;
> - **§7** voice does not ship as a standalone product;
> - **§8** self-test before Don review (visual via multimodal vision; frontend used-as-user).
>
> The "OSS Preview as wedge / Pro as flagship" two-product framing in earlier drafts of this file is **retired**. Anywhere this file conflicts with `01_product_doctrine.md`, doctrine wins.

---

## Core vision

Build a production-grade conversational AI assistant that users interact with primarily through **text/chat mode** and **avatar/video mode**. The assistant should feel **socially present**, **persistent**, and **trustworthy** — not a tool, not a chatbot, not a widget.

This is not a hobby project. It is not a demo. It is not an "AI toy." UX/UI quality is a top-level strategic priority, not a surface layer.

---

## Experience thesis

**People prefer to converse with a human-like assistant to get work done.**

Conversation quality depends on:
- **Low-latency acknowledgement** — no silence, no dead air.
- **Believable timing** — listening, thinking, answering each feel distinct and right.
- **Strong memory continuity** — the assistant remembers what matters across sessions.
- **Permission trust** — the user knows what the assistant will and won't do, and can change it.
- **Polished presentation** — the interface feels premium, warm, confident.

**Text mode and avatar mode are both first-class.** Neither is a "main mode with the other bolted on." Both must work well in isolation and better together.

**Voice-only is not a separate mode.** It is chat mode with microphone and audio output enabled, where either party may be muted visually or aurally. Same orchestration, same permissions.

---

## Strategic thesis

### Local-first where possible, cloud-backed where necessary

- Local state, memory, persona, fast acknowledgment, and real-time media control are **absolute locals**.
- Remote (cloud) is reserved for expensive reasoning, live research, long-horizon tool use, or when the local stack explicitly decides frontier-model quality is worth the latency/cost.
- The local stack never depends on the network for basic responsiveness.

### Strict separation of concerns

Four systems, kept structurally separated:

1. **Real-time local reflex behavior** — acknowledgments, state transitions, memory retrieval, fast answers.
2. **Remote high-quality reasoning** — frontier LLM for depth, research, multi-step tool use.
3. **Avatar rendering and behavior** — a media pipeline with its own timing contract, not welded to the reasoning path.
4. **User permission/policy enforcement** — evaluated between orchestration and tools; never bypassable.

The user sees one coherent assistant. The engineering preserves four independent timing budgets so no single slow component breaks social presence.

### Moat comes from integration, not single components

The product's defensibility is not a single avatar or a single model. It is the combination of:

- a latency-aware social timing engine
- a persistent identity and memory architecture
- a custom behavior-to-animation runtime
- a local-first companion state model
- a provider-swappable intelligence router
- a desktop-to-mobile continuity model

Any competitor can buy a lip-sync API. None of them have these layers working together.

### One product, ships when complete (doctrine §6)

- **Companion** is the single product — it is built primarily from custom software. Borrowed primitives are isolated and replaceable. Companion ships once, when complete; no interim wedge product, no headshot-only release, no voice-only release, no chat-only release.
- The OSS-friendly engineering posture (clean Tauri shell, layer scaffolds, open-weights tooling) remains correct as engineering practice — it just does not ship as a separate product. The prior "OSS Preview as wedge" thesis is retired.
- **Isabelle** is a private overlay on top of Companion, not a separate codebase.
- **Voice** (doctrine §7) is a sub-feature of Companion — STT + TTS + push-to-talk + presence-aware turn-taking are integrated continuously, but the surface that exposes voice ships only with the complete Companion.

---

## Experience target (flagship north star)

> **The highest believable assistant/companion relationship the product can realistically build toward.**

Operationalized as measurable targets:
- Acknowledgment timing (first visible response ms)
- Time-to-useful-answer (answer quality ms)
- Memory continuity (recall precision across sessions)
- Presence quality (believability under load)
- Control transparency (user can always see what's happening)
- Graceful fallback (network loss / model slow / tool failure)
- Stable personalization (doesn't drift or forget)

Aspirational framing: "indistinguishable from a real human assistant/companion." This is a north star, not an SLA — but it is the direction every architectural decision aims.

---

## Experience principles (applied)

| Principle | Implication |
|-----------|-------------|
| Social presence > benchmark scores | Routes are judged by conversation feel, not MMLU deltas |
| Continuity > completeness | Finish fewer things well; no conversation ever ends in silence |
| Trust > autonomy | The assistant never surprises the user with an action |
| Memory > prompt-stuffing | Durable structured memory beats ever-larger context windows |
| Presence quality at full-body fidelity | Photoreal full-body is the locked target (doctrine §5). Presence quality (gaze, blink, micro-motion, anti-uncanny stabilization) is engineered into the photoreal pipeline — not traded against it. The pipeline must hit both at once; "lower-fidelity but feels alive" is no longer an acceptable fallback. |
| Clarity > cleverness | Settings and permissions are legible to non-technical users |

---

## Anti-patterns (things this vision explicitly rejects)

- **"Just wrap an LLM"** — the product ceiling is set by integration, not by the wrapped model.
- **"Good enough is fine for now"** — close-enough SaaS quality is unacceptable in core experience layers (see doctrine).
- **"Realism without reliability"** — a photoreal character that freezes, drifts identity, or breaks lip-sync under load is a liability. Doctrine §5 locks photoreal full-body as the target *and* requires reliability under load; the two are not traded against each other.
- **"Lock the user into our cloud"** — local-first is a doctrine, not an optimization.
- **"Hide the permissions behind an advanced menu"** — trust must be legible to mainstream users.
- **"Feature-match competitors"** — the product is a relationship, not a checklist.

---

## Proof points

These establish that the flagship target is reachable:

- AI-generated human-indistinguishable models exist.
- AI-generated human-indistinguishable videos with natural movement exist.
- Real-time TTS-driven lip-sync with human-like motion exists.

The engineering challenge is **assembly, integration, and presence quality under load** — not inventing from zero. Don has spent months hitting "highly-believable" with existing tooling; the path forward is deeper integration and custom-built must-own layers, not more vendor stacking.

---

## Self-test before review (doctrine §8)

Don's review time is the scarce resource. Nothing reaches him until the agent has self-tested it.

- **Visual artifacts** (reference images, identity-LoRA samples, motion clips, video, lip-sync output): multimodal-vision evaluation against acceptance criteria; failed self-tests re-loop the producing step.
- **Frontend changes** (any UI in `apps/desktop/`): used-as-user via browser/Tauri automation; "looks fine in the diff" or "unit tests pass" is **not** sufficient.

This is the gate, not a recommendation.

---

## Cross-references
- Doctrine: [01_product_doctrine.md](01_product_doctrine.md)
- Product family: [02_product_family.md](02_product_family.md)
- Architecture: [08_system_architecture.md](08_system_architecture.md)
- Realtime model: [09_realtime_interaction.md](09_realtime_interaction.md)
