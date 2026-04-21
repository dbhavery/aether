# Handoff — Continue the companion build (2026-05-03)

**Written:** 2026-05-02 (autonomous continuation run).
**Branch state:** `dev`, **14 commits ahead of origin/dev** at SHA `3434e0b`.
**Push status:** **NOT authorized this session.** All 14 commits
since the last push remain local. Treat the next push as a fresh
authorization decision.
**Next session mode:** broad autonomous build authorization on the
multimodal/video assistant track only.

---

## 0. Morning status

1. `dev` is 14 commits ahead of `origin/dev` at `3434e0b`.
2. Working tree clean.
3. Full check set is green:
   - `cargo fmt --all -- --check`
   - `cargo check --workspace`
   - `cargo test --workspace`
   - `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp`
     → **57 / 57**
   - `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp`
     → **81 / 81** (was 77; +4 TtlSource / resolve_ttl_from_env)
   - `python tools/lint-layer-boundaries/check.py` → 0 violations
   - `apps/desktop && pnpm typecheck && pnpm build` → clean
   - `apps/desktop && pnpm test` → **76 / 76** (was 64;
     +7 visionProviders, +5 transcript tier dedup)

## 1. What landed in the most recent run

| SHA | Subject |
| --- | --- |
| `0276bf3` | refactor(apps/desktop): extract shared vision-provider id vocabulary |
| `ef0689c` | feat(apps/desktop): drop duplicating tier chip on transcript vision turns |
| `3434e0b` | feat(apps/desktop): always log effective vision cache TTL at boot |

Reports:

- [P1_TRANSCRIPT_TIER_DEDUP_EXECUTION_REPORT_2026-05-02.md](file:///C:/Users/dbhav/Projects/aether/P1_TRANSCRIPT_TIER_DEDUP_EXECUTION_REPORT_2026-05-02.md)
- [P2_PROVIDER_ID_DEDUP_EXECUTION_REPORT_2026-05-02.md](file:///C:/Users/dbhav/Projects/aether/P2_PROVIDER_ID_DEDUP_EXECUTION_REPORT_2026-05-02.md)
- [P3_VISION_CACHE_TTL_BOOT_LOG_EXECUTION_REPORT_2026-05-02.md](file:///C:/Users/dbhav/Projects/aether/P3_VISION_CACHE_TTL_BOOT_LOG_EXECUTION_REPORT_2026-05-02.md)

## 2. Multimodal product surface today

Stable since 2026-05-01; this run was polish/dedup/observability:

1. Local-only media permissions
   (`<app_data>/media_permissions.json`).
2. Camera + Screen panels — single-shot capture, OS picker for
   screen, default OFF.
3. `analyze_frame` — permissioned, audited, telemetered,
   transcript-visible.
4. Vision providers: Ollama and llama.cpp, both with discovery and
   in-provider model selection.
5. `vision_provider.json` persists `active` + `model_per_provider`,
   with first-launch seeding from adapter `current_model()`.
6. Per-provider model-list TTL cache (default 60s; bounded
   `[5, 3600]` env override; manual `↻` refresh).
   **Effective TTL is now logged at boot unconditionally.**
7. UI surfaces — VisionBadge, ActiveVisionRoute hint, Trust
   drawer media rows, transcript footer all surface
   provider + model consistently.
8. **Provider id vocabulary lives in a single
   `apps/desktop/src/lib/visionProviders.ts` registry.** All five
   downstream helpers (mediaTurns, ActiveVisionRoute,
   visionRouteSummary, transcript tier dedup, badge derivation)
   consume it.
9. **Transcript footer drops the `tier` chip on vision turns** so
   it stops duplicating the dedicated provider + model chips.
   Text-only turns still carry tier where it adds info.

## 3. What to build next — multimodal track

### Priority 1 — `ts-rs`-style codegen for vision provider ids

The Rust adapter `id()` returns and the TS `VISION_PROVIDER_REGISTRY`
are still two sources of truth that must agree. The agreement is
now narrow (id strings only — labels are TS-only) but the strings
are easy to typo. A small build-script or `ts-rs`-emitted constants
file would close the loop. **Defer until a third adapter is on the
table** — single-source dedup is more compelling with three than
two sources.

### Priority 2 — Trust drawer body line wrap on long model ids

`TrustDrawer.tsx` uses `break-all` on the body line so verbose
model ids
(`qwen2.5-vl-72b-instruct-q4_k_m`) wrap rather than overflow. Soft
nice-to-have: clip with title-tooltip after N chars and show the
suffix on hover. Optional polish; defer.

### Priority 3 — `analyze_frame` empty-frame guard

Today `maybe_apply_vision` rejects an empty `image_b64` body with
`ProviderBadResponse`, which surfaces as a confusing error in the
UI. The shell-side `analyze_frame` already validates the data URL
prefix (`starts_with("data:image/")`), but a zero-length b64 body
slips through. Suggested: tighten the check to require both prefix
AND non-empty body before calling the engine. Tiny.

### Priority 4 — Privacy posture × remote vision

Wait for a third (remote) vision adapter; cheap to land then.

### Priority 5 — Microphone consent (separate track)

Out of scope for the multimodal vision foundation; mirror the
permission tri-state when the voice/STT path lands.

## 4. Risks / things to review first

- **`VISION_PROVIDER_REGISTRY` is still TS-side only.** Rust
  adapters define their `id()` independently. Mismatch is a runtime
  bug that the existing tests catch (the registry tests assert
  the two known ids), but a typo on either side could still ship
  if only one side were updated.
- **`vision_provider.json` shape stable since 2026-05-01.** Any
  future field must default-safe on read.
- **Boot log line is INFO, not WARN.** Operators running at WARN
  level won't see the TTL line. Acceptable trade-off — the WARN
  line for invalid env values still prints.
- **`AETHER_VISION_MODEL_TTL_SECS` no hot reload** — env read once
  at boot. Documented in the const docstring.
- **`tierChipForFooter`** drops the tier chip on vision turns
  *unconditionally*, including when the model chip is absent (e.g.
  passive future adapter that returns `None` from `current_model`).
  That means a vision turn served by a passive adapter would
  render only `provider · latency · tokens` — provider is still
  there, just without the long URL noise. Document if this becomes
  a problem.
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
- `dev` is 14 commits ahead of `origin/dev` at `3434e0b`.
- Push is NOT pre-authorized this session. Ask first if you think
  pushing is needed.
- All multimodal vision-track work through 2026-05-02 has shipped
  AND committed locally; nothing has been pushed.

Mandatory first steps (do these in order before editing):
1. Read `HANDOFF_2026-05-03_CONTINUE_COMPANION_BUILD.md` end to
   end.
2. `git status` and `git log --oneline -30`.
3. Read these reports for shape context:
   - `P1_TRANSCRIPT_TIER_DEDUP_EXECUTION_REPORT_2026-05-02.md`
   - `P2_PROVIDER_ID_DEDUP_EXECUTION_REPORT_2026-05-02.md`
   - `P3_VISION_CACHE_TTL_BOOT_LOG_EXECUTION_REPORT_2026-05-02.md`
4. Skim:
   - `apps/desktop/src-tauri/src/commands.rs::analyze_frame`
     (data URL guard)
   - `apps/desktop/src/components/TrustDrawer.tsx` (long-id wrap)
   - `apps/desktop/src/lib/visionProviders.ts`
     (single-source registry)

Session focus (multimodal / vision assistant track ONLY) —
small polish round, no new product surface:

P1 — analyze_frame empty-body guard
  - Tighten the prefix check in analyze_frame to also reject
    payloads whose comma-separated body is empty / too short to
    decode. Surface a friendly error message instead of letting
    the provider blow up downstream.
  - Add focused tests on the validation helper.

P2 — Optional: Trust drawer long-model-id ellipsis-with-title
  - Only land if you can keep it pure and tiny. Otherwise document
    the deferral.

P3 — Optional: ts-rs-style id constants codegen
  - Decide first whether it's the right time. With only two
    adapters it almost certainly isn't — defer with a written
    reason. If yes, scope it tightly.

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
