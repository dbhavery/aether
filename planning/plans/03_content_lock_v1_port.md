---
status: locked
locked_date: 2026-04-18
layer: cross-cutting / content-port
source_repo: file:///C:/Users/dbhav/Projects/aether/docs/
---

# 03 — v1.0 Content Lock (port manifest)

## Rationale

Per locked decision #6 (2026-04-18), valuable v1.0 content is preserved **now**, before the segmented L1..L7 + X1..X4 plans execute, so that future agents are not blocked waiting on a retrieval pass against the retired v1.0 docs. This file is the single canonical bridge between `file:///C:/Users/dbhav/Projects/aether/docs/` (retired, repo private) and the new planning folder.

Signal only. No long prose imported verbatim. Each section cites the v1.0 path for retrieval and maps the artifact into the new plan space. If a claim is not cited here, it is **not** ported — do not reconstruct from memory.

---

## 1. 8-screen onboarding wizard

**What it is:** Concrete screen-by-screen spec for first-run flow — Welcome, Avatar, Personality, Name, LLM setup, Voice setup, T&P, Hand-off. State machine with resumability (partial state to `wizard_state.yaml`), per-screen validation, backend mirroring via WebSocket, per-step routing for back-button support. Includes explicit failure modes (Ollama missing, key validation fail, model download fail, config write fail).

**Why it still matters:** The v1.0 spec is materially more detailed than the new `06_onboarding_spec.md`'s 7-step outline. Resumability, per-screen state schema, and telemetry event shape are load-bearing for "time-to-first-message" — the product's most important P0 metric. Non-technical onboarding is a must-own layer (L7).

**Maps to:** `L7_trust_ux_onboarding.md` (primary), `06_onboarding_spec.md` (supplement), `17_persona_pack_schema.md` (avatar/archetype cards feed persona pair computation).

**Different from v1.0:**
- Screen 5 LLM setup: tier abstraction (fast/main/heavy) now per-provider, not per-model — already ported in `18_model_router_spec.md`.
- "Guest mode" card preserved (see §2).
- Wizard routes stay on the desktop webview (Tauri long-term, pywebview tactical); Next.js assumption dropped.
- Persona computation (avatar_id × archetype_id → active persona) preserved as-is.

**Port status:** **[ported forward]** into L7 execution plan. Source for wizard state-machine detail.

**Source:** `file:///C:/Users/dbhav/Projects/aether/docs/ONBOARDING-SPEC.md` (253 lines).

---

## 2. Guest mode / Aether Guest endpoint

**What it is:** Low-friction onboarding path: no Ollama install, no BYOK. Cloudflare Worker proxy at `guest.aether.sh` → Groq free tier. Per-installation-UUID rate-limiting (10/hr, 40/day, 4096 max tokens). Simple jailbreak keyword filter. Aggregate logs only (no prompt content). $0.01/day cost cap on the Worker.

**Why it still matters:** Removes the single largest onboarding friction point (first-contact LLM key) for non-technical users. OSS Preview wedge depends on time-to-first-message; Guest mode is how that number stays under five minutes for users with no API key and no GPU for Ollama.

**Maps to:** `L4_model_router.md` (as a provider row in the routing table), `L7_trust_ux_onboarding.md` (wizard Screen 5 Card C), `X1_repo_restructure.md` (infra surface lives outside the client monorepo — Worker deploy target).

**Different from v1.0:**
- Operates alongside Gemma 4 default local LLM — Guest is fallback *only* when Ollama not detected and no BYOK key present.
- Policy engine (L5) gates any Guest-mode traffic (user sees "your bytes leave your machine" disclosure).
- `guest.aether.sh` is OSS Preview only; Pro users always configure their own keys or Ollama.

**Port status:** **[ported forward]** as OSS Preview feature. Explicitly **retired** for Pro.

**Source:** `file:///C:/Users/dbhav/Projects/aether/docs/LLM-PROVIDERS.md` §11 (lines 186–198), onboarding Screen 5 Card C.

---

## 3. Distribution playbook

**What it is:** Channel-by-channel launch template — GitHub release metadata, repo description + topics, LinkedIn copy, Show HN draft, r/LocalLLaMA, r/selfhosted, r/privacy drafts, X/Bluesky/Mastodon 5-post thread, Product Hunt deferral rationale. Metrics-to-track post-launch (stars, clones, views, referrer split).

**Why it still matters:** Reusable scaffold for the next public launch (OSS Preview, whenever that ships). The *copy itself* is retired with v1.0 (messaging will change), but the **channel matrix, cadence, and metric set** are reusable doctrine. Saves a week of re-discovery when it's time to launch again.

**Maps to:** No layer (not a runtime concern). Referenced from `X4_v1_content_port.md` and from the OSS Preview launch phase in `roadmaps/aether_oss_preview.md`.

**Different from v1.0:**
- All copy is retired — v1.0 messaging ("449 ms, $0/query, MIT") does not match the new doctrine positioning.
- Channel list + cadence + metric set preserved as a checklist.
- LinkedIn auto-post via morning-intel is still the distribution channel.

**Port status:** **[preserved here as reference]** — channel/metric scaffold only; copy retired.

**Source:** `file:///C:/Users/dbhav/Projects/aether/docs/DISTRIBUTION.md` (195 lines).

---

## 4. BYOK cost-visibility UX

**What it is:** Sandbox → LLM → Usage panel showing rolling cost per provider: last-hour, today, this-month. Token counts via litellm's counter + provider pricing tables. User-set "warn at $X/day" and "hard cap at $Y/day" budget thresholds. No PII in cost logs — aggregate tokens + estimated USD only. Local-only providers (Ollama, Guest) show `$0.00` but still emit token counts for parity.

**Why it still matters:** BYOK is table stakes for Pro. Cost transparency converts BYOK from a usability risk (surprise bills) into a trust surface. Budget caps are a policy-engine (L5) affordance, not a vanity feature — a hard cap is a capability boundary.

**Maps to:** `L4_model_router.md` (cost accounting, budget caps, per-provider rolling costs — already cited in L4 plan `Owns` list), `L5_policy_engine.md` (hard cap enforcement as capability), `L7_trust_ux_onboarding.md` (Sandbox UX surface).

**Different from v1.0:**
- Hard cap is now enforced by L5 (policy) rather than router-internal — cleaner separation.
- Guest mode and Ollama still show `$0.00`; token counts emitted everywhere.
- Per-persona cost breakdown added (new) — Pro feature; OSS Preview keeps flat per-provider view.

**Port status:** **[ported forward]** into L4 execution plan; UX surface into L7.

**Source:** `file:///C:/Users/dbhav/Projects/aether/docs/LLM-PROVIDERS.md` §8 (lines 153–161).

---

## 5. Inno Setup installer + auto-updater

**What it is:** Windows-first installer scaffold using Inno Setup (upstream Isabelle already has one under `packaging/`). Bundles WebView2 bootstrapper for older Windows. Models download on first run (keeps installer <500 MB). Custom auto-updater checks GitHub Releases on launch; detects new version, downloads, relaunches. No third-party updater dep.

**Why it still matters:** Packaging is the step that turns "runs on my machine" into "ship to users." The scaffold exists and works. For OSS Preview this is the shortest path to a distributable binary. For Pro, the Tauri updater supersedes this (Tauri has a signed-update mechanism), but the **install-time model download**, **WebView2 check**, and **GitHub Releases update-source pattern** carry forward.

**Maps to:** `X3_tauri_architecture.md` (Tauri updater + code signing — Pro doctrine), `X4_v1_content_port.md` (Inno Setup scaffold reusable for OSS Preview tactical shortcut), `15_updates_releases.md` (stable/beta/experimental channels already specified).

**Different from v1.0:**
- **Pro uses Tauri's signed updater**, not Inno Setup + custom GitHub-Releases poller. Inno Setup is explicitly OSS-Preview-only.
- WebView2 bootstrapper remains for Windows; Tauri WebView2 on Windows keeps the dependency semantic.
- Install-time model download is the same pattern for both.
- Code signing (Pro requirement) was not in v1.0 scope; X3 owns it.

**Port status:** **[ported forward]** for OSS Preview (Inno Setup scaffold reusable). **[explicitly retired]** for Pro (Tauri updater doctrine).

**Sources:**
- `file:///C:/Users/dbhav/Projects/aether/docs/PRODUCT-PLAN.md` lines 27–28, 45–46, 121–124, 159
- `file:///C:/Users/dbhav/Projects/aether/docs/ARCHITECTURE-V2.md` lines 91, 276–277
- Upstream Isabelle `packaging/` folder.

---

## Summary table — v1.0 artifact → new home

| v1.0 artifact | Source path | New home | Port status |
|---|---|---|---|
| 8-screen wizard | `aether/docs/ONBOARDING-SPEC.md` | `plans/L7_trust_ux_onboarding.md`, `06_onboarding_spec.md` | ported forward |
| Guest mode / Aether Guest endpoint | `aether/docs/LLM-PROVIDERS.md` §11 | `plans/L4_model_router.md`, `plans/L7_*`, `X1` (worker infra) | ported forward (OSS Preview only); retired for Pro |
| Distribution playbook | `aether/docs/DISTRIBUTION.md` | `prompts/X4_v1_content_port.md`, `roadmaps/aether_oss_preview.md` | preserved here as reference (scaffold only; copy retired) |
| BYOK cost visibility | `aether/docs/LLM-PROVIDERS.md` §8 | `plans/L4_model_router.md`, `plans/L5_policy_engine.md`, `plans/L7_*` | ported forward |
| Inno Setup + auto-updater | `aether/docs/PRODUCT-PLAN.md`, `ARCHITECTURE-V2.md` | `prompts/X3_tauri_architecture.md` (Pro), `prompts/X4_*` (OSS Preview) | ported forward (OSS Preview); explicitly retired (Pro) |
| Persona pack schema | `aether/docs/PERSONA-SCHEMA.md` | `17_persona_pack_schema.md` | already ported (prior session) |
| LLM tier abstraction | `aether/docs/LLM-PROVIDERS.md` §2–§4 | `18_model_router_spec.md`, `plans/L4_model_router.md` | already ported (prior session) |
| ARCHITECTURE-V2 (pywebview + Next.js + litellm + Ollama + LivePortrait + ChromaDB) | `aether/docs/ARCHITECTURE-V2.md` | — | explicitly retired (superseded by new doctrine) |
| PRODUCT-PLAN (v1.0 phase plan, 7.5 weeks) | `aether/docs/PRODUCT-PLAN.md` | — | archive only |
| SYNC-ISABELLE | `aether/docs/SYNC-ISABELLE.md` | `prompts/X2_isabelle_migration.md` (superseded by new migration doctrine) | archive only — new migration agent reads this as historical context, not spec |
| superpowers/ subfolder | `aether/docs/superpowers/` | — | archive only (tooling artifacts, not product content) |

---

## Files confirmed present in v1.0 docs folder (retrieval targets)

- `ARCHITECTURE-V2.md` (296 lines)
- `DISTRIBUTION.md` (195 lines)
- `LLM-PROVIDERS.md` (221 lines)
- `ONBOARDING-SPEC.md` (253 lines)
- `PERSONA-SCHEMA.md` (261 lines)
- `PRODUCT-PLAN.md` (196 lines)
- `SYNC-ISABELLE.md` (185 lines)
- `superpowers/` (subfolder; contents not inventoried here)

No files flagged as missing during this lock.
