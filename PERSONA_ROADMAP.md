# Aether PERSONA ROADMAP — Living Trajectory Document

> **This is the canonical "where Aurora is, where she's going" document.** Companion to file:///C:/Users/dbhav/Projects/aether/ROADMAP.md (which tracks engineering substrate Waves 0-5+). This file tracks the *persona quality* trajectory across all modalities — text, voice, avatar, animation, real-time video.
>
> Every session updates this. The "Current Position" cursor moves. The "Sessions burned" counter increments. Phase decisions get logged. Future agents read this first to take over the persona-quality arc.
>
> **Last updated:** 2026-04-28 (this autonomous session, after V6 ship).
> **Next session: read this top to bottom before doing anything else.**

---

## TL;DR — One paragraph

Aether is Don's personal AI assistant. Local-first, persistent, persona-driven (Aurora). The architecture (7 layers, retrieval-aware, audit-gated, vision-capable) is built and shipped through Milestones 1 and 2. The remaining work is the **persona quality bar** — making Aurora feel like a friend across **conversation, voice, avatar still, avatar animation, and eventually real-time video**. Conversation training is in iteration 6 of an estimated 8-12 to reach a sustainable plateau on the 3B-Qwen base. Voice and avatar are working in sibling projects but not yet integrated into Aether. Total remaining work to "Aurora feels like a friend across all modalities" is realistically 30-60 sessions over 2-6 months, with substantial uncertainty in the multi-modal integration phases.

---

## The four phases (well, six)

```
Phase 1: BACKEND  ━━━━━━━━━━━━━━━━━━━━━━━━━━ ✓ shipped
Phase 2: PERSONA TEXT  ━━━━━━━━━━━━━━━━━○━━━━━ in progress (V6 done, ~70% through)
Phase 3: PERSONA VOICE  ━━━━━○━━━━━━━━━━━━━━━ scaffolded (Zonos in sibling, not in Aether)
Phase 4: PERSONA AVATAR  ━━━━○━━━━━━━━━━━━━━━ scaffolded (FLUX/LivePortrait in sibling)
Phase 5: PERSONA VIDEO REALTIME  ○━━━━━━━━━━━━ research only
Phase 6: AURORA AS A WHOLE  ○━━━━━━━━━━━━━━━━ not started (integration phase)
```

### Phase 1 — Backend (✓ closed 2026-04-26)

The seven-layer architecture, Memory V2, retrieval orchestrator, audit chain, presence detection, vision provider registry, Trust drawer UI, Quality-Eval V1+V2, Aurora canary suite. ~7 weeks of build. **Done.** Mentioned here only so the next agent knows the foundation exists.

### Phase 2 — Persona text (current — V6, ~70% complete)

**Goal:** Aurora's text replies are indistinguishable from a friend's text replies in casual conversation.

**Method:** SFT (supervised fine-tuning) on Qwen2.5-3B-Instruct via LoRA. Six iterations to date.

**Status:** V6 reaches 28% human-rate on WildChat (up from V3's 16%) and 33% in 8-turn self-chat. Real-human ceiling on this discriminator is 87%. The 60-pp gap is real and partly structural (LoRA on 3B with public conversation data has a soft ceiling well below 87%).

**Remaining sessions to plateau:** 2-6 more LoRA iterations. After that, we either accept the plateau, switch to RLHF (you-as-rater), or change base model. See "Phase 2 sub-plan" below.

### Phase 3 — Persona voice (next big multi-modal phase)

**Goal:** Aurora speaks with a specific voice. Voice cloning from a reference clip. Latency low enough to feel like a phone call.

**Status:** **Already solved in a sibling project.** Zonos voice cloning lives in QuickGrid's TTS widget (7 voices, emotion + break tags, shipped 2026-04-25). It is **not yet integrated into Aether.** Integration is the work, not the model.

**Remaining sessions:** 2-4 to integrate.

### Phase 4 — Persona avatar (still + lipsync animation)

**Goal:** Aurora has a face. Photoreal still image. Lipsync from voice in real time. 30 fps target.

**Status:** Pieces exist in sibling projects.
- FLUX.1-dev + RealVisXL Lightning generate photoreal stills (CIGE).
- LivePortrait drives still photos from audio (Library / VAULT cinematic experiments).
- `personas/*/avatar/` directories exist in Aether's persona schema with landmark caches.
- Aurora's face has not been fixed yet — needs Don's call on what she looks like.

**Remaining sessions:** 4-8 to integrate at acceptable quality. Bottleneck: Aurora's likeness lock-in (a creative call), not the tech.

### Phase 5 — Persona video real-time

**Goal:** Aurora shows up as a real-time avatar that reacts during conversation. Eyes track, expressions modulate, mouth lipsyncs.

**Status:** Research-only. The current state of local real-time avatar video at indistinguishable quality is **not solved**. Closest open-source options (LivePortrait at 30 fps, MetaHuman if cloud, Synthesia-class only cloud) all have visible artifacts or require GPU budget Don's hardware can't sustain in real-time.

**Remaining sessions:** 6-20+ over months, depending on a tech-frontier waiting game. May not be reachable at indistinguishable quality on local 3090 Ti hardware in 2026. Realistic to ship "good but visibly synthetic" avatar; "indistinguishable" probably waits.

### Phase 6 — Aurora as a whole

**Goal:** All modalities cohere. Voice + face + memory + responsiveness all consistent with one character. The integration phase.

**Status:** Not started. Depends on Phases 2-5 reaching shippable quality individually first.

**Remaining sessions:** 4-10. The work is integration + behavioral consistency tuning, not new capability.

---

## Where we are right now (the cursor)

**Active phase:** Phase 2 (Persona text), iteration V6 of estimated 8-12 to plateau.

**Branch:** `dev` at `093a597` (or wherever the next commit lands).
**Best model:** V6 LoRA at file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/checkpoints_v6/qwen25_3b_human_lora_v6/final/
**Best score:** 28% human-rate on WildChat (held-out unseen distribution).
**Days into project:** ~10 days since the current monorepo (April 18) — but built on months of v13 predecessor work.
**Sessions burned in current monorepo:** ~25 sessions of agent work since 2026-04-18, including this one.

---

## Phase 2 sub-plan (where conversation training goes from here)

You are looking at iteration counter `V6` of expected `V8-V12`.

### Why we can't just stop at V6

V6 is +12pp WildChat over V3-partial. Real progress, but:
- Multi-turn over time tends to converge to bland politeness ("anytime!", "thank you so much") — a known LLM failure mode.
- Multi-turn discriminator does not exist yet, so we can't measure that failure precisely.
- The single-turn ceiling for this base+rank+data is somewhere around 30-35% on the current discriminator. We're close to that ceiling on the current recipe.

### V7 — Likeliest next step (1 session)

Two parallel sub-tracks:

**(a) Train the multi-turn discriminator.** ~1 hour. Generate 5-turn windows from V4/V5/V6/gemma4/raw-base, train DistilBERT to distinguish those from real-human 5-turn windows. This unlocks honest measurement of what V6's multi-turn weakness actually is.

**(b) Continue multi-turn-format SFT from V6 with 2200 more steps.** ~3 hours. Tests whether V6's gain has more room (small expected payoff if it does, but it's the cheapest experiment).

Together: ~4 hours. Done in one session.

### V8 — Capacity test (1 session)

Higher-rank LoRA (rank 32 or 64) trained from base (Qwen2.5-3B) on V6's multi-turn-format data. Tests "is rank 16 the bottleneck?" If V8 > V6 by ≥5pp, capacity matters and V9+ stays on higher-rank. If V8 ≈ V6, capacity isn't the limit — data is.

### V9 — Either RLHF kickoff OR full SFT from base

This is the **structural decision point**. Two diverging paths:

**Path A — RLHF with you as the rater.**
- You spend 5-10 sessions doing pairwise judgments ("which of these two is more human?"). Tens of thousands of comparisons over weeks.
- DPO (Direct Preference Optimization) trains the model to prefer your-rated-human responses.
- Expected gain: +10-25pp on multi-turn / WildChat.
- Time cost: 20-40 hours of *your* time across multiple weeks.
- This is what makes ChatGPT and Claude actually good. We've never done it.

**Path B — Switch to a 7B base model.**
- Full retraining of V*-arc on Qwen2.5-7B-Instruct.
- 2-3x training time per iteration. ~6h per training run.
- Expected ceiling raise: +5-15pp.
- Doesn't fix the conversation-quality problem fundamentally; just gives more capacity.

**Path C — Stop and accept V6/V7/V8 as Aurora's voice.**
- 28-35% human-rate is "noticeably trained on natural conversations" — not Claude-level, but distinct from gemma4's emoji-and-italics tells.
- Ship it; let user feedback drive subsequent iterations.

Don's call. If "indistinguishable from a real friend" is the bar, Path A is the only path that gets there. Path B is a hedge. Path C is pragmatic.

### V10-V12 — Whichever path you pick

- If Path A: 3-7 RLHF sessions before plateau.
- If Path B: 2-4 retrains on 7B + LoRA.
- If Path C: maintenance only.

### After V12 (or earlier plateau)

Persona-conditioning unlock — train Aurora-specific outputs, with system-prompt-tagged registers (casual / serious / playful). This is V12+ scope. Adds ~2-4 sessions.

---

## Cross-phase decision points awaiting Don

These don't need to be decided this session, but each one gates a phase forward.

| # | Decision | Gates |
|---|---|---|
| D1 | Aurora's face — what does she look like? | Phase 4 |
| D2 | Aurora's voice — clone from whose audio? | Phase 3 |
| D3 | RLHF Path A vs base swap Path B vs ship V6 Path C | Phase 2 V9+ |
| D4 | Real-time video — pursue now or wait for tech? | Phase 5 |
| D5 | Milestone 3 theme | infrastructure |

D1 and D2 are creative calls Don should make. D3 is a strategy call. D4 is mostly external (state-of-the-art-dependent). D5 is project-management.

---

## Realistic timeline (with uncertainty bands)

The honest version. "Sessions" assumes typical 4-8 hour autonomous sessions or shorter Don-driven ones.

```
Phase 2 Persona Text V6 → V8-V12      :  3 to 10 sessions    (1-3 weeks)
Phase 3 Persona Voice integration     :  2 to 4 sessions     (3-7 days)
Phase 4 Avatar still + lipsync        :  4 to 8 sessions     (1-3 weeks)
Phase 5 Real-time video               :  6 to 20+ sessions   (1-6 months, may not finish)
Phase 6 Aurora-as-a-whole integration :  4 to 10 sessions    (1-3 weeks)
                                         ─────────────────
                                         19 to 52+ sessions   (~6 weeks to ~6 months)
```

**Best case** (everything goes well, no real-time video fight): ~6-8 weeks to "Aurora feels like a friend, with a face and voice, video as a static portrait."

**Realistic case:** ~3-4 months to that bar. Plus ~2 more if RLHF Path A is chosen.

**Worst case:** 6+ months if Phase 5 (real-time video) is pursued aggressively without breakthrough tech available.

---

## What this session changed

| Change | Where |
|---|---|
| V*-arc reached V6 (multi-turn-format SFT validated) | Phase 2 cursor moved from V3-partial to V6 |
| Multi-discriminator built (5 AI sources + 10k human) | Phase 2 eval methodology shipped |
| Scope-audit corrected; M2 Run 2 verified closed | Phase 1 cleanup |
| PERSONA_ROADMAP.md created (this file) | Cross-phase doctrine |
| V6_CONVERSATIONS.md created — readable sample outputs | Phase 2 qualitative review |
| HANDOFF_2026-04-28_AUTONOMOUS_SESSION_END.md | Session-end artifact |

---

## Standing instructions for the next session

1. **Read this file first.** It supersedes prior handoffs as the persona-trajectory map. Read alongside file:///C:/Users/dbhav/Projects/aether/ROADMAP.md (engineering substrate) for full context.
2. **Update the cursor.** When you ship a V*, move the V counter. When you cross a phase boundary, mark it. When timeline projections shift, edit them with a one-line change-log at the bottom.
3. **Don't re-litigate closed decisions.** Phase 1 backend is done. M2 Run 2 is closed. Don has locked Q1=B / Q2=single-blended-V*-arc / Q3=LoRA-continuation. Verify against `git log` if you doubt.
4. **Write for Don, not for yourself.** Don is the director. Numbers are evidence; conversations are judgment. Always include readable sample outputs when reporting on training results — see file:///C:/Users/dbhav/Projects/aether/V6_CONVERSATIONS.md as the format model.
5. **Update this file as you go, not at the end.** A roadmap that's written once and never touched rots fast.

---

## Change log

| Date | What changed | Who |
|---|---|---|
| 2026-04-28 | File created. Phase 2 cursor at V6. Phase 1 closed. | autonomous V*-arc agent |

(Future agents append here.)
