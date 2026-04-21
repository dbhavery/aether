# Handoff — Continue the companion build (2026-05-07)

**Written:** 2026-05-06 (overnight autonomous run).
**Branch state:** `dev`, **11 commits ahead of `origin/dev`** at SHA
`d93d7f0`. (One follow-up doc commit will land on top before this
file is final — see §1.)
**Push status:** **NOT authorized this session.** Treat the next
push as a fresh authorization decision.
**Next session mode:** continue overnight-style polish + safety on
the multimodal/video assistant track only, OR review the unpushed
batch and authorize a push.

---

## 0. Morning status

1. `dev` is `d93d7f0`.
2. Working tree clean after the docs commit.
3. Full check set is green:
   - `cargo fmt --all -- --check`
   - `cargo check --workspace`
   - `cargo test --workspace`
   - `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp`
     → **57 / 57**
   - `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp`
     → **93 / 93**
   - `python tools/lint-layer-boundaries/check.py` → 0 violations
   - `apps/desktop && pnpm typecheck && pnpm build` → clean
   - `apps/desktop && pnpm test` → **86 / 86**

## 1. What landed in the most recent run

| SHA | Subject |
| --- | --- |
| `d61a97e` | feat(apps/desktop): emit telemetry on analyze_frame early exits |
| `a9fc15d` | log: include URL/path context in vision boot WARN lines |
| `d93d7f0` | docs: add VISION-V1-ARCHITECTURE.md reference |

Reports:

- [CHUNK_A_FRAME_EARLY_EXIT_TELEMETRY_EXECUTION_REPORT_2026-05-06.md](file:///C:/Users/dbhav/Projects/aether/CHUNK_A_FRAME_EARLY_EXIT_TELEMETRY_EXECUTION_REPORT_2026-05-06.md)
- [CHUNK_B_LOG_CLARITY_EXECUTION_REPORT_2026-05-06.md](file:///C:/Users/dbhav/Projects/aether/CHUNK_B_LOG_CLARITY_EXECUTION_REPORT_2026-05-06.md)
- [CHUNK_C_VISION_V1_ARCHITECTURE_DOC_EXECUTION_REPORT_2026-05-06.md](file:///C:/Users/dbhav/Projects/aether/CHUNK_C_VISION_V1_ARCHITECTURE_DOC_EXECUTION_REPORT_2026-05-06.md)

Reference: [docs/VISION-V1-ARCHITECTURE.md](file:///C:/Users/dbhav/Projects/aether/docs/VISION-V1-ARCHITECTURE.md)

## 2. Multimodal product surface today

Same scope as 2026-05-05; this round only sharpened observability
and documentation.

1. Local-only media permissions
   (`<app_data>/media_permissions.json`).
2. Camera + Screen panels — single-shot capture, OS picker for
   screen, default OFF.
3. `analyze_frame` — permissioned, audited, telemetered,
   transcript-visible. Rejects empty/invalid data URL payloads at
   the shell boundary with a friendly, actionable error. **Now
   records telemetry on every early exit (`frame_invalid`,
   `permission_denied`, `permission_ask`) so the Trust drawer's
   History tab shows the user every attempted analysis, not just
   the ones that reached a provider.**
4. `maybe_apply_vision` mirrors the same guard.
5. Vision providers: Ollama and llama.cpp, both with discovery and
   in-provider model selection. **Boot WARN lines now include the
   base URL + persistence file path** for actionable triage.
6. `vision_provider.json` persists `active` + `model_per_provider`,
   first-launch seeding, additive-default-safe contract locked by
   tests.
7. Per-provider model-list TTL cache (default 60s; bounded
   `[5, 3600]` env override; manual `↻` refresh; effective TTL
   logged at boot unconditionally).
8. UI surfaces — VisionBadge, ActiveVisionRoute hint, Trust drawer
   media rows, transcript footer all surface provider + model
   consistently.
9. Trust drawer history rows middle-truncate verbose model ids
   (default 28 chars, suffix 8); full id in `title` tooltip.
10. **Architecture documented at `docs/VISION-V1-ARCHITECTURE.md`**
    so future tracks (remote vision, voice) can design against a
    stable reference.

## 3. What to build next — multimodal track

### Priority 1 — Optional polish: TrustDrawer "frame_invalid" copy

The History tab will now show a `frame invalid` row (the existing
`{kind.replace(/_/g, " ")}` rendering pipeline). If you want a
dedicated friendly label (e.g. "Capture rejected"), wire it through
the kind-mapping helper rather than the raw replace. Optional;
defer if you don't see it in real use.

### Priority 2 — Audit `analyze_frame` for any remaining error paths
that don't surface to the user

Spotted while writing the architecture doc but not pursued: the
"unknown media kind" early `Err` returned from
`MediaKind::from_wire(&request.kind).ok_or_else(...)` in
`analyze_frame` does NOT record a telemetry entry, because that
branch is technically a frontend bug (UI shouldn't be sending a
`kind` other than `camera|screen`). Worth deciding: do we want a
`frame_invalid_kind` telemetry kind for completeness, or is "this
shouldn't happen, surface a hard error" the right contract?

### Priority 3 — `ts-rs`-style codegen for vision provider ids

**Defer until a third adapter is on the table** — see
`P2_TS_RS_CODEGEN_DECISION_EXECUTION_REPORT_2026-05-05.md`.

### Priority 4 — Privacy posture × remote vision

**Defer until a third (remote) vision adapter is being scoped** —
see `P3_DEFERRALS_EXECUTION_REPORT_2026-05-04.md` and
`docs/VISION-V1-ARCHITECTURE.md` §9.

### Priority 5 — Microphone consent (separate track)

Out of scope. The architecture doc §9 records the suggested
mirror pattern (`mic_invalid` / `mic_permission_denied` /
`mic_permission_ask`).

## 4. Risks / things to review first

- **Telemetry semantics widened.** Every Deny / Ask / validation
  rejection now produces a TelemetryEntry. The History tab will
  surface these immediately. If a test environment frequently
  exercises Ask paths, the buffer will accumulate more rows than
  before. Buffer is in-memory and `clear_telemetry`-able from the
  drawer footer, so no real risk — flagged for awareness.
- **`frame_invalid` is a new TS allow-list member.** The
  parameterized vitest test asserts parity. A future TS-side
  consumer that switches on the kind exhaustively (none today)
  would need to handle it.
- **Rust unit test coverage gap on `record_frame_early_exit_telemetry`.**
  The helper is straight-line with literal kind strings; State-
  driven integration tests would require Tauri scaffolding the
  workspace doesn't have yet. Not worth building today; revisit
  if the helper grows.
- **Architecture doc will rot if not maintained.** It claims
  "Current as of 2026-05-05". If a future PR changes Vision-v1
  behavior, update the doc in the same PR. Consider a CI check.
- **Nothing pushed for ~11 commits.** Review the batch and
  authorize a push when ready.

## 5. Recommended next prompt (copy-paste, detailed)

Paste this into the next session as-is — or, if you want to push
first, do that and then start the next session against the new
`origin/dev`.

---

```md
You are Claude Code, continuing work on Aether.

Repo root:
C:/Users/dbhav/Projects/aether/

Branch:
dev

Current state (treat repo as source of truth if anything differs):
- `dev` is at `d93d7f0` plus a docs commit on top.
- 12 commits ahead of `origin/dev` since the last push.
- Working tree clean.
- Push is NOT pre-authorized for this session. Do NOT push unless
  explicitly instructed at the end of the session.
- All multimodal vision-track work through 2026-05-06 has shipped
  AND committed locally; nothing has been pushed.
- The multimodal vision stack now also includes:
  - shell-side empty/invalid frame data URL guard via
    `validate_frame_data_url`,
  - the same guard mirrored into `maybe_apply_vision`,
  - Trust drawer middle-truncates long model ids,
  - vision_provider.json additive-default-safe contract is
    test-locked,
  - analyze_frame emits telemetry for every early exit
    (`frame_invalid`, `permission_denied`, `permission_ask`),
  - vision boot WARN lines include URL/path context,
  - architecture documented at `docs/VISION-V1-ARCHITECTURE.md`.

Mandatory first steps (do these in order before editing):
1. Read `HANDOFF_2026-05-07_CONTINUE_COMPANION_BUILD.md` end to end.
2. `git status` and `git log --oneline -30`.
3. Read `docs/VISION-V1-ARCHITECTURE.md` for the canonical surface.
4. Read the most recent reports:
   - `CHUNK_A_FRAME_EARLY_EXIT_TELEMETRY_EXECUTION_REPORT_2026-05-06.md`
   - `CHUNK_B_LOG_CLARITY_EXECUTION_REPORT_2026-05-06.md`
   - `CHUNK_C_VISION_V1_ARCHITECTURE_DOC_EXECUTION_REPORT_2026-05-06.md`
5. Skim:
   - `apps/desktop/src-tauri/src/commands.rs::analyze_frame`,
     `::record_frame_early_exit_telemetry`,
     `::maybe_apply_vision`
   - `apps/desktop/src/lib/mediaTurns.ts`
   - `apps/desktop/src/components/TrustDrawer.tsx::kindClass`

Session focus (multimodal / vision assistant track ONLY) — small
polish round, no new product surface:

P1 — Decide on the `MediaKind::from_wire` Err path
  - Today an unknown `kind` from the frontend returns a hard
    string error with no telemetry. Decide: is that the right
    contract (frontend bug, surface loudly, no History row), or
    should it record a `frame_invalid_kind` telemetry entry for
    consistency with the other early-exit paths?
  - If you decide to record, follow the pattern in
    `record_frame_early_exit_telemetry` and update
    `MEDIA_TURN_KINDS` + the TrustDrawer `kindClass`.
  - If you decide not to record, document the rationale in a
    short report.

P2 — Optional: dedicated friendly label for `frame_invalid` rows
  - The History tab currently renders kinds via
    `{kind.replace(/_/g, " ")}` so `frame_invalid` shows as
    "frame invalid". If a friendlier "Capture rejected" reads
    better, wire it through a kind-label helper.

P3 — Optional: any other small polish you spot
  - Only land if you can keep it pure and tiny. Otherwise document
    the deferral.

Hard constraints (don't drift):
- No push without explicit user authorization.
- No release / distribution / signing work.
- No streaming or continuous capture modes.
- No microphone / voice / STT / TTS work.
- No broad settings redesign.
- Do NOT unify LlamaCppConfigError + OllamaConfigError across the
  feature boundary.
- Do NOT extend L5's AuditRecordEvent to carry provider info.
- Do NOT change the durable-memory privacy posture for images
  (image bytes stay transient).
- Do NOT change the analyze_frame trust/audit contract beyond
  telemetry-only kinds.
- Do NOT widen the vision_provider.json contract beyond
  additive-default-safe shapes.
- Do NOT introduce new vision providers.
- Do NOT add new test deps.

Process for each priority:
1. Implement.
2. Run focused tests for the touched layer.
3. Run the full check set:
   - cargo fmt --all -- --check
   - cargo check --workspace
   - cargo test --workspace
   - cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp
   - apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp
   - python tools/lint-layer-boundaries/check.py
   - apps/desktop && pnpm typecheck && pnpm build && pnpm test
4. Fix all failures.
5. Commit in clear scoped slices.
6. Update `docs/VISION-V1-ARCHITECTURE.md` in the same commit if
   you change anything it describes.

Before stopping:
- Keep git status clean.
- Write/update execution reports for each priority you touch.
- Write a fresh handoff file with the same structure as this one.
- Confirm whether push is authorized for the run; if not, leave
  commits unpushed and note it in the handoff.

Stay strictly on the multimodal vision track. No drift.
```

---

(end of handoff)
