# RUNWAY.md — Session Handoff

**Last session:** 2026-04-17 — P0 architecture freeze + P1 de-Isabelle pass.
**Branch:** `dev` (pushed to origin).
**Latest commit:** `2c2e5c6 [FIX] Resolve installation UUID race between wizard and secrets`.
**Next session owner:** Finish P1 boot-smoke test and start P2 frontend scaffold.

---

## Where we are

Aether is now publicly installable in principle. Private modules removed, Don-specific paths gone, config + secrets + personas + LLM routing all rewritten with public-install defaults. Onboarding wizard backend built. Everything MIT-licensed and ready for a frontend to drive it.

**Everything shipped this session is on `dev` at https://github.com/dbhavery/aether/tree/dev**

---

## What got done this session

**P0 planning docs** (committed earlier in the session):
- `docs/PRODUCT-PLAN.md` — binding decisions, phases, acceptance criteria.
- `docs/ARCHITECTURE-V2.md` — process topology, ports, config schema.
- `docs/PERSONA-SCHEMA.md` — persona pack format + 12 canonical personas.
- `docs/ONBOARDING-SPEC.md` — 7-screen wizard state machine.
- `docs/LLM-PROVIDERS.md` — litellm abstraction, tier mapping.
- `docs/SYNC-ISABELLE.md` — upstream-port rules.
- `personas/_example/` reference pack.
- `frontend/README.md` placeholder.

**P1 de-Isabelle pass** (later in the session, 10 commits):

1. `702c327 [SCOPE-CUT]` — deleted `src/agents/`, `src/tools/`, `src/notifications/`, `src/media/`, `src/persona/`, `src/data_server/`, `src/shared/key_store.py`. Renamed `src/desktop/` → `src/desktop_legacy/`.
2. `9653a63 [INFRA]` — added `src/shared/paths.py` (platformdirs), `src/shared/secrets.py` (OS keyring), `configs/default_config.yaml` (template). Rewrote `src/shared/config.py` with `AetherConfig` Pydantic model + `get_config()`/`save_config()`/`is_onboarding_complete()`. Legacy API retained.
3. `a0a1320 [TYPES]` — added 5 wizard events (`WIZARD_STEP_SUBMIT`, etc.), removed 8 obsolete events (wake word, speaker verify, notifications, agents, approval, old persona).
4. `d4efa27 [FEATURE]` — full onboarding wizard backend under `src/onboarding/` (state, validators, handler, finalizer).
5. `d2fbd45 [FEATURE]` — persona pack loader under `src/personas/` (models, loader, manager, audit).
6. `e692815 [FEATURE]` — litellm-based tier router + streaming client + fallback chain + cost tracking under `src/brain/` (llm_router.py, llm_client.py, fallback.py, cost.py).
7. `c3c30f6 [REFACTOR]` — rewrote `src/brain/persona.py` (system-prompt builder pulls from active persona pack) and `src/brain/handler.py` (v1.0 streaming chat loop; no tools/agents/emotion tracking).
8. `f503055 [REFACTOR]` — rewrote `src/core/startup.py` (v1.0 boot order with onboarding gate), trimmed `src/core/server.py` (no tools import), `src/core/shutdown.py` (no notifications/persona).
9. `e289a05 [RELEASE]` — updated `requirements.txt` (removed wake-word/agent/notification deps; added platformdirs, keyring, litellm), rewrote `.env.example` (minimal keys; keyring is primary), rewrote `README.md` (public-product framing with install/run/modes/what's-not-in-v1.0).
10. `2c2e5c6 [FIX]` — installation UUID race fix. `secrets._installation_uuid()` now resolves three-tier: config.yaml → wizard_state.yaml → mint. Keys written during wizard stay readable after finalize.

**Static verification** performed:
- `grep` for imports of deleted modules in active src/: only hits are under `src/desktop_legacy/` (expected).
- `ast.parse` across all non-legacy src .py files: clean.

**Dynamic verification NOT performed:**
- No `.venv` existed at `C:/Users/dbhav/Projects/aether/.venv/`. Nobody has actually booted `python -m src.main` yet against the new codebase.
- First thing next session: create venv, `pip install -r requirements.txt`, run `python -m src.main`, watch for import errors or config-load errors.

---

## Immediate next actions

**1. Boot smoke test (5-10 minutes).**
```
cd C:/Users/dbhav/Projects/aether
python -m venv .venv
.venv/Scripts/activate
pip install torch==2.7.0+cu128 torchaudio==2.7.0+cu128 --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt
python -c "from src.shared.config import get_config; print(get_config())"
python -c "from src.personas import get_persona_manager; print(get_persona_manager().list_all())"
python -m src.main
```
Fix any import errors or config-load errors as they surface. Expect: health server starts, persona manager loads (only `_example` until P4), WebSocket starts, no crashes. Voice + avatar stay in `pending_onboarding` state until wizard runs.

**2. Clean up old brain files (15 minutes).**
`src/brain/router.py` and `src/brain/clients.py` are no longer imported by the new handler, but weren't deleted to avoid breaking anything surprise-imported. Now that the new handler lands cleanly, grep for their usage. If nothing else imports them, `git rm` and commit.

**3. Start P2 — frontend scaffold (1-2 hours).**
```
cd frontend
npx create-next-app@latest . --ts --tailwind --app --no-eslint --import-alias "@/*"
```
Then build:
- `lib/ws.ts` — typed WebSocket client matching backend :8765 contract.
- Three mode routes under `app/(shell)/` — chat, sandbox, video.
- Wizard route stubs under `app/(onboarding)/` — 8 pages with navigation but no logic yet.
- `desktop/main.py` — pywebview shell that launches a window pointing at `frontend/out/index.html`.
- Dark theme tokens (fresh; don't use old `don-design-system`).

**4. Start P3 — wizard UI (2-3 hours after P2 shell exists).**
Implement the 7 screens per `docs/ONBOARDING-SPEC.md`. Each screen is a route component that builds a `WizardStepSubmit` payload and sends via WebSocket. Reads results from `WizardStepResult` events. Persists local state via Zustand (frontend mirror of backend state).

**5. Start P4 — persona pack generation (spread over multiple sessions).**
Per `docs/PERSONA-SCHEMA.md` §6. Can run parallel to P2/P3. Each of the 12 personas takes 2-4 hours: portrait → states → clips → voice reference → system prompt → QA → metadata audit.

---

## Known issues / follow-ups

- **venv not created.** User must set this up before the first real boot.
- **`src/brain/clients.py` and `src/brain/router.py`** left in tree; likely safe to delete but confirm first with grep in the next session.
- **`src/brain/content_guard.py`, `sanitizer.py`, `response_formatter.py`** were kept and are still imported by the new brain/handler.py. They may have Isabelle-ish content; worth an audit pass.
- **`src/shared/vram_manager.py` and `api_registry.py` and `api_tests.py` and `validation.py` and `protocols.py`** — imported by deleted modules but not used by new code. Check if they're dead.
- **`src/memory/store.py`** — still has `get_recent_turns()` and `search_memory()` but may assume a single-user schema. Should support per-persona collection isolation per `docs/ARCHITECTURE-V2.md` §4.6. Audit during boot smoke test.
- **CI (`.github/workflows/ci.yml`)** — exists but not reviewed this session. May be running against deleted modules and turning red on `dev`. Check `gh run list --branch dev --limit 1` first thing next session.
- **Aether Guest endpoint not implemented.** Wizard Screen 5 Card C references it; backend will 404 until we provision the Cloudflare Worker proxy. Guest mode blocked in validators for now (see `validators.py` comment).
- **No tests** written for the new modules (onboarding, personas, llm_router, fallback, paths, secrets). Worth a P1.5 test-writing pass before P2 gets large.

---

## Locked decisions (do not revisit without explicit reversal)

1. Evolve existing `aether` repo, don't fork.
2. License stays **MIT**.
3. `master` = stable showcase; `dev` = productization.
4. Legacy `src/desktop/` → `src/desktop_legacy/`, not deleted, not booted.
5. Next.js + pywebview for the product UI.
6. LivePortrait only for v1.0 avatar engine.
7. Push-to-talk (no wake word) for v1.0.
8. Per-persona ChromaDB isolation.
9. OS keyring as primary key store; env-var fallback only.
10. `litellm` as the sole LLM-provider interface.
11. Windows-first installer.
12. 10-12 bundled personas per `docs/PERSONA-SCHEMA.md` §7.

---

## Open questions for Don (none blocking P1 boot)

Same as previous RUNWAY section — see the session-1 handoff. Summary:
1. Who drafts `TERMS.md` and `PRIVACY.md`?
2. Portfolio embed approach: iframe or inline React?
3. Aether Guest endpoint hosting (Cloudflare Worker cost OK?).
4. Telemetry tool choice (PostHog recommended).
5. macOS/Linux v1.0 or defer?
6. Voice reference WAV source budget.

---

## How to resume

1. `cd C:/Users/dbhav/Projects/aether && git checkout dev && git pull`
2. Read this file.
3. Run the boot smoke test commands (item 1 in "Immediate next actions").
4. Proceed to P2 frontend scaffold.
5. Commit atomically per concern. Push after each commit.
6. Update this RUNWAY.md before session end.

---

## Repository state reference

| Path | State |
|------|-------|
| `master` | Unchanged March-24 showcase snapshot. |
| `dev` | Active. 15 commits ahead of master as of this session. |
| `docs/` | Full planning doc set (P0 from session 1). |
| `src/shared/{paths,secrets,config}.py + configs/default_config.yaml` | New infra. |
| `src/onboarding/` | Full wizard backend (no UI yet). |
| `src/personas/` | Pack loader + manager + audit. |
| `src/brain/{llm_router,llm_client,fallback,cost}.py` | New LLM abstraction. |
| `src/brain/{persona,handler}.py` | Rewritten for v1.0 scope. |
| `src/core/{startup,server,shutdown}.py` | Updated for v1.0 module set. |
| `src/desktop_legacy/` | Renamed from src/desktop/. Not product surface. |
| `personas/_example/` | Reference pack. Other 12 come in P4. |
| `frontend/` | Placeholder README only. P2 scaffolds here. |
| `requirements.txt`, `.env.example`, `README.md` | Public v1.0 versions. |

---

## Anti-drift reminders

- **Do not modify `Isabelle_Kunstig/` files** — another agent active there per memory.
- **Do not commit secrets** — keyring is primary, `.env` is dev-only fallback.
- **Do not edit `src/desktop_legacy/`** — it's historical.
- **Do not delete `master` branch** — linked from portfolio.
- **Do not change the license** without explicit Don approval.
- **Do not port from Isabelle without going through `docs/SYNC-ISABELLE.md` rules** (script to build later).
- **Do not skip the boot smoke test before starting P2** — discovering broken imports mid-frontend-build wastes hours.
