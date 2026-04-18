# RUNWAY.md — Session Handoff

**Last session:** 2026-04-17 — full E2E integration pass.
**Branch:** `dev` (pushed to origin).
**Latest commit:** `e02a194 [FRONTEND] Scaffold Next.js 15 UI with wizard, chat, sandbox, video modes` (preceded by `ecc88ab [INTEGRATION] Wire backend for frontend E2E + fix path/contract bugs`).
**Status:** Backend boots clean. Wizard + chat E2E work via direct WS client. UI renders screens 1–5 in browser. Screens 5→6 advance hangs in the browser — fixable, documented below. Minor sanitizer issue truncating responses.

---

## Agent 2 complete — Desktop shell + Voice pipeline (2026-04-17)

**Branch:** `feature/desktop-shell-voice` (not yet merged — draft PR against `dev`).
**Worktree:** `../aether-desktop-voice/` (created via `git worktree add`).

### What ships

1. **`desktop/` package** — pywebview shell.
   - `desktop/main.py`: backend supervision (attach to :8765 if listening,
     otherwise spawn `python -m src.main` and tear down on window close).
     URL auto-selects the Next.js dev server if :3000 responds within 1 s
     probe, otherwise loads the static export at `frontend/out/index.html`.
     Window: 1280x860, min 1024x720, dark chrome `#0B0B0F`.
   - `desktop/bridge.py`: JS ↔ Python bridge exposed as
     `window.pywebview.api` — `open_file_dialog`, `get_keyring_token`
     (proxied via backend `/auth/token`), `open_external` (refuses
     non-web URLs), `get_app_info`.
   - `desktop/launcher.ps1`: pythonw launcher so no console flashes.
   - `desktop/README.md`: dev vs packaged mode, troubleshooting.

2. **Voice pipeline rewrite** — push-to-talk, no wake word, no speaker verify.
   - `src/voice/pipeline.py`: subscribes to `USER_SPEECH_START` /
     `USER_SPEECH_END` from the frontend. Opens a permanent sounddevice
     InputStream on start but only buffers between events. On END, runs
     the buffer through `transcribe()` and publishes `TRANSCRIPT_READY`
     plus `USER_MESSAGE` (mode=voice). 120 s hard cap on a single segment.
   - `src/voice/stt.py`: faster-whisper primary (model via
     `config.voice.stt_model`, default `base.en`, `distil-large-v3`
     supported). ElevenLabs Scribe attempted only when user picked
     `mode=elevenlabs` AND keyring has an `elevenlabs` key. CircuitBreaker
     retained.
   - `src/voice/tts.py`: Chatterbox primary with persona-aware voice
     cloning — looks up active persona's `voice/reference.wav` via
     `get_persona_manager().active_persona.reference_wav_path`, falls
     back to Chatterbox default when the file is absent. ElevenLabs
     primary only in `mode=elevenlabs`, with Chatterbox safety-net on
     cloud failure.
   - `src/voice/tts_handler.py`: on `RESPONSE_TEXT_READY` (non-interim,
     voice/video modes only) synthesises, then concurrently plays the
     clip AND emits 100 ms int16 PCM chunks as `RESPONSE_AUDIO_CHUNK`
     events plus a final `RESPONSE_AUDIO_END` for future avatar lip-sync.
   - **Deleted:** `src/voice/wake_word.py`, `speaker_verify.py`,
     `wake_context.py`, plus `tests/unit/test_wake_context.py`. Grep
     confirms no Python imports reference them. `requirements.txt`
     already had `pvporcupine` and `speechbrain` removed.

### What's tested

- `pytest tests/unit/test_voice_in.py::TestSTT tests/unit/test_voice_in.py::TestCircuitBreaker`
  → 9/9 pass. Covers faster-whisper/ElevenLabs fallback routing both when
  the user opted in and when they didn't.
- Voice pipeline smoke test (throwaway `AETHER_DATA_DIR`, voice.mode=local):
  - `start_voice_pipeline()` subscribes to START/END events and opens
    the sounddevice stream with default device.
  - Publishing `USER_SPEECH_START` / `USER_SPEECH_END` drives capture +
    `transcribe()` call (faster-whisper model load is lazy so the
    pipeline boots clean even when `faster-whisper` isn't installed —
    transcribe returns None cleanly).
  - `stop_voice_pipeline()` unsubscribes both handlers, closes the stream.
- TTS handler smoke test: `register_tts_handlers()` subscribes one
  handler to `RESPONSE_TEXT_READY`; `_publish_audio_chunks(320ms, 16kHz)`
  emits 4 `RESPONSE_AUDIO_CHUNK` events plus 1 `RESPONSE_AUDIO_END`.
- Desktop shell: module imports clean, `DesktopBridge.get_app_info()`
  returns platform + data_dir. Backend subprocess spawn + wait-for-listen
  + teardown on shell exit verified via port-state observation.

### Known-fragile paths

- **Pywebview visual rendering** not screen-verified from this agent
  (no screen capture available). Don should run
  `.\desktop\launcher.ps1` to confirm the window renders and can
  round-trip a message.
- **Faster-whisper install** is still optional in the dev venv —
  `pip install faster-whisper` is in requirements.txt but needs torch
  (CUDA) installed separately per the top-of-file note. Voice pipeline
  start succeeds either way; transcription is the lazy load that can
  fail with a clean `ModuleNotFoundError`.
- **Chatterbox install** similarly lazy; first synth will either load
  the model or log a clean error. A machine without Chatterbox installed
  but with ElevenLabs configured will route everything through the cloud.
- **Audio device** comes from `config.voice.device`. `"default"` and
  empty string both resolve to `None` (system default). Other values
  are passed through to sounddevice (substring match of device name,
  or int index).
- **Frontend has not been rebuilt** in the worktree — the shell will
  load `file://.../frontend/out/index.html` if you run packaged mode;
  run `cd frontend && npm install --legacy-peer-deps && npm run build`
  or use dev mode (`npm run dev` in one terminal, launcher in another).
- **Backend instance lock** at `%LOCALAPPDATA%/aether/...` blocks two
  backends running against the same data dir. The desktop shell already
  handles this by attaching to an existing backend on :8765.

### Commits this session (Agent 2)

```
[DESKTOP]  Add pywebview desktop shell
[CLEANUP]  Delete wake-word + speaker-verify modules
[VOICE]    Rewrite voice pipeline for v1.0 push-to-talk
```

### How to test Agent 2 deliverables

```bash
cd C:/Users/dbhav/Projects/aether-desktop-voice
# .venv is a junction to the main repo's venv; pywebview + sounddevice
# + soundfile are already installed there.

# Unit tests
.venv/Scripts/python.exe -m pytest tests/unit/test_voice_in.py::TestSTT tests/unit/test_voice_in.py::TestCircuitBreaker -q

# Desktop shell (visual check)
.\desktop\launcher.ps1
# → native window titled "Aether", window closed → backend terminated.

# Voice pipeline live test requires faster-whisper installed:
.venv/Scripts/python.exe -m pip install faster-whisper
# then boot the backend with voice.mode=local and publish
# USER_SPEECH_START/END events from the frontend to observe TRANSCRIPT_READY.
```
## Agent 1 complete — frontend UX + text polish

**Branch:** `feature/frontend-ux-complete` (pushed; draft PR against `dev` open).
**Scope:** the six deliverables from Don's brief — owned `frontend/**`, `src/brain/sanitizer.py`, and one StepHandoff fix that needed `src/onboarding/handler.py` shape verification (read-only — no changes there).

### What changed (commit-by-commit)

1. `cd68e1b [FIX] brain: sanitizer preserves multi-sentence responses past banned phrases` — substring matching in `_SENTENCE_BANS` was truncating "Hello! How can I assist you today?" to "Hello!". Switched Pass 1 to exact-match-after-normalize so a sentence is stripped only when its substantive content equals a banned phrase verbatim. Standalone openers ("Absolutely!", "Of course.", "Great question!") and bare service offers ("How can I assist?") are still removed; longer responses round-trip intact. Added `tests/unit/test_brain_sanitizer.py` with 11 cases covering the regression, true-opener stripping, and empty/whitespace edges.
2. `78877e4 [FIX] frontend: home page probes /health and redirects instead of hanging` — `app/page.tsx` now runs its own `GET http://localhost:8767/health` with a 2 s `AbortController` timeout and `router.replace`s to `/chat/` or `/onboarding/1-welcome/` based on `onboarding_complete`. Probe failures default to onboarding so a fresh install with no backend reachable still reaches the wizard within the timeout.
3. `191c370 [FIX] frontend: wizard Step 5 LLM Continue ships key inline, no Test gate` — BYOK Continue used to refuse unless Test Key had returned `ok` AND the submit payload omitted `key` entirely (so even the gate-lifted submit would have been rejected by the backend). Decoupled Continue from Test Key (Test Key remains as an optional pre-flight affordance), validated non-empty key on Continue, and added `key?: string` to `LlmStepPayload` so the field is typed end-to-end. Backend validates via litellm and writes to keyring atomically — same code path as Test Key, just inlined into the submit.
4. `025543e [FIX] frontend: wizard StepHandoff submits HANDOFF and redirects to /chat` — the handoff screen subscribed to `ONBOARDING_COMPLETE` but never submitted the HANDOFF step, so `finalize_wizard` never ran and the user was trapped on `/onboarding/8-handoff/` forever. Wired `submitStep(WizardStepId.HANDOFF, {})` on mount, redirect on the submit reply (not the broadcast — broadcasts can be lost across the WS reconnect cycle, see caveats), and kept the broadcast subscriber as a secondary trigger. Added `HandoffStepPayload = Record<string, never>` to the discriminated union; this surfaced a pre-existing inference error in `StepVoice` that I fixed by adding the optional `elevenlabs_configured` flag to `VoiceSettings`.
5. `1d15800 [FIX] frontend: WS validator no longer rejects bare {type:"pong"} acks` — the strict `isAetherEvent` check required `data` to be an object, which dropped the backend's heartbeat ack `{"type":"pong"}` and triggered a `console.warn` every 25 s. Replaced with a coercer that defaults `data` to `{}` and `timestamp` / `source_module` to safe fallbacks; recognized `pong` inline before dispatch and stamped `lastPongAt`. The 30 s reconnect cycle persists after this change — see caveats.
6. `5986e56 [UI] welcome + chat empty state + sandbox persona polish` — Welcome subtitle tightened to "Private. Yours. Pick who you want to talk to."; chat empty state subtitle now "Local-first, yours alone. Type when ready." (was "They're running on your machine. Speak freely." — voice-implying); Sandbox → Persona tab gets per-persona `hue` swatches matching the wizard's visual language, active card flexes swatch + name + tagline, footnote rephrased from a docs pointer to actionable guidance.

### What was tested

- `pytest tests/unit/test_brain_sanitizer.py` → 11/11 pass (regression + true-opener + edge).
- `npm run typecheck` → clean for every file I touched. One pre-existing motion-typing error in `frontend/components/wizard/WizardStepShell.tsx:31` remains (`className` not on `motion.section`'s typed props with the shipped framer-motion version) — not a regression and didn't block dev.
- `playwright-cli` end-to-end walk against fresh `%LOCALAPPDATA%\aether\aether\` state (deleted `config.yaml` + `wizard_state.yaml`):
  - `/` → redirected to `/onboarding/1-welcome/` within 2 s ✓
  - Walked Welcome → Avatar (Aurora) → Personality (Warm & supportive) → Name (default "Aurora") → LLM (BYOK OpenAI, key from `OPENAI_API_KEY` env, **clicked Continue without clicking Test Key**) → Voice (Text only) → Terms (agree) → Finish → handoff → landed in `/chat/` ✓
  - Sent "Say hello in one sentence." → assistant streamed "Hello! It's great to connect with you." back as a full multi-sentence response (sanitizer no longer truncating at the first `!`) ✓
  - Backend `/health` after the run: `onboarding_complete: True`, `persona_active: aurora` ✓
  - Full transcript embedded in the PR description.

### Caveats for the merger

1. **WS reconnect cycle still fires every ~30 s.** Backend log shows clean closes on a 30 s cadence regardless of UI activity, with no app-level message preceding them. Direct Python WS clients (with `websockets` library pings enabled) survive past 90 s against the same backend, which points the cause at the browser side of the connection. My pong-validation fix removed the `console.warn` spam but not the underlying close. I time-boxed the investigation — escalate with Chrome devtools open during the 30 s closure to see whether the close frame originates client-side (and which code dispatches it) or server-side (likely websockets `ping_timeout`). The user-facing impact is small today: each reconnect is sub-second and the heartbeat keeps state coherent, but it WILL race with one-shot broadcasts (e.g., `ONBOARDING_COMPLETE`) — that's why the StepHandoff fix relies on the submit reply rather than the broadcast.
2. **Frontend `LlmProvider.GUEST` serializes to `"guest"` but the backend expects `"aether_guest"`.** Validators.py line 191 hardcodes the canonical id. Out of scope for this session (the OpenAI BYOK path is the test target and works); fixing it is a one-line frontend rename or a backend alias.
3. **`StepVoice` ElevenLabs path is still typed loosely.** I added `elevenlabs_configured?: boolean` to `VoiceSettings` to clear the inference error my discriminated union widening introduced; the wizard sends the marker but backend treats voice settings as opaque pass-through. If Agent 2's voice work tightens this contract, revisit.
4. **Pre-existing `WizardStepShell` motion-typing error is still there.** Not a regression. Either the framer-motion version needs to bump or the `<motion.section>` should be replaced with a typed wrapper. Out of scope for my deliverables.
5. **No new `EventType` values added.** Per integration contract — kept `WIZARD_STEP_SUBMIT` / `WIZARD_STEP_RESULT` / `ONBOARDING_COMPLETE` / `PERSONA_CHANGED` / `PROVIDER_CHANGED` as the only events I rely on.
6. **Files touched are limited to my whitelist:** `frontend/**`, `src/brain/sanitizer.py`, `tests/unit/test_brain_sanitizer.py`, `RUNWAY.md` (per the handoff instructions). `src/brain/handler.py`, `src/brain/response_formatter.py`, `src/onboarding/handler.py` were read-only inspection.

---

## What's proven working

1. **Backend boots** — `.venv/Scripts/python.exe -m src.main` starts health (:8767), WebSocket (:8765), persona loader, memory, brain, onboarding, probe handlers. No import errors, no stale-module references, no Don-specific path assumptions.
2. **Config system works** — first boot seeds `%LOCALAPPDATA%\aether\aether\config.yaml` from `configs/default_config.yaml`. `onboarding.complete: false` until wizard runs.
3. **Wizard E2E via WS client** — direct Python test drives all 8 steps (welcome → avatar → personality → name → llm + real OpenAI key validation → voice → terms → handoff). Result: `config.yaml` written with `onboarding.complete: true`, persona=aurora/warm_supportive, provider=openai, tier_map pointing at `openai/gpt-4o-mini` / `openai/gpt-4o`. Keys stored in OS keyring.
4. **Chat E2E** — after wizard, `{type:"user_message", data:{text:"...", mode:"text"}}` flows through `USER_MESSAGE` → complexity router → `call_with_fallback` → litellm → OpenAI → `RESPONSE_START` → streaming `RESPONSE_TEXT_CHUNK` events → `RESPONSE_TEXT_READY` → `RESPONSE_END`. Verified first-call latency ~8.5s (fast tier, OpenAI cold start). Streamed content: `"Hello! How can I assist you today?"`.
5. **Frontend scaffolded and renders** — `cd frontend && npm install --legacy-peer-deps && npm run dev` starts on :3000. Walks the user through screens 1 (Welcome) → 2 (Avatar grid with all 12 letter-in-disc placeholders) → 3 (Personality 12-archetype grid) → 4 (Name, pre-filled) → 5 (LLM with BYOK form, provider dropdown, masked key input).
6. **Contract fixes landed** — backend now accepts the ONBOARDING-SPEC.md canonical field names the frontend sends (`selected_avatar_id`, `selected_archetype`, `llm_provider`, `llm_tier_map`, `voice_mode`, `voice_settings`, `telemetry{}`, `accepted_terms_at`).
7. **Commits pushed:** https://github.com/dbhavery/aether/tree/dev

---

## What's broken / not yet working

1. **Frontend: Step 5 → Step 6 advance hangs in browser** (works via direct WS). After entering OpenAI key and clicking Continue, the UI reports "1 error" and stays on Step 5. Backend did NOT log a `wizard_step_submit` during the failure — frontend may be failing before WS send.
   - First thing next session: open browser DevTools on the frontend, watch the Console + Network (WS tab) when clicking Continue on Step 5. Compare to the working direct-WS payload shape.
   - The frontend's `StepLlm.tsx` likely has a validation step (e.g. requiring `Test key` to pass) that isn't wired to just-continue. Or the test-key round-trip depends on `LLM_KEY_TEST_RESULT` which the backend sends but frontend may not subscribe to correctly.
2. **Home page routing gate stuck** — `http://127.0.0.1:3000/` shows "Starting Aether…" indefinitely instead of redirecting to `/onboarding/1-welcome/`. Workaround: navigate directly to `/onboarding/1-welcome/`. Fix: `app/page.tsx` reads `session.onboardingComplete` but the initial health fetch may race the render. Force the redirect via `useEffect` or server component check.
3. **Response sanitizer truncates text** — the brain emitted full streaming response `"Hello! How can I assist you today?"` but `RESPONSE_TEXT_READY` carried only `"Hello!"`. `src/brain/sanitizer.py` or `response_formatter.py` is stripping too aggressively. Chat chunks stream correctly; only the final `RESPONSE_TEXT_READY` payload is truncated.
4. **Ollama errors clutter logs** — memory embeddings default to `nomic-embed-text` via Ollama which isn't running. Non-fatal (handled in try/except) but noisy. Fix: make embeddings lazy/optional; only embed if Ollama is reachable on boot.
5. **LLM router level-3 classifier tries Ollama first** — classifier is hardcoded to use FAST tier via Ollama even when config says OpenAI. Works by accident because fallback cascades to main tier. Worth cleaning up so the classifier uses the user's configured FAST model.
6. **Frontend WS keeps reconnecting every ~30s** — probably heartbeat mismatch. Server replies `{type:"pong"}` to `{type:"ping"}` but the frontend's `ws.ts` may expect a different shape. Low priority — reconnects are fast and transparent.
7. **Voice + avatar modules not yet rewritten for v1.0** — `src/voice/pipeline.py` still references `wake_word.py` and `speaker_verify.py` which we're dropping. Will fail the moment onboarding completes with `voice.mode: local`. For now voice stays at `mode: off` — it's a feature-gate in startup.py. Needs rewrite in a future session.
8. **Personas have no assets** — `personas/_example/` has placeholders, none of the 12 canonical packs (aurora/caelum/etc) exist with real portraits, voices, or system prompts. Wizard UI shows letter-in-disc placeholders. P4 work — generating the persona packs.

---

## How to resume (next session kickoff)

```bash
cd C:/Users/dbhav/Projects/aether
git checkout dev && git pull
py -3.13 -m venv .venv   # if not already
.venv/Scripts/activate
pip install --no-audit -r requirements.txt
# (optional) pip install torch==2.7.0+cu128 torchaudio==2.7.0+cu128 --index-url https://download.pytorch.org/whl/cu128

# backend
.venv/Scripts/python.exe -m src.main

# frontend (new terminal)
cd frontend
npm install --legacy-peer-deps
npm run dev

# in browser
open http://127.0.0.1:3000/onboarding/1-welcome/
```

Expected at fresh boot: wizard screens render, backend logs `wizard_step_submit`/`wizard_step_result` as you click Continue on steps 1–4, then Step 5 hangs (the bug documented above).

---

## Immediate next actions

Priority order:

1. **Fix Step 5 → Step 6 advance** (est. 30 min).
   - Open DevTools on `http://127.0.0.1:3000/onboarding/5-llm/` while wizard is mid-flow.
   - Watch the WebSocket Messages tab.
   - If `wizard_step_submit` isn't sent, bug is in `StepLlm.tsx` — inspect the Continue handler, check if `Test key` must pass first, or if payload shape is wrong (`selected_avatar_id` works now — verify `llm_provider`/`llm_tier_map` pass through correctly).
   - If the submit IS sent but no `wizard_step_result` is received, bug is the frontend's subscribe logic for request_id correlation.
2. **Fix home page routing gate** — force `useRouter().replace("/onboarding/1-welcome/")` in a `useEffect` when `!session.onboardingComplete` and `session.onboardingComplete !== null`.
3. **Fix sanitizer truncation** — read `src/brain/sanitizer.py` and `response_formatter.py`. Likely regex or length cap is cutting the response at the first `!`. Remove or relax the rule.
4. **Drive full UI flow through to chat** — once 1–3 land, click through screens 5→8, land on `/chat`, type a message, verify streaming response appears.
5. **Start a pywebview desktop shell** — tiny Python file that launches a native window pointing at `frontend/out/index.html` (after `npm run build`).
6. **Generate at least 1 real persona pack** — portrait + 4 state images + voice reference + system prompt for Aurora. Proves the pack pipeline end-to-end and gives the wizard real art instead of letters.
7. **Rewrite `src/voice/pipeline.py`** — push-to-talk model, strip wake_word/speaker_verify. Then enable `voice.mode: local` in the wizard can actually boot.

---

## Session artifacts

- Config written to: file:///C:/Users/dbhav/AppData/Local/aether/aether/config.yaml
- Backend log: `/tmp/aether_backend.log` (tmpfs — gone after session)
- Frontend log: `/tmp/aether_frontend.log`
- Playwright session: `.playwright-cli/` (now gitignored)

---

## Locked decisions (unchanged)

All from prior sessions. See git history or `docs/PRODUCT-PLAN.md § 1`.

- MIT license.
- Next.js + pywebview UI.
- LivePortrait-only avatar.
- Push-to-talk (no wake word).
- OS keyring for secrets.
- 10–12 bundled personas per `docs/PERSONA-SCHEMA.md § 7`.
- Evolve the existing `aether` repo; `master` stays as showcase snapshot.
- Python 3.13 + Tailwind 3 + Turbopack off (v3/no-turbopack is the stable combo on Windows).

---

## Commit log this session

```
e02a194 [FRONTEND] Scaffold Next.js 15 UI with wizard, chat, sandbox, video modes
ecc88ab [INTEGRATION] Wire backend for frontend E2E + fix path/contract bugs
77c11dd [DOCS] Update RUNWAY.md with session-2 handoff
2c2e5c6 [FIX] Resolve installation UUID race between wizard and secrets
e289a05 [RELEASE] Update requirements, .env.example, README for public v1.0
f503055 [REFACTOR] Rewrite core/startup; fix core/server and core/shutdown
c3c30f6 [REFACTOR] Rewrite brain/persona + brain/handler for v1.0 scope
e692815 [FEATURE] litellm-based tier router, streaming client, fallback, cost
d2fbd45 [FEATURE] Persona pack loader (src/personas/)
d4efa27 [FEATURE] Onboarding wizard backend (src/onboarding/)
a0a1320 [TYPES] Add wizard events; remove obsolete module events
9653a63 [INFRA] Platformdirs-based paths, OS keyring secrets, AetherConfig
702c327 [SCOPE-CUT] Remove private modules; rename desktop to desktop_legacy
```

---

## Anti-drift reminders

- Backend runs only on Python 3.13 — `py -3.13 -m venv .venv`. 3.14 breaks pydantic-core wheel builds.
- Frontend uses Tailwind 3 — do NOT upgrade to 4.x without Turbopack being disabled in Next and a working `@tailwindcss/postcss` combination (neither was stable on Windows as of this session).
- Localhost WS bypasses auth; non-localhost still needs the token from `/auth/token`.
- Wizard config write invalidates the shared config cache; if brain is still talking to the wrong provider after a finalize, check `src/onboarding/finalizer.py::_reset_shared_config_cache`.
- `_LLM_TEST_MAX_TOKENS = 16` in `src/onboarding/validators.py` — do not drop to 1; newer OpenAI models refuse.
- `.playwright-cli/` and `.superpowers/` are gitignored.

---

## Agent 3 complete — first three persona packs (branch `feature/personas-first-three`)

Shipped three end-to-end persona packs (the remaining nine of the twelve in PERSONA-SCHEMA.md §7 can be produced in a future session with the same tooling). The wizard grid now has real art instead of letter-in-disc placeholders.

### Packs delivered

| id     | archetype              | disk size | portrait + 4 states | voice reference / sample |
|--------|------------------------|-----------|---------------------|--------------------------|
| aurora | warm_supportive        | 7.9 MB    | 1024x1024 each, OpenAI gpt-image-1.5 | 20s / 4s @ 24kHz mono, LibriVox 'Old Fashioned Roses' (CC0) |
| caelum | analytical_precise     | 7.8 MB    | 1024x1024 each, OpenAI gpt-image-1.5 | 20s / 4s @ 24kHz mono, LibriVox 'Dover Beach' (CC0) |
| luma   | playful_witty          | 7.5 MB    | 1024x1024 each, OpenAI gpt-image-1.5 | 20s / 4s @ 24kHz mono, LibriVox 'Jabberwocky' (CC0) |

Total persona payload: ~23.2 MB on disk. All three pass `scripts/persona_generator/audit_pack.py --all` with 0 issues. The loader's acceptance-criterion check:

```bash
.venv/Scripts/python.exe -c "from src.personas import get_persona_manager; mgr = get_persona_manager(); print([p.manifest.id for p in mgr.list_all()])"
# ['aurora', 'caelum', 'luma']
```

### Generator tooling (scripts/persona_generator/, ~104 KB)

- `prompts.py` — per-persona PersonaPromptSpec dataclasses with locked slop-exclusion negatives.
- `_backends.py` — image generation with fallback chain (fal → OpenAI gpt-image-1.5 → Gemini 3). Centralises PIL normalisation to exactly 1024x1024 RGB.
- `generate_portrait.py` + `generate_states.py` — one-persona portrait and four-state pipeline; each writes its exact prompt+model into the pack's `avatar/README.md` for reproducible regeneration.
- `source_voice.py` — downloads an MP3/WAV URL, trims via ffmpeg to schema-compliant 20s reference + 4s sample at 24kHz mono.
- `preprocess_landmarks.py` — 68-point face landmark extraction with face_alignment → dlib → stub fallback.
- `audit_pack.py` — thin CLI over `src.personas.audit` (exit 0 clean / 1 issues / 2 schema-validation-failure).
- `README.md` — one-persona recipe + troubleshooting.

Run `python scripts/persona_generator/README.md` for the full recipe. Remaining nine personas (milo, ivy, atlas, wren, rhea, kai, nova, onyx, sage) can be produced by adding specs to `prompts.py` and running the same pipeline.

### Notable decisions / failures

- **fal balance exhausted** at start of session (`User is locked. Reason: Exhausted balance`). Every portrait + state image went through OpenAI `gpt-image-1.5` via the Images API. Top up fal if a future session wants nano-banana-pro's output characteristics; the backend fallback chain in `_backends.py` already prefers fal.
- **State images generated fresh, not inpainted** from the base portrait. Inpainting at 1024x1024 through the available APIs produced more identity drift than fresh full-portraits sharing a base prompt. The identity anchor at runtime is LivePortrait, which re-reads landmarks from `portrait.png` — state images are expression references for LivePortrait's library, not identity sources.
- **Voice sources: LibriVox Short Poetry collections**. All LibriVox recordings are dedicated to the public domain worldwide (CC0-equivalent). Picked by poem character matching archetype — warm Riley for Aurora, reflective Arnold for Caelum, playful Carroll for Luma. If any voice sounds wrong on review, swap URL in the pack's metadata.yaml and re-run `source_voice.py` with `--force`.
- **.gitignore patched** so `personas/*/voice/*.wav` is committable (the top-level `*.wav` rule was blocking the REQUIRED ship assets in PERSONA-SCHEMA.md §1). LivePortrait's `clips/` and `landmarks.json` stay ignored as before. This was a ship-blocker fix, not a preference change.
- **System prompts hand-authored** per PERSONA-SCHEMA.md §6 step 8 lock. Each distinguishes voice-mode vs text-mode guidance and explicitly bans the "How can I help you today?" service-desk opener.

### Out of scope for this session

- Other nine persona packs (milo, ivy, atlas, wren, rhea, kai, nova, onyx, sage) — tooling is ready; just needs prompt specs + voice sources.
- LivePortrait preprocessing of idle clips (`avatar/clips/*.mp4`). Those are machine-generated and will be produced on first load per PERSONA-SCHEMA.md §1.
- QA conversations against each persona (PERSONA-SCHEMA.md §6 step 9). System prompt behaviour needs live-testing before the packs get bundled into an installer.
