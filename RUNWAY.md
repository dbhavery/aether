# RUNWAY.md — Session Handoff

**Last session:** 2026-04-17 — full-UI self-test + B1/B2/B3 fixes landed on top of the three-agent combine.
**Branch:** `dev` (pushed to origin @ `7ec4b88`).
**Latest commit:** `7ec4b88 [FIX] Persona activation, portrait serving, and health CORS (B1/B2/B3)`.

**Status:** **v1.0 core loop is working end-to-end as a real user.** Fresh-install → wizard (all 8 screens) → chat turn with streaming OpenAI response in the active persona's voice, all validated in a real browser via playwright-cli.

---

## What's confirmed working end-to-end this session

Walked with a real browser on fresh `%LOCALAPPDATA%\aether\aether\` state:

1. `http://127.0.0.1:3000/` on first visit → auto-redirects to `/onboarding/1-welcome/`.
2. Welcome screen: heading, value bullets (Private / Flexible / Real), "Get started" CTA.
3. Avatar grid: all 12 personas render. **Aurora / Caelum / Luma show real AI-generated portraits** via `http://localhost:8767/personas/<id>/avatar/portrait.png` (served by the backend's StaticFiles mount). The nine packs that don't exist yet fall back to letter-in-disc placeholders.
4. Personality grid: 12 archetype cards with hand-authored example snippets.
5. Name: pre-fill, live preview, 40-char limit enforced ("Keep it to 40 characters or fewer."), emoji rejected ("No HTML, markdown, or emoji in v1.0").
6. LLM: BYOK path with OpenAI + env-variable key → Continue advances (previously the big blocker, now solid).
7. Voice: "Skip" path accepted.
8. Terms: "Finish setup" enables on agreement click.
9. Handoff: backend finalizer writes config.yaml, creates ChromaDB collection for the persona, stamps installation UUID, **now also calls `persona_manager.set_active(id)`** — the runtime persona is live, not just the config entry.
10. `/chat`: full streaming OpenAI response renders, in Aurora's persona voice (no forbidden service-speak like "How can I assist you today?"). Aurora's first real reply was: *"I like helping by listening closely, asking thoughtful questions, and offering clear, grounded ideas that actually move things forward—no fluff, just steady support."*
11. Multi-turn works. Mode-switcher Chat ↔ Sandbox ↔ Video preserves conversation state. Sandbox's six tabs all render with correct content (Persona marks Aurora as active, LLM shows provider + tier map, Memory shows clear-button, About shows version).
12. Post-onboarding `http://127.0.0.1:3000/` reload now correctly redirects to `/chat` (previously sent users back to Step 1 — CORS was silently blocking the health probe).

## The three B-fixes landed this session

- **B1** — `finalize_wizard` now calls `get_persona_manager().set_active(state.selected_avatar_id)` so the brain's `_get_active_persona_prompt()` picks up the active pack's `personality.system_prompt`.
- **B2** — Backend `/health` app mounts `personas/` under `/personas` via `StaticFiles`; frontend `PersonaPortrait` loads real portraits from that URL with onError fallback to the placeholder gradient.
- **B3** — `CORSMiddleware` added to the health app with `localhost:3000` / `127.0.0.1:3000` / `null` (file:// for pywebview) in the allow list.

## Open bugs (from self-test, NOT fixed yet)

**Medium:**

- **B4. Checkbox-component click target.** On Step 7 the "I agree" custom checkbox doesn't toggle when you click the box itself — only the label text works. Likely `pointer-events-none` on the inner visual element or a missing `<input>` → `<label htmlFor>` link. File: `frontend/components/ui/Checkbox.tsx`.

- **B5. Backend OpenAI tier presets use invalid model names.** `TIER_PRESETS["openai"]` in `src/brain/llm_router.py` is `openai/gpt-5-mini`, `openai/gpt-5`, `openai/gpt-5-thinking` — none of those exist on OpenAI's API. The flow works accidentally because the frontend sends its own `llm_tier_map` that overrides. Users who don't touch the tier map will get broken chat. Fix: `openai/gpt-4o-mini` (fast), `openai/gpt-4o` (main), `openai/o1-preview` or similar (heavy). Same audit for anthropic/google/groq presets — any referenced model that doesn't currently exist on the live API needs to be swapped.

**Low / cosmetic:**

- **B6. Ollama embedding noise.** `src.memory.embeddings` fires `localhost:11434/api/embeddings` on every user/assistant message. Currently logs an ERROR on every turn. Gate behind a startup probe with a 60s retry cache so the log noise stops.
- **B7. Favicon 404.** Add `frontend/app/favicon.ico`.
- **B8. Preview-voice button has no observable feedback.** Probe handler fires (logs would confirm at debug level) but user hears nothing / sees nothing unless TTS pipeline is fully online. Consider a toast ("Playing Aurora's voice sample…") or verify sounddevice is playing the right file.

**Pre-existing carry-forwards (not regressions):**

- `LlmProvider.GUEST` ↔ `aether_guest` id mismatch — one-line fix on either frontend or backend.
- `WizardStepShell` framer-motion typing error — needs version bump or `motion.section` replacement.
- CI red on `requirements.txt` numpy / chatterbox-tts conflict.
- fal.ai balance exhausted — need to top up before the other 9 persona packs can be generated.
- "30s WS reconnect cycle" described in earlier RUNWAY — did NOT reproduce in this session's 9-minute browser session. May have been tied to an older frontend build; keeping on the watch list but no longer confirmed.

---

## Immediate next session's job

Primary: **Fix B4 + B5 so first-contact chat is reliable without frontend tier-map overrides.** Then do a second full self-test pass to confirm regressions from the portrait/CORS work didn't seep into other surfaces.

Secondary: Fix `LlmProvider.GUEST` id mismatch, the CI `requirements.txt` conflict, and add the favicon. These are all ~10 minutes each.

After that: author the remaining canonical persona packs under `personas/`.

---

## How to resume

```bash
cd C:/Users/dbhav/Projects/aether
git checkout dev && git pull
py -3.13 -m venv .venv   # if not already
.venv/Scripts/python.exe -m pip install -r requirements.txt

# terminal A
.venv/Scripts/python.exe -m src.main

# terminal B
cd frontend && npm run dev

# browser → http://127.0.0.1:3000/
```

First-boot expectations: backend loads 3 persona packs (aurora/caelum/luma), binds :8765 + :8767, mounts `/personas` static. Frontend serves `:3000`. Wizard end-to-end with OpenAI BYOK takes under 90 seconds, lands in chat with a persona-voiced reply in another 5-10 seconds on first OpenAI call.

---

## Locked decisions (unchanged)

MIT license. Python 3.13 only (3.14 breaks pydantic-core). Tailwind 3, Next.js dev without Turbopack. OS keyring for secrets. 10-12 bundled personas (3 shipped real, 9 pending). `master` stays as showcase; all work on `dev`.

---

## Commit log (session-culminating)

```
7ec4b88 [FIX] Persona activation, portrait serving, and health CORS (B1/B2/B3)
ef0facc [DOCS] Update RUNWAY with three-agent combine state
05ac5ba [MERGE] Agent 1: wizard fixes (Step 5 advance, routing gate, sanitizer, WS pong, polish)
3238149 [MERGE] Agent 2: pywebview desktop shell + push-to-talk voice pipeline rewrite
30b8eb3 [MERGE] Agent 3: persona packs (aurora/caelum/luma) + generator tooling
```

---

## Anti-drift reminders

- Python 3.13 only. 3.14 breaks pydantic-core wheel builds.
- Tailwind 3 + no Turbopack = the stable combo on Windows.
- `/personas` is now a live URL path served by the health app; frontend's `NEXT_PUBLIC_AETHER_ASSETS_BASE` defaults to `http://localhost:8767/personas`. If the port ever changes, update that env var.
- OpenAI keys in OS keyring under service `aether.openai` + username = installation UUID from `config.aether.user_installation_id`. Wizard also has a UUID-race workaround — installation_id is stamped into `wizard_state.yaml` on first save so keys written during the wizard stay reachable after finalize.
- `.playwright-cli/` is gitignored.
- The 9 non-existent persona packs (milo, ivy, atlas, wren, rhea, kai, nova, onyx, sage) gracefully fall back to placeholders — do NOT touch the portrait loader to "handle" them; it already does.
