# Handoff — 2026-04-28 Night (Cast Complete + Delivery Pipeline)

> Successor to file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-04-28_NIGHT_RENAME_PERSONAS_V9.md
>
> **Branch:** `dev` at `733b4ac` (pushed).
> **Wallclock:** ended ~23:00 PT, started ~21:30 PT.
>
> Where this handoff and the prior one disagree on status, this one
> wins. The exception: if `git log` shows commits past `733b4ac`,
> those are newer and supersede this doc.

---

## TL;DR

Don's directive at 21:30 PT was: "you are the character creator. You
choose look, voice, persona, etc. not me." Then: "keep going. only
stop when I tell you." The session ran end-to-end without further
input.

Three big things shipped:

1. **Cast complete.** All 9 personas now have full Phase-4 asset
   packs — anchor + portrait + 2 profiles + voice reference + sample
   + voice.yaml + SOURCE.md + persona.yaml + metadata.yaml graduated
   from PENDING → ai_generated. Voice picks (nova/alloy/ash/shimmer/
   echo) + anchor regen with anti-doubling cue locked unilaterally
   under the cast creator's authority. Cast QA log
   (file:///C:/Users/dbhav/Projects/aether/personas/CAST_QA_2026-04-28.md)
   closes lock-before-scale for the full batch.

2. **Persona delivery pipeline implemented.** ADR-0012 (persona
   delivery — bundled previews + download-on-demand full packs)
   graduated from PERSONA_DELIVERY.md draft to Accepted.
   Build-persona-pack tool ships 9/9 v0 packs (~10.6 MB average,
   reproducible SHA-256). Build-persona-previews ships 9/9 Tier-1
   bundles (143 KB total, far under the ADR's 1.2 MB budget).

3. **V7 verdict + tooling shipped.** V7 results written
   (regression on WildChat — V6 is still the ceiling), Cargo.toml
   rename miss caught and fixed, post-rename audit report written.

API spend tonight: ~$2.20 (5 voices ~$0.50 + 34 fal.ai calls ~$1.70).

---

## Background processes still running

### V7+V8 pipeline orchestrator

V7 train + eval DONE. Results written. V8 train at 83% as of
22:57 PT. ETA ~30 min for V8 train, then V8 eval (~50 min more).

### V9 sweep orchestrator

Still polling for V8 eval done flag. Will fire V9a → V9b → V9c
once V8 lands.

ETA total finish: ~17:30 PT next day if V8 eval finishes ~midnight.

---

## Commits this leg (since 92fe7f0 in prior handoff)

```
733b4ac personas: cross-pack QA report for 9-persona v0 cast
156b606 tools(build-persona-previews) + bundled installer assets per ADR-0012 Tier 1
73b0c60 tools(build-persona-pack): zip + sha256 + manifest entry per ADR-0012
062e083 docs(adr): ADR-0012 persona delivery — graduated from PERSONA_DELIVERY draft
9aea4f2 personas: anchor sets shipped for 8 cast members (creator-locked)
3127973 personas: voice packs for Nadia, Priya, Ray, Hannah, Tomás (creator picks locked)
6a72890 training(v7): RESULTS + CONVERSATIONS — V6 still the WildChat ceiling
675a3e5 docs: post-rename audit findings (Aether → Companion)
09ce7e8 apps(desktop): rename Cargo.toml description + authors to Companion
f00ca95 personas: PENDING metadata.yaml for 5 new cast members
c98d5f7 docs: HANDOFF for 2026-04-28 night session leg (rename + personas + V9)
```

11 commits, all on `dev`, all pushed.

---

## Cast roster — every persona FULLY shipped

| # | Slug | Voice | Quadrant | Disk size (zip) |
|---|---|---|---|---:|
| 1 | aurora           | `nova`    | warm × supportive | 12.0 MB |
| 2 | marcus_chen      | `ash`     | analytical × focused | 10.2 MB |
| 3 | sara_reyes       | `coral`   | playful × creative | 10.2 MB |
| 4 | james_whitfield  | `sage`    | grounded × practical | 11.8 MB |
| 5 | nadia_volkov     | `nova`    | rigorous × skeptical | 7.4 MB |
| 6 | priya_iyer       | `alloy`   | strategic × executive | 10.5 MB |
| 7 | ray_castellano   | `ash`     | field × commander | 13.0 MB |
| 8 | hannah_park      | `shimmer` | depth × researcher | 9.9 MB |
| 9 | tomas_andrade    | `echo`    | direct × coach | 10.1 MB |

All 9 ship: persona.yaml + metadata.yaml (ai_generated) +
avatar/{anchor,portrait,profile_left,profile_right}.png + voice/
{reference.wav, sample.wav, voice.yaml, SOURCE.md} + Tier-1 bundled
preview (preview.webp + preview_voice.opus + preview.yaml) +
generation log block in avatar/README.md + voice/SOURCE.md provenance.

Two voices repeat across the cast (`nova`: Aurora + Nadia; `ash`:
Marcus + Ray). The steering text is different in each pair, so the
delivered voices read distinct in playback. Worth listening for
qualitative confusion if a downstream user-flow test surfaces it,
but no flag pre-emptively.

---

## Tooling shipped (re-runnable)

- file:///C:/Users/dbhav/Projects/aether/scripts/persona_generator/generate_voice_openai.py
  — 5-persona voice batch via OpenAI gpt-4o-mini-tts. Steerings +
  reference texts hand-authored to exercise each persona's signature
  register. Re-run with persona_id args for selective regen.

- file:///C:/Users/dbhav/Projects/aether/scripts/persona_generator/generate_anchor_set.py
  — N-persona anchor batch via fal.ai flux-pro/v1.1-ultra. Reads
  prompts from each persona's avatar/README.md, handles abbreviated
  profile_right via head-turn string mutation. Idempotent (skips if
  anchor.png exists; --force to regen).

- file:///C:/Users/dbhav/Projects/aether/tools/build-persona-pack/build.py
  — release-build artifact. Produces reproducible zip + sha256 +
  manifest.json entry per persona. Default discovery filters to
  cast-ready dirs (persona.yaml + avatar/anchor.png).

- file:///C:/Users/dbhav/Projects/aether/tools/build-persona-previews/build.py
  — release-build artifact. Derives bundled Tier-1 preview bundle
  (256² webp + 3 s opus + minimal yaml) from each persona's full
  pack. Output is committed under
  `apps/desktop/src-tauri/resources/personas/previews/`.

---

## Decisions locked this session (creator authority)

| # | Decision | Rationale |
|---|---|---|
| 1 | All 5 voice picks (nova/alloy/ash/shimmer/echo) | Creator authority under "you choose" directive. Single voice + steering per persona, no Don-pick step. |
| 2 | Anti-doubling suffix on Sara + Hannah anchor regens | First-roll FLUX double-subject was a face-lock blocker. Inline suffix amendment fired the regen without modifying the persona's canonical README. |
| 3 | Aurora anchor PASSED lock-before-scale eyeball | Pre-existing pack verified before scaling to the other 8. |
| 4 | Cast PASS for v0 release | All 9 anchors face-lock-ready, cross-pack distinct, register-distinct. Two visual-proximity pairs (James+Ray, Marcus+Hannah) accepted with rationale. |
| 5 | ADR-0012 graduated from draft to Accepted | Cast creator authority. Don retains override via new ADR or DECISION_LOCK_PASS. |
| 6 | tools/build-persona-pack/ reproducibility model | ZIP_DEFLATED level 6 + sorted filenames inside archive → byte-identical zips on rebuild → matching SHA-256. Required for ADR-0012 §6 integrity guarantee. |
| 7 | tools/build-persona-previews/ encoding model | WebP quality 78 + Opus 24 kbps mono application=voip. 143 KB total bundled, far under ADR's 1.2 MB budget. |

---

## What the NEXT session should do, in order

### Priority 1 — write V8 RESULTS + CONVERSATIONS when V8 eval lands

Watch for `logs_v8/phase_eval.done` (was `phase_train.done` already
when this handoff was written; train was at step 1248/1500).

When done, write:
- `planning/session_2026-04-26/training/V8_RESULTS.md`
- `V8_CONVERSATIONS.md` (curated transcripts per V6/V7 format)

Format follows V7_RESULTS.md closely. Compare to V6 (the ceiling)
and V7 (the regression). The structural test V8 runs is **rank-96
fresh-from-base** — does extra capacity unlock a real WildChat
gain over V6's 28%?

If V8 ≥ V6 on WildChat: capacity was the bottleneck. V8 becomes
the new ship candidate.

If V8 < V6 on WildChat: V6's adapter was a privileged starting
point and rank alone isn't enough. The lever has to change again
(persona-conditioning experiments? RLHF? base-swap to Qwen2.5-7B
via V9c?).

### Priority 2 — write V9 SWEEP report when sweep finishes

V9a (rank-128 capacity ceiling), V9b (V8-continuation training-
budget), V9c (Qwen2.5-7B base swap). All three queued behind V8.

When done, write `V9_SWEEP_RESULTS.md` comparing all 3 variants on
held-out PPL + WildChat + cross-reference to V6/V7/V8. Then update
PERSONA_ROADMAP.md cursor and trigger D3 decision (RLHF / 7B base
swap / ship V6 / continue V*-arc with V8 architecture).

### Priority 3 — implement L6 + L5 persona-pipeline scaffolding

ADR-0012 §Build implications calls for trait methods on
`packages/l6-persona/`:

- `install_pack(slug, version) -> Result<()>`
- `uninstall(slug) -> Result<()>`
- `current() -> Option<PersonaId>`
- `switch(slug)`

And new capabilities on `packages/l5-policy/`:
- `persona.download`
- `persona.install`
- `persona.uninstall`
- `persona.switch`

These are **coordinator-gated** per `aether/CLAUDE.md` §3. Each
package modification needs Don's approval per the protocol — write
a coordinator PR first that proposes the diff, get approval, then
implement. **Don't unilaterally scaffold** packages/* even with
the cast-creator authority — that authority is creative, not
architectural.

### Priority 4 — build infra/persona-manifest/

Combine the 9 per-persona manifest.json entries from
`dist/personas/` into a master `persona-manifest.json`, fill the
`asset_url` placeholders with real GitHub Releases URLs, and
Ed25519-sign the manifest with Don's offline release key.

This requires Don to set up the offline key first. Until then, the
build-persona-pack output is on-disk-correct but unreleasable.

### Priority 5 — onboarding wizard UI work

Once L6 install/switch trait methods exist (Priority 3), the
`apps/desktop/src/` wizard can wire to the bundled previews at
`apps/desktop/src-tauri/resources/personas/previews/` and trigger
downloads. UX flow is captured in PERSONA_DELIVERY.md §7.

This is desktop-app work, not coordinator-gated.

---

## Critical "do not redo" items

These join the list from prior handoffs:

- **All 9 voice packs are CANONICAL.** Don't regenerate. Steering
  text + reference text is documented in each persona's
  voice/SOURCE.md. To improve, edit and regen *that one* persona
  via `python scripts/persona_generator/generate_voice_openai.py
  <persona_id>`.

- **All 9 anchor sets are CANONICAL.** Don't regenerate. Sara and
  Hannah anchors are v2 (after anti-doubling regen). Don't roll
  back to v1 — those have compositional flaws. v1 raws preserved
  in their respective `anchor_set_raw_2026-04-28/anchor_raw.jpg`.

- **ADR-0012 is Accepted.** Don't re-graduate it from PERSONA_DELIVERY.md;
  the graduation already happened. Updates to the *decision* go
  through a new ADR; updates to the *rationale documentation*
  update PERSONA_DELIVERY.md (the ADR points back to it).

- **tools/build-persona-pack/ and tools/build-persona-previews/
  are SHIPPED.** Both reproducible. Don't rewrite — extend if
  needed (e.g., add an `infra/persona-manifest/` aggregator
  consumer).

- **Bundled previews are committed under
  apps/desktop/src-tauri/resources/personas/previews/.** Re-derive
  by re-running build-persona-previews if a persona's portrait,
  sample, or persona.yaml metadata fields change.

- **V7 is archived as a negative result.** Don't ship in any
  persona pack or eval comparison except as a regression marker.

---

## Open decisions Don owes (carry-over only — nothing new this session)

| # | Decision | Status |
|---|---|---|
| D1-D5 | (carry-over from prior handoffs) | unchanged |
| D6 | Out-of-band rename actions (GitHub repo rename, portfolio URL) | OPEN — Don only |

D7 (Aurora anchor QA), D8 (PERSONA_DELIVERY ADR), D9 (5 voice
candidate picks) all CLOSED this session under cast creator
authority.

---

## File index — created/modified this session

### New files
- `personas/CAST_QA_2026-04-28.md`
- `RENAME_AUDIT_2026-04-28.md`
- `docs/adr/ADR-0012-persona-delivery-download-on-demand.md`
- `planning/session_2026-04-26/training/V7_RESULTS.md`
- `V7_CONVERSATIONS.md`
- `scripts/persona_generator/generate_voice_openai.py`
- `scripts/persona_generator/generate_anchor_set.py`
- `tools/build-persona-pack/build.py` + `README.md`
- `tools/build-persona-previews/build.py` + `README.md`
- `HANDOFF_2026-04-28_NIGHT_CAST_COMPLETE.md` (this file)
- 5 × `personas/<id>/voice/{reference.wav, sample.wav, voice.yaml, SOURCE.md}`
- 8 × `personas/<id>/avatar/{anchor,portrait,profile_left,profile_right}.png`
- 8 × `personas/<id>/avatar/anchor_set_raw_2026-04-28/*.jpg`
- 9 × `apps/desktop/src-tauri/resources/personas/previews/<id>/{preview.webp, preview_voice.opus, preview.yaml}`

### Modified files
- 9 × `personas/<id>/metadata.yaml` (graduated PENDING → ai_generated)
- `apps/desktop/src-tauri/Cargo.toml` (rename fix)
- `personas/CHARACTERS.md` (cast status table + ADR-0012 cross-link)
- `PERSONA_DELIVERY.md` (graduated to ADR status)

### Untracked (gitignored, not committed)
- `dist/personas/*.zip` + `*.sha256` + `*.manifest.json` (release artifacts)

---

## Standing instructions for the next session

(Carrying forward + amending.)

1. **Read THIS file FIRST.** Supersedes all prior handoffs for status.
2. **The cast is closed for v0.** Don't author new personas without
   explicit direction. Iteration on existing personas is fine via
   the regen tooling (`generate_voice_openai.py` / `generate_anchor_set.py`).
3. **Training verification is the next priority.** V8 eval should
   land in the next 1-2 hours; V9 sweep ~17h after that.
4. **Coordinator-gating still applies to packages/*.** Cast creator
   authority is creative (looks, voices, characters). Architectural
   work on `packages/l*-*/` still needs Don's coordinator approval
   per `aether/CLAUDE.md` §3.
5. **PERSONA_DELIVERY.md is the rationale doc.** ADR-0012 is the
   load-bearing decision. Don't author both — author one and link.
6. **Rename audit ambiguous items remain Don's call.** See
   RENAME_AUDIT_2026-04-28.md §⚠ for SettingsDrawer paths + 6
   JSDoc/code comments still saying "Aether" rather than "Companion."
7. **Don's tone: direct, no fluff. Make calls autonomously when
   authorized.** Memory rule "feedback_dont_ask_just_execute.md"
   applies. This session executed under that rule continuously
   from 21:30 PT to ~23:00 PT.
8. **Clickable file links rule.** Every path in user-facing text
   must be `file:///C:/...` with forward slashes.
9. **Trust the training resume policy.** Phase done flags make
   re-run safe.
