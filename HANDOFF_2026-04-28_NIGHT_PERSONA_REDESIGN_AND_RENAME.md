# Ultra-Detailed Handoff — 2026-04-28 Night Session

> Successor to:
> - file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-04-28_V7_V8_PIPELINE_LAUNCHED.md
> - file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-04-28_AUTONOMOUS_SESSION_END.md
>
> This handoff supersedes both for status reading. Where they
> conflict with this doc, this doc wins.
>
> **Branch:** `dev` at `6b4fde8` (pushed). All session work landed.
> **Wallclock:** ~3.5h Don-driven session 2026-04-28 17:55 → 21:30 PT.
>
> **Rename pending:** project public-facing name changing from
> "Aether" to "Companion." This handoff still uses "Aether" (the
> rename has not executed yet — see §Rename below for plan).

---

## TL;DR

Three threads of work this session:

1. **V7+V8 LoRA training pipeline launched unattended at 18:00 PT.** Currently 97% through V7 train; full pipeline (V7 train → V7 eval → V8 train → V8 eval) ETA ~23:45 PT. Engineering-side work done by 18:30; the rest is wallclock waiting.

2. **Persona cast redesigned end-to-end.** 4-persona plan grew to 9. Asset schema replaced (single portrait → anchor + portrait + profile_left + profile_right). Phase 4/5 split into sub-phases. Aurora's first-pass shipped earlier today was archived after Don raised the face-consistency critique; her new anchor-schema pack shipped. Marcus archived, awaiting next-session regen. 7 more personas need full asset packs over the next several sessions.

3. **Public rename Aether → Companion directed but not executed.** Planning doc shipped; atomic-commit execution queued for next session per Don's "next 24 hrs" directive.

---

## What's running NOW

### V7+V8 LoRA training orchestrator

- **Process:** `python run_v7_v8_pipeline.py` PID 70398, started 2026-04-28 18:00:09 PT.
- **Phase at handoff write time:** V7 train ~step 1450/1500 (97%, ~4 min left).
- **Pipeline ETA:** ~23:45 PT for all four phases (V7 train ~85min → V7 eval ~50min → V8 train ~125min → V8 eval ~50min).
- **GPU:** 24076/24314 MiB used, ~240 MiB free. Stable. No OOM in 95 min of training.
- **Step time:** ~5.0s/step (started at 4s, climbed to 8s with longer batches, settled at ~5s).
- **Logs:**
  - file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/logs_v7/orchestrator.log
  - file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/logs_v7/v7_train.log
  - logs_v7/v7_eval.log + logs_v8/v8_train.log + logs_v8/v8_eval.log will populate as phases run
- **Phase flag files** (orchestrator's resume state):
  - logs_v7/phase_train.done — set when V7 training finishes
  - logs_v7/phase_eval.done — set when V7 eval finishes
  - logs_v8/phase_train.done — set when V8 training finishes
  - logs_v8/phase_eval.done — set when V8 eval finishes
- **If orchestrator crashes:** safe to re-run `python run_v7_v8_pipeline.py` — phase flags skip completed work.

### Other agents

None known. The Isabelle_Kunstig sibling agent reference in MEMORY is for a different project (Projects/Isabelle_Kunstig/), not this repo. Aether/Companion has the GPU lock for the next several hours.

---

## Don's directives this session, in order

| # | Directive (paraphrased) | Status |
|---|---|---|
| 1 | "Go" — execute the V7+V8 pipelined experiment | DONE — orchestrator launched, running unattended |
| 2 | OLLAMA_FLASH_ATTENTION=false permanent env var | DONE by Don (PowerShell setx) |
| 3 | fridge_open.jpg in tools/evals/fixtures/ | DONE by Don |
| 4 | 10th-paraphrase decision (b — leave as canary) | RESOLVED, committed to STATE_2026-04-28.md |
| 5 | Aurora's face — "you create the characters, good-looking" | First-pass shipped (cafe-candid candidate 03), then archived after face-consistency critique; new anchor set shipped |
| 6 | "Continue" / "Go" on the avatar swap | Path (b): replaced 2026-04-17 portrait with FLUX-pro candidate 03 (later archived again) |
| 7 | Aurora's voice — "any voice that you think matches, just make sure it sounds like a natural human, conversational speaker" | DONE — gpt-4o-mini-tts voice 'nova' with warm-conversational steering, 20.0s reference + 4.0s sample |
| 8 | "Keep developing these characters using your own judgement for looks, voice, etc. Use realistic names. Improve training before video." | Cast plan locked at 9 personas, training-first priority captured in PERSONA_ROADMAP, D4 (real-time video) DEFERRED |
| 9 | "How many characters?" → settled on 9 after Don pushed back on 4 | LOCKED at 9 in CHARACTERS.md |
| 10 | "These will eventually be full human-like video avatars, with full bodies. Headshots with lipsync now, then full body and full movement video toward the end of the project." | Phase 4/5 split into sub-phases reflecting this trajectory |
| 11 | "You can start the characters over. It's fine. Update all project files." | Aurora redone with anchor schema; Marcus archived; CHARACTERS.md + PERSONA_ROADMAP.md updated; first-pass packs preserved under `_archived_2026-04-28_first_pass/` |
| 12 | "Public facing name now = 'Companion'. Make all necessary changes within next 24 hrs." | PLAN written (RENAME_TO_COMPANION.md); execution queued for next session |

---

## Persona cast state (full inventory)

### Roster — 9 personas planned

| # | Slug | Display name | Archetype | Portrait state | Voice state | persona.yaml |
|---|---|---|---|---|---|---|
| 1 | `aurora` | Aurora Nash | warm_supportive | ✓ ANCHOR SET shipped (anchor + portrait + profile_left + profile_right, FLUX-pro v1.1-ultra, 2752×1536 raw) | ✓ shipped (gpt-4o-mini-tts nova, 20.0s ref + 4.0s sample) | ✓ shipped, hand-authored |
| 2 | `marcus_chen` | Marcus Chen | analytical_focused | ✗ first-pass archived; new anchor set NOT generated | ✓ shipped (gpt-4o-mini-tts ash, 20.0s + 4.0s) | ✓ shipped, hand-authored |
| 3 | `sara_reyes` | Sara Reyes | playful_creative | ✗ not yet generated; portrait URL was returned but never assembled under new schema | ✓ generated to disk (gpt-4o-mini-tts coral, 20.0s + 4.0s) but uncommitted | ✓ DRAFTED on disk but uncommitted |
| 4 | `james_whitfield` | James Whitfield | grounded_practical | ✗ not yet generated under new schema | ✓ generated (gpt-4o-mini-tts sage, 20.0s + 4.0s) but uncommitted | ✓ DRAFTED on disk but uncommitted |
| 5 | `nadia_volkov` | Nadia Volkov | rigorous_skeptic | ✗ planned only | ✗ planned only | ✗ not authored |
| 6 | `priya_iyer` | Priya Iyer | strategic_executive | ✗ planned only | ✗ planned only | ✗ not authored |
| 7 | `ray_castellano` | Ray Castellano | field_commander | ✗ planned only | ✗ planned only | ✗ not authored |
| 8 | `hannah_park` | Hannah Park | depth_researcher | ✗ planned only | ✗ planned only | ✗ not authored |
| 9 | `tomas_andrade` | Tomás Andrade | direct_coach | ✗ planned only | ✗ planned only | ✗ not authored |

### Asset schema (Phase 4 — current target)

Per persona, the goal pack is:

```
personas/<slug>/
├── persona.yaml          # display_name, archetype, hand-authored system prompt
├── metadata.yaml         # full provenance for every asset (incl prior_versions)
├── avatar/
│   ├── anchor.png        # canonical face-consistency reference
│   ├── portrait.png      # personality picker shot
│   ├── profile_left.png  # 3/4 left angle
│   ├── profile_right.png # 3/4 right angle
│   ├── anchor_set_raw_<date>/  # raw JPGs for re-cropping
│   └── README.md         # per-asset provenance
└── voice/
    ├── reference.wav     # 20.0s 24kHz mono 16bit PCM
    ├── sample.wav        # 4.0s wizard preview
    ├── voice.yaml        # Chatterbox knobs + ElevenLabs voice_id slot
    └── SOURCE.md         # generation provenance + reference text
```

### Phase 4 sub-phases (added 2026-04-28)

- **4a — anchor sets for all 9 personas** (current). 5 generations per persona × 9 personas = ~45 FLUX-pro calls. The bottleneck is the hand-authored system prompts (each is a character bible, deserves real thought).
- **4b — lipsync pipeline verified end-to-end on Aurora.** Drive Aurora's anchor with her voice clone via PuLID + FLUX redux or LivePortrait. Audit: face identity consistent across frames? Mouth shape matches phonemes? Latency 30 fps?
- **4c — lipsync replicated for the other 8.** Mostly mechanical once 4b verifies.

### Phase 5 sub-phases (deferred to end-of-project)

- **5a — body shots** (~9 stills, locks proportions/build/wardrobe)
- **5b — multi-pose reference set** (~3-5 stills per persona for animation rig)
- **5c — full-body motion pipeline** built on one persona
- **5d — motion replicated** for the other 8

Don directive: "improve training before video." Phase 5 unblocks only after Phase 2 (text training) plateau and Phase 4 lipsync ships.

### What was archived from the first pass

The 2026-04-28 morning attempt shipped Aurora (cafe-candid candidate 03 chosen by Don) and Marcus (study-glasses, agent-picked under autonomy directive). After Don raised the face-consistency critique, both were archived:

- file:///C:/Users/dbhav/Projects/aether/personas/aurora/_archived_2026-04-28_first_pass/
- file:///C:/Users/dbhav/Projects/aether/personas/marcus_chen/_archived_2026-04-28_first_pass/

Each archive contains the original portrait + states + candidates dirs + a REASON.md explaining why the second-pass anchor schema replaced it. The Aurora archive is layered (it also contains the original 2026-04-17 gpt-image-1.5 attempt nested under `_archived_2026-04-17/`).

### What's NOT in the schema (intentionally)

- **Pre-generated expression states (idle/listening/thinking/speaking).** First-pass had 4 PNGs per persona. Replaced 2026-04-28 by runtime rendering from `anchor.png` + visemes via the Phase 4b lipsync pipeline. Pre-generated stills are abandoned because runtime rendering produces more consistent results.
- **Body shots, multi-pose, motion video.** Phase 5+, end-of-project.
- **Wardrobe variants.** Locked single look per persona for now.

### What's stored on disk but not committed (Sara & James)

These were generated during the session but never assembled under the new anchor schema before the redesign landed:

- `personas/sara_reyes/voice/reference.wav` — 20.0s gpt-4o-mini-tts coral
- `personas/sara_reyes/voice/sample.wav` — 4.0s
- `personas/sara_reyes/persona.yaml` — hand-authored system prompt (playful_creative archetype, "Oh — wait, what if we flipped it?" voice examples)
- `personas/james_whitfield/voice/reference.wav` — 20.0s gpt-4o-mini-tts sage
- `personas/james_whitfield/voice/sample.wav` — 4.0s
- `personas/james_whitfield/persona.yaml` — hand-authored system prompt (grounded_practical archetype, "Yeah. Yeah, I hear you." voice examples)

These are good drafts; **next session should commit them alongside their newly-generated anchor sets**, not regenerate from scratch.

---

## Rename Aether → Companion

### Status

Planning doc shipped (file:///C:/Users/dbhav/Projects/aether/RENAME_TO_COMPANION.md). Execution NOT done in this session — Don's directive said "next 24 hrs," not urgent.

### Scope split

**CHANGE (user-visible):**
| File | What changes |
|---|---|
| `README.md` | "Free Aether — Community Edition" → "Free Companion — Community Edition", first paragraph, body refs (lines 1, 15, 17, 39, 45, 390+) |
| `apps/desktop/src-tauri/tauri.conf.json` | `productName: "Aether"` → `"Companion"`; window `title: "Aether"` → `"Companion"`; `shortDescription` + `longDescription` line 44-45 |
| `apps/desktop/index.html` | `<title>` if it says Aether |
| `personas/CHARACTERS.md` | "Aether Persona Cast" heading + intro |
| `personas/README.md` | "ship with Aether v1.0" → "ship with Companion v1.0" |
| `personas/{aurora,marcus_chen,caelum,luma,sara_reyes,james_whitfield}/persona.yaml` | header comment "Canonical persona pack for the Aether first-run wizard" → "Companion first-run wizard" |
| `personas/*/metadata.yaml` | prose "owned by Aether" → "owned by Companion"; license identifier `custom_aether` STAYS |
| `personas/*/voice/SOURCE.md` | prose "Aether persona pack's `custom_aether` license" → "Companion persona pack's `custom_aether` license" |
| `personas/_example/metadata.yaml` | `creator: "Aether"` → `"Companion"` |
| Any wizard / onboarding UI string in `apps/desktop/src/` | Aether → Companion |

**KEEP (internal codename):**
- Repo / directory `aether/`, GitHub `dbhavery/aether`
- Tauri identifier `dev.aether.desktop` (changing breaks auto-update + user data)
- Crate / package names (`aether-*` Rust crates, TS packages)
- Database files (`aether.db`, `aether_audit.db`)
- Code identifiers, internal docs, planning/, ROADMAP, ADRs, MEMORY, CLAUDE.md
- License identifier `custom_aether` (license names are forever)

**Out-of-band Don actions** (optional, not blocking the rename):
- GitHub repo rename `dbhavery/aether` → `dbhavery/companion` (Don only, GitHub web UI)
- Portfolio showcase URL update at `dbhavery.dev/aether` (separate repo)

### Rollout plan (next session)

5 atomic commits, each independently reviewable:

1. `docs: rename public — README.md` (top-level marketing surface)
2. `apps(desktop): rename productName + window title to Companion` (Tauri config + HTML title)
3. `personas: rename public references to Companion in YAML headers + metadata notes`
4. `apps(desktop): rename UI strings to Companion` (wizard / onboarding / about-screen if any)
5. `personas/CHARACTERS.md`: rename heading + intro to "Companion Persona Cast"

After all 5 commits land, update RENAME_TO_COMPANION.md decision log to mark COMPLETE.

---

## Repo state (commits this session, all on dev)

| Commit | Subject |
|---|---|
| `d3168f2` | training(v8): build_v8_sft.py — multi-turn windows 8-12 turns |
| `5bbce81` | training(v7): LoRA continuation from V6 with adamw_8bit |
| `5040950` | training(v8): rank-128 LoRA from base — capacity test |
| `e6d92c4` | training(eval): V7 + V8 eval scripts |
| `26d1f09` | training: run_v7_v8_pipeline.py — sequential V7+V8 orchestrator |
| `a0ea0b2` | training(v8): drop to rank-96 + batch-2 — VRAM telemetry correction |
| `9727cc4` | docs: V7+V8 pipeline handoff + PERSONA_ROADMAP cursor update |
| `7359046` | docs(state): RESOLVE 10th-paraphrase canary decision — leave as canary |
| `4e32a96` | personas(aurora): D1 RESOLVED — Aurora's face is candidate 03 (FLUX-pro) |
| `17bb1b3` | personas(aurora): D2 RESOLVED — Aurora's voice via gpt-4o-mini-tts nova |
| `60df5c3` | personas(marcus_chen): new persona — analytical_focused archetype |
| `ccaf889` | docs: persona cast design doc + decision-table updates |
| `8be19fb` | personas: redesign — anchor schema, 9-roster cast, redo Aurora + Marcus |
| `6b4fde8` | docs: RENAME_TO_COMPANION.md — public rename plan (Aether → Companion) |

**Branch tip:** `6b4fde8` on `dev`, pushed.

**Working tree note:** when next session opens, the V7+V8 training orchestrator will likely have produced `phase_*.done` files and populated `eval_v7/` / `eval_v8/` directories. These are untracked (gitignored under `planning/session_*/training/data/` and various checkpoint paths). Verify with `git status` before assuming.

---

## Open decisions Don owes

| # | Decision | Gating | Status |
|---|---|---|---|
| D1 | Aurora's face | Phase 4 | RESOLVED 2026-04-28 (anchor set committed) |
| D2 | Aurora's voice | Phase 3 | RESOLVED 2026-04-28 (gpt-4o-mini-tts nova) |
| D3 | V9 path: RLHF / 7B base swap / ship V6 | Phase 2 V9+ | DELEGATED to engineering agent post-V7+V8 results |
| D4 | Real-time video — pursue now or wait | Phase 5 | DEFERRED 2026-04-28 (training first) |
| D5 | Milestone 3 theme | infrastructure | OPEN |
| D6 | Rename out-of-band actions | brand consistency | OPEN — GitHub repo rename + portfolio URL update are Don-only actions |
| D7 | Are non-Aurora personas (Marcus/Sara/James) personality-shot QA approved? | Phase 4a continuing | OPEN — Don should eyeball Aurora's anchor-set 4 images side-by-side first |

---

## What the next session should do, in order

### Priority 1 — verify training results

When you open the session, the V7+V8 pipeline may have completed (~23:45 PT or later). Verify:

```bash
cd C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/
ls logs_v7/phase_train.done logs_v7/phase_eval.done logs_v8/phase_train.done logs_v8/phase_eval.done
```

If all 4 flags exist:
- Read `eval_v7/v7_eval_results.json` and `eval_v8/v8_eval_results.json`
- Pull representative samples from `eval_v*/v*_self_test_transcripts.jsonl`
- Write `V7_RESULTS.md` + `V7_CONVERSATIONS.md` + `V8_RESULTS.md` + `V8_CONVERSATIONS.md` per the V6_CONVERSATIONS.md format
- Update PERSONA_ROADMAP cursor and best-on-WildChat number
- Decision-rule table in HANDOFF_2026-04-28_V7_V8_PIPELINE_LAUNCHED.md tells you which V9 path is implied

If any flag is missing:
- Read the corresponding `*_train.log` or `*_eval.log` for the failure mode
- Common failures + recovery in HANDOFF_2026-04-28_V7_V8_PIPELINE_LAUNCHED.md §"Hard-fail conditions"

### Priority 2 — execute the rename

Per RENAME_TO_COMPANION.md, 5 atomic commits. Each commit references the plan doc. Do this before more persona work so subsequent persona docs are written under the new public name.

### Priority 3 — finish persona pack assembly for Marcus / Sara / James

In order:

**Marcus Chen (most progress, just needs new anchor set):**
- Generate anchor + portrait + profile_left + profile_right via FLUX-pro v1.1-ultra. Marcus prompt notes in `_archived_2026-04-28_first_pass/avatar_README.md`. Anchor needs different framing (neutral light, mouth closed, looking forward) — DO NOT reuse the old prompt verbatim.
- Update metadata.yaml with the new anchor schema (use Aurora's new metadata.yaml as the template).
- Update avatar/README.md.
- Commit + push.

**Sara Reyes (voice + persona.yaml on disk uncommitted):**
- Verify `personas/sara_reyes/voice/{reference,sample}.wav` and `personas/sara_reyes/persona.yaml` are present (they should be from this session).
- Generate anchor + portrait + profile_left + profile_right via FLUX-pro. Sara archetype: Latina woman late 20s, dark wavy hair, expressive mid-thought smile, denim jacket, outdoor cafe terrace.
- Build metadata.yaml + avatar/README.md + voice/voice.yaml + voice/SOURCE.md from Aurora's templates.
- Commit + push.

**James Whitfield (same shape as Sara):**
- Voice + persona.yaml on disk, uncommitted.
- Generate anchor set.
- Assemble.
- Commit + push.

### Priority 4 — generate the 5 new personas

Per CHARACTERS.md, in order:
1. Nadia Volkov — rigorous_skeptic
2. Priya Iyer — strategic_executive
3. Ray Castellano — field_commander
4. Hannah Park — depth_researcher
5. Tomás Andrade — direct_coach

Each requires:
- Hand-authored system prompt (slow part — character bible, ~30 min/persona of real thought)
- 4 FLUX-pro stills (anchor + portrait + profile_left + profile_right)
- 2 OpenAI gpt-4o-mini-tts WAVs (reference + sample) with archetype-specific steering
- 5 doc files (persona.yaml, metadata.yaml, avatar/README.md, voice/voice.yaml, voice/SOURCE.md)

Realistic pace: 1-2 personas per session. So full cast complete 3-4 sessions out.

### Priority 5 — verify lipsync end-to-end on Aurora (Phase 4b)

Once all 9 personas have anchor sets, build the lipsync pipeline:
- Pick stack: PuLID + FLUX redux, or LivePortrait, or hybrid
- Drive Aurora's anchor.png with Aurora's voice/reference.wav clone
- Audit: face identity consistent across frames? Mouth match phonemes? Latency 30 fps target?
- Once verified on Aurora, replicate for the 8 others (Phase 4c, mostly mechanical)

This is a research session, not a "spec → execute" session. Allocate 1-2 sessions for the pipeline build.

---

## Critical "do not redo" items

These are closed; future agents should not re-litigate:

- **V6 is rank 64 / alpha 128**, not "rank 16" or "rank 32" as earlier docs claimed. Verified against `personas/aurora/avatar/_archived_2026-04-17/...adapter_config.json`. Repo beats prompt.
- **V7 = LoRA continuation from V6 with adamw_8bit, 1500 steps. V8 = rank-96 from base, 1500 steps, batch 2, grad_accum 8.** VRAM-safe per V7 telemetry showing 240 MB headroom at rank-64 + batch-4. DO NOT increase V8 to rank-128 without dropping batch further.
- **Aurora's first-pass cafe-candid is archived for face-consistency reasons, not because Don changed his mind on the look.** The personality shot itself is fine; it's just the wrong asset to lock downstream pipelines to. The new anchor schema ships both anchor (canonical face) and portrait (personality), so nothing is lost.
- **Marcus's first-pass is archived. His voice + persona.yaml are NOT archived — they're at canonical paths.** Same for any future persona where face needs redo but voice + system prompt are fine.
- **Pre-generated expression states (idle/listening/thinking/speaking) are abandoned.** Replaced by runtime rendering from anchor + visemes via Phase 4b lipsync pipeline. Do not generate states/*.png stills for new personas.
- **Phase 5 (full body + motion) is DEFERRED until end-of-project.** Don directive 2026-04-28: "improve training before video."
- **Multi-turn discriminator was descoped from the V7+V8 run.** Use existing `checkpoints_v4/discriminator_multi/` (single-turn DistilBERT) for V7/V8 eval. Multi-turn discriminator is a separate session's work if it ever happens.
- **D4 is closed (DEFERRED).** Don pinged this multiple times. Don't re-ask.
- **The 10th paraphrase variant for `memory_appropriateness` is intentionally left out** of expectations. Don picked option (b) — leave as canary. Don't add it later "to make the test pass."
- **OLLAMA_FLASH_ATTENTION=false is set system-wide as of 2026-04-28 by Don.** The training scripts no longer need to plumb this per-process. Verify with `echo %OLLAMA_FLASH_ATTENTION%` before assuming.
- **Tauri identifier `dev.aether.desktop` STAYS** when the rename to Companion executes. Changing it breaks auto-update channels and user data paths. License identifier `custom_aether` also stays.

---

## File index — what was created / modified this session

### New files

| Path | What |
|---|---|
| `planning/session_2026-04-26/training/build_v8_sft.py` | V8 multi-turn data prep (8-12 turn windows) |
| `planning/session_2026-04-26/training/train_pipeline_v7.py` | V7 LoRA continuation from V6 |
| `planning/session_2026-04-26/training/train_pipeline_v8.py` | V8 rank-96 LoRA from base |
| `planning/session_2026-04-26/training/eval_v7.py` | V7 held-out + WildChat + self-test eval |
| `planning/session_2026-04-26/training/eval_v8.py` | V8 same |
| `planning/session_2026-04-26/training/run_v7_v8_pipeline.py` | Sequential orchestrator |
| `HANDOFF_2026-04-28_V7_V8_PIPELINE_LAUNCHED.md` | First handoff (training launch) |
| `personas/aurora/avatar/anchor.png` | Aurora canonical face reference (NEW second-pass) |
| `personas/aurora/avatar/portrait.png` | Aurora personality picker shot (NEW second-pass, replaces first-pass) |
| `personas/aurora/avatar/profile_left.png` | Aurora 3/4 left |
| `personas/aurora/avatar/profile_right.png` | Aurora 3/4 right |
| `personas/aurora/avatar/anchor_set_raw_2026-04-28/*.jpg` | Raw FLUX outputs (4 files) |
| `personas/aurora/avatar/README.md` | New anchor-schema provenance |
| `personas/aurora/_archived_2026-04-28_first_pass/...` | First-pass Aurora pack archived |
| `personas/marcus_chen/_archived_2026-04-28_first_pass/...` | First-pass Marcus pack archived |
| `personas/marcus_chen/persona.yaml` | Hand-authored Marcus system prompt |
| `personas/marcus_chen/metadata.yaml` | Marcus provenance |
| `personas/marcus_chen/voice/{reference,sample}.wav` | Marcus voice (gpt-4o-mini-tts ash) |
| `personas/marcus_chen/voice/voice.yaml` | Marcus Chatterbox knobs |
| `personas/marcus_chen/voice/SOURCE.md` | Marcus voice provenance |
| `personas/sara_reyes/persona.yaml` | DRAFTED, uncommitted, on disk |
| `personas/sara_reyes/voice/{reference,sample}.wav` | DRAFTED, uncommitted, on disk |
| `personas/james_whitfield/persona.yaml` | DRAFTED, uncommitted, on disk |
| `personas/james_whitfield/voice/{reference,sample}.wav` | DRAFTED, uncommitted, on disk |
| `personas/CHARACTERS.md` | 9-roster cast design doc |
| `RENAME_TO_COMPANION.md` | Rename plan |
| `HANDOFF_2026-04-28_NIGHT_PERSONA_REDESIGN_AND_RENAME.md` | This file |

### Modified files

| Path | What |
|---|---|
| `PERSONA_ROADMAP.md` | Phase 4/5 sub-phases added; decision table updated; change log appended |
| `personas/aurora/persona.yaml` | display_name → "Aurora Nash" |
| `personas/aurora/metadata.yaml` | anchor + portrait + profile_left + profile_right entries; state_images marked DEFERRED |
| `planning/session_2026-04-26/STATE_2026-04-28.md` | 10th-paraphrase decision marked RESOLVED |
| `C:/Users/dbhav/.claude/projects/C--Users-dbhav-Projects/memory/MEMORY.md` | V7+V8 launch state + rename to Companion noted |

### Untracked / generation scratch

- V7+V8 training checkpoints under `checkpoints_v7/` and `checkpoints_v8/` (gitignored per `*.gitignore` rule blocking trainer/ state). Only `final/` adapters and `training_meta.json` will be force-added when training completes.
- Background-task output logs under `C:\Users\dbhav\AppData\Local\Temp\claude\...` (cleaned automatically).

---

## Wallclock summary (this session)

| Step | Wallclock |
|---|---:|
| Mandatory first reads + repo state verification | ~5 min |
| V8 data prep (CPU) | <2 min |
| Authoring V7/V8 training scripts (build_v8_sft, train_pipeline_v7, train_pipeline_v8, eval_v7, eval_v8, run_v7_v8_pipeline) | ~25 min |
| Pre-flight (gitignore check, syntax check, optim sanity check) | ~3 min |
| Orchestrator launch + verification | ~2 min |
| HANDOFF_V7_V8 doc + PERSONA_ROADMAP update + first push | ~10 min |
| 10th paraphrase decision committed | ~2 min |
| Aurora candidate generation (4 candidates via FLUX-pro) | ~2 min generation + ~5 min file work |
| Aurora face committed | ~5 min |
| Aurora voice generated (gpt-4o-mini-tts nova) + committed | ~10 min |
| Cast plan written (CHARACTERS.md, 4 personas) + Marcus generated + committed | ~20 min |
| Sara + James generated (background, voice + persona.yaml) but uncommitted | ~10 min |
| 9-persona expansion debate + CHARACTERS.md rewrite | ~10 min |
| Anchor-schema redesign + Aurora redo (4 stills + metadata + README + commit) | ~20 min |
| RENAME_TO_COMPANION.md plan written + committed | ~10 min |
| MEMORY.md update | ~2 min |
| This handoff doc | ~25 min |
| **Engineering session total** | **~3.5 hours** |
| **Background V7+V8 training (parallel, separate)** | **~5h 45min total, ~3h elapsed by handoff write time** |

---

## Standing instructions for the next session

1. **Read this file FIRST.** It supersedes the V7+V8 launch handoff and any earlier handoff. Anywhere they conflict with this doc, this doc wins. The exception: if `git log` shows commits past `6b4fde8`, those are newer and supersede this doc.

2. **Verify training before persona work.** Whether Phase-4a/persona work is the right next priority depends on V7+V8 results. If V7 ≈ V6 and V8 ≈ V6 (hard plateau), surface decision D3 to Don before more training; persona work can fill the wait time. If V8 > V6 by ≥5pp, V9 plan changes; persona work is fine to do in parallel.

3. **Don's directive is "improve training before video."** That's still the priority order. Persona cast development is parallel work, not blocking, but training takes precedence on shared resources (GPU, attention, system-prompt-authoring effort).

4. **Eyeball Aurora's new anchor set (4 PNG files) before generating the other 8 personas' anchor sets.** If Aurora's anchor doesn't read as a clean canonical face — even diffuse light, neutral expression, mouth closed, looking forward — the entire cast inherits the same problem. Verify the lock before scaling.

5. **System prompts for new personas are the slow part.** Each is a character bible. Don't LLM-generate them; the schema rule says hand-author. Budget ~30 min of real thought per persona. Read the existing 4 (Aurora, Marcus Chen, Sara Reyes, James Whitfield) for tone calibration first.

6. **Voice-face match.** When generating each persona, briefly listen to the voice while looking at the anchor. Does the voice match the face? If not, regenerate one. The combination is what users perceive, not either alone.

7. **Persona-specific SFT fine-tunes vs shared base + system-prompt steering.** Default: shared base (V*-arc trained), archetype in system prompt. Persona-specific tune only if behavioral consistency falls short of the bar after V9. Don't pre-build per-persona LoRAs.

8. **Rename execution sequencing.** If you do the rename in the same session as persona work, do the rename FIRST so subsequent persona docs are authored under the new public name. Avoids a doc-drift round trip.

9. **Don's tone preferences.** Direct, no fluff. He directs, you build. Make calls autonomously when authorized. Surface tradeoffs when genuinely ambiguous, not as a way to punt decisions back. Memory rule "feedback_dont_ask_just_execute.md" applies.

10. **Clickable file links rule.** Every path in user-facing text must be `file:///C:/...` with forward slashes, not Windows backslashes. Terminal won't auto-linkify backslashes. Locked feedback rule.

---

## Where things will be when you open the next session

```
C:/Users/dbhav/Projects/aether/  (cwd)
├── HANDOFF_2026-04-28_NIGHT_PERSONA_REDESIGN_AND_RENAME.md   # THIS FILE — read first
├── HANDOFF_2026-04-28_V7_V8_PIPELINE_LAUNCHED.md             # superseded but has training-side detail
├── HANDOFF_2026-04-28_AUTONOMOUS_SESSION_END.md              # earlier in day, superseded
├── PERSONA_ROADMAP.md                                         # updated this session
├── RENAME_TO_COMPANION.md                                     # plan, queued for execution
├── personas/
│   ├── CHARACTERS.md                                          # updated 9-roster
│   ├── aurora/                                                # ANCHOR SET SHIPPED
│   │   ├── persona.yaml          (display_name "Aurora Nash")
│   │   ├── metadata.yaml         (anchor + portrait + profile_left + profile_right)
│   │   ├── avatar/
│   │   │   ├── anchor.png  portrait.png  profile_left.png  profile_right.png
│   │   │   ├── anchor_set_raw_2026-04-28/  (raw FLUX JPGs)
│   │   │   └── README.md
│   │   ├── voice/                (shipped 2026-04-28 nova)
│   │   └── _archived_2026-04-28_first_pass/  (first-pass + nested 2026-04-17)
│   ├── marcus_chen/              (voice + persona.yaml shipped; avatar archived; needs anchor set regen)
│   │   ├── persona.yaml  metadata.yaml  voice/  _archived_2026-04-28_first_pass/
│   │   └── avatar/  (empty, awaiting next session)
│   ├── sara_reyes/               (DRAFTED on disk, UNCOMMITTED)
│   │   ├── persona.yaml          (drafted, uncommitted)
│   │   ├── voice/{reference,sample}.wav  (drafted, uncommitted)
│   │   └── (no avatar/, no metadata.yaml)
│   ├── james_whitfield/          (DRAFTED on disk, UNCOMMITTED — same shape as Sara)
│   ├── (5 more personas to create from scratch: nadia_volkov, priya_iyer, ray_castellano, hannah_park, tomas_andrade)
│   ├── caelum/  luma/            (older personas — schema unclear, may pre-date the redesign; audit before assuming)
│   └── _example/                 (template)
└── planning/session_2026-04-26/training/
    ├── logs_v7/  logs_v8/        (training logs, phase flag files)
    ├── checkpoints_v7/  checkpoints_v8/  (gitignored, populated as training runs)
    ├── eval_v7/  eval_v8/        (populated when eval phases run)
    └── run_v7_v8_pipeline.py     (orchestrator, may still be running)
```

---

## Final word

The session shipped a lot — a complete persona-architecture redesign, a launched 5h training pipeline, and a public-rename plan, in 3.5 hours of Don-driven directive cycles. The next session should not try to ship the same volume; pick one priority (training results OR rename OR continued persona cast) and finish it cleanly.

Good luck.
