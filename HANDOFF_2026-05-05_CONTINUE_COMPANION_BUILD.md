# Handoff — Continue the companion build (2026-05-05)

**Written:** 2026-05-04 (autonomous polish run, second round of the day).
**Branch state:** `dev`, **5 commits ahead of `origin/dev`** at SHA
`b2ee7ff`. (One follow-up doc commit will land on top before this
file is final — see §1.)
**Push status:** **NOT authorized this session.** Treat the next
push as a fresh authorization decision.
**Next session mode:** small, focused polish + safety on the
multimodal/video assistant track only.

---

## 0. Morning status

1. `dev` is `b2ee7ff`.
   - Pre-day base was `90e4bc2` (the 2026-05-02 polish-round
     reports + 2026-05-03 handoff doc commit).
   - Earlier today: `48757f5`, `b653e6a`, `46016ef` — analyze_frame
     guard + Trust drawer truncation v1 + 2026-05-03 reports/handoff.
   - This session: `5a4b15c`, `b2ee7ff` — maybe_apply_vision guard
     symmetry + middle-truncation upgrade.
   - This handoff + the P1/P2/P3 reports land in a docs commit on
     top of `b2ee7ff`.
2. Working tree clean after the docs commit.
3. Full check set is green:
   - `cargo fmt --all -- --check`
   - `cargo check --workspace`
   - `cargo test --workspace`
   - `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp`
     → **57 / 57**
   - `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp`
     → **89 / 89**
   - `python tools/lint-layer-boundaries/check.py` → 0 violations
   - `apps/desktop && pnpm typecheck && pnpm build` → clean
   - `apps/desktop && pnpm test` → **85 / 85** (was 81;
     +4 truncateMiddleForDisplay)

## 1. What landed in the most recent run

| SHA | Subject |
| --- | --- |
| `5a4b15c` | feat(apps/desktop): mirror frame-validation guard into maybe_apply_vision |
| `b2ee7ff` | feat(apps/desktop): middle-truncate long model ids to preserve suffix |

Reports:

- [P1_MAYBE_APPLY_VISION_GUARD_SYMMETRY_EXECUTION_REPORT_2026-05-04.md](file:///C:/Users/dbhav/Projects/aether/P1_MAYBE_APPLY_VISION_GUARD_SYMMETRY_EXECUTION_REPORT_2026-05-04.md)
- [P2_MIDDLE_TRUNCATION_EXECUTION_REPORT_2026-05-04.md](file:///C:/Users/dbhav/Projects/aether/P2_MIDDLE_TRUNCATION_EXECUTION_REPORT_2026-05-04.md)
- [P3_DEFERRALS_EXECUTION_REPORT_2026-05-04.md](file:///C:/Users/dbhav/Projects/aether/P3_DEFERRALS_EXECUTION_REPORT_2026-05-04.md)

## 2. Multimodal product surface today

Polished further this round, no new surface:

1. Local-only media permissions
   (`<app_data>/media_permissions.json`).
2. Camera + Screen panels — single-shot capture, OS picker for
   screen, default OFF.
3. `analyze_frame` — permissioned, audited, telemetered,
   transcript-visible. Rejects empty/invalid data URL payloads at
   the shell boundary with a friendly, actionable error before any
   provider call runs. **`maybe_apply_vision` mirrors the same
   guard so a future caller can't bypass it and trigger a
   duplicate WARN line.**
4. Vision providers: Ollama and llama.cpp, both with discovery and
   in-provider model selection.
5. `vision_provider.json` persists `active` + `model_per_provider`,
   with first-launch seeding from adapter `current_model()`.
6. Per-provider model-list TTL cache (default 60s; bounded
   `[5, 3600]` env override; manual `↻` refresh). Effective TTL
   logged at boot unconditionally.
7. UI surfaces — VisionBadge, ActiveVisionRoute hint, Trust drawer
   media rows, transcript footer all surface provider + model
   consistently.
8. Provider id vocabulary lives in a single
   `apps/desktop/src/lib/visionProviders.ts` registry.
9. Transcript footer drops the `tier` chip on vision turns to
   avoid duplicating provider + model chips.
10. **Trust drawer history rows now middle-truncate verbose model
    ids (default 28 chars, suffix 8) so filename-style ids
    preserve their quantization tag — the full id stays in a
    `title` tooltip.**

## 3. What to build next — multimodal track

### Priority 1 — `vision_provider.json` schema-tolerant read for forward-compat

The shape has been stable since 2026-05-01, but the
default-safe-on-read constraint hasn't been load-tested. A focused
test that round-trips a config with an unknown extra field would
prove the read path tolerates additive shapes — and lock that
contract before a future field gets added.

### Priority 2 — `ts-rs`-style codegen for vision provider ids

**Defer until a third adapter is on the table** — see
P3_DEFERRALS_EXECUTION_REPORT_2026-05-04.md.

### Priority 3 — Privacy posture × remote vision

**Defer until a third (remote) vision adapter is being scoped** —
see P3_DEFERRALS_EXECUTION_REPORT_2026-05-04.md.

### Priority 4 — Microphone consent (separate track)

Out of scope for the multimodal vision foundation; mirror the
permission tri-state when the voice/STT path lands.

## 4. Risks / things to review first

- **`validate_frame_data_url` is now called from two sites.** Any
  future change to its rules should keep both call sites happy.
  The shell-side gate returns `Result<&str, String>`; the
  vision-side gate ignores the `Ok` body slice. If the gate ever
  needs to return more structured data (e.g. parsed MIME), update
  both call sites in lockstep.
- **Middle-truncation `suffixLen = 8`** preserves typical
  quantization tags. If model ids start using longer trailing
  metadata (`-instruct-vision-q5_k_m`), the suffix may need
  bumping. Today's choice is a sensible default.
- **`MODEL_ID_DISPLAY_MAX = 28`** still a single magic number.
  If reviewers want a width-responsive value, that's a different
  scope.
- **`title`-attribute tooltip is browser-default.** No custom
  hover card.
- **`VISION_PROVIDER_REGISTRY` Rust↔TS contract is convention,
  not codegen** (see P3 deferral).
- **Vitest pinned to ^2; jsdom ^29; RTL ^16; RTL/dom ^10.**
  Bumping requires aligning the stack.

## 5. Recommended next prompt (copy-paste, detailed)

Paste this into the next session as-is.

---

```md
You are Claude Code, continuing work on Aether.

Repo root:
C:/Users/dbhav/Projects/aether/

Branch:
dev

Current state:
- `dev` is `b2ee7ff` plus a docs commit on top.
- 6 commits ahead of `origin/dev` since the last push.
- Push is NOT pre-authorized this session. Ask first if you think
  pushing is needed.
- All multimodal vision-track work through 2026-05-04 has shipped
  AND committed locally; nothing has been pushed.
- The multimodal vision stack now also includes:
  - shell-side empty/invalid frame data URL guard via
    `validate_frame_data_url`,
  - the same guard mirrored into `maybe_apply_vision`,
  - Trust drawer middle-truncates long model ids
    (`MODEL_ID_DISPLAY_MAX = 28`, `suffixLen = 8`) so
    quantization tags survive; full id in `title` tooltip.

Mandatory first steps (do these in order before editing):
1. Read `HANDOFF_2026-05-05_CONTINUE_COMPANION_BUILD.md` end to end.
2. `git status` and `git log --oneline -30`.
3. Read these reports for shape context:
   - `P1_MAYBE_APPLY_VISION_GUARD_SYMMETRY_EXECUTION_REPORT_2026-05-04.md`
   - `P2_MIDDLE_TRUNCATION_EXECUTION_REPORT_2026-05-04.md`
   - `P3_DEFERRALS_EXECUTION_REPORT_2026-05-04.md`
4. Skim:
   - `apps/desktop/src-tauri/src/commands.rs::validate_frame_data_url`
     and `::maybe_apply_vision`
   - `apps/desktop/src/lib/displayString.ts`
   - `apps/desktop/src/components/TrustDrawer.tsx`
   - the `vision_provider.json` read path (find it via grep in
     `apps/desktop/src-tauri/src/`)

Session focus (multimodal / vision assistant track ONLY) —
small polish round, no new product surface:

P1 — `vision_provider.json` schema-tolerant read test
  - Add a focused test that loads a config containing an unknown
    extra top-level field and proves it round-trips (or is
    silently ignored) without losing `active` /
    `model_per_provider`.
  - Locks the additive-default-safe contract before the next
    field gets added.

P2 — Optional: ts-rs-style id constants codegen
  - Decide first whether it's the right time. With only two
    adapters it almost certainly isn't — defer with a written
    reason. If yes, scope it tightly.

P3 — Optional: any small polish you spot in the existing surface
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
- Do NOT change the analyze_frame trust/audit contract.
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
