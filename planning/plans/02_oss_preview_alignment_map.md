# 02 — OSS Preview Alignment Map

**Status:** draft
**Last updated:** 2026-04-18
**Axis:** per-must-own-layer × OSS-Preview-vs-Pro scope split.
**Depends on:** L1..L7 layer plans, `roadmaps/aether_oss_preview.md`, `roadmaps/aether_pro.md`, `02_product_family.md`.

---

## Introduction — OSS Preview purpose

Aether OSS Preview is the free, open-source wedge (`02_product_family.md`). Its job is to launch fast, spread through the open-source community, and prove the flagship is being built to a serious quality bar. It explicitly **may use open-source / available-now primitives aggressively** (`01_product_doctrine.md` §Aether OSS Preview) — but even here, shallow quality is not acceptable in the user-facing experience.

The critical doctrine rule for this document: **no must-own layer is fully borrowed even in OSS Preview — the control plane stays ours.** Borrowed primitives may do work in a given layer, but they sit behind our interfaces. That distinction is what lets OSS Preview be tactical without compromising the Pro moat.

This map, for each of L1..L7:
- states what of that layer ships in OSS Preview (possibly borrowed primitives behind our control),
- states what is Pro-only and does not ship in OSS Preview,
- declares whether the OSS Preview code is **throwaway** (will be rewritten custom for Pro), **keep** (carries forward unchanged or nearly so), or **refactor** (structure survives; implementation rewritten).

---

## Alignment table

| Layer | OSS Preview scope | Pro-only scope | Carry-forward decision |
|---|---|---|---|
| **L1 Interaction timing & reflex router** | Hand-coded reflex rules (Python/TS acceptable); fixed ack phrase pool; simple state machine; VAD borrowed (Silero/WebRTC) behind our interface; 250/800 ms budgets observed best-effort. | Distilled reflex classifier model; Rust typed event bus; full timing-contract enforcement with auto-ack on budget breach; deliberative cancellation; persona-driven rotating ack pool; context-conditioned phrase selection. | **Refactor.** State-machine structure + event names + phrase-pool schema carry forward. Python/TS implementation is rewritten in Rust for Pro P1. VAD wrapper interface survives. |
| **L2 Memory kernel** | Session + durable SQLite memory; basic vector index (likely chromadb-class, borrowed); write path + recall; no rich governance; two-toggle retention (session / durable). | Five-layer architecture (ephemeral/session/durable/artifact/behavior); novelty + salience filter; confidence decay; provenance tracking; multimodal ingestion; memory-editing API; sync-aware schema; cross-project Isabelle overlays. | **Refactor.** Schema migrates to the 5-layer model for Pro. Borrowed vector index swappable behind our interface. User-visible memory categories survive onboarding carry-forward. |
| **L3 Presence engine** | Headshot/bust avatar via MuseTalk or TalkingHead (borrowed heavily); real-time or near-real-time lip-sync; basic listening/thinking/speaking state cues; speech-driven facial animation only; Lite visual fallback. | Custom presence controller (gaze/blink/idle/anti-uncanny stabilizer); rendering-surface decision (Unreal-class / custom GL); state-linked + speech-linked rich animation; photoreal path; gesture & body (stretch). | **Throwaway** (implementation) + **Keep** (presence-state model). MuseTalk/TalkingHead integration is replaced entirely in Pro Phase 3. The state → visible-behavior map designed for OSS carries forward; it is the control plane. |
| **L4 Model router** | Gemma 4 local only (smallest variant); deep-task escalation deferred or gracefully degraded; optional user-provided remote API key (stub); no latency-aware routing — if remote, it's explicit. | Full tier abstraction (fast/main/heavy); latency-aware local-vs-remote decision; fallback chains; BYOK with cost visibility; memory-confidence-weighted routing; route_decision audit events. | **Refactor.** The tier-abstraction interface (fast/main/heavy) from `18_model_router_spec.md` is introduced even in OSS (as a degenerate "fast only" configuration), so Pro extends rather than replaces it. BYOK plumbing rewritten. |
| **L5 Policy engine** | Simplified preset ladder (Observer / Assistant default); scoped capabilities for files, browser, memory, clipboard; approval prompts for medium-risk actions; light action history (session-scoped, viewable). | Full 5-preset ladder; 4 risk classes with default approval behaviors; non-bypassable evaluation; session grants with revocation; append-only cryptographic-integrity audit log; replay support; red-team suite. | **Refactor.** Capability model + event contract carry forward. Evaluator rewritten in Rust for Pro P1. Audit log goes from session-scoped JSON to append-only with integrity in Pro. |
| **L6 Persona compiler** | Preset personas (Warm / Professional / Playful / Custom) compiled to system prompt + fixed phrase pool + basic voice settings; YAML pack schema per `17_persona_pack_schema.md`; no appearance or salience outputs. | Full compiler: system prompt + phrase pool + animation params + voice settings + memory salience rules + appearance params; 12-archetype catalog; licensing layer; Isabelle-private overrides. | **Keep.** Persona-pack YAML schema is doctrinal and ships identical from OSS forward. Compiler extends to emit more outputs in Pro; OSS-emitted outputs (prompt + phrase pool + voice) are unchanged. |
| **L7 Trust UX & onboarding** | 7-step onboarding (or 8-screen v1.0 wizard condensed); info-explainer component (the (i) icon); AI/data/memory disclosures; simplified permissions UI; light trust center (permissions + recent actions + AI disclosure + memory controls); first-run checklist (3 items); inline walkthroughs for core features; optional guest-mode entry (Cloudflare Worker + Groq free tier, per v1.0 concept). | Full trust center (searchable action history + replay + model disclosure + safety docs); routing-decision audit UI; full 5-preset permission ladder UI with resource pickers; consent-revocation uniformity; Isabelle-private trust surfaces; sync-aware trust UI. | **Keep.** The design system, info-explainer component, onboarding wizard shell, and disclosure copy all carry forward. Trust center light is extended — not rewritten — into Pro's full trust center. This is the layer with the most OSS→Pro carry-forward, because it is doctrinally custom from the start. |

---

## pywebview-as-tactical-shortcut vs Tauri-long-term

Doctrine lock this session: **Tauri long-term desktop; pywebview only tactical OSS Preview, explicitly non-doctrinal.** This cuts across the table in two ways:

- **L7 is affected most.** The onboarding wizard shell, info-explainer component, and trust-center UI are React/TypeScript regardless of shell — so a React component tree authored under pywebview (OSS Preview) *can* carry forward to Tauri (Pro) unchanged if the boundary between shell and UI is disciplined. This is the one place where the tactical shortcut buys the most carry-forward leverage. The executing agent must enforce "no pywebview-specific APIs leak into the component tree" to preserve that leverage.
- **L1, L2, L5 runtime code** in OSS Preview can ship as Python/TS behind a Rust FFI shim in Pro, or be rewritten. The matrix above labels these "Refactor" because the interfaces survive and the implementations do not.
- **Locked feedback conflict**: `feedback_css_default_for_ui.md` (2026-04-11) asserts pywebview for UI. Tauri is a webview shell too (WebView2 on Windows / WKWebView on macOS), so the spirit — "HTML/CSS/JS for UI, never Tkinter/Qt" — is preserved. The old memory is updated in spirit, not contradicted. Flag to Don for explicit rewrite of that memory note.

---

## Doctrine check — control plane stays ours, per row

Per doctrine §1.2, no must-own layer is fully borrowed even in OSS Preview. Verified per row:

- **L1** — reflex rules, phrase pool, state machine, timing budgets are ours. VAD is borrowed behind our interface. ✓
- **L2** — memory schema, retention policy, write/recall orchestration are ours. Vector index borrowed behind our interface. ✓
- **L3** — state model + state → visible-behavior map are ours. MuseTalk/TalkingHead are borrowed primitives behind our control-plane layer; they do not decide what "listening" looks like — we do. ✓
- **L4** — tier abstraction + routing policy are ours. Gemma 4 (local) and any remote model are borrowed inference runtimes behind our router. ✓
- **L5** — capability model, risk classes, preset ladder, evaluator are ours. No policy evaluation is delegated to a vendor. ✓
- **L6** — pack schema + compiler are ours; ships identical from day one. ✓
- **L7** — design system, wizard shell, info-explainer, disclosure copy, permission UI, trust-center shell are all custom from OSS Preview. Form primitives (Radix/Headless UI) and markdown/search libraries are borrowed behind the design-system wrapper. ✓

**Conclusion:** every must-own layer has its control plane custom-owned in OSS Preview. The borrowing is tactical and isolated, and removing any borrowed primitive does not require rewriting the control plane.

---

## Open decisions

- **L3 MuseTalk vs TalkingHead vs Wav2Lip** — pick one as OSS Preview baseline in Phase 2; the other two are comparison references, not shipped primitives.
- **L7 guest-mode infrastructure** — ship v1.0's Cloudflare Worker + Groq free tier, use a different provider, or defer guest-mode to post-OSS-Preview.
- **Vector index choice for L2** — ChromaDB, SQLite vector extension, or Qdrant embedded. All are borrowed behind our interface; pick for DX and package size.
- **OSS Preview shell** — pywebview (tactical, aligns with locked memory) vs. Tauri (aligns with Pro doctrine; may slow OSS launch). Cross-cuts L7 most.
- **OSS Preview BYOK** — does the optional remote-API-key slot ship at all, or is OSS Preview strictly local-only? Currently drawn as "optional stub"; may be cut entirely for speed.
- **Inbox vs canonical OSS roadmap** — inbox version (`inbox_2026-04-18b/aether_oss_preview_roadmap.md`) and canonical (`roadmaps/aether_oss_preview.md`) are substantively aligned (same 4-phase structure, same tech stack). Canonical is richer and is the source of truth. No content conflicts.
