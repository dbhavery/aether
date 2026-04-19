# Session-Start Summary — 2026-04-18 (second planning session)

**Status:** working
**Last updated:** 2026-04-18
**Depends on:** HANDOFF_2026-04-18.md, 01_product_doctrine.md, all 18 numbered specs, OPEN_QUESTIONS.md.

---

## Already complete

- Full planning folder `file:///C:/Users/dbhav/Projects/aether-planning/` (26 docs, ~6000 lines).
- v1.0 fully retracted across every public surface.
- Persona schema + model-router spec ported forward.
- 8 doctrine rules locked — see `01_product_doctrine.md`.

## Locked this session (from next-session prompt)

1. **Segmentation axis** — per-must-own-layer primary; per-Pro-phase crosswalk secondary.
2. **Desktop framework** — Tauri long-term doctrine. pywebview allowed only as tactical OSS-Preview shortcut, explicitly non-doctrinal.
3. **Isabelle migration** — phased, short parallel overlap, then cutover. No hard cutover; no indefinite parallel.
4. **Repo structure** — monorepo with strong internal boundaries (apps / packages / planning / research).
5. **Prompt model** — self-contained briefing packs + task-specific one-shots. Don = human coordinator.
6. **v1.0 content port** — do it now before declaring segmented plans complete.
7. **Doctrine carried forward** — no close-enough SaaS, custom moat layers, UX outranks convenience, companion-grade ceiling, local-first, Gemma 4 default, 50% VRAM, Isabelle-as-profile.

## Still open (do not block deliverables)

- Final product names (Aether Pro vs Core vs One; Isabelle vs Isabelle_Kunstig formal).
- Exact OSS Preview MVP cut line and ms budgets.
- Rendering engine for Pro avatar (Unreal-class / custom GL / hybrid).
- Sync architecture (CRDT vs op-log).
- Mobile stack.

Each is surfaced in the affected layer plan so the executing agent knows what to decide vs defer.

## Files this session will touch

### Create
- `plans/00_ORCHESTRATION_MAP.md`
- `plans/01_pro_phase_crosswalk.md`
- `plans/02_oss_preview_alignment_map.md`
- `plans/03_content_lock_v1_port.md`
- `plans/L1_interaction_timing.md`
- `plans/L2_memory_kernel.md`
- `plans/L3_presence_engine.md`
- `plans/L4_model_router.md`
- `plans/L5_policy_engine.md`
- `plans/L6_persona_compiler.md`
- `plans/L7_trust_ux_onboarding.md`
- `prompts/L1..L7_*.md` (one per layer)
- `prompts/X1_repo_restructure.md`
- `prompts/X2_isabelle_migration.md`
- `prompts/X3_tauri_architecture.md`
- `prompts/X4_v1_content_port.md`
- `SESSION_END_INDEX_2026-04-18b.md`

### Update
- `OPEN_QUESTIONS.md` — lock 6 decisions as `[DECIDED 2026-04-18]`.

### Read-only (relied on, not modified)
- `01_product_doctrine.md`, `02_product_family.md`, `08_system_architecture.md`, `09_realtime_interaction.md`, `10_memory_architecture.md`, `11_avatar_presence.md`, `12_permissions_autonomy.md`, `13_trust_security_redteam.md`, `16_tech_stack.md`, `17_persona_pack_schema.md`, `18_model_router_spec.md`, `roadmaps/*`, `COMPARISON_REPORT.md`.

## Conflicts detected

- Locked memory `feedback_css_default_for_ui.md` (2026-04-11) asserts pywebview-only for UI. This session locks Tauri long-term. **Resolution:** preserve both. Tauri is a webview shell (WebView2 on Windows / WKWebView on macOS), so the spirit — "no Tkinter/Qt, use web tech for UI" — is preserved. The old memory's framework specificity (pywebview) is superseded only for the Aether family's long-term desktop foundation. Will flag in orchestration map; Don decides whether to rewrite the memory note after this session.
