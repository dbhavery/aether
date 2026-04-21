# Handoff — Continue the companion build (2026-05-06)

**Written:** 2026-05-05 (autonomous polish + safety run).
**Branch state:** `dev`, **7 commits ahead of `origin/dev`** at SHA
`3c94037`. (One follow-up doc commit will land on top before this
file is final — see §1.)
**Push status:** **NOT authorized this session.** Treat the next
push as a fresh authorization decision.
**Next session mode:** small, focused polish + safety on the
multimodal/video assistant track only.

---

## 0. Morning status

1. `dev` is `3c94037`.
   - Pre-day base was `90e4bc2` (the 2026-05-02 polish-round
     reports + 2026-05-03 handoff doc commit).
   - Earlier this week: `48757f5`, `b653e6a`, `46016ef`, `5a4b15c`,
     `b2ee7ff`, `a90715c` — analyze_frame guard, Trust drawer
     truncation v1 + middle-truncate upgrade, maybe_apply_vision
     symmetry, plus the matching docs.
   - This session: `3c94037` — vision_provider.json
     schema-tolerant read tests.
   - This handoff + the P1/P2/P3 reports land in a docs commit on
     top of `3c94037`.
2. Working tree clean after the docs commit.
3. Full check set is green:
   - `cargo fmt --all -- --check`
   - `cargo check --workspace`
   - `cargo test --workspace`
   - `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp`
     → **57 / 57**
   - `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp`
     → **93 / 93** (was 89; +4 vision_registry schema-tolerance
     cases)
   - `python tools/lint-layer-boundaries/check.py` → 0 violations
   - `apps/desktop && pnpm typecheck && pnpm build` → clean
   - `apps/desktop && pnpm test` → **85 / 85**

## 1. What landed in the most recent run

| SHA | Subject |
| --- | --- |
| `3c94037` | test(apps/desktop): lock vision_provider.json additive-default-safe contract |

Reports:

- [P1_VISION_PROVIDER_JSON_SCHEMA_TOLERANT_READ_EXECUTION_REPORT_2026-05-05.md](file:///C:/Users/dbhav/Projects/aether/P1_VISION_PROVIDER_JSON_SCHEMA_TOLERANT_READ_EXECUTION_REPORT_2026-05-05.md)
- [P2_TS_RS_CODEGEN_DECISION_EXECUTION_REPORT_2026-05-05.md](file:///C:/Users/dbhav/Projects/aether/P2_TS_RS_CODEGEN_DECISION_EXECUTION_REPORT_2026-05-05.md)
- [P3_DEFERRAL_EXECUTION_REPORT_2026-05-05.md](file:///C:/Users/dbhav/Projects/aether/P3_DEFERRAL_EXECUTION_REPORT_2026-05-05.md)

## 2. Multimodal product surface today

No new product surface this session — only safety net tightened:

1. Local-only media permissions
   (`<app_data>/media_permissions.json`).
2. Camera + Screen panels — single-shot capture, OS picker for
   screen, default OFF.
3. `analyze_frame` — permissioned, audited, telemetered,
   transcript-visible. Rejects empty/invalid data URL payloads at
   the shell boundary with a friendly, actionable error.
   `maybe_apply_vision` mirrors the same guard.
4. Vision providers: Ollama and llama.cpp, both with discovery and
   in-provider model selection.
5. **`vision_provider.json` additive-default-safe contract is now
   covered by tests.** Unknown top-level fields are ignored on
   read (load and `attach_persistence` both pass) and dropped on
   rewrite (documented limitation, locked by test). Malformed JSON
   still falls back to defaults without panicking.
6. Per-provider model-list TTL cache (default 60s; bounded
   `[5, 3600]` env override; manual `↻` refresh). Effective TTL
   logged at boot unconditionally.
7. UI surfaces — VisionBadge, ActiveVisionRoute hint, Trust drawer
   media rows, transcript footer all surface provider + model
   consistently.
8. Provider id vocabulary lives in a single
   `apps/desktop/src/lib/visionProviders.ts` registry. Rust
   adapters declare `id()` independently — codegen still deferred
   (see §3 P2).
9. Transcript footer drops the `tier` chip on vision turns.
10. Trust drawer history rows middle-truncate verbose model ids
    (default 28 chars, suffix 8) so quantization tags survive;
    full id in `title` tooltip.

## 3. What to build next — multimodal track

### Priority 1 — Telemetry surface for `analyze_frame` validation rejections

Right now an `analyze_frame` validation rejection short-circuits
*before* any audit row, telemetry entry, or memory record is
written. That's correct for L5 / audit (no provider call ran), but
it means the Trust drawer's History tab can't show the user that
their last capture was rejected. Consider a tiny scoped change:

- Record a telemetry entry only (no audit row) on validation
  rejection so the History tab can render a `frame_invalid` row
  alongside `frame_analyzed` / `frame_blocked` / `permission_denied`.
- Keeps L5/audit semantics untouched (no policy decision was made).
- Requires no new audit fields.

Defer if the trade-off feels too noisy; otherwise small.

### Priority 2 — `ts-rs`-style codegen for vision provider ids

**Defer until a third adapter is on the table** — see
P2_TS_RS_CODEGEN_DECISION_EXECUTION_REPORT_2026-05-05.md for the
trigger conditions and likely approach.

### Priority 3 — Privacy posture × remote vision

**Defer until a third (remote) vision adapter is being scoped** —
see P3_DEFERRALS_EXECUTION_REPORT_2026-05-04.md (still current).

### Priority 4 — Microphone consent (separate track)

Out of scope for the multimodal vision foundation; mirror the
permission tri-state when the voice/STT path lands.

## 4. Risks / things to review first

- **`VisionPersistedState` does not preserve unknown keys on
  rewrite.** Locked by test
  (`unknown_fields_are_dropped_on_rewrite`). Any future field
  must default-safe on read AND tolerate being absent from a
  rewritten file. If round-trip preservation is ever needed, the
  options are `#[serde(flatten)] extras` or a versioning system —
  both bigger than the current contract justifies.
- **`malformed_json_falls_back_to_default_state` test** uses
  `"active": ["not", "a", "string"]` to force a real serde error
  — i.e. it's the wrong-type-for-known-field path, not the
  unknown-field path. If a future serde upgrade ever changes
  defaults around `Option<String>` deserialization, this test
  should be the canary.
- **`validate_frame_data_url` is now called from two sites.** Any
  rule change must keep both call sites happy.
- **Middle-truncation `suffixLen = 8`** preserves typical
  quantization tags. Revisit if model ids grow longer trailing
  metadata.
- **`MODEL_ID_DISPLAY_MAX = 28`** still a single magic number.
- **`title`-attribute tooltip is browser-default.** No custom
  hover card.
- **`VISION_PROVIDER_REGISTRY` Rust↔TS contract is convention,
  not codegen** (see P2 deferral).
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

Current state (assume true unless the repo says otherwise):
- `dev` is at `3c94037` plus a docs commit on top.
- 8 commits ahead of `origin/dev` since the last push.
- Working tree clean.
- Push is NOT pre-authorized for this session. Do NOT push unless
  explicitly instructed at the end of the session.
- All multimodal vision-track work through 2026-05-05 has shipped
  AND committed locally; nothing has been pushed.
- The multimodal vision stack now also includes:
  - shell-side empty/invalid frame data URL guard via
    `validate_frame_data_url`,
  - the same guard mirrored into `maybe_apply_vision`,
  - Trust drawer middle-truncates long model ids,
  - `vision_provider.json` additive-default-safe contract is
    test-locked: unknown fields ignored on read, dropped on
    rewrite (documented).

Mandatory first steps (do these in order before editing):
1. Read `HANDOFF_2026-05-06_CONTINUE_COMPANION_BUILD.md` end to end.
2. `git status` and `git log --oneline -30`.
3. Read the most recent reports:
   - `P1_VISION_PROVIDER_JSON_SCHEMA_TOLERANT_READ_EXECUTION_REPORT_2026-05-05.md`
   - `P2_TS_RS_CODEGEN_DECISION_EXECUTION_REPORT_2026-05-05.md`
   - `P3_DEFERRAL_EXECUTION_REPORT_2026-05-05.md`
4. Skim:
   - `apps/desktop/src-tauri/src/commands.rs::analyze_frame`
     and `::maybe_apply_vision`
   - `apps/desktop/src-tauri/src/vision_registry.rs` (the new
     schema-tolerance tests are at the top of the test mod)
   - `apps/desktop/src-tauri/src/telemetry*.rs` (find the
     telemetry write path — needed for P1)
   - `apps/desktop/src/components/TrustDrawer.tsx` (HistoryView)

Session focus (multimodal / vision assistant track ONLY) — small
polish round, no new product surface:

P1 — Telemetry-only entry on analyze_frame validation rejection
  - Today validation rejections short-circuit before any telemetry
    entry, so the Trust drawer History tab can't show the user a
    `frame_invalid` row alongside `frame_analyzed` /
    `frame_blocked` / `permission_denied`.
  - Add a telemetry entry (no audit row) when
    `validate_frame_data_url` rejects the payload, so the History
    tab can render the rejection.
  - Keep L5 / audit semantics untouched — no policy decision was
    made, no audit row.
  - Add a focused test on the path if there's a clean way; else
    cover via the existing telemetry surface tests.
  - If the trade-off feels too noisy, defer with a written reason.

P2 — Optional: ts-rs-style id constants codegen
  - Decide first whether it's the right time. With only two
    adapters it almost certainly isn't — defer with a written
    reason.

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
