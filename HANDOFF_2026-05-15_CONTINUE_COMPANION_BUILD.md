# Handoff — Continue the companion build (2026-05-15)

**Written:** 2026-05-14.
**Branch state:** `dev` at `b2b7963` with **10 unpushed commits**
ahead of `origin/dev`.
**Push status:** **Not authorized for this session.**
**Next session mode:** Presence V1 step 2 (controller + OS-idle
probe + event emission) — the session with the user holding
explicit priority on this track. Alternatives: Memory V2 step 2
(memory.json + policy surface), live-backend eval harness.

---

## 0. Morning status

1. `dev` is `b2b7963`, 10 commits ahead of `origin/dev`.
2. Working tree clean.
3. Full check matrix run 2026-05-14, all green:
   - `cargo fmt --all -- --check` — clean.
   - `cargo check --workspace` — clean (pre-existing warnings only).
   - `cargo test --workspace` — **137 / 137**.
   - `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp` — **96 / 96** (was 86; +10 whisper inference).
   - `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp,speech-whispercpp` — **154 / 154**.
   - `python tools/lint-layer-boundaries/check.py` — 0 violations.
   - `python tools/lint-vision-doc/check.py` — 51 anchors.
   - `python tools/lint-voice-doc/check.py` — 48 anchors.
   - `python tools/evals/__main__.py --dry-run` — **6 / 6 pass**.
   - `apps/desktop && pnpm typecheck && pnpm build && pnpm test` — **145 / 145**.

## 1. What landed in this run

| SHA | Subject |
| --- | --- |
| `a84e6ea` | feat(l4-router): real whisper.cpp HTTP inference |
| `f762032` | feat(l5-policy): Memory V2 step 1 — additive coarse capabilities |
| `b06d734` | feat(quality): v1 quality-eval architecture doc + minimal harness scaffold |
| `b2b7963` | chore(fmt + l7-trust): apply rustfmt + fill exhaustive match for Memory V2 capabilities |

Reports:

- [WHISPERCPP_INFERENCE_EXECUTION_REPORT_2026-05-14.md](file:///C:/Users/dbhav/Projects/aether/WHISPERCPP_INFERENCE_EXECUTION_REPORT_2026-05-14.md)
- [MEMORY_V2_STEP1_CAPABILITIES_EXECUTION_REPORT_2026-05-14.md](file:///C:/Users/dbhav/Projects/aether/MEMORY_V2_STEP1_CAPABILITIES_EXECUTION_REPORT_2026-05-14.md)
- [QUALITY_EVAL_V1_SCAFFOLD_EXECUTION_REPORT_2026-05-14.md](file:///C:/Users/dbhav/Projects/aether/QUALITY_EVAL_V1_SCAFFOLD_EXECUTION_REPORT_2026-05-14.md)

## 2. Track status

### Track V — Vision V1: **DONE** (maintenance only)

No changes this round.

### Track VOICE — Voice V1: **COMPLETE** + real inference wired 🎉

Steps 1–6 shipped in prior sessions. This session replaced the
`WhisperCppSpeechProvider::transcribe` scaffold with a real
multipart/form-data POST to whisper-server's `/inference`
endpoint. Voice V1 is now a fully live subsystem end-to-end: the
user presses record, audio is captured and encoded, transcribed
by a real local model, and the transcript becomes a normal user
turn through the engine.

The no-silent-fallback contract is preserved — transport / HTTP /
parse errors all surface as visible errors.

### Track PRESENCE — Presence V1: **Step 1 COMPLETE**

- Step 0 — Architecture doc ✅
- Step 1 — presence.json + Settings toggles ✅
- **Step 2 — Controller + OS-idle probe + event emission:
  pending, and it is the recommended next session focus.**
- Step 3 — Trust drawer presence-history rendering: pending.
- Step 4 — Presence rot guard: pending.

### Track MEMORY — Memory V2: **Step 1 COMPLETE**

- Step 0 — Architecture doc ✅
- **Step 1 — Additive L5 capabilities (`MemoryWrite`,
  `MemoryRead`, `MemoryForget`, `MemoryEdit`): done this run.**
- Step 2 — `memory.json` policy surface + Settings section +
  Tauri policy read/write: pending.
- Steps 3–7 (plumbing, Memory tab, retention sweep, embeddings,
  rot guard): pending.

### Track QUALITY — Quality/Eval v1: **Scaffold COMPLETE**

- **Architecture doc + minimal harness + one seed scenario per
  domain + one adversarial probe: done this run.**
- Live-backend response capture: pending.
- Session-log replay importer: pending.
- `tools/lint-quality-doc/` rot guard: pending.
- `pnpm eval` wrapper / regression CLI: pending.

## 3. What to build next

The user's session priorities put Presence V1 step 2 at the top
of Priority A. That is the recommended default. Alternatives:

### Option A — Presence V1 step 2 (recommended)

- Extend the L3 presence model with the user-attention axis
  (Active / Idle / Away) from design §2, complementing the
  assistant-posture axis (Quiet / Listening / Thinking / …)
  that L3 already owns.
- Add a `PresenceController` for user-attention (name to avoid
  collision: `UserAttentionController` or new module).
- OS idle probe behind a small trait so tests can inject a
  mock. Windows first via `GetLastInputInfo`
  (`winapi::um::winuser::GetLastInputInfo`) — no new dep needed
  since `tauri` pulls a winapi-class crate transitively; if
  that isn't clean, the `user-idle` crate is acceptable if
  pure-Rust.
- Poll loop at `poll_hz` from `presence.json` (a tokio task or
  a dedicated thread — match the existing presence patterns
  in the shell).
- Emit `PresenceEvent` on transitions only (not on every poll);
  record `presence_state_changed` telemetry per design §6.
- `presence_status` Tauri command returning a richer snapshot
  than the pre-existing interaction `presence_current` (decide
  alias vs rename vs new command; doc says new command).
- Settings: replace the read-only threshold line from step 1
  with editable number inputs; preserve the `enabled` and
  `history_in_trust_drawer` toggles.
- Tests: state transitions, disabled-path no-op, threshold
  boundary behavior, mock idle-probe injection, config reload
  after `set_presence_config`.

### Option B — Memory V2 step 2

- `memory.json` config file (additive-default-safe, mirror of
  `presence_config.rs`'s shape).
- Per-domain policy map — which Memory V2 capabilities are Auto /
  Ask / Deny per domain.
- `get_memory_policy` / `set_memory_policy` Tauri commands.
- Settings section for memory policy.
- Test: round-trip, malformed fallback, unknown-field tolerance,
  unknown-field drop on rewrite (the contract this repo uses
  everywhere).

### Option C — Live-backend eval harness

- Extend `tools/evals/__main__.py` with a `--backend` arg that
  invokes the current Ollama / vision / speech providers and
  captures real `actual` responses.
- Emit an `actual-captured` markdown alongside the baseline.
- First adversarial scenario per domain (chat_realism already
  has one; add the other five).

## 4. Current Voice V1 + Quality + Memory V2 surface

- **whisper-server endpoint**: `<base_url>/inference` via
  `POST multipart/form-data` with a `file` part and optional
  `language` part. Envs `AETHER_WHISPERCPP_SPEECH_*` unchanged.
- **Inline base64 decoder**: pure-Rust, whitespace-tolerant,
  strict length check, 4 tests. Lives in the adapter; not
  exported.
- **L5 Memory V2 variants**: `MemoryWrite`, `MemoryForget`,
  `MemoryEdit`. `MemoryRead` pre-existed. Risk Low for Read,
  Medium for the rest. Not wired into `wave3_default` yet —
  lands in step 2.
- **`tools/evals/`**: CLI runner, JSONL scenarios, expectation
  DSL (forbids / requires / length / tone). Seed scenarios +
  baseline markdown committed.
- **`docs/QUALITY-EVAL-V1-ARCHITECTURE.md`**: design-only until
  `tools/lint-quality-doc/` rot guard ships.

## 5. Decisions for Don's review

Carried over + new:

1–21. (Carried from 2026-05-14 handoff.) No changes this run.
22. **Inline base64 decoder over `base64` crate.** See the
    whisper inference report. One call site + 4 tests beats a
    new dependency.
23. **Two layers of Memory capabilities coexist.** The older
    session/durable/extracted-pref split is retained; V2 adds a
    coarser surface. Step 2 decides which layer the Ask flow
    keys on for user-sensitive domains.
24. **Quality doc stays design-only until rot guard lands.**
    Mirrors the pattern vision and voice followed. The
    `Current as of` flip happens when `tools/lint-quality-doc/`
    is live.
25. **Adversarial probes live in `tools/evals/adversarial/`,
    not `tools/evals/scenarios/`.** Separate invocations keep
    the baseline 6/6-pass while still proving the detector
    works.

## 6. Risks / things to review first

- **10 unpushed commits.** Push remains NOT authorized.
- **whisper.cpp inference is untested against a live server
  in CI.** The 11 new L4 tests exercise validation, multipart
  body construction, and transport-error surfacing — the
  round-trip against a real `whisper-server` has not been run
  in this session (no local server running). Running one
  manually is the fastest way to validate end-to-end; a
  feature-gated live test is a later slice.
- **Memory V2 capabilities land with no preset default.** Any
  turn that requests `MemoryWrite`/`Edit`/`Forget` today will
  return `NeedsUpgrade`. Intentional — step 2 wires the policy.
- **Quality eval runner is dry-run-only.** Live backend wiring
  is explicit future work; the current tests prove the DSL and
  the detector, not real-world quality.
- **Flaky persona test still flaky.** No cleanup this session;
  still unrelated to these changes.
- **Voice rot guard's 48 anchors** rely on the VoiceBadge /
  ActiveVoiceRoute / VoicePanel / speechProviders / voiceTurns
  surface. Any UI refactor must update the manifest in the same
  PR.

## 7. Recommended next prompt (copy-paste)

```md
You are Claude Code, continuing work on Aether.

Repo root:
C:/Users/dbhav/Projects/aether/

Branch:
dev

Current state (treat repo as source of truth if anything differs):
- `dev` is at `b2b7963`, 10 commits ahead of `origin/dev`.
- Working tree clean.
- Push is NOT pre-authorized.
- Vision V1 complete and rot-guarded.
- Voice V1 complete through step 6, with real whisper.cpp
  inference now wired. Push-to-talk is live end-to-end.
- Presence V1 step 1 complete: presence.json + Settings toggles.
- Memory V2 step 1 complete: L5 capabilities landed (additive
  `MemoryWrite`, `MemoryForget`, `MemoryEdit` + pre-existing
  `MemoryRead`). No preset defaults yet.
- Quality-Eval v1 scaffold complete: docs/QUALITY-EVAL-V1-
  ARCHITECTURE.md + tools/evals/ with six seed scenarios and
  one adversarial probe. Dry-run only.

Mandatory first steps:
1. Read `HANDOFF_2026-05-15_CONTINUE_COMPANION_BUILD.md` end to end.
2. `git status` and `git log --oneline -30`.
3. Read the three 2026-05-14 execution reports referenced in the
   handoff.
4. Read `docs/PRESENCE-V1-ARCHITECTURE.md` end to end.

Session focus: Presence V1 step 2 — controller + OS-idle probe
+ event emission + threshold editing UI.

Scope:
- Extend L3 presence with the user-attention axis (Active / Idle
  / Away). Add a module or type for the new axis; do not
  refactor the existing assistant-posture controller.
- OS idle probe behind a small trait so tests can inject a mock.
  Windows first via `GetLastInputInfo` (no new dep if tauri's
  transitive winapi crate suffices; otherwise `user-idle` is an
  acceptable pure-Rust alternative — flag the choice in the
  execution report).
- Poll loop at `poll_hz` from presence.json. Match the shell's
  existing presence patterns (tokio task vs thread).
- Emit `PresenceEvent` on transition only; record the
  `presence_state_changed` telemetry kind per design §6.
- Add `presence_status` Tauri command returning the new
  snapshot. Do NOT break the pre-existing `presence_current`
  command that returns the interaction-presence snapshot
  (assistant posture).
- Replace the read-only threshold line in Settings with editable
  number inputs. Preserve the `enabled` + `history_in_trust_drawer`
  toggles.
- Tests: state transitions, disabled-path no-op, threshold edge
  cases, mock idle-probe injection, config reload after
  set_presence_config.

Out of scope:
- Trust drawer presence-history rendering (step 3).
- Presence rot guard (step 4).
- Memory V2 step 2 unless step 2 is done AND tests are green
  AND there is real session time remaining.

Hard constraints (still in force):
- No push.
- No release / signing.
- No L5 capability gate for presence (design §4).
- No continuous capture / wake words / VAD.
- No new heavy dependencies; prefer platform-native probes.
- Do not destabilise the vision or voice rot guards.
- Do not weaken the eval harness — it runs as part of the check
  matrix now.

Process:
1. L3 module or type for user-attention axis + state machine.
2. Idle-probe trait + Windows impl.
3. Poll loop + event emission.
4. Tauri command + TS wrappers + UI threshold controls.
5. Tests.
6. Full check matrix (fmt, workspace, l4-router, shell, lints,
   evals, pnpm typecheck/build/test).
7. Commits in scoped slices.
8. Execution report + fresh handoff.
```

---

(end of handoff)
