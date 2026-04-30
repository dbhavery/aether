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

**Goal (revised 2026-04-28):** Each of the 9 cast personas has a
photoreal headshot rendering with realtime lipsync from voice.
30 fps target. **Headshots only at this phase** — full-body avatars
deferred to Phase 5+ (end of project).

**Sub-phases (added 2026-04-28 after asset-schema redesign):**

**4a — Anchor sets for the 9-persona cast (current).**
Per persona, generate the Phase-4 asset schema:
`anchor.png` (canonical face-consistency reference, even diffuse
light, neutral relaxed expression, mouth closed, looking forward,
simple background) + `portrait.png` (personality shot for picker UI)
+ `profile_left.png` + `profile_right.png` (3/4 angles for lipsync
support) + voice reference clip + hand-authored system prompt. See
file:///C:/Users/dbhav/Projects/aether/personas/CHARACTERS.md for
the full roster and asset schema.
**Sessions:** 2-4 (one session per 2-3 personas).

**4b — Lipsync pipeline verified end-to-end on one persona (Aurora).**
Drive Aurora's anchor with Aurora's voice clone via PuLID + FLUX redux
or LivePortrait. Audit qualitatively: face identity consistent across
frames? Mouth shape matches phonemes? Latency target 30 fps?
**Sessions:** 1-2.

**4c — Lipsync replicated for the other 8 personas.**
Once 4b verifies, run the same pipeline for Marcus, Sara, James,
Nadia, Priya, Ray, Hannah, Tomás. Mostly mechanical at this point.
**Sessions:** 1-2.

**Status (2026-04-28):** First-pass headshots for Aurora (cafe-candid)
and Marcus (study-glasses) shipped earlier today, archived after
Don raised the face-consistency critique — single candid stills are
suboptimal as anchors for downstream face-consistent generation.
Second pass uses the proper anchor-set schema.

**Remaining sessions:** 4-8 total to ship lipsynced headshots for
all 9 personas.

### Phase 5 — Persona full body + motion video (end-of-project)

**Goal (revised 2026-04-28):** Each persona has full-body rendering
with motion. Walking, gesturing, full-figure presence in chat or
ambient UI. **Pursued at end-of-project per Don's directive 2026-04-28:
"shoot for headshots with lip-syncing now, then move towards full body
and full movement video toward the end of the project."**

**Sub-phases (planned, sequence approximate):**

**5a — Body shots per persona** (`body.png`, ~9 stills, locks
proportions/build/wardrobe).
**5b — Multi-pose reference set** (`poses/{front,three_quarter_*,...}.png`,
~3-5 stills per persona for animation rig).
**5c — Full-body motion pipeline** built end-to-end on one persona
(LivePortrait → AnimateDiff → custom rig, exact stack TBD).
**5d — Motion replicated** for the other 8.

**Status:** Deferred. Don directive 2026-04-28: "improve training
before video." Phase 5 work begins only after Phases 2 (text training)
and 4 (headshot lipsync) reach shippable quality.

**Remaining sessions:** 8-20+ over the remaining project. The body +
motion pipeline is genuinely harder than headshot lipsync; "real-time
indistinguishable" full-body avatar at local 3090 Ti hardware in 2026
is the hardest target on the trajectory and may not fully resolve.
Realistic ship target: "good but visibly synthetic" full-body in the
2027 horizon, maybe earlier if open-source tooling matures.

### Phase 6 — Aurora as a whole

**Goal:** All modalities cohere. Voice + face + memory + responsiveness all consistent with one character. The integration phase.

**Status:** Not started. Depends on Phases 2-5 reaching shippable quality individually first.

**Remaining sessions:** 4-10. The work is integration + behavioral consistency tuning, not new capability.

---

## Where we are right now (the cursor)

**Active phase:** Phase 2 (Persona text), V6 still ship default after V7/V8/V9 sweep + V9c full eval (2026-04-29).

**Branch:** `dev` at `7fc7434` or later (run `git pull` first).
**Best model:** V6 LoRA at file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/checkpoints_v6/qwen25_3b_human_lora_v6/final/
**Best score:** 28% human-rate on WildChat. Unbeaten across V7 (23.5%, overfit), V8 (20.5%, fresh-from-base under-fit), V9a (under-fit), V9b (continuation alone insufficient), V9c (25.0% — strongest non-V6, doesn't beat).

**V*-arc updates since 2026-04-28:**
- V7 archived as negative result (multi-turn-format continuation overfits) — see file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/V7_RESULTS.md
- V8 archived as negative result (rank-96 fresh-from-base under-fits at 1500 steps) — see file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/V8_RESULTS.md
- V9 sweep done — see file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/V9_SWEEP_RESULTS.md and file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/V9C_FULL_RESULTS.md
- D3 decision: V6 retained as ship default. Two open follow-ups:
  - **Path B (V9b' = V6-merged + rank-96 expansion).** Scripts shipped (file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/train_pipeline_v9b_prime.py + file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/eval_v9b_prime_full.py). Cheapest test of "is the V*-arc continuation chain the WildChat lever?" ~3-4 hr train + ~50-60 min eval.
  - **Path A (V9c-3000).** Speculative; only if Path B lands short of 28%.
- ADR-0012 (persona delivery via Tier-1 bundled previews + Tier-2 download-on-demand packs) ACCEPTED. Wizard onboarding flow shipped end-to-end in dev as of `e122bfa` → `7fc7434`. 8 cast persona packs bundled + seeded into `<app_data>/personas/` on first boot.

**Days into project:** ~11 days since the current monorepo (April 18) — but built on months of v13 predecessor work.
**Sessions burned in current monorepo:** ~28 sessions of agent work since 2026-04-18, including the autonomous continuation runs of 2026-04-29.

---

## Bare-metal parallelization (added 2026-04-28)

Don's pushback this session: "We aren't using retail software. Can any of this be done in parallel? How about moving anything we don't need to RAM?"

Right call. The prior arc treated GPU and CPU as serial phases. GPU sat at 24 GB during training but 6-10 GB during eval, and CPU was idle most of the time. This addendum locks the bare-metal parallelization rules.

### Hardware envelope

RTX 3090 Ti (24 GB VRAM) + 64 GB system RAM. The 64 GB RAM is currently underused — most sessions touch <8 GB. Use it.

### Standing rules for V7+ training sessions

| # | Rule | Why |
|---|---|---|
| 1 | **Discriminator inference → CPU permanently** | DistilBERT ~250 MB, runs ~17 docs/sec on CPU. Frees 0.5-1 GB VRAM for the main pipeline. |
| 2 | **`optim="adamw_8bit"` always (bitsandbytes)** | Drops optimizer state from 4 GB to 0.5 GB. Same accuracy. Drop-in replacement. |
| 3 | **`offload_optimizer=True` during training** | Frees 8-10 GB VRAM by moving Adam state to CPU RAM. Costs 5-15% step time. We have the RAM. |
| 4 | **CPU work runs concurrently with GPU work** | Data prep, normalization, JSON writes, report scaffolds — always launch as background bash tasks during GPU pipelines. |
| 5 | **Two-process GPU sharing when VRAM allows** | A generation process (~6 GB) + a training process (~14 GB w/ rules 2-3) shares one GPU via CUDA's stream scheduler. Saves ~25% session wallclock. |
| 6 | **`PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512`** | Predictable allocation when two processes share GPU. Set as env var. |
| 7 | **Pre-load eval datasets to CPU memory at session start** | GPU shouldn't wait on disk reads. `to_list()` and keep in Python. |
| 8 | **Kill stray Ollama before GPU-heavy work** | 5 GB tax. Set `OLLAMA_KEEP_ALIVE=0` for short gens. |
| 9 | **`PYTHONUTF8=1` always** | cp1252 surfaces in trl/transformers reading non-ASCII corpora on Windows. |
| 10 | **`device_map="auto"` + `offload_folder` for big-model swap** | If V9 path B (7B base) lands, accelerate puts layers 0-15 GPU, 16-31 CPU. Slower but fits. |

### Concrete VRAM accounting for V7 with these rules

| Component | Without rules | With rules 2 & 3 |
|---|---:|---:|
| Qwen2.5-3B base in 4-bit | 2.0 GB | 2.0 GB |
| LoRA adapter rank 16 (active params) | 0.5 GB | 0.5 GB |
| Activations + gradients (batch 4, max_length 1024) | 4.5 GB | 4.5 GB |
| Optimizer state (Adam fp32 momentum + variance) | **8-12 GB** | **0.5 GB** (rest on CPU) |
| KV cache during inline eval | 2.5 GB | 2.5 GB |
| **Training-phase total** | **~22 GB** | **~7.5 GB** |
| **Eval-phase headroom** | ~14 GB | ~16 GB |

The unlock: training uses only ~7.5 GB instead of ~22 GB. The other ~14-16 GB is available for a *concurrent* generation or training process. That's why pipelining V7 + V8 fits in one session.

### Pipeline pattern for V7 onward

```
HOUR 0────1────2────3────4────5
GPU [discrim train ~1h][V7 LoRA train ~3h───────][V7 gen + V8 train start ~1h]
CPU [V8 data prep ~30m][rescore V*-arc on new discrim ~30m][V7 report ~30m]
```

GPU is busy 100% of the session. CPU is busy whenever GPU is busy. Sessions get ~25-40% more done per wallclock hour.

### When to NOT pipeline

Robustness wins over speed when:
- Don is AFK and an OOM at hour 4 isn't recoverable for hours.
- A new technique is introduced and we want clean attribution of what worked.
- The session has a hard deadline (e.g. Don coming back) and a partial result beats a crashed pipeline.

In those cases, fall back to serial training. Document the fallback choice in the session report.

---

## Phase 2 sub-plan (where conversation training goes from here)

You are looking at iteration counter `V6` of expected `V8-V12`. **All V7+ sessions should default to pipelined execution per the rules above.**

### Why we can't just stop at V6

V6 is +12pp WildChat over V3-partial. Real progress, but:
- Multi-turn over time tends to converge to bland politeness ("anytime!", "thank you so much") — a known LLM failure mode.
- Multi-turn discriminator does not exist yet, so we can't measure that failure precisely.
- The single-turn ceiling for this base+rank+data is somewhere around 30-35% on the current discriminator. We're close to that ceiling on the current recipe.

### V7 — Pipelined dual experiment (1 session, ~5h, was ~9h serial)

Default to **V7 + V8-partial in one session** using the pipeline pattern above. Three GPU sub-phases interleaved with three CPU sub-phases:

**(a) Multi-turn discriminator** (GPU, ~1h). 5-turn windows from V4/V5/V6/gemma4/raw-base + real-human 5-turn windows from `data/normalized_eval_v3.jsonl`. ~3000 each. 2 epochs DistilBERT. Save to `checkpoints_v7/multi_turn_discriminator/final/`.

**(b) V7 LoRA continuation from V6** (GPU, ~3h). Same multi-turn-format SFT, lr 1e-4, max_length 1024. Use rules 2 & 3 above (8-bit optimizer + offload). Save to `checkpoints_v7/qwen25_3b_human_lora_v7/final/`.

**(c) V8 rank-32 LoRA from base** (GPU, ~1h start; finishes in next session). Higher-rank capacity test. Overlapped with V7 generation in the final hour. Save to `checkpoints_v8/qwen25_3b_human_lora_v8/`.

**CPU pipelines run concurrently:**
- V8 data prep during (a)
- Re-score V*-arc against new multi-turn discriminator during (b)
- V7 report scaffold during (c)

Result: ~5h instead of ~9h serial. V7 fully done + V8 launched.

### V8 — Capacity test (continued / completes in same or next session)

Higher-rank LoRA trained from base (Qwen2.5-3B) on V6's multi-turn-format data. Tests "is rank 64 the bottleneck?" If V8 > V6 by ≥5pp, capacity matters and V9+ stays on higher rank. If V8 ≈ V6, capacity isn't the limit — data is.

**Correction 2026-04-28:** prior versions of this section said "rank 16" / "rank 32" — both wrong. V6's `adapter_config.json` shows rank 64, alpha 128. V8 launched with rank 96 (was originally planned at rank 128, dropped after in-flight V7 telemetry showed only ~240 MB VRAM headroom on the 3090 Ti). Still a +50% capacity bump vs V6 — meaningful test.

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

| # | Decision | Gates | Status |
|---|---|---|---|
| D1 | Aurora's face — what does she look like? | Phase 4 | **RESOLVED 2026-04-28** — candidate 03 (FLUX-pro), see avatar/portrait.png |
| D2 | Aurora's voice — clone from whose audio? | Phase 3 | **RESOLVED 2026-04-28** — gpt-4o-mini-tts voice 'nova', see voice/reference.wav |
| D3 | RLHF Path A vs base swap Path B vs ship V6 Path C | Phase 2 V9+ | **DELEGATED to engineering agent** — pick after V7+V8 results land |
| D4 | Real-time video — pursue now or wait for tech? | Phase 5 | **DEFERRED 2026-04-28** — Don directive: "improve training before video" |
| D5 | Milestone 3 theme | infrastructure | open |

Cast expansion (autonomous, per Don's 2026-04-28 directive "keep developing these characters using your own judgement"): see file:///C:/Users/dbhav/Projects/aether/personas/CHARACTERS.md for the planned 4-persona roster (Aurora + Marcus Chen + Sara Reyes + James Whitfield) covering ANALYTICAL/CREATIVE × SUPPORTIVE/PRACTICAL quadrants.

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
| 2026-04-28 (eve) | V7+V8 pipeline launched unattended (~5-6h wallclock). V7 = LoRA continuation from V6 with adamw_8bit. V8 = rank-96 LoRA from base (corrected from "rank 32 from base" — V6 is already rank 64; rank-96 fits VRAM after rank-128 OOM risk surfaced from V7 telemetry). Multi-turn discriminator descoped to next session. Cursor moves to V7/V8 once results land. See HANDOFF_2026-04-28_V7_V8_PIPELINE_LAUNCHED.md. | V7+V8 launch agent |
| 2026-04-28 (night) | **Persona cast redesigned to 9 characters** + new asset schema. Don directive: "These will eventually be full human-like video avatars, with full bodies. Headshots with lip-syncing now, then full body and full movement video toward the end of the project." First-pass picks (Aurora cafe-candid, Marcus study-glasses) archived after face-consistency critique landed — single candid stills are suboptimal as anchors for downstream lipsync. Second-pass schema = anchor.png (canonical neutral reference, even diffuse light) + portrait.png (personality picker shot) + profile_left/right.png (3/4 angles). Phase 4 split into 4a (anchor sets, current) / 4b (lipsync verified on Aurora) / 4c (lipsync replicated for 8 others). Phase 5 split into 5a (body shots) / 5b (multi-pose) / 5c (motion pipeline) / 5d (motion replicated) — deferred to end-of-project. Roster: Aurora Nash, Marcus Chen, Sara Reyes, James Whitfield, Nadia Volkov, Priya Iyer, Ray Castellano, Hannah Park, Tomás Andrade. See file:///C:/Users/dbhav/Projects/aether/personas/CHARACTERS.md. | persona-cast redesign agent |

(Future agents append here.)
