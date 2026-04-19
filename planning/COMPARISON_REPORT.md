# Comparison Report — New Planning vs Old Project Files

**Date:** 2026-04-18
**Status:** Initial audit — decisions deferred to Don

This report audits existing project files against the new `aether-planning/` source of truth and flags **conflicts**, **unique content worth carrying**, and **items to discard/archive**. No files deleted or modified until Don decides.

---

## CRITICAL FLAG — v1.0.0-pre shipped TODAY

The `aether/` repo (not to be confused with the new `aether-planning/` folder) **shipped `v1.0.0-pre` publicly on 2026-04-18** (today). Evidence:

- `file:///C:/Users/dbhav/Projects/aether/docs/DISTRIBUTION.md` — distribution playbook marked "Shipped 2026-04-18"
- GitHub release: `v1.0.0-pre` at `https://github.com/dbhavery/aether/releases/tag/v1.0.0-pre`
- LinkedIn post auto-published via morning-intel's LinkedInPoster
- Portfolio showcase deployed to `dbhavery.dev`
- Show HN, Reddit r/LocalLLaMA / r/selfhosted / r/privacy drafts ready

**The v1.0 that just shipped uses a DIFFERENT tech stack than the new Aether OSS Preview plan describes.** This is the biggest single thing Don needs to decide: does the new plan replace v1.0, supersede it at next version, or describe a separate product line?

---

## The four old locations

### 1. Projects root — 3 roadmap MDs + sources matrix

| File | Lines | Status |
|------|-------|--------|
| `file:///C:/Users/dbhav/Projects/aether_oss_preview_roadmap.md` | 169 | **Superseded** by `roadmaps/aether_oss_preview.md` |
| `file:///C:/Users/dbhav/Projects/aether_pro_roadmap.md` | 226 | **Superseded** by `roadmaps/aether_pro.md` |
| `file:///C:/Users/dbhav/Projects/aether_cross_systems_spec.md` | 123 | **Absorbed** across `04`–`16` and roadmaps |
| `file:///C:/Users/dbhav/Projects/aether_sources_matrix.md` | 155 | **Ported** to `sources_matrix.md` |

**Verdict:** These are the research output from the planning conversation that seeded the new folder. Content is ~95% captured. Differences:
- Old uses `[cite:XX]` markers; new stripped them.
- Old does NOT mention Gemma 4 (new addition from today's direction).
- Old doctrine is softer than new doctrine; new doctrine explicitly rules that Aether Pro onward is primarily custom-written.

**Recommendation:** Archive these 4 root files after Don confirms. They are redundant with the new folder.

---

### 2. `aether/` repo — the v1.0 codebase that shipped today

Location: `file:///C:/Users/dbhav/Projects/aether/`
Docs: `file:///C:/Users/dbhav/Projects/aether/docs/`

Contains 7 docs + superpowers:
- `PRODUCT-PLAN.md` (v1.0 productization plan, 2026-04-17)
- `ARCHITECTURE-V2.md` (v1.0 architecture)
- `LLM-PROVIDERS.md` (litellm abstraction)
- `ONBOARDING-SPEC.md` (8-screen wizard with persona grid)
- `PERSONA-SCHEMA.md` (persona pack schema — avatar + voice + personality)
- `SYNC-ISABELLE.md` (rules for porting from upstream Isabelle_Kunstig)
- `DISTRIBUTION.md` (launch channels — posted today)

**This is a completely different vintage than the new plan.** The v1.0 plan is concrete, shipped, and uses these tech choices:

| Concern | Old v1.0 (shipped) | New plan | Conflict? |
|---------|-------------------|----------|-----------|
| Desktop shell | **pywebview + Next.js 15 + React 19** | **Tauri + React** | **YES** |
| Default fast LLM | **Ollama qwen2.5:7b** | **Gemma 4** | **YES** |
| LLM abstraction | **litellm (100+ providers, BYOK)** | provider-swappable router (custom) | Partial |
| Lip-sync engine | **LivePortrait (TensorRT)** | MuseTalk / TalkingHead / Wav2Lip | **YES** |
| STT | faster-whisper | Parakeet / Whisper V3 Turbo | Partial (Whisper overlaps) |
| TTS | Chatterbox Turbo | XTTS-v2 / Piper / Coqui | **YES** |
| VAD | Silero | Silero / WebRTC | Compatible |
| Memory | ChromaDB 1.5.2 per-persona | SQLite + vector index (implementation TBD) | Partial |
| Code strategy | **Port from upstream Isabelle_Kunstig** | **Fresh code (especially Pro)** | **YES** |
| Product family | v1.0 + v2 ground-up rebuild | OSS Preview + Pro + Isabelle (3 products) | Framing diverges |
| Wake word | Removed, push-to-talk (spacebar) | VAD + PTT hybrid | Compatible |
| Personas | 10–12 bundled packs (3 shipped: Aurora, Caelum, Luma) | Persona compiler (count TBD) | Old has concrete packs |
| Installer | Inno Setup Windows only | (TBD) | Old is concrete |
| Monetization | Free, MIT-licensed | OSS Preview free; Pro commercial | Old only covers free |
| Mobile | **NOT in v1.0** (deferred to v2) | Pro includes React Native companion | Compatible (phasing) |
| UI rule cited | **pywebview per Don's 2026-04-11 locked feedback** | Tauri | **Conflicts with locked memory feedback** |

#### Hard conflict: Tauri vs pywebview

Don's memory at `file:///C:/Users/dbhav/.claude/projects/C--Users-dbhav-Projects/memory/feedback_css_default_for_ui.md` says: "Use HTML/CSS/JS via pywebview. Locked 2026-04-11."

The new plan picks Tauri. Tauri **does use a webview** (platform-native: WebView2 on Windows, WKWebView on macOS), so the spirit of the rule (HTML/CSS/JS for UI, not Qt/Tkinter) is preserved. But the specific pywebview library is replaced.

**Options:**
1. Update the locked feedback to allow Tauri (treat the rule as "webview-based UI, not toolkit").
2. Use pywebview in the new plan (maintains rule, but gives up Rust alignment Tauri provides).
3. OSS Preview uses pywebview (respects rule + inherits v1.0 work); Pro uses Tauri (rebuild).

Don's decision needed.

#### Hard conflict: Gemma 4 vs Ollama qwen2.5:7b

The v1.0 shipped today uses **Ollama qwen2.5:7b** as the default fast-tier. The new plan says **Gemma 4** is the default local LLM. Also: `aether/docs/LLM-PROVIDERS.md` references **`anthropic/claude-sonnet-4-6`** and similar — which is fine for frontier deliberative, but the old plan doesn't mention Gemma 4 at all.

Don today explicitly directed Gemma 4 integration. Old Ollama choice is stale.

#### Hard conflict: port-from-Isabelle vs fresh code

The v1.0 `SYNC-ISABELLE.md` defines a deterministic port script from upstream Isabelle_Kunstig. The new plan doctrine says "Aether Pro onward is primarily custom-written software." 

**If the new plan stands:** SYNC-ISABELLE.md is obsolete; no more ports. Pro is a greenfield rebuild.
**If incremental:** OSS Preview keeps v1.0's ported code; Pro is the rebuild.

#### Unique v1.0 content worth carrying forward

Several pieces in old `aether/docs/` have no equivalent in new planning:

1. **Persona pack schema** (`PERSONA-SCHEMA.md`) — concrete YAML schema for persona packs (avatar + voice + personality + metadata + licensing). Useful as a concrete input for the Pro persona compiler.
2. **LLM tier abstraction** (`LLM-PROVIDERS.md`) — concrete implementation pattern for fast/main/heavy tier mapping to providers. Useful as reference for Pro's model router.
3. **8-screen onboarding wizard** (`ONBOARDING-SPEC.md`) — concrete screen-by-screen spec including persona grid, LLM setup with key validation, voice setup. More detailed than new `06_onboarding_spec.md`.
4. **Guest mode / Aether Guest endpoint** — clever low-friction onboarding (Cloudflare Worker proxying to Groq free tier, rate-limited). Worth preserving as a concept.
5. **Distribution playbook** (`DISTRIBUTION.md`) — shipped GitHub release metadata, LinkedIn post copy, Show HN draft, Reddit drafts. Valuable marketing work already done.
6. **Inno Setup installer scaffold + auto-updater design** — concrete Windows distribution.
7. **Cost visibility / BYOK cost tracking** — per-provider rolling cost display concept.

**Recommendation:** Extract these into new planning docs or preserve v1.0 docs read-only for reference, depending on Don's direction on v1.0's fate.

---

### 3. `aether-desktop-voice/`, `aether-frontend-ux/`, `aether-personas/` — parallel repo experiments

These three sibling repos each contain 6 of the 7 docs from `aether/` (missing DISTRIBUTION.md) but with **different content** (diff confirmed they're not identical copies).

**Likely purpose:** experimental parallel tracks or work-in-progress forks/worktrees of the main `aether/` work. Not production repos.

**Recommendation:** Don should confirm whether these are:
- Experimental forks to archive
- Active parallel work that should be consolidated
- Agent worktrees from the 2-agent Isabelle coordination pattern

If experimental → move to `_deprecated/` or delete. If active → needs consolidation decision.

---

### 4. `Isabelle_Kunstig/` — the private project's docs

Location: `file:///C:/Users/dbhav/Projects/Isabelle_Kunstig/docs/`

Contents (substantial):
- `architecture/` (subfolder)
- `archive/`
- `changelog.md`
- `config-guide.md`
- `decisions-log.md`
- `frozen-exe-runtime-deps.md`
- `issues.md`
- `migration-audit-2026-03-05.md`
- `mockups/`
- `module-readmes/`
- `perf/`
- `preferences.md` — Isabelle's identity, appearance, UI rules, interaction modes, security, memory, cost constraint
- `project-status.md` — Phase 2 complete as of 2026-04-03, 548+ tests passing
- `runbook.md`
- `session-logs/`
- `specs/`
- `superpowers/`
- `voice-reference-guide.md`

Plus `CLAUDE.md` at repo root with module boundaries (01-Core through 12-Notifications), LLM routing tiers, hardware specs, key paths (`I:\IsabelleData\`, `I:\ObsidianVault\Isabelle_Kunstig\`).

**Status per memory:** Isabelle_Kunstig is the ACTIVE project; LoRA v2.0 trained 2026-04-12; another agent is currently working in it (2-agent coordination rule). **Don's rule: do not touch Isabelle_Kunstig files when warned.**

#### Key observations vs new Isabelle plan

The new `roadmaps/isabelle_private.md` says:
- Isabelle is a **privileged profile layer** on Aether Pro, not a separate codebase.
- Isabelle memory migration from Isabelle_Kunstig is **curated, not auto-imported**.
- Don's existing preferences/data carry forward.

The existing `Isabelle_Kunstig/` has:
- Full running system with 12 modules + avatar pipeline
- 548+ tests passing
- Phase 2 shipped
- Specific design system (#222222 base, #333333 cards, #0044AA accent)
- Hardware specific (RTX 3090 Ti 24GB, I: drive)
- PySide6 desktop UI (pre-dates 2026-04-11 CSS/pywebview rule)

**Conflicts with new plan:**

| Concern | Existing Isabelle | New plan |
|---------|-------------------|----------|
| UI | PySide6 (#222222 / #333333 / #0044AA) | Custom design system, deep 3D neumorphic monochrome (new) |
| Code base | Standalone Python | On top of Aether Pro (custom Rust + TS) |
| LLM tiers | Ollama qwen2.5:7b + Claude Sonnet/Opus + Gemini | Gemma 4 (local) + frontier remote |
| Memory | ChromaDB at I:\IsabelleData\chroma | SQLite + vector (Pro implementation) |
| Avatar | FlashHead Lite / Ditto / MuseTalk (subprocess) | Pro custom presence + rendering |
| Module boundaries | 01–12 Python modules | Six engines (Rust) |

**Recommendation:** This is the most sensitive migration. Options:
1. **Keep Isabelle_Kunstig running as-is** until Aether Pro is stable enough to take over. Treat Isabelle_Kunstig as "Isabelle v0" — the current working companion. Freeze at its last stable state when Pro is ready.
2. **Incremental migration** — move modules over one at a time as Pro phases ship.
3. **Hard cutover** — develop Aether Pro in parallel; when ready, spin down Isabelle_Kunstig.

Don's decision needed. The existing `Isabelle_Kunstig/docs/preferences.md` and identity content MUST port forward (it's Isabelle's persona foundation).

---

## Conflict summary

The new plan contradicts concrete decisions that are currently deployed:

1. **Tauri vs pywebview** — conflicts with Don's 2026-04-11 locked memory rule
2. **Gemma 4 vs Ollama qwen2.5:7b** — new direction overrides old (Don confirmed today)
3. **MuseTalk/TalkingHead/Wav2Lip vs LivePortrait** — old has TensorRT-optimized LivePortrait shipped
4. **Fresh code vs port-from-Isabelle** — old has SYNC-ISABELLE.md scripts; new plan obsoletes them
5. **Six engines (Rust) vs twelve modules (Python)** — complete architecture shift
6. **SQLite+vector vs ChromaDB** — different memory stack
7. **Custom design system vs #222222 palette** — UI direction shift
8. **React Native companion vs Jetpack Compose Android client** — mobile direction shift

---

## Unique content worth carrying forward

From old v1.0 → into new planning:

1. **PERSONA-SCHEMA.md** — concrete persona pack YAML schema → absorb into a new `17_persona_pack_schema.md` or similar
2. **LLM tier abstraction** (fast/main/heavy with per-preset model mapping) → expand `09_realtime_interaction.md` with concrete tier spec
3. **8-screen onboarding wizard screens** → expand `06_onboarding_spec.md` with concrete screen specs (currently it has a 7-step outline)
4. **Guest mode** concept → add to `06_onboarding_spec.md` or a new doc
5. **Distribution playbook** → carry forward as `distribution_playbook.md` (useful for every future launch)
6. **Cost visibility / BYOK tracking** → add to `12_permissions_autonomy.md` (cost is a capability concern) or new doc

From existing Isabelle_Kunstig → into new Isabelle plan:

1. **`preferences.md`** — Isabelle's identity, appearance, interaction modes → carry into Isabelle persona pack
2. **Hardware specs / paths** — RTX 3090 Ti 24GB, I: drive, Tailscale 100.105.108.18 → already in memory, already referenced in `roadmaps/isabelle_private.md`
3. **Design system tokens** — #222222/#333333/#0044AA — but note: memory says old design system is OUTDATED as of 2026-03-22, fresh per-project
4. **Acknowledgment phrase behavior** (>3000ms response rule, >30s status update) → concrete input for Pro's latency-aware social timing system
5. **Module test infrastructure** (548 tests) → reference for Pro quality bar (not ported directly, but reference)
6. **Memory tier design** (hot GPU / RAM ~5GB / cold I: drive) → concrete pattern for Pro's memory kernel

---

## Recommendations (in priority order)

1. **Don decides v1.0's fate.** Three options:
   - **A. v1.0 = Aether OSS Preview (shipped).** New OSS Preview plan describes a *future rebuild*; v1.0 stands. Update new plan to acknowledge v1.0 exists and is the current preview; the Tauri/Gemma 4/MuseTalk rebuild is OSS Preview v2.
   - **B. v1.0 is deprecated.** New OSS Preview plan replaces it with a Tauri/Gemma 4 rebuild; v1.0 archived.
   - **C. v1.0 continues as-is; Aether Pro is the new thing.** New OSS Preview plan is scrapped because v1.0 already fills that slot.

2. **Don decides the Tauri vs pywebview rule.** Update or keep the 2026-04-11 locked feedback.

3. **Port unique content** from old v1.0 docs that has no new-plan equivalent:
   - Persona pack schema
   - 8-screen wizard concrete specs
   - LLM tier abstraction details
   - Distribution playbook

4. **Archive decisions** for old root-level files:
   - `aether_oss_preview_roadmap.md`, `aether_pro_roadmap.md`, `aether_cross_systems_spec.md` → move to `_deprecated/` or delete (content captured)
   - `aether_sources_matrix.md` → delete (ported)

5. **Clarify `aether-*/` sibling repos** (desktop-voice, frontend-ux, personas) — active work or deletable experiments?

6. **Isabelle_Kunstig migration strategy** — phased, parallel, or hard cutover?

7. **Update `Isabelle_Kunstig/CLAUDE.md`** — it still references module boundaries and tech choices that conflict with the new plan. If the plan is incremental migration, add a note. If it's a cutover, mark Isabelle_Kunstig for freeze at the transition point.

---

## What to do next

**Don should:**
1. Read this report
2. Decide on question 1 (v1.0's fate) — everything else follows from that
3. Then decide on questions 2–7

**I (Claude) should NOT:**
- Delete any old files
- Modify Isabelle_Kunstig files (2-agent coordination rule — another agent may be working there)
- Unilaterally resolve the Tauri vs pywebview conflict
- Port unique content until Don confirms which direction wins

---

## Open questions added to OPEN_QUESTIONS.md

The following should be added to [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md):

- **v1.0 fate** — replace / supersede at v2 / treat as the current OSS Preview
- **Tauri vs pywebview** — update locked feedback or use pywebview
- **Port from Isabelle** — new plan's "fresh code" absolute or allow incremental port of v1.0?
- **Isabelle_Kunstig migration timing** — phased / parallel / hard cutover
- **Fate of `aether-desktop-voice/`, `aether-frontend-ux/`, `aether-personas/`** — archive / consolidate / active

---

## Cross-references
- Planning index: [README.md](README.md)
- Doctrine (the new direction): [01_product_doctrine.md](01_product_doctrine.md)
- Open questions: [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md)
- v1.0 product plan (old): `file:///C:/Users/dbhav/Projects/aether/docs/PRODUCT-PLAN.md`
- v1.0 architecture (old): `file:///C:/Users/dbhav/Projects/aether/docs/ARCHITECTURE-V2.md`
- v1.0 distribution playbook (old): `file:///C:/Users/dbhav/Projects/aether/docs/DISTRIBUTION.md`
- Isabelle_Kunstig status (old): `file:///C:/Users/dbhav/Projects/Isabelle_Kunstig/docs/project-status.md`
- Isabelle preferences (carry forward): `file:///C:/Users/dbhav/Projects/Isabelle_Kunstig/docs/preferences.md`
