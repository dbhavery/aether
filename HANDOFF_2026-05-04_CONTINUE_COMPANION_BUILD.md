# Handoff — Continue the companion build (2026-05-04)

**Written:** 2026-05-03 (autonomous polish run).
**Branch state:** `dev`, **2 commits ahead of `origin/dev`** at SHA
`b653e6a`. (One follow-up doc commit will land on top before this
file is final — see §1.)
**Push status:** **NOT authorized this session.** Treat the next
push as a fresh authorization decision.
**Next session mode:** small, focused polish + safety on the
multimodal/video assistant track only.

---

## 0. Morning status

1. `dev` is `b653e6a`.
   - Pre-session base was `90e4bc2` (the 2026-05-02 polish-round
     reports + 2026-05-03 handoff doc commit).
   - `48757f5` — analyze_frame empty-body guard.
   - `b653e6a` — Trust drawer model-id truncation.
   - This handoff + the P1/P2/P3 reports land in a docs commit on
     top of `b653e6a`.
2. Working tree clean after the docs commit.
3. Full check set is green:
   - `cargo fmt --all -- --check`
   - `cargo check --workspace`
   - `cargo test --workspace`
   - `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp`
     → **57 / 57**
   - `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp`
     → **89 / 89** (was 81; +8 validate_frame_data_url cases)
   - `python tools/lint-layer-boundaries/check.py` → 0 violations
   - `apps/desktop && pnpm typecheck && pnpm build` → clean
   - `apps/desktop && pnpm test` → **81 / 81** (was 76;
     +5 displayString)

## 1. What landed in the most recent run

| SHA | Subject |
| --- | --- |
| `48757f5` | feat(apps/desktop): reject empty/invalid frame data URLs in analyze_frame |
| `b653e6a` | feat(apps/desktop): truncate long model ids on Trust drawer body line |

Reports:

- [P1_ANALYZE_FRAME_EMPTY_BODY_GUARD_EXECUTION_REPORT_2026-05-03.md](file:///C:/Users/dbhav/Projects/aether/P1_ANALYZE_FRAME_EMPTY_BODY_GUARD_EXECUTION_REPORT_2026-05-03.md)
- [P2_TRUST_DRAWER_MODEL_ID_TRUNCATION_EXECUTION_REPORT_2026-05-03.md](file:///C:/Users/dbhav/Projects/aether/P2_TRUST_DRAWER_MODEL_ID_TRUNCATION_EXECUTION_REPORT_2026-05-03.md)
- [P3_DEFERRALS_EXECUTION_REPORT_2026-05-03.md](file:///C:/Users/dbhav/Projects/aether/P3_DEFERRALS_EXECUTION_REPORT_2026-05-03.md)

## 2. Multimodal product surface today

Stable since 2026-05-01, polished further this run:

1. Local-only media permissions
   (`<app_data>/media_permissions.json`).
2. Camera + Screen panels — single-shot capture, OS picker for
   screen, default OFF.
3. `analyze_frame` — permissioned, audited, telemetered,
   transcript-visible. **Now rejects empty/invalid data URL
   payloads at the shell boundary with a friendly,
   actionable error before any provider call runs.**
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
   `apps/desktop/src/lib/visionProviders.ts` registry. All five
   downstream helpers consume it.
9. Transcript footer drops the `tier` chip on vision turns so it
   stops duplicating the dedicated provider + model chips.
10. **Trust drawer history rows now truncate verbose model ids
    (default 28 chars + `…`) inline, with the full id preserved
    in a `title` tooltip.**

## 3. What to build next — multimodal track

### Priority 1 — Empty-body guard symmetry on `maybe_apply_vision`

`analyze_frame` now rejects bad payloads at the shell boundary, but
`maybe_apply_vision` still calls L4's `split_data_url` and treats a
zero-length body as a `ProviderBadResponse` warning. Consider:

- Have `maybe_apply_vision` short-circuit on the same
  `validate_frame_data_url` rules so the shell never logs
  "vision: data URL decode failed: …" for shapes the gate already
  rejects.
- Tiny refactor; defer until you're touching that function.

### Priority 2 — Trust drawer middle-truncation for filename-style ids

Today's prefix-truncation drops the suffix (e.g. `…q4_k_m`), which
hides the quantization tag — sometimes the most informative part. A
middle-truncation variant
(`qwen2.5-vl-72b…q4_k_m`) preserves both ends. Optional polish;
only worth doing if the `…` keeps cutting off the bit users want to
read.

### Priority 3 — `ts-rs`-style codegen for vision provider ids

**Defer until a third adapter is on the table** — see
P3_DEFERRALS_EXECUTION_REPORT_2026-05-03.md §"Deferral 1" for the
two candidate approaches.

### Priority 4 — Privacy posture × remote vision

**Defer until a third (remote) vision adapter is being scoped** —
see P3_DEFERRALS_EXECUTION_REPORT_2026-05-03.md §"Deferral 2" for
the seven open questions to answer then.

### Priority 5 — Microphone consent (separate track)

Out of scope for the multimodal vision foundation; mirror the
permission tri-state when the voice/STT path lands.

## 4. Risks / things to review first

- **`validate_frame_data_url` is shell-side only.** The L4
  `split_data_url` helper still tolerates an empty body. The shell
  guard is the user-facing contract; L4's permissive behavior is
  fine because no caller can reach it without going through the
  shell. If a future caller bypasses the shell, the gap reopens.
- **Truncation `MODEL_ID_DISPLAY_MAX = 28` is a single magic
  number.** If ids start commonly exceeding 50 chars, revisit.
- **Truncation drops the suffix.** See Priority 2 above.
- **`title`-attribute tooltip is browser-default.** No custom hover
  card. Acceptable for the Trust drawer's information density today;
  revisit if the row becomes a primary touchpoint.
- **`VISION_PROVIDER_REGISTRY` Rust↔TS contract is convention,
  not codegen.** See P3 deferral.
- **`vision_provider.json` shape stable since 2026-05-01.** Any
  future field must default-safe on read.
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
- `dev` is `b653e6a` plus a docs commit on top.
- 3 commits ahead of `origin/dev` since the last push (including
  the 2026-05-03 docs commit).
- Push is NOT pre-authorized this session. Ask first if you think
  pushing is needed.
- All multimodal vision-track work through 2026-05-03 has shipped
  AND committed locally; nothing has been pushed.
- The multimodal vision stack now also includes:
  - shell-side empty/invalid frame data URL guard via
    `validate_frame_data_url`,
  - Trust drawer truncates verbose model ids inline (`MODEL_ID_DISPLAY_MAX = 28`)
    while preserving the full id in a `title` tooltip.

Mandatory first steps (do these in order before editing):
1. Read `HANDOFF_2026-05-04_CONTINUE_COMPANION_BUILD.md` end to end.
2. `git status` and `git log --oneline -30`.
3. Read these reports for shape context:
   - `P1_ANALYZE_FRAME_EMPTY_BODY_GUARD_EXECUTION_REPORT_2026-05-03.md`
   - `P2_TRUST_DRAWER_MODEL_ID_TRUNCATION_EXECUTION_REPORT_2026-05-03.md`
   - `P3_DEFERRALS_EXECUTION_REPORT_2026-05-03.md`
4. Skim:
   - `apps/desktop/src-tauri/src/commands.rs::validate_frame_data_url`
     and `::maybe_apply_vision`
   - `apps/desktop/src/lib/displayString.ts`
   - `apps/desktop/src/components/TrustDrawer.tsx`
   - `apps/desktop/src/lib/visionProviders.ts`

Session focus (multimodal / vision assistant track ONLY) —
small polish round, no new product surface:

P1 — Empty-body guard symmetry on `maybe_apply_vision`
  - Have `maybe_apply_vision` reject payloads matching the same rules
    as `validate_frame_data_url` *before* calling L4's `split_data_url`,
    so the shell never logs "vision: data URL decode failed: ..." for
    shapes the gate already rejects.
  - Add a focused test if there's a clean way to trigger it.

P2 — Optional: Trust drawer middle-truncation
  - Only land if you can keep the helper pure and tiny. Otherwise
    document the deferral. Preserve a hover-recoverable full id.

P3 — Optional: ts-rs-style id constants codegen
  - Decide first whether it's the right time. With only two adapters
    it almost certainly isn't — defer with a written reason. If yes,
    scope it tightly.

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

Final response format (return exactly this structure):

## Tasks completed
- ...

## Commits
- SHA — message

## Tests and checks
- ...

## Remaining multimodal backlog
1. ...
2. ...

## Decisions for review
1. ...
2. ...

## Next recommended prompt
```md
...
```

Stay strictly on the multimodal vision track. No drift.
```

---

(end of handoff)
