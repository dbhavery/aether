# Handoff — Continue the companion build (2026-05-09)

**Written:** 2026-05-08.
**Branch state:** `dev` at `ccd1a2d` with **5 unpushed commits**
ahead of `origin/dev` (`fb2ce1c`, `88159f8`, `4d67da8`, `e65e35f`,
`ccd1a2d`).
**Push status:** **Not authorized for this session.** Don reviews
the 5-commit batch and authorizes push before next session starts.
**Next session mode:** begin Voice V1 step 1 (mic permission
surface) OR pivot to an adjacent track. Both are teed up.

---

## 0. Morning status

1. `dev` is `ccd1a2d`, 5 commits ahead of `origin/dev`.
2. Working tree clean.
3. Full check set run 2026-05-08:
   - `cargo fmt --all -- --check` — clean
   - `cargo check --workspace` — clean (pre-existing warnings only)
   - `cargo test --workspace` — green across all workspace crates
   - `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp` — **57 / 57**
   - `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp` — **93 / 93**
   - `python tools/lint-layer-boundaries/check.py` — 0 violations
   - `python tools/lint-vision-doc/check.py` — OK, 51 anchors
   - `apps/desktop && pnpm typecheck && pnpm build && pnpm test` — **86 / 86**

## 1. What landed in this run

| SHA | Subject |
| --- | --- |
| `e65e35f` | tools: add Vision V1 architecture-doc rot guard |
| `ccd1a2d` | docs: Voice V1 architecture reference (design only) |

(Plus 3 commits from 2026-05-07: `fb2ce1c`, `88159f8`, `4d67da8`.)

Reports:

- [P1_VISION_DOC_ROT_GUARD_EXECUTION_REPORT_2026-05-08.md](file:///C:/Users/dbhav/Projects/aether/P1_VISION_DOC_ROT_GUARD_EXECUTION_REPORT_2026-05-08.md)
- [P2_VOICE_V1_DESIGN_DOC_EXECUTION_REPORT_2026-05-08.md](file:///C:/Users/dbhav/Projects/aether/P2_VOICE_V1_DESIGN_DOC_EXECUTION_REPORT_2026-05-08.md)

New artifacts:

- [tools/lint-vision-doc/check.py](file:///C:/Users/dbhav/Projects/aether/tools/lint-vision-doc/check.py) — rot-guard script
- [tools/lint-vision-doc/README.md](file:///C:/Users/dbhav/Projects/aether/tools/lint-vision-doc/README.md) — operator guide
- [docs/VOICE-V1-ARCHITECTURE.md](file:///C:/Users/dbhav/Projects/aether/docs/VOICE-V1-ARCHITECTURE.md) — Voice V1 design (mirrors Vision V1)

Updates:

- [docs/VISION-V1-ARCHITECTURE.md](file:///C:/Users/dbhav/Projects/aether/docs/VISION-V1-ARCHITECTURE.md): new §11 describing the rot-guard contract; §10 reference reports refreshed through 2026-05-08.

## 2. Decisions locked this round

- **Vision V1 gets a rot guard.** 51 anchors across 12 files.
  Manifest is curated, not auto-extracted. When the doc starts
  claiming a new file / symbol / string, the manifest MUST be
  updated in the same PR; the `Status:` header date MUST be
  bumped. First real run caught a real miss
  (`vision_seed_missing_models` living in `state.rs` not
  `vision_registry.rs`) — the guard paid for itself on day 1.
- **Voice V1 is the next track, scoped at design level only.**
  Chosen over L3 presence and L2 memory maturation because it has
  the clearest pattern parity with Vision V1 and is sized for a
  six-session sequence that mirrors the Vision V1 slices. No code
  written; design doc is exhaustive enough to drive step 1 of
  implementation.
- **Voice V1 hard boundaries locked in the doc.** Single utterance
  only (no continuous listening, no VAD, no wake word), input only
  (TTS is its own future "Voice Output v1" track), local-first
  providers only, audio bytes transient, no silent STT fallback.

## 3. Vision V1 product surface

Unchanged. This round added a rot-guard tool around it but did not
touch the feature itself.

## 4. Voice V1 design state

- Full end-to-end flow documented in
  `docs/VOICE-V1-ARCHITECTURE.md` §1.
- Provider trait (`SpeechProvider`) and request/response shapes
  specified (§2).
- `voice_provider.json` contract specified (§3), identical shape to
  `vision_provider.json`.
- Selection rules, model-list TTL cache contract inherited (§4).
- Utterance validation + telemetry kinds specified (§5, §6).
- UI surfaces named (§7): `VoicePanel`, `VoiceBadge`,
  `ActiveVoiceRoute`, plus transcript + TrustDrawer threading.
- Hard constraints enumerated (§8).
- Six-step implementation sequencing (§10) sized to match existing
  Vision-v1 session slices.

**No code. No providers. No commands. No runtime behavior changed.**

## 5. What to build next — menu

### Option A — Voice V1 step 1: mic permission surface (recommended)

Ship the smallest usable slice:

- `<app_data>/mic_permissions.json` with the tri-state (Allow / Ask /
  Deny), additive-default-safe contract, single-writer rule.
- `set_mic_permission` Tauri command.
- `MediaKind` extension or a parallel `MicKind` enum — decide
  based on whether mic capture has per-surface granularity. v1 is
  a single surface so `MicPermissions` as a standalone state is
  probably cleaner.
- Settings UI: a single row mirroring the media permission rows.
- Audit on state change.
- **No actual capture yet.** This slice only makes the permission
  bit settable and persisted.

Tests follow the Vision V1 pattern: deny/ask/allow matrix,
persistence round-trip, default-safe read of unknown fields.

### Option B — Vision V1 CI wire-up for the rot guard

Currently `python tools/lint-vision-doc/check.py` runs only from
the session check set. Wire it into a lightweight CI workflow
alongside `lint-layer-boundaries` once (or if) CI lands. Out of
scope until a CI config exists to extend.

### Option C — L3 presence or L2 memory maturation (design only)

If Don wants a second architecture doc before any more code lands,
pick the next track the same way Voice V1 was picked. Both are
larger than Voice v1 and need explicit scoping agreement before
starting a design doc.

### Option D — Reverse rot guard

Add a second pass to `tools/lint-vision-doc/check.py` that checks
the reverse direction: for every file or symbol the doc mentions,
verify there's an anchor for it. Catches "prose drifted ahead of
manifest" cases. Deferred in the P1 report as potentially
over-engineering for now.

## 6. Risks / things to review first

- **5 unpushed commits.** `fb2ce1c` (roadmap visual), `88159f8` (P1
  from_wire decision), `4d67da8` (2026-05-08 handoff — now
  superseded by this one), `e65e35f` (rot guard), `ccd1a2d` (voice
  design doc). Review the batch and authorize a push when ready.
- **Voice V1 doc is design-only.** Every file path it names is TBD.
  Don't grep for those files and then panic when they don't exist
  — that is the intended state until implementation begins.
- **Rot guard is not wired into CI.** Still run manually or from
  the session check set. A future CI wave integrates it alongside
  `lint-layer-boundaries`.
- **Vision V1 doc `Status:` date is `2026-05-07`.** Today's edits
  (adding §11) are additive descriptions of a new guard, not
  changes to any existing code the doc claims — so the date did
  not bump. If you disagree with that reading, bump it.

## 7. Recommended next prompt (copy-paste, detailed)

Paste this into the next session as-is — or authorize a push first
and start from the new `origin/dev`.

---

```md
You are Claude Code, continuing work on Aether.

Repo root:
C:/Users/dbhav/Projects/aether/

Branch:
dev

Current state (treat repo as source of truth if anything differs):
- `dev` is at `ccd1a2d`, 5 commits ahead of `origin/dev`.
- Working tree clean.
- Push is NOT pre-authorized for this session. Do NOT push unless
  explicitly instructed at the end of the session.
- Vision V1 is stable and guarded by `tools/lint-vision-doc/check.py`
  (51 anchors, 12 files).
- Voice V1 is documented at `docs/VOICE-V1-ARCHITECTURE.md` in
  design-only state. NO code exists for voice yet.

Mandatory first steps (do these in order before editing):
1. Read `HANDOFF_2026-05-09_CONTINUE_COMPANION_BUILD.md` end to end.
2. `git status` and `git log --oneline -30`.
3. Read `docs/VOICE-V1-ARCHITECTURE.md` end to end (this is the
   spec you are about to start implementing).
4. Read `docs/VISION-V1-ARCHITECTURE.md` §3 (the
   `vision_provider.json` contract — `mic_permissions.json` should
   mirror its default-safe, additive, single-writer shape).
5. Read `P2_VOICE_V1_DESIGN_DOC_EXECUTION_REPORT_2026-05-08.md`
   for why voice is next and what decisions are already locked.
6. Read the media-permission files for reference:
   - `apps/desktop/src-tauri/src/media_permissions.rs`
   - any existing `set_media_permission` Tauri command
   - the Settings surface in `apps/desktop/src/components/Settings*`

Session focus: Voice V1 step 1 (mic permission surface, no capture).

Scope:
- Add `<app_data>/mic_permissions.json` with the tri-state
  (Allow / Ask / Deny), additive-default-safe contract, single-
  writer rule.
- Persist reads return default on first run, tolerate unknown
  fields silently, fall back to default on malformed JSON with a
  WARN that names the path (mirror Vision V1 behavior).
- `set_mic_permission` Tauri command, structured like
  `set_media_permission`. Emit `AuditRecordEvent` on state change
  with capability + scope only (no provider info).
- Settings UI: a single row mirroring the media permission rows.
- Tests (follow the Vision V1 pattern):
  - default state
  - allow / ask / deny round-trip
  - unknown fields tolerated on read
  - unknown fields dropped on rewrite (documented limitation)
  - malformed JSON falls back to default with a WARN

Out of scope (do NOT do any of these in this session):
- Any actual audio capture.
- Any `transcribe_utterance` command.
- Any SpeechProvider trait or adapter.
- Any `voice_provider.json` contract work (that is step 3).
- Any VoicePanel UI.
- Any TTS.
- Any wake word / VAD / continuous listening.

Hard constraints (don't drift):
- No push without explicit user authorization.
- No release / distribution / signing work.
- No new vision providers.
- No mic / voice / STT implementation — only the permission
  surface.
- No streaming or continuous capture modes.
- Do NOT unify LlamaCppConfigError + OllamaConfigError.
- Do NOT extend L5's AuditRecordEvent to carry provider info.
- Do NOT change the durable-memory privacy posture for images
  (image bytes stay transient).
- Do NOT widen the vision_provider.json contract beyond
  additive-default-safe shapes.
- Do NOT add new test deps.

Process for this session:
1. Scaffold `mic_permissions.rs` and the persistence path.
2. Add the `set_mic_permission` command and audit-event emission.
3. Wire the Settings UI row.
4. Run focused tests for the new module.
5. Run the full check set:
   - cargo fmt --all -- --check
   - cargo check --workspace
   - cargo test --workspace
   - cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp
   - apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp
   - python tools/lint-layer-boundaries/check.py
   - python tools/lint-vision-doc/check.py
   - apps/desktop && pnpm typecheck && pnpm build && pnpm test
6. Fix all failures.
7. Commit in clear scoped slices.
8. Update `docs/VOICE-V1-ARCHITECTURE.md` ONLY if the
   implementation revealed a concrete correction; the doc is
   "design-only" but it should stay truthful.

Before stopping:
- Keep git status clean.
- Write/update execution reports for the step.
- Write a fresh handoff file with the same structure as this one.
- Confirm whether push is authorized for the run; if not, leave
  commits unpushed and note it in the handoff.

Stay strictly on-scope. No drift into capture or STT.
```

---

(end of handoff)
