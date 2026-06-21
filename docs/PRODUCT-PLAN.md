# Aether v1.0 — Productization Plan

**Status:** Active planning → execution
**Branch:** `dev`
**Starting state:** March-24 showcase snapshot at `master`, MIT-licensed, PySide6 UI, out-of-date relative to the upstream codebase.
**Target:** Public product release with onboarding wizard, 10–12 pre-made personas, bring-your-own-key LLM, local-first voice + avatar, portfolio-embedded demo.
**Not this release:** Full-body photorealistic avatar, GraphRAG memory, agentic workflows, mobile client, vision input, tool execution. Those are for the ground-up rebuild that follows v1.0.

---

## 1. Binding Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Evolve the existing `aether` repo**, don't fork. | Preserves git history, public GitHub link, SEO. Productization is a fork in spirit, not in git. |
| 2 | **License stays MIT.** | Already published. Appropriate for a consumer app. Relicensing retroactively is complicated and unnecessary. |
| 3 | **Branches:** `master` = stable showcase snapshot; `dev` = productization; `feature/*` off `dev`. | Protects the showcase state that's already linked from CV/portfolio. |
| 4 | **Legacy PySide6 desktop stays** in the repo as `src/desktop/` — read-only "legacy mode". | Don's locked 2026-04-11 rule: HTML/CSS via pywebview for all new UI. PySide6 pre-dates the rule. Don't delete, don't extend. |
| 5 | **New product UI:** Next.js 15 + React 19 + TypeScript, loaded by pywebview. | Matches portfolio stack (`dbhavery.ai`), matches locked rule, lets same codebase serve desktop AND the portfolio demo widget. |
| 6 | **Backend:** Python 3.13 + FastAPI + websockets. No change from current. | Existing modules already use this pattern. |
| 7 | **Lip-sync engine v1.0:** LivePortrait (TensorRT). | Best quality/VRAM ratio for headshots. Other engines (Ditto, MuseTalk, FlashHead) stay in the upstream codebase and can be ported later if needed. |
| 8 | **Voices:** Chatterbox Turbo + cloned from royalty-free reference samples. ElevenLabs optional BYOK. | Avoids redistribution ambiguity. Users never need a cloud voice key to get voice. |
| 9 | **Memory:** ChromaDB hybrid search ships in v1.0, per-persona isolated. | It's built, it works, it's a companion differentiator. Strip any Don-specific data. |
| 10 | **Wake word:** **Removed for v1.0.** Replaced by push-to-talk (spacebar hold). | Porcupine requires per-user key registration — too much onboarding friction. Wake word returns in v1.1 if demand justifies. |
| 11 | **LLM routing:** Unified through `litellm`. Users pick providers in the wizard. | Single integration point, supports 100+ providers, already in the upstream codebase deps. |
| 12 | **Monetization v1.0:** Free download, no billing. Reassess at 30 days post-launch. | Remove all friction until we have signal that people care. |
| 13 | **Installer:** Inno Setup for Windows first. macOS/Linux later. | The upstream codebase already has Inno Setup scaffold under `packaging/`. Majority of the audience is Windows. |
| 14 | **Portfolio demo:** 60-second hero video + inline text-chat widget (Groq free tier). No live voice/avatar demo in v1.0. | Avoids hosting a GPU backend before we know demand exists. Video shows the product at its best; widget proves the shell works. |

---

## 2. Scope

### In v1.0

- **Chat mode** — text conversation with streaming responses.
- **Voice mode** — push-to-talk, local STT + TTS, same transcript shown in chat.
- **Video mode** — headshot avatar with lip-sync during speech, idle animation during silence.
- **Sandbox/settings mode** — configure LLM provider, voice settings, persona switch, theme, memory viewer.
- **Onboarding wizard** — 7 screens, first-run only, config written to `%APPDATA%/aether/`.
- **10–12 personas** — bundled packs, each with avatar + voice + personality. User can mix avatar+personality freely.
- **BYOK LLM** — Anthropic, OpenAI, Google, Groq, OpenRouter, Ollama (local).
- **BYOK voice (optional)** — ElevenLabs if user wants cloud TTS/STT.
- **Per-persona memory** — conversation history + facts, ChromaDB-backed, isolated per persona.
- **Windows installer** — Inno Setup with WebView2 runtime check, model download on first run.
- **Auto-update** — check-on-launch using GitHub releases.
- **Opt-in telemetry** — nothing sent without explicit user consent in wizard.
- **Crash reporting** — local log files, optional upload on user request.

### Deferred to v2 (the ground-up rebuild)

- Full-body photorealistic avatar (Gaussian Splatting, dual-GPU architecture).
- True real-time interruption / barge-in.
- Agentic tool use (web scraping, code execution, research agents).
- Vision input (image recognition, OCR, screen understanding).
- Mobile client.
- Multi-device sync.
- GraphRAG / semantic-graph memory.
- Any hosted paid tier.

---

## 3. Phased Execution

### P0 — Architecture freeze and repo scaffold

**Output:** this document, ARCHITECTURE-V2.md, PERSONA-SCHEMA.md, ONBOARDING-SPEC.md, LLM-PROVIDERS.md, empty `personas/` and `frontend/` directories, initial commit on `dev`.

**Acceptance:**
- All planning docs committed.
- `dev` branch pushed to origin.
- Task list seeded and visible.

**Status:** In progress (this session).

### P1 — Backend port from the upstream codebase

**Output:** Fresh port of `core/`, `shared/`, `voice/`, `avatar/`, `brain/`, `memory/` from the current upstream codebase into `src/`. De-personalized. Legacy PySide6 `src/desktop/` renamed to `src/desktop_legacy/` and marked read-only.

**Acceptance:**
- Backend starts cleanly with no hardcoded Don-specific paths.
- `python -m src.main` boots WebSocket (8765), Health (8767), avatar MJPEG (8770).
- Existing tests (that don't require Don's data) pass.
- Speaker verification is optional (behind a config flag, default off).
- Wake word is gone (push-to-talk trigger event exists instead).

### P2 — Frontend scaffold

**Output:** Next.js 15 app under `frontend/` with three modes (Chat, Sandbox, Video) and a stub onboarding wizard. Dark theme design system (fresh, not `don-design-system` tokens per locked 2026-03-22 rule). WebSocket client that speaks existing port-8765 protocol. pywebview shell under `desktop/` that loads the static export.

**Acceptance:**
- `npm run dev` on 3000 connects to backend on 8765, sends `{type:"user_message", text:"..."}`, displays streamed response.
- `npm run build && npm run export` produces a static bundle that pywebview loads as native window.
- All three modes navigable. Video mode renders MJPEG stream from backend:8770.

### P3 — Onboarding wizard

**Output:** 7-screen wizard UI + state machine + config writer. LLM provider cards with key validation. Voice setup with auto-detection of GPU/VRAM.

**Acceptance:**
- Fresh install (no `%APPDATA%/aether/config.yaml`) boots to wizard.
- Completing wizard writes valid config and drops user into Chat mode.
- Every API key entered is validated against provider (1 test call) before accepting.
- Partial wizard state is persisted; user can close and resume.

### P4 — Persona pack pipeline

**Output:** 10–12 persona packs under `personas/`, each with portrait, state images, idle clips, voice reference, personality prompt, license metadata. Generation tooling under `scripts/persona_generator/` so future personas can be added deterministically.

**Acceptance:**
- Each persona has all required assets per PERSONA-SCHEMA.md.
- Licensing audit: every source asset documented, commercial-use clean.
- Switching personas in Sandbox mode reloads avatar + voice within 3 seconds.
- Each persona generates a coherent 10-turn conversation in a test harness.

### P5 — Integration and polish

**Output:** End-to-end test pass, installer, auto-update, crash reporting scaffolding, landing page copy, PRIVACY.md, TERMS.md.

**Acceptance:**
- Inno Setup installer produces a <500 MB installer (minus model weights, which download on first run).
- Fresh Windows VM: install → wizard → chat → voice → video in under 10 minutes.
- PRIVACY and TERMS reviewed by an actual human (not me) who has done consumer-app terms before.
- Auto-updater tested: release v1.0.1 → running v1.0.0 client detects, downloads, relaunches.

### P6 — Portfolio demo + launch

**Output:** 60-second hero video, inline text-chat widget embedded in portfolio (`dbhavery.ai`), launch posts drafted for HN/ProductHunt/Reddit/LinkedIn.

**Acceptance:**
- Video shows all three modes, at least 4 different personas, lip-sync under good lighting.
- Widget on portfolio connects to Groq free tier, shows streaming text response.
- Launch checklist complete, first post scheduled.

---

## 4. Work estimation

| Phase | Calendar weeks (solo + AI agents) | Compressible with parallel tracks? |
|------:|----------------------------------:|:----------------------------------:|
| P0 | 0.5 | No (single-stream planning) |
| P1 | 1.5 | Partial (core + voice + avatar in parallel) |
| P2 | 1.0 | Partial (shell + wizard in parallel) |
| P3 | 1.0 | No (depends on P2) |
| P4 | 2.0 | Yes (per-persona parallelism) |
| P5 | 1.0 | Yes (installer + docs + QA parallel) |
| P6 | 0.5 | Yes (video + widget parallel) |
| **Total** | **7.5 weeks** | **5–6 weeks compressed** |

---

## 5. Key risks

1. **Avatar quality variability across 10–12 personas.** Some source portraits animate better than others in LivePortrait. Mitigation: generate 20 candidates, keep the 12 that pass QA.
2. **Model download sizes scare first-time users.** Chatterbox + faster-whisper + LivePortrait models can push first-run downloads past 5 GB. Mitigation: progressive download (text mode works immediately, voice/avatar downloads in background).
3. **Groq free tier rate limits hit portfolio widget** during a launch-day traffic spike. Mitigation: fall back to OpenRouter free models; cap widget sessions to 3 turns per visitor.
4. **Licensing ambiguity on generated avatars.** Must ensure every portrait was produced by Don's own AI pipeline (per locked feedback rule "AI-generated source models only"). Audit before shipping.
5. **First-contact LLM key friction.** User without any API key has to either install Ollama (6 GB+) or register with a provider. Mitigation: wizard offers a guest mode using Groq free tier with a warning that it's rate-limited and public-keyed.
6. **pywebview WebView2 dependency** on older Windows installs. Mitigation: installer bundles the WebView2 bootstrapper.

---

## 6. Metrics (post-launch)

Track from day one:

- Installs (unique machines via anon installer ID, opt-in).
- Wizard completion rate (by-screen drop-off).
- Time-to-first-message (install → first LLM response).
- LLM provider distribution (which providers users actually pick).
- Most/least used personas.
- Voice/video mode adoption vs text-only.
- Crash rate per hour of runtime.
- Session length distribution.

Decision gate at T+30 days: if installs < 1000 and daily active < 50, re-evaluate scope before committing to the ground-up v2 rebuild.

---

## 7. What happens after v1.0

Per user direction: **v2 is a ground-up rebuild**, not an evolution. Architectural targets set in prior session (see chat history): dual-GPU, Gaussian Splatting avatar, Rust orchestration, C++/CUDA rendering, <1000ms latency budget, GraphRAG memory, full-body presence, indistinguishable-from-human quality bar.

v1.0 exists to:
1. Validate demand before investing v2 engineering time.
2. Build a user base that can beta v2.
3. Generate revenue / attention that justifies a second GPU purchase.
4. Produce real telemetry about which modes/personas/providers matter.

v1.0 and v2 will share almost no code. That's intentional.

---

## Changelog

- **2026-04-17** — Plan created on `dev` branch off `master`@dc92ba3. Binding decisions locked. P0 in progress.
