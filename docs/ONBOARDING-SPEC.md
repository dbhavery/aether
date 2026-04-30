# Onboarding Wizard Spec

**Purpose:** First-run experience. Takes a user from fresh install to "I'm talking to my assistant" in under 5 minutes.

**Platform:** Runs inside the same Next.js frontend as the main app, at route `/onboarding`. Backend mirrors wizard state in `src/onboarding/` so partial progress survives a crash.

**Trigger:** No `%APPDATA%/aether/config.yaml` exists, OR `config.yaml` exists with `aether.onboarding_complete: false`.

---

## 1. State machine

```
  [ 0. Launch ]
       |
       v
  [ 1. Welcome ] -------------> (back button disabled, can minimize but not close)
       |
       v
  [ 2. Avatar ] <-----+--------- can revisit from Sandbox later
       |              |
       v              |
  [ 3. Personality ]--+
       |
       v
  [ 4. Name ]---------+--------- auto-fills persona canonical name
       |
       v
  [ 5. LLM setup ]----+--------- validates key before advancing
       |
       v
  [ 6. Voice setup ]--+--------- optional; can be skipped entirely
       |
       v
  [ 7. Terms & Privacy ]
       |
       v
  [ 8. Hand-off ] ------------> writes config, sets onboarding_complete=true,
                                 navigates to Chat mode
```

Back navigation is allowed at every step except 1 and 8. Forward navigation requires the step's validation to pass. Close-window on any step saves partial state and resumes at the same step next launch.

---

## 2. Screen specs

### Screen 1 — Welcome

**Content:**
- Hero line: "Meet your AI companion."
- Subline: "Companion runs on your computer. Private. Yours. Choose who you want to talk to."
- Three value bullets: Private (runs locally), Flexible (pick any LLM), Real (lip-synced voice).
- Single CTA button: "Get started".

**Validation:** none.
**State written:** `wizard.started_at: <ISO timestamp>`.
**Analytics event (opt-in only, not until step 7):** `onboarding_step` with `step=1`.

### Screen 2 — Avatar

**Content:**
- 4x3 grid of 12 persona portrait cards.
- Each card: portrait image, persona display name, 1-line tagline.
- Hovering a card plays the `avatar/clips/idle_to_listening.mp4` idle clip muted, looped.
- Selected card gets a highlighted border + check badge.
- "Preview voice" mini-button on each card — plays `voice/sample.wav` (2-4s).

**Validation:** exactly one avatar selected.
**State written:** `wizard.selected_avatar_id: "<persona_id>"`.
**Note:** this picks the AVATAR (visual). Step 3 picks PERSONALITY (behavior). They're independent.

### Screen 3 — Personality

**Content:**
- 3x4 grid of 12 archetype cards.
- Each card: archetype name, short description, 2-3 example sentences showing the voice/tone.
- Hovering a card swaps the sample sentences to show a short 3-turn conversation snippet using the selected avatar's future voice reading the personality's example.
- Selected card gets a highlighted border + check badge.

**Validation:** exactly one archetype selected.
**State written:** `wizard.selected_archetype: "<archetype_id>"`.
**Computation:** the wizard now has `(avatar_id, archetype_id)` — this pair defines the active persona. If it matches one of the canonical 12 pairings, use that `persona.yaml` directly. If not, synthesize a virtual persona: avatar assets from the chosen avatar, system prompt from the archetype template, voice from the avatar's voice dir.

### Screen 4 — Name

**Content:**
- Single centered input field, pre-filled with the avatar's canonical `display_name`.
- Below: "Most people keep the default. You can change this anytime."
- Character counter (max 40).
- Below input: live preview — "Your assistant: **Aurora**" (updates as they type).

**Validation:** non-empty, <= 40 chars, no HTML/markdown, no emoji (v1.0 constraint — revisit later).
**State written:** `wizard.display_name: "<string>"`.

### Screen 5 — LLM setup

**Content:** 3 provider cards, radio-style selection.

**Card A — "Free & Local" (recommended for first-timers)**
- Requirement: Ollama must be installed.
- Live detection: wizard makes a test call to `http://localhost:11434/api/tags`.
  - If Ollama not detected: show "Ollama is not running on this machine. [Install Ollama] [I have it elsewhere]."
  - If detected: show list of installed models, recommend `qwen2.5:7b`, offer to `ollama pull` if missing (bridged through backend to show progress).
- Sub-setting: model name (default `qwen2.5:7b`).

**Card B — "Bring your own key" (best quality)**
- Provider dropdown: Anthropic, OpenAI, Google, Groq, OpenRouter.
- Key input (masked, with reveal toggle, with paste-from-clipboard detection).
- Tier auto-mapping visible below input: "Fast: claude-haiku-4-5. Main: claude-sonnet-4-6. Heavy: claude-opus-4-7." (Values differ per provider.)
- "Test key" button — makes one real call to the provider, returns checkmark or error message.
- "Where do I get a key?" link per provider opens the provider's key page.

**Card C — "Guest mode" (try before you commit)**
- Uses Groq free tier with Companion's public rate-limited key.
- Shown as "Limited — 10 messages/hour. Good for trying Companion out."
- No user action required beyond selecting.

**Validation:**
- If Card A: Ollama reachable and selected model is pulled.
- If Card B: test call returned 2xx.
- If Card C: always valid.

**State written:**
```
wizard.llm_provider: "<provider>"
wizard.llm_tier_map: { fast: "...", main: "...", heavy: "..." }
# Keys go directly to OS keyring, not to wizard state or config.yaml.
```

### Screen 6 — Voice setup

**Content:** 3 provider cards with a "skip voice" link.

**Card A — "Local voice (recommended)"**
- Auto-detects GPU and VRAM via backend.
- Shows detected hardware: "NVIDIA RTX 3090 Ti, 24 GB VRAM. Local voice will run smoothly."
- If no GPU or < 6 GB VRAM: shows "Your hardware may be slow for local voice. Consider cloud voice below, or skip voice entirely."
- Downloads required: faster-whisper base model (~200 MB) + Chatterbox Turbo (~800 MB).

**Card B — "ElevenLabs (cloud, costs apply)"**
- API key input.
- "Test key" button.
- Note: "ElevenLabs charges per character. You'll see usage in Sandbox → Voice."

**Card C — "Text only for now"**
- Skip voice setup. Can be enabled later in Sandbox.

**Validation:**
- If Card A: backend confirms sufficient resources.
- If Card B: test call returned 2xx.
- If Card C: always valid.

**State written:**
```
wizard.voice_mode: "local" | "elevenlabs" | "off"
wizard.voice_settings: { ... per-provider ... }
```

### Screen 7 — Terms & Privacy

**Content:**
- Short plain-English summary (3-5 bullets):
  - Companion runs on your machine. Your conversations do not leave unless you use a cloud LLM/voice you configured.
  - We don't collect any data by default.
  - Opt-in: anonymous crash reports (off by default).
  - Opt-in: anonymous usage counters (off by default).
  - You are responsible for how you use AI outputs.
- Two checkboxes: "Send anonymous crash reports" (off), "Send anonymous usage counters" (off).
- Two required links: "Read full Terms" and "Read full Privacy Policy" (open modal with full text).
- One required checkbox: "I agree to the Terms of Service and Privacy Policy."
- CTA: "Finish setup".

**Validation:** agreement checkbox must be checked.
**State written:**
```
wizard.accepted_terms_at: <ISO timestamp>
wizard.telemetry: { crash_reports: bool, usage_counters: bool }
```

### Screen 8 — Hand-off

**Content:** Short progress indicator while the backend:
1. Writes `config.yaml` atomically.
2. Initializes the active persona's ChromaDB collection.
3. Loads the avatar engine and runs a 0.5s warmup.
4. Preloads the voice models (if voice mode != "off").
5. Generates a single "welcome" message from the brain, with the selected personality.

Then navigates to Chat mode with the welcome message already shown, avatar in idle state, ready for the user's first input.

---

## 3. Error handling

| Failure | Behavior |
|---------|----------|
| Wizard process crashes mid-step | On relaunch, wizard resumes at the same step; all entered data (except keys, which are persisted to keyring immediately on validation) restored. |
| API key validation fails | Stay on the current step, show error inline, let user retry. Never advance. |
| Ollama not available on Screen 5 Card A | Inline guidance + installer link. User can switch to a different card. |
| Model download fails on Screen 6 | Retry button. If persistently failing, user can switch to Card C (text-only) and re-enable later. |
| Config write fails on Screen 8 | Show a retry button with the error. User's data is still in wizard state — they're not locked out. |
| Wizard cancelled/closed on any step | Persist partial state to `%APPDATA%/aether/wizard_state.yaml`. Next launch resumes at the latest completed step. |

---

## 4. Resumability

Wizard state is persisted to disk after every validated step, not just at the end. The file `%APPDATA%/aether/wizard_state.yaml` contains the partial config. When wizard completes, it:

1. Copies wizard state into the final `config.yaml`.
2. Deletes `wizard_state.yaml`.
3. Sets `aether.onboarding_complete: true` in `config.yaml`.

If a user abandons the wizard and comes back weeks later, they pick up where they left off — no re-entering keys, no re-choosing personas.

---

## 5. Telemetry (if opted in)

Every wizard step that's completed successfully fires an `onboarding_step` event with:
```json
{
  "step": 1..8,
  "timestamp": "ISO8601",
  "duration_ms": <time since previous step>,
  "installation_id": "<uuid from config.aether.user_installation_id>"
}
```

No other data. No key contents, no persona choices, no hardware details. Just "someone got to step N".

Used to answer: where in the wizard do users drop off? This is our most important P0 product metric.

---

## 6. Later iterations (post-v1.0)

Deferred:
- Persona preview chat on Screens 2–3 (type a test message, hear a response, before selecting).
- "Quickstart" mode: single-click path that skips to defaults (Guest LLM, text-only voice, first canonical persona).
- Onboarding analytics dashboard for our own use, aggregating telemetry from opted-in users.
- Language selection (v1.0 is English-only).
- Accessibility audit (WCAG AA).

---

## 7. Implementation notes for P3

- Wizard state is a single Zustand store on the frontend, persisted via `zustand/middleware/persist` to a local IndexedDB, AND mirrored to backend on each step via WebSocket message `{type: "wizard_state_update", state: {...}}`. Backend writes to `wizard_state.yaml`. Two sources of truth is deliberate: frontend keeps snappy, backend keeps durable.
- All validating calls (API key test, Ollama probe, model download) go through backend, not directly from frontend — keeps CORS + key exposure clean.
- No page reloads during the wizard. All transitions are React state changes.
- Each step is its own route (`/onboarding/1-welcome`, `/onboarding/2-avatar`, etc.) so back button works and deep links work for testing.
