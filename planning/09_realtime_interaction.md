# 09 — Real-time Interaction & Latency Model

The two-speed cognition model, acknowledgment pattern, and timing contracts that make Aether feel socially present.

---

## Latency goals

### Experience target
The assistant must feel **fast and socially responsive** — not because the answer is always fast, but because the *acknowledgment* is always fast.

### Behavioral rule
**If a full answer takes longer than the reflex budget, the system acknowledges first.** No dead air. No silent waiting. No "AI is thinking..." spinner alone.

### Why timing matters more than answer depth
The product is judged as a **conversation**, not as a benchmark. Users forgive a 4-second research answer that opens with "Let me check that — one moment" more readily than a 1.5-second answer that starts with silence.

---

## The two-speed cognition model

### Reflex path (local, fast)
- **Runs on:** local hardware, default Gemma 4
- **Handles:**
  - Acknowledgment emission
  - Quick simple answers
  - Local memory retrieval
  - State transitions
  - Intent classification for routing
  - Can decide when to escalate to the deliberative path
- **Target latency:** first visible response under 250 ms; first audible response under 500 ms

### Deliberative path (slower, deeper)
- **Runs on:** either local (larger model for offline deep work) or remote (frontier LLM for hardest tasks)
- **Handles:**
  - Deep reasoning
  - Research
  - Multi-step tool use
  - Coding
  - Long-form drafting
- **Target latency:** complete within 4000 ms for most tasks; beyond that, streams partial progress

### UX requirement
**Both paths feel like one coherent assistant.** The user does not see "local mode" vs "cloud mode" labels mid-conversation. The router decides, the presence controller bridges the gap, and the output stream is unified.

---

## Timing contract (the "conversation clock")

The target budgets every engine works against:

| Time since user ends turn | Expected behavior |
|---------------------------|-------------------|
| **0–250 ms** | Avatar state transitions to "thinking" or "checking." Interaction engine emits visible state change. |
| **250–800 ms** | If reflex path has an answer, it begins streaming. Otherwise, an acknowledgment phrase is selected and begins streaming. |
| **800–2000 ms** | Either the answer is streaming, or acknowledgment has completed and presence controller maintains "working" state (gaze pattern, subtle motion). |
| **2000–4000 ms** | If deliberative path is still computing, a secondary status phrase may fire ("Still looking — almost there"). Avatar holds working state. |
| **>4000 ms** | Explicit progress update. User can interrupt or refine. |

The contract is not rigid — it defines defaults that the presence controller and reflex router enforce.

---

## Acknowledgment phrase pool

### Purpose
Short prewritten phrases that fire when the deliberative path takes longer than the reflex budget. They preserve social continuity while real work proceeds in the background.

### Examples by intent class

| Intent | Phrase candidates |
|--------|-------------------|
| Looking up info | "Checking that." / "Let me look that up." / "One moment." |
| Verifying | "Let me verify that." / "Making sure." |
| Thinking | "Give me a moment to think about that." / "Hmm, let me work through that." |
| Researching | "Digging into that now." / "Pulling up what I can find." |
| Tool running | "Running that now." / "Working on it." |
| Long task | "This will take a moment — stay with me." |

### Selection rules
- **Not random** — selected by intent class and persona style.
- **Non-repetitive** — avoid repeating the same phrase back-to-back.
- **Persona-coherent** — the phrase pool is part of the persona compile output (see [01_product_doctrine.md](01_product_doctrine.md#must-own-layers-custom-built-aether-pro-onward) — persona compiler).
- **Avatar-synced** — when the phrase fires, the presence controller triggers the matching social behavior (e.g., "thinking" gaze while saying "Let me think about that").

### Why phrase pools over streamed LLM acknowledgments
- **Faster** — prewritten phrases have near-zero latency vs. waiting for the first LLM token.
- **Controllable** — we own the tone, length, and persona fit.
- **Reliable** — works when the LLM is slow or offline.
- **Cheap** — no remote round-trip for the acknowledgment itself.

---

## Presence continuity during slow operations

### The rule
**The assistant must remain socially present while thinking.** Never freeze. Never go fully still. Never produce "spinner-only" UX.

### Implementation
When the reflex budget is exceeded and the deliberative path is running:

1. Presence controller holds the avatar in a "working" state:
   - Gaze shifts subtly (glance away as if thinking)
   - Blink cadence stays natural
   - Micro-motion continues (breath, small head movement)
2. Interaction engine surfaces a non-blocking status indicator (if user is in a text-heavy mode).
3. Acknowledgment phrase has already fired (or is about to).
4. If the user interrupts, the deliberative path cancels cleanly.

### State transitions (visible)
- **Listening** → user is speaking or typing
- **Thinking** → reflex path processing
- **Working** → deliberative path running (post-acknowledgment)
- **Speaking** → output streaming
- **Idle** → no active turn

Each state has distinct visual/audio cues. No state is silent dead air.

---

## Interruption and turn-taking

### Interruption handling
- User speaks while assistant is responding → media engine emits `speech_start`, interaction engine pauses TTS, cognition cancels the current answer stream.
- No retry — the new turn starts fresh with the user's new input.
- State transitions visibly show the assistant yielding the turn.

### Turn detection
- **Push-to-talk** — explicit, deterministic.
- **VAD (voice activity detection)** — automatic; user can toggle.
- **Text mode** — explicit on send.
- **Hybrid** — VAD in avatar mode, explicit in text mode by default.

### Barge-in
- Assistant respects user interruption at any point.
- Echo cancellation, gain control always active in avatar / voice modes.

---

## Default local LLM: Gemma 4

### Role
**Gemma 4 is the default local LLM** — it powers the reflex path and the local deliberative fallback.

### Where Gemma 4 runs
- **Reflex path**: always local, always Gemma 4.
- **Local deliberative (offline or privacy-scoped tasks)**: Gemma 4 (larger variant if tier allows).
- **Remote deliberative**: frontier LLM (Anthropic/OpenAI/equivalent) for the hardest tasks that exceed local capability.

### Variant selection per performance tier
- **Lite**: smallest Gemma 4 variant; reflex path only; deliberative always remote.
- **Balanced**: mid-size Gemma 4; handles most deliberative locally; remote only for edge cases.
- **Full / Pro**: largest Gemma 4 variant the VRAM budget allows (per the 50% rule in [14_performance_tiers_vram.md](14_performance_tiers_vram.md)); most tasks stay local.

### Isabelle (private branch)
Isabelle uses Gemma 4 as base with Don's custom tuning, persona overlays, and private memory integration. See [roadmaps/isabelle_private.md](roadmaps/isabelle_private.md).

---

## Model router behavior (reflex path decisions)

The router (a must-own layer) decides, per turn:
- Direct local answer (reflex answers)
- Acknowledge-and-wait (deliberative path needed)
- Search / research (tool path)
- Tool plan (multi-step)
- Remote frontier call (hardest tasks)
- Safety deflection (policy blocks)
- Memory write / update (post-turn)

Factors considered:
- Latency budget
- Privacy sensitivity of content
- Memory confidence
- Task type (quick Q&A vs research vs coding)
- Model cost
- Tool availability
- Current hardware headroom

---

## Failure modes and graceful degradation

| Failure | Behavior |
|---------|----------|
| Local LLM slow | Acknowledgment fires, router reconsiders remote escalation |
| Network down for remote | Router forces local-only; acknowledges limitation if task requires research |
| STT slow or fails | Falls back to text input prompt; presence shows "had trouble hearing" |
| TTS slow | Text answer streams visually; audio delivers when ready |
| Avatar render stalls | Chat mode remains responsive; avatar recovers when ready |
| Memory query slow | Answer proceeds without memory hit; memory retry logged |

The presence controller always has a graceful state to occupy while any failure mode is active.

---

## Measurement targets (to lock in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md))

- **Time to first acknowledgment** — target ms
- **Time to useful answer** — target ms by task class
- **Avatar frame smoothness under load** — target fps by tier
- **Interruption response latency** — target ms
- **Memory hit retrieval latency** — target ms

---

## Cross-references
- Architecture: [08_system_architecture.md](08_system_architecture.md)
- Memory: [10_memory_architecture.md](10_memory_architecture.md)
- Presence controller: [11_avatar_presence.md](11_avatar_presence.md#presence-controller)
- Tech stack (Gemma 4, inference runtime): [16_tech_stack.md](16_tech_stack.md)
- Performance tiers (Gemma 4 variants): [14_performance_tiers_vram.md](14_performance_tiers_vram.md)
