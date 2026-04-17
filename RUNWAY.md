# RUNWAY.md — Session Handoff

**Last session:** 2026-04-17 — P0 architecture freeze and planning docs.
**Branch:** `dev` (new, off `master`@dc92ba3).
**Unpushed state:** new docs + personas scaffold, not yet committed.
**Next session owner:** continue P1 — backend port from upstream Isabelle.

---

## Where we are

Aether is being productized from a showcase repo into a public v1.0 consumer product. The existing `master` branch holds a March-24 sanitized snapshot of Isabelle with a PySide6 UI (suitable for portfolio linking, kept untouched). All productization happens on `dev`.

**Binding decisions locked** in `docs/PRODUCT-PLAN.md`. Summary:
- Evolve existing `aether` repo, don't fork.
- MIT license retained.
- Next.js + pywebview UI (replaces PySide6, which becomes `src/desktop_legacy/`).
- LivePortrait-only avatar in v1.0.
- litellm for LLM abstraction, BYOK wizard.
- Push-to-talk (no wake word).
- 10–12 personas as pack folders.
- Windows-first installer.

---

## What got done this session

1. `dev` branch created off `master`.
2. Six planning docs written under `docs/`:
   - `PRODUCT-PLAN.md` — full roadmap, phases P0–P6, acceptance criteria.
   - `ARCHITECTURE-V2.md` — process topology, directory layout, ports, events, config.
   - `PERSONA-SCHEMA.md` — persona pack format, 12 canonical personas, generation pipeline.
   - `ONBOARDING-SPEC.md` — 7-screen wizard state machine.
   - `LLM-PROVIDERS.md` — litellm abstraction, tier mapping, key storage, guest mode.
   - `SYNC-ISABELLE.md` — deterministic upstream port rules.
3. Top-level `personas/` directory scaffolded with README and `_example` reference pack.
4. Top-level `frontend/` directory scaffolded with README.
5. Task list seeded and worked through.

**What was NOT done:**
- No code changes (planning-only session per Don's explicit direction).
- No commits yet — next step after this doc lands.
- No GitHub push — happens after commits.

---

## Immediate next actions for next session

**P1 kickoff — port backend modules from upstream Isabelle:**

1. **Build `scripts/sync_from_isabelle.py`** per rules in `docs/SYNC-ISABELLE.md`.
   - Start with `--dry-run` to validate transformations.
   - Target: one atomic commit per ported module.
2. **Port order:**
   1. `src/shared/` (paths, config, types, logging) — everything else depends on it.
   2. `src/core/` (EventBus, WS server, health).
   3. `src/memory/` (ChromaDB, per-persona isolation added).
   4. `src/voice/` (stripped — no wake word, no speaker verify, push-to-talk events).
   5. `src/avatar/` (LivePortrait only, drop Ditto/MuseTalk/FlashHead).
   6. `src/brain/` (replace Don's custom router with litellm tier abstraction).
3. **Rename `src/desktop/` → `src/desktop_legacy/`** and mark read-only.
4. **Strip `src/tools/`, `src/agents/`, `src/notifications/`, `src/media/`, `src/data_server/`, `src/persona/`, `android/`** — delete, don't port.
5. **Write `src/personas/loader.py`** — scans `personas/` dir, validates against schema, returns `PersonaManifest`.
6. **Update `requirements.txt`** per SYNC-ISABELLE.md § 3.5.
7. **Rename `isabelle_config.yaml` → `aether_config.yaml`.**
8. **Boot test:** `python -m src.main` should start clean on a fresh checkout with no secrets configured (fails loud with clear messages, doesn't silently use Don's defaults).

**P2 kickoff — frontend scaffold (can run in parallel with P1):**

1. `cd frontend && npx create-next-app@latest .` (Next.js 15, TypeScript, App Router, Tailwind v4).
2. Build WebSocket client in `lib/ws.ts` matching the backend :8765 contract.
3. Three-mode shell under `app/(shell)/` — chat, sandbox, video.
4. Wizard stub under `app/(onboarding)/` — 8 routes, no logic yet.
5. pywebview bridge in `desktop/main.py` that launches a window pointing at `frontend/out/`.

---

## Open questions for Don

These don't block P1 but will need answers before P4 / P5:

1. **Who drafts TERMS.md and PRIVACY.md?** Recommend paying someone once for a template, then we adapt.
2. **Portfolio embed approach:** iframe from `dbhavery.ai` or fully inline React component? Iframe is safer (sandbox); inline is prettier.
3. **Aether Guest endpoint hosting:** Cloudflare Worker is cheap. OK to provision?
4. **Telemetry:** any opinion on Sentry vs. PostHog vs. custom? I'd default to PostHog (self-hostable, product-analytics focused). Can defer.
5. **macOS and Linux installers in v1.0 or later?** I scoped Windows-only. Confirm.
6. **Persona generation assets:** where do the voice reference WAVs come from? Need a curated CC0 voice pool. Budget?

---

## Decisions already locked (don't revisit without explicit reversal)

See `docs/PRODUCT-PLAN.md § 1 — Binding Decisions`. Key ones:

- MIT license.
- Next.js + pywebview.
- LivePortrait only.
- Push-to-talk (no wake word).
- 10–12 personas as pack folders.
- litellm for LLM abstraction.
- Windows-first.
- Free download, no billing in v1.0.

---

## Repo state reference

| Path | State |
|------|-------|
| `master` branch | Unchanged showcase snapshot (2026-03-24 state). |
| `dev` branch | New. Contains all planning docs + personas scaffold from this session. |
| `docs/PRODUCT-PLAN.md` | Source of truth for scope, decisions, phases. |
| `docs/ARCHITECTURE-V2.md` | Source of truth for technical design. |
| `docs/PERSONA-SCHEMA.md` | Source of truth for persona pack format. |
| `docs/ONBOARDING-SPEC.md` | Source of truth for wizard UX. |
| `docs/LLM-PROVIDERS.md` | Source of truth for LLM provider abstraction. |
| `docs/SYNC-ISABELLE.md` | Source of truth for upstream port rules. |
| `personas/_example/` | Reference persona pack, filtered from wizard. |
| `frontend/README.md` | Placeholder; P2 builds the actual app. |

---

## How to resume

1. `cd C:/Users/dbhav/Projects/aether && git checkout dev`
2. Read this file.
3. Read `docs/PRODUCT-PLAN.md` if unfamiliar with the phase structure.
4. Start on P1 per the "Immediate next actions" above.
5. Commit after every meaningful change. Push `dev` after each commit.
6. Update this RUNWAY.md at session end.

---

## Anti-drift reminders

- **Do not touch `Isabelle_Kunstig/` files** — another agent is working there per memory `project_two_agent_coordination.md`.
- **Do not commit secrets** — keys live in OS keyring, never in YAML or env files in git.
- **Do not edit `src/desktop_legacy/`** after the rename — it's a historical artifact.
- **Do not delete `master` branch** — it's linked from Don's portfolio.
- **Do not change the license** from MIT without explicit Don approval.
- **Do not hand-port Isabelle code** — always go through the sync script once it's built, even if it's only a few files.
