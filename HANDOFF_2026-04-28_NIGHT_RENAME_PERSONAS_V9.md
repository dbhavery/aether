# Handoff — 2026-04-28 Night (Rename + Personas + V9 Sweep)

> Successor to file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-04-28_NIGHT_PERSONA_REDESIGN_AND_RENAME.md
>
> This handoff supersedes that one for status reading. Where they
> conflict, this one wins. The exception: if `git log` shows commits
> past `92fe7f0`, those are newer and supersede this doc.
>
> **Branch:** `dev` at `92fe7f0` (pushed).
> **Wallclock:** Don-driven session continuing from 21:30 PT.

---

## TL;DR

Three threads of work landed this leg of the session:

1. **Public rename Aether → Companion: COMPLETE.** 5 atomic commits
   (2cc40d2 → 3658242). README + Tauri config + index.html + persona
   YAML/metadata + 14 desktop UI source files + CHARACTERS.md heading
   all flipped. Internal codename `aether` preserved as planned.

2. **9-persona cast: system prompts + anchor specs + voice drafts all
   committed.** All 9 personas now have hand-authored `persona.yaml`
   and `avatar/README.md` (anchor-set generation specs). 4 of 9 have
   voice WAVs committed (Aurora, Marcus, Sara, James). 5 of 9 still
   need voice generation (Nadia, Priya, Ray, Hannah, Tomás). Anchor
   sets for 8 of 9 still pending generation (Aurora is the one
   shipped); they're ready to fire as a batch when Don approves API
   spend.

3. **V9 ablation sweep launched in background, queues behind V7+V8.**
   3-variant sweep (V9a rank-128 capacity ceiling, V9b V8-continuation
   training-budget, V9c 7B base swap). ~17.5 hr after V8 finishes.
   PID running, polling for `logs_v8/phase_eval.done` every 60s.
   Per Don's "21 hrs straight in parallel with character creation."

4. **Persona delivery model captured** as `PERSONA_DELIVERY.md` (DRAFT,
   pending Don approval). Captures download-on-demand model: previews
   bundled in app, full pack downloads on selection, switching =
   uninstall + install. 6 open questions documented.

---

## Background processes still running

### V7+V8 pipeline orchestrator (PID 33672)

V7 train DONE (logs_v7/phase_train.done). V7 eval still running
(PID 78060, started 19:41 PT). V8 hasn't started yet. logs_v8/ empty.

ETA: ~23:45 PT for V8 eval to finish.

If V7 eval has been running >2 hours by the time you read this, peek
at `logs_v7/v7_eval.log` for hangs. The eval's quiet by design (long
forward-pass phases) but >2.5h is suspicious.

### V9 sweep orchestrator

Background task ID: `b1ss1wuxd`. Started 20:04 PT. Polling
`logs_v8/phase_eval.done` with 8-hour timeout.

When V8 finishes, V9a fires. Total V9 sweep wallclock ~17.5 hr.

ETA total finish: ~17:30 PT next day if V8 finishes ~23:45 PT tonight.

If V9 sweep has FAILED (timeout waiting on V8, or a script crashes),
re-run with:
```
cd planning/session_2026-04-26/training/
python run_v9_sweep.py
```
Phase done flags make resume safe.

---

## Persona cast — full status table

| # | Slug | persona.yaml | avatar/README.md (spec) | anchor PNGs | voice WAVs | voice.yaml + SOURCE.md | metadata.yaml |
|---|---|---|---|---|---|---|---|
| 1 | aurora           | ✓ | ✓ | ✓ shipped | ✓ shipped | ✓ shipped | ✓ shipped |
| 2 | marcus_chen      | ✓ | ✓ | ✗ pending | ✓ shipped | ✓ shipped | ✓ shipped |
| 3 | sara_reyes       | ✓ | ✓ | ✗ pending | ✓ shipped | ✓ draft | ✓ draft |
| 4 | james_whitfield  | ✓ | ✓ | ✗ pending | ✓ shipped | ✓ draft | ✓ draft |
| 5 | nadia_volkov     | ✓ | ✓ | ✗ pending | ✗ pending | ✗ | ✗ |
| 6 | priya_iyer       | ✓ | ✓ | ✗ pending | ✗ pending | ✗ | ✗ |
| 7 | ray_castellano   | ✓ | ✓ | ✗ pending | ✗ pending | ✗ | ✗ |
| 8 | hannah_park      | ✓ | ✓ | ✗ pending | ✗ pending | ✗ | ✗ |
| 9 | tomas_andrade    | ✓ | ✓ | ✗ pending | ✗ pending | ✗ | ✗ |

**To complete the cast:**
- Generate 8 anchor sets × 4 stills = 32 FLUX-pro calls (~$1.60)
- Generate 5 voice packs × 2 WAVs = 10 OpenAI gpt-4o-mini-tts calls (~$0.50)
- Author 5 metadata.yaml + 5 voice.yaml + 5 voice/SOURCE.md
  (~10 min/persona, all template work — read Sara's draft for
  the shape)

Anchor generation MUST WAIT on Don's eyeball-check of Aurora's anchor
set first per CHARACTERS.md face-consistency lock-before-scale rule.
Don's call when to fire.

---

## Don's directives this session

| # | Directive | Status |
|---|---|---|
| 1 | "continue" — orient + pick next priority | DONE — picked rename (training mid-flight, no V7+V8 results yet) |
| 2 | "keep going" — execute autonomously | DONE — 5 commits rename + 5 persona drafts + V9 sweep + delivery doc |
| 3 | "start new multi-hour GPU trainings. 21 hrs straight, in parallel with character creation" | DONE — V9 sweep launched in background, persona work continued |
| 4 | "These characters are only going to be samples ... persona and all animations download only for chosen ... changing later means removing the first and installing new" | CAPTURED in PERSONA_DELIVERY.md, cross-linked from CHARACTERS.md, awaiting Don review to graduate to ADR |

---

## Commits this leg (since 99c002e)

```
92fe7f0 personas(sara_reyes, james_whitfield): commit floating drafts + voice WAVs
974a948 personas: anchor-set generation specs for 7 remaining cast members
83f0fee personas(marcus_chen): anchor-set generation spec ready to fire
d6cd18d docs(personas): PERSONA_DELIVERY.md — download-on-demand model
5ce7d4c training(v9): 3-variant ablation sweep covering D3 paths
019310f personas: 5 new system-prompt drafts (Nadia, Priya, Ray, Hannah, Tomás)
3658242 personas(CHARACTERS.md) + docs: rename to Companion + mark RENAME COMPLETE
3ab5558 apps(desktop): rename UI strings to Companion
cad2d0e personas: rename public references to Companion in YAML headers + metadata notes
8d480f3 apps(desktop): rename productName + window title to Companion
2cc40d2 docs: rename public — README.md (Aether → Companion)
```

11 commits, all on `dev`, all pushed.

---

## What the NEXT session should do, in order

### Priority 1 — verify training results (when V7+V8+V9 are done)

When you open the session, check phase done flags:

```bash
ls planning/session_2026-04-26/training/logs_v7/phase_*.done
ls planning/session_2026-04-26/training/logs_v8/phase_*.done
ls planning/session_2026-04-26/training/logs_v9_sweep/phase_*.done
```

If V7+V8 are done but V9 is still running, write V7_RESULTS.md +
V7_CONVERSATIONS.md + V8_RESULTS.md + V8_CONVERSATIONS.md NOW per
the V6 format. Don't wait on V9.

If V9 is also done, write V9_SWEEP_RESULTS.md comparing all 3
variants on held-out PPL + WildChat generations + cross-reference
to V6/V7/V8 metrics. Then update PERSONA_ROADMAP.md cursor and
trigger D3 decision (RLHF / 7B base swap / ship V6 / continue
V*-arc with V8 architecture).

### Priority 2 — Don eyeball-check on Aurora's anchor set

Before firing the 8 batch anchor-set generations, Don should open all
4 Aurora PNGs side-by-side and confirm the anchor schema reads
clean (face-consistency-ready). If any pre-existing Aurora image
needs regen, do that before scaling.

If Aurora's anchor checks out: fire the batch (32 FLUX-pro calls).
Each persona's `avatar/README.md` has the prompts ready.

### Priority 3 — generate voice packs for the 5 new personas

After anchors, generate voice WAVs for Nadia, Priya, Ray, Hannah,
Tomás via OpenAI gpt-4o-mini-tts. Each persona's `persona.yaml` has
voice direction in the system_prompt + voice_descriptors. Voice
choices to consider:
- Nadia (precise, slightly clipped, dry): try `nova` + alert/precise steering OR `shimmer` if available
- Priya (polished-warm, executive): try `nova` + polished-executive steering OR `alloy`
- Ray (gruff working-class): try `onyx` OR `ash` + working-class-NY steering
- Hannah (quiet careful researcher): try `shimmer` OR `nova` + thoughtful-researcher steering
- Tomás (warm direct): try `echo` OR `verse` + grounded-direct steering

Test 3 candidates per persona, Don picks. Save WAVs canonically with
voice.yaml + SOURCE.md following Sara/James template.

### Priority 4 — graduate PERSONA_DELIVERY.md to ADR

After Don reviews and confirms the download-on-demand model, the doc
becomes `planning/adr/0010_persona_delivery.md` (or similar — check
existing ADR numbering).

### Priority 5 — implement persona delivery scaffolding

When the ADR lands, scaffold the build/runtime pieces:
- `tools/build-persona-pack/` — zip + sha256 + manifest entry
- `tools/build-persona-previews/` — preview asset derivation
- `packages/l6-persona/` — install/uninstall/switch traits
- `packages/l5-policy/` — `persona.download` capability

Each is its own session worth of work.

---

## Critical "do not redo" items

These join the list from the prior handoff:

- **Public rename to Companion is COMPLETE.** Don't re-do. Internal
  codename `aether` STAYS in repo dir, GitHub URL, Tauri identifier
  `dev.aether.desktop`, all crate names, db files, env vars
  (`AETHER_*`), license id `custom_aether`, Tailwind tokens
  (`bg-aether-*` / `text-aether-*`), and all internal docs/planning/.
- **5 new persona system prompts are HAND-AUTHORED CHARACTER BIBLES**
  (Nadia, Priya, Ray, Hannah, Tomás). Don't regenerate from an LLM —
  the schema rule says hand-author. If they need iteration, edit
  surgically.
- **Anchor specs for 8 personas are committed and ready to fire**
  (Marcus + 7 others). Don't rewrite them — they were calibrated
  against Aurora's pattern with care. Iterate if generation reveals
  drift; don't preemptively rewrite.
- **V9 sweep design is concrete: V9a rank-128, V9b V8+1500, V9c 7B
  base.** Don't redesign before V9 results land.
- **Sara/James voice WAVs are canonical**, but their voice
  steering text and reference text need recovery from session logs
  for SOURCE.md before release ship. Don't regenerate the WAVs.
- **PERSONA_DELIVERY.md is DRAFT.** Don't implement its scaffolding
  until Don approves and it graduates to ADR.

---

## Open decisions Don owes (carry-over + new)

| # | Decision | Status |
|---|---|---|
| D1-D5 | (carry-over from prior handoff) | unchanged |
| D6 | Out-of-band rename actions (GitHub repo rename, portfolio URL) | OPEN — Don only |
| D7 | Aurora anchor-set QA before firing the 8 batch | OPEN — eyeball + sign off |
| D8 | Persona delivery model approval (PERSONA_DELIVERY.md → ADR) | OPEN — review and confirm |
| D9 | Voice candidates for 5 new personas | OPEN — pick from 3 candidates each when generation lands |

---

## File index — created/modified this leg

### New files
- `RENAME_TO_COMPANION.md` (decision log marked COMPLETE)
- `PERSONA_DELIVERY.md` (DRAFT design doc)
- `personas/nadia_volkov/persona.yaml` + `avatar/README.md`
- `personas/priya_iyer/persona.yaml` + `avatar/README.md`
- `personas/ray_castellano/persona.yaml` + `avatar/README.md`
- `personas/hannah_park/persona.yaml` + `avatar/README.md`
- `personas/tomas_andrade/persona.yaml` + `avatar/README.md`
- `personas/marcus_chen/avatar/README.md` (new spec for second-pass)
- `personas/sara_reyes/{persona.yaml, metadata.yaml, voice/{voice.yaml, SOURCE.md, reference.wav, sample.wav}, avatar/README.md}`
- `personas/james_whitfield/{persona.yaml, metadata.yaml, voice/{voice.yaml, SOURCE.md, reference.wav, sample.wav}, avatar/README.md}`
- `planning/session_2026-04-26/training/train_pipeline_v9a.py`
- `planning/session_2026-04-26/training/train_pipeline_v9b.py`
- `planning/session_2026-04-26/training/train_pipeline_v9c.py`
- `planning/session_2026-04-26/training/eval_v9_quick.py`
- `planning/session_2026-04-26/training/run_v9_sweep.py`
- `HANDOFF_2026-04-28_NIGHT_RENAME_PERSONAS_V9.md` (this file)

### Modified files (rename)
- `README.md`
- `apps/desktop/src-tauri/tauri.conf.json`
- `apps/desktop/index.html`
- `apps/desktop/package.json`
- `apps/desktop/README.md`
- 14 files under `apps/desktop/src/` (App, ApprovalModal, Disclosure, Header, InputBar, PresetPicker, CameraPanel, RetrievalTab, ScreenPanel, VisionBadge, VoiceBadge, VoicePanel, SettingsDrawer, TrustDrawer)
- 11 files under `personas/` (per-persona YAML headers, metadata prose, SOURCE.md prose)
- `personas/CHARACTERS.md`

### Untracked / scratch (gitignored or just untracked)
- V7+V8+V9 checkpoints under `checkpoints_v*` / `logs_v*_sweep/`
- Background-task output logs under `C:\Users\dbhav\AppData\Local\Temp\claude\...`

---

## Standing instructions for the next session

(Carrying forward from prior handoff plus new items.)

1. **Read THIS file FIRST.** Supersedes all prior handoffs for status.
2. **Verify training before persona work.** Whether Phase-4a/persona
   work is the right next priority depends on V7+V8+V9 results.
3. **Don's directive remains "improve training before video."** Phase 5
   stays deferred.
4. **Eyeball Aurora's anchor set BEFORE firing batch generations.**
   Lock-before-scale.
5. **Hand-author character bibles.** All 9 personas already have them.
   For voice generation, hand-author 3 candidate steerings per persona,
   let Don pick.
6. **Voice-face match.** When generation lands, listen to the voice
   while looking at the anchor. Verify the combination reads as one
   person.
7. **Persona-specific SFT fine-tunes are deferred.** Default: shared
   base + system-prompt steering. PERSONA_DELIVERY.md reinforces this
   (per-persona LoRAs would push pack size 10x).
8. **Don's tone: direct, no fluff. Make calls autonomously when
   authorized.** Memory rule "feedback_dont_ask_just_execute.md"
   applies.
9. **Clickable file links rule.** Every path in user-facing text must
   be `file:///C:/...` with forward slashes.
10. **Trust the training resume policy.** All V*+V9 phases have
    individual done flags. Re-run orchestrators after a partial crash;
    they skip completed phases.
