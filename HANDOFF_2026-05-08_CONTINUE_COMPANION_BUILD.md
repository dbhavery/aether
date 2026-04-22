# Handoff — Continue the companion build (2026-05-08)

**Written:** 2026-05-07.
**Branch state:** `dev` at `88159f8` with 2 unpushed commits ahead of
`origin/dev` (`fb2ce1c`, `88159f8`). 2026-05-06 batch still pushed.
**Push status:** **Not authorized for this session.** Leave commits
local; Don will review and push when ready.
**Next session mode:** continue polish + safety on the multimodal /
vision assistant track.

---

## 0. Morning status

1. `dev` is `88159f8`, 2 commits ahead of `origin/dev`.
2. Working tree clean.
3. Focused checks run 2026-05-07 (docs-only changes):
   - `cargo fmt --all -- --check` — clean
   - `cargo check --workspace` — clean (pre-existing warnings only)
   - `python tools/lint-layer-boundaries/check.py` — 0 violations
   - `apps/desktop && pnpm typecheck` — clean
4. Full test matrix was green at `01f40e5` (the last code-landing
   commit). No code changed since.

## 1. What landed in this run

| SHA | Subject |
| --- | --- |
| `fb2ce1c` | docs: add 2026-05-07 roadmap visual |
| `88159f8` | docs: P1 decision - keep MediaKind::from_wire Err path as hard error, no telemetry |

Reports:

- [P1_MEDIAKIND_FROM_WIRE_TELEMETRY_DECISION_EXECUTION_REPORT_2026-05-07.md](file:///C:/Users/dbhav/Projects/aether/P1_MEDIAKIND_FROM_WIRE_TELEMETRY_DECISION_EXECUTION_REPORT_2026-05-07.md)

Status visual (not code, not process — a one-page state view for Don):

- [ROADMAP_VISUAL_2026-05-07.html](file:///C:/Users/dbhav/Projects/aether/ROADMAP_VISUAL_2026-05-07.html)

Reference: [docs/VISION-V1-ARCHITECTURE.md](file:///C:/Users/dbhav/Projects/aether/docs/VISION-V1-ARCHITECTURE.md) §6
now documents the intentional `MediaKind::from_wire` telemetry
exclusion.

## 2. Decisions locked this round

- **`MediaKind::from_wire` Err path stays a hard error, no
  telemetry.** Rationale: IPC contract violation vs. user-attempted
  analysis — different audiences, different ledgers. Widening the
  telemetry kind vocabulary without a user-reachable path would be
  premature. See the P1 report for the full reasoning and the
  conditions that would reopen the decision (remote vision adapter,
  TS exhaustive-typecheck loss, or a real production bug).
- **P2 ("Capture rejected" label) deferred.** Adding a kind-label
  helper for a single kind is premature infrastructure. Revisit if
  a second kind needs a friendly label or if users report the raw
  "frame invalid" rendering as unclear.

## 3. Multimodal product surface today

Unchanged from 2026-05-07 — this round made no behavior changes.

1. Local-only media permissions
   (`<app_data>/media_permissions.json`).
2. Camera + Screen panels — single-shot capture, OS picker for
   screen, default OFF.
3. `analyze_frame` — permissioned, audited, telemetered,
   transcript-visible. Rejects empty/invalid data URL payloads at
   the shell boundary. Records telemetry on three early-exit paths
   (`frame_invalid`, `permission_denied`, `permission_ask`). The
   fourth possible early exit — `MediaKind::from_wire` failure —
   remains intentionally telemetry-free and returns a hard error.
4. `maybe_apply_vision` mirrors the frame validation guard.
5. Vision providers: Ollama and llama.cpp, both with discovery and
   in-provider model selection. Boot WARN lines include base URL +
   persistence file path.
6. `vision_provider.json` persists `active` + `model_per_provider`,
   additive-default-safe, test-locked.
7. Per-provider model-list TTL cache (default 60s; bounded
   `[5, 3600]` env override; manual `↻` refresh; effective TTL
   logged at boot unconditionally).
8. UI surfaces — VisionBadge, ActiveVisionRoute hint, Trust drawer
   media rows, transcript footer all surface provider + model
   consistently.
9. Trust drawer history rows middle-truncate verbose model ids
   (default 28 chars, suffix 8); full id in `title` tooltip.
10. Architecture documented at `docs/VISION-V1-ARCHITECTURE.md` and
    now reflects the `MediaKind::from_wire` exclusion.

## 4. What to build next — multimodal track

### Priority 1 — Open

Nothing urgent on the vision-v1 slice. The observability surface is
now fully documented and closed, and both open judgment calls from
2026-05-07 are resolved.

### Priority 2 — Optional: arch-doc rot guard

Ship a lightweight CI check (or pre-commit) that fails when
`docs/VISION-V1-ARCHITECTURE.md` has a `Status: Current as of
<date>` more than N days stale relative to the latest commit that
touches `apps/desktop/src-tauri/src/commands.rs`,
`packages/l4-router/src/vision.rs`, or the vision-registry/cache
files. Keep it advisory, not blocking. Tracked as a flagged risk in
the 2026-05-06 Chunk C report.

### Priority 3 — Optional: small polish you spot

Land only if pure and tiny. Otherwise document the deferral.

### Priority 4 — Defer

- `ts-rs` codegen for vision provider ids — defer until a third
  adapter is on the table.
- Privacy posture × remote vision — defer until a third (remote)
  vision adapter is being scoped.
- Microphone consent — separate track. Architecture doc §9 records
  the suggested mirror pattern.

## 5. Risks / things to review first

- **Nothing pushed for 2 commits.** Review the two-commit batch
  before authorizing a push. Both are docs-only.
- **Vision v1 slice is in "steady-state polish".** The low-hanging
  observability, safety, and documentation work is done. Future
  vision-track rounds will either be: (a) external-trigger work
  (new adapter, remote track), (b) rot guards (arch-doc CI), or
  (c) optional polish. Consider whether the next session should
  instead pivot to an **adjacent Wave 5+ track** (L3 presence, L2
  durable memory maturation, voice scoping) rather than continuing
  to drill on Vision v1.
- **Architecture doc is still the primary rot risk.** No CI guard
  yet. Today's touch bumped the `Status: Current as of` marker to
  2026-05-07, which is correct but not self-enforcing.

## 6. Recommended next prompt (copy-paste, detailed)

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
- `dev` is at `88159f8`, 2 commits ahead of `origin/dev`.
- Working tree clean.
- Push is NOT pre-authorized for this session. Do NOT push unless
  explicitly instructed at the end of the session.
- Vision-v1 polish slice reached steady-state on 2026-05-07. Both
  open judgment calls from the 2026-05-07 handoff are resolved:
  - `MediaKind::from_wire` Err path: hard error, no telemetry
    (decision locked; rationale in
    `P1_MEDIAKIND_FROM_WIRE_TELEMETRY_DECISION_EXECUTION_REPORT_2026-05-07.md`).
  - "Capture rejected" label (P2): deferred.

Mandatory first steps (do these in order before editing):
1. Read `HANDOFF_2026-05-08_CONTINUE_COMPANION_BUILD.md` end to end.
2. `git status` and `git log --oneline -30`.
3. Read `docs/VISION-V1-ARCHITECTURE.md` — especially §6 which now
   documents the telemetry exclusion, and §9 which lists the
   deferred tracks.
4. Read `P1_MEDIAKIND_FROM_WIRE_TELEMETRY_DECISION_EXECUTION_REPORT_2026-05-07.md`.

Session focus — confirm direction with Don before coding:

Option A — arch-doc rot guard (Priority 2 from the handoff)
  - Add a lightweight pre-commit or CI script that warns (or fails)
    when `docs/VISION-V1-ARCHITECTURE.md`'s `Status:` date drifts
    more than N days behind the latest commit touching vision code
    (`apps/desktop/src-tauri/src/commands.rs`, the vision files
    under `packages/l4-router/src/`, `apps/desktop/src-tauri/src/
    vision_registry.rs`, `vision_cache.rs`).
  - Scope: one new script under `tools/`, optional wire-up in the
    existing check harness. Keep additive, no new deps.

Option B — pivot to an adjacent track
  - L3 presence maturation, L2 durable-memory maturation, or voice
    track scoping. All are larger than a polish round and deserve
    explicit buy-in from Don before starting.

Option C — continue vision polish
  - Only if Don spots something specific. The mechanical backlog
    is empty.

Hard constraints (don't drift):
- No push without explicit user authorization.
- No release / distribution / signing work.
- No streaming or continuous capture modes.
- No microphone / voice / STT / TTS work unless explicitly scoped.
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
- Do NOT add `frame_invalid_kind` telemetry unless the P1 decision
  is explicitly reopened by Don or one of the reopen conditions
  in the P1 report is met.

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

Stay strictly on-scope. No drift.
```

---

(end of handoff)
