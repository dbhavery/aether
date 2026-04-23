# Handoff — Memory V2 step 3 + Presence V1 step 4 + NFR skeleton (2026-05-17)

**Written:** 2026-05-17.
**Branch state:** `dev` ahead of `origin/dev`. Push **not authorized**.
**Next session mode:** decide between Memory V2 step 4 (Trust
drawer Memory tab), Memory V2 step 5 (retention sweep), or
advancing the spec package (forward-looking requirement IDs,
OSS/Pro pointer views, or AC-style doc). Quality-Eval replay
importer also available.

This session shipped three work items that had been queued on
prior handoffs: Memory V2 step 3 (in three scoped slices),
Presence V1 step 4 (rot guard + doc flip), and the NFR skeleton
(audit gap #2). It also caught a stale-prompt drift (the
mid-session prompt asked for Memory V2 step 3 work that had
already landed five commits earlier) and followed Decision #32 by
pushing back rather than silently re-executing.

---

## 0. Session-end status

| Check | Result |
| --- | --- |
| `git status` | clean |
| Commits this session | 5 |
| Commits ahead of `origin/dev` | **24** (was 19 at session start) |
| `cargo fmt --all -- --check` | clean |
| `cargo check --workspace` | clean (pre-existing warnings only) |
| `cargo test --workspace` | **151 / 151** (was 149; +2 net at L5) |
| `cargo test -p aether-l3-presence` | 22 / 22 |
| `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp -- --test-threads=1` | 96 / 96 |
| `apps/desktop/src-tauri cargo test --features …` | **186 / 186** (was 175; +11 memory_service) |
| `python tools/lint-layer-boundaries/check.py` | 0 violations |
| `python tools/lint-vision-doc/check.py` | OK (51 anchors) |
| `python tools/lint-voice-doc/check.py` | OK (48 anchors) |
| `python tools/lint-presence-doc/check.py` | **OK (39 anchors, NEW)** |
| `python tools/evals/__main__.py --dry-run` | 6 / 6 pass |
| `apps/desktop && pnpm typecheck` | clean |
| `apps/desktop && pnpm build` | 227 kB / 65 kB gzip (unchanged) |
| `apps/desktop && pnpm test` | **169 / 169** (was 145; +24 memoryTurns) |

Known flaky tests (unchanged, pre-existing): the two env-seam
flakes flagged in the 2026-05-16 handoff. Neither introduced
nor addressed this session.

---

## 1. What landed this session

### 1.1 Memory V2 step 3 — per-domain write/read plumbing (three slices)

Three commits against the scope of `HANDOFF_2026-05-16_GLOSSARY.md`'s
"next recommended prompt".

**Slice 1 — L5 preset registration (`939d953`).**
`packages/l5-policy/src/engine.rs::wave3_default` now registers
`MemoryWrite` / `MemoryRead` / `MemoryEdit` / `MemoryForget` with
modes and risk classes mirroring `default_risk_for(...)` — Read is
`(Auto, Low)`, Write/Edit/Forget are `(Auto, Medium)`. Observer
overlay adjusted to whitelist `MemoryRead` alongside `FilesRead`
so read-only posture still allows grounding reads. Operator
overlay keeps the baseline (no escalation of memory mutations).
The `memory_v2_capabilities_have_no_preset_default_yet` test was
flipped to the inverse and two new overlay-behaviour tests added.
L5 suite: 11 → 18 (+7).

**Slice 2 — Shell memory service (`b43a9b0`).**
New module `apps/desktop/src-tauri/src/memory_service.rs` (~570
lines with tests). Methods extend `AppState`:

- `evaluate_memory_gate(domain) -> MemoryGate` — parallel to
  `evaluate_media_permission` / `evaluate_mic_permission`.
- `memory_write(domain, session_id, content, role) -> Result<MemoryWriteOutcome>`
  — the primary write API. Auto → `policy.evaluate(MemoryWrite)` →
  append + `memory_written`. Ask → return `RequiresApproval`
  without persisting. Deny → emit `memory_write_denied` + return
  `Denied`.
- `memory_write_after_approval(…)` — post-modal path; emits
  `memory_write_asked` + `memory_written`.
- `memory_forget(domain, session_id)` — gated `clear_session` with
  `memory_forgotten` telemetry and `Capability::MemoryForget`
  audit.
- `memory_edit(domain, memory_id)` — gate + audit + telemetry
  wired; per-item storage mutation arrives with the Memory tab
  (step 4).
- `memory_read_audit_tick(domain)` — sampled-read hook per
  design §4. Per-domain `AtomicU64` counter; every 100th tick
  emits `memory_retrieval` + `MemoryRead` audit.

State: `TelemetryEntry` gains two additive optional fields
(`memory_domain`, `memory_id`), `AppState.memory_read_counters`
pre-populated at `build()`, `AppState::memory_read_counter(domain)`
accessor. Ten existing `TelemetryEntry` literals (commands.rs,
state.rs) updated to set the new fields to `None`.

Legacy `state.memory.append` call sites not retrofitted — those
remain trusted-internal writes. Step 3 only adds the gated path
future UI will consume.

Shell suite: 175 → 186 (+11 memory_service tests).

**Slice 3 — TS types + parity test (`a02a851`).**
`apps/desktop/src/lib/memoryTurns.ts` exposes `MEMORY_TURN_KINDS`
and `isMemoryTurn`. Parity test (24 cases) pins the set size so
silent server-side drift fails CI. `api.ts::TelemetryEntry`
gains matching optional `memory_domain` / `memory_id` fields.
Front-end suite: 145 → 169 (+24).

#### Design crack surfaced and deferred

The L2 kernel (`packages/l2-memory/src/kernel.rs`) defines a
different `MemoryDomain` enum (`Personal / Work / Health /
Finance / Creative / System`) than the shell's
`memory_config::MemoryDomain` (`Session / Durable / Facts /
Projects / Preferences / Artifacts`). The L2 kernel stub has
zero consumers today, so step 3 does not reconcile them — shell
gating plus the design-doc-aligned shell enum is sufficient for
the user-visible behaviour step 3 promises.

Reconciliation will be forced when the first real L2 consumer
lands (probably with Memory V2 step 5 retention sweep or step 6
embeddings). Options at that point:
1. Replace the L2 kernel enum with the design-doc one; migrate
   the `MemoryItem` struct.
2. Keep L2's current enum for deep/durable structured memory
   while the shell's enum stays the user-facing policy axis,
   with an explicit mapping.
3. Retire the L2 stub entirely and have the shell talk to the
   `SessionMemoryStore` + a new domain-typed durable store
   without the Wave-4-stub kernel trait in between.

No decision needed this session. Flagging so it is not forgotten.

### 1.2 Presence V1 step 4 — rot guard + doc flip (`37f00fa`)

`docs/PRESENCE-V1-ARCHITECTURE.md` reconciled with reality and
flipped to `**Status:** Current as of 2026-05-17`. The prior
"design-only" doc described three axes (attention / posture /
session lifecycle) and three telemetry kinds; actual V1
implements two axes and one kind. Session lifecycle + the two
unused telemetry kinds are now labelled **Future / V2** in
§§0, 2, 5, 9.

Key section reconciliations:
- §1 end-to-end flow redrawn around the actual code paths
  (`idle_probe.rs::WindowsIdleProbe` → `UserAttentionController`
  → `run_presence_loop` → `push_presence_history` +
  `presence:attention`).
- §2 documents both controllers' actual types: `PresenceController`
  / `PresenceSnapshot` / `PresenceState` (posture) alongside
  `UserAttentionController` / `AttentionSnapshot` /
  `AttentionThresholds` / `AttentionEvent` (attention), plus the
  shell-side `PresenceHistoryEntry` ring.
- §5 reduced to the single implemented kind
  (`presence_state_changed`) with explicit Future / V2 labels on
  the session kinds.
- §6 UI surfaces marked Implemented / Future / V2 explicitly so
  the header `PresenceIndicator` polish is not confused for
  current behaviour.
- §8 adds two previously-implicit invariants — transition-only
  emission and `deny(unsafe_code)` at the L3 crate level — and
  restates the rot-guard-vs-AC split per glossary §6.
- §10 aligned to the four canonical handoff steps.

`tools/lint-presence-doc/check.py` mirrors the Voice lint
exactly: same manifest shape, same `_check_status_line`, same
`--json` mode, same exit codes, same `AETHER_REPO_ROOT`
override. 39 anchors across 10 files:

- `main.rs::run_presence_loop` + `PRESENCE_POLL_MS`,
- `idle_probe.rs`: `trait IdleProbe`, `WindowsIdleProbe`,
  `UnsupportedIdleProbe`,
- `attention.rs`: `enum UserAttention`, `struct AttentionThresholds`,
  `struct AttentionSnapshot`, `struct AttentionEvent`,
  `struct UserAttentionController`,
- `controller.rs`: `enum PresenceState`, `struct PresenceSnapshot`,
  `trait PresenceController`, `InMemoryPresenceController`,
  `TRANSITION_LOG_CAP`,
- `l3-presence/src/lib.rs` + the `deny(unsafe_code)` string,
- `state.rs`: `struct PresenceHistoryEntry`, `push_presence_history`,
  `presence_history_recent`, `PRESENCE_HISTORY_CAPACITY`,
- `presence_config.rs`: filename `presence.json`,
  `DEFAULT_IDLE_AFTER_S`, `DEFAULT_AWAY_AFTER_S`,
- `state.rs`: `attach_presence_config_file`, `set_presence_config`,
- telemetry kind `presence_state_changed`, event-bus channel
  `presence:attention`,
- `commands.rs`: `fn presence_current`, `fn presence_status`,
  `fn presence_recent_history`,
- UI files: `SettingsDrawer.tsx`, `TrustDrawer.tsx`.

Run first-try green: `presence-doc rot-guard: OK (39 anchors
across 10 files)`.

`tools/lint-presence-doc/README.md` mirrors the voice README
and restates the update protocol (anchor manifest + doc date
bump + rot-guard-vs-AC split).

### 1.3 NFR skeleton (`86798ee`)

`docs/NFR.md` — audit gap #2 closed. 11 sections, structure +
stubs per the skeleton-scope guidance. Load-bearing decisions
encoded in the skeleton itself:

- **Router tier ≠ performance tier** (orthogonal axes, locked
  against future conflation).
- **Latency has three scales** (interaction / model / UI)
  that must not be collapsed.
- **Security NFRs are one-way** — latency is never a reason to
  weaken audit, consent, or privacy invariants. §6 lists the
  specific bright lines from Voice V1 "no silent fallback",
  Memory V2 user-sensitive-default-Ask, L5 sync audit, no
  raw-media persistence.
- **Tiering is a lens, not a category** — OSS Preview / Pro /
  Private cannot introduce new NFR categories, only relax or
  tighten targets within them.
- **Numbers deferred on purpose.** Seven named open decisions
  in §10 gate concrete numbers on baseline measurements,
  Quality-Eval scenarios, or design locks.
- **Rot-guard-vs-AC split restated** — NFR behavioural checks
  live in tests / evals, not in this doc.

No rot guard yet. The doc has too few stable anchors worth
protecting; glossary §9 remains the tie-breaker if a term here
drifts. A rot guard can land alongside the first numerical
commitment.

---

## 2. Commits (this session)

| SHA | Subject |
| --- | --- |
| `939d953` | feat(l5-policy): register Memory V2 coarse caps in wave3_default — Memory V2 step 3 (slice 1) |
| `b43a9b0` | feat(apps/desktop): memory_service with per-domain gate + audit + telemetry — Memory V2 step 3 (slice 2) |
| `a02a851` | feat(apps/desktop/src/lib): memory telemetry kinds + TS parity test — Memory V2 step 3 (slice 3) |
| `37f00fa` | feat(presence): rot guard + flip Presence V1 doc to current — Presence V1 step 4 |
| `86798ee` | docs: add NFR skeleton — closes audit gap #2 |

---

## 3. Track status snapshot

- **Vision V1** — DONE, rot-guarded. Maintenance only.
- **Voice V1** — DONE (steps 1–6 + real whisper.cpp). Rot-guarded.
- **Presence V1**:
  - Step 1 (presence.json + Settings toggles) ✅
  - Step 2 (controller + OS-idle probe + events + threshold
    editor) ✅
  - Step 3 (Trust drawer presence-history rendering) ✅
  - **Step 4 (rot guard + doc flip) ✅ this session**
  - **Presence V1 closed subsystem.**
- **Memory V2**:
  - Step 0 (architecture) ✅
  - Step 1 (L5 additive capabilities) ✅
  - Step 2 (`memory.json` + policy surface + Settings
    section) ✅
  - **Step 3 (per-domain write/read plumbing) ✅ this session**
  - Step 4 (Trust drawer Memory tab) — pending
  - Step 5 (retention sweep) — pending
  - Step 6 (embeddings, opt-in) — pending
  - Step 7 (memory rot guard) — pending
- **Quality-Eval**:
  - v1 scaffold ✅
  - v1.1 (adversarial probes + live Ollama hook) ✅
  - Replay importer, rot guard, regression harness — pending
- **Spec package (audit-gap work)**:
  - Glossary (gap #1) ✅
  - **NFR skeleton (gap #2) ✅ this session**
  - Forward-looking requirement IDs (gap #3) — pending
  - OSS / Pro / Cross-system views (gap #4) — pending
  - Light RTM view from rot-guard manifests (gap #5) — pending
  - AC house style doc (gap #6) — pending

---

## 4. Risks / things to review first next session

1. **Unpushed commits remain unpushed.** 24 ahead of `origin/dev`.
   Push still not authorized.
2. **L2 / shell MemoryDomain enum mismatch.** Deferred by step 3;
   will surface as a forced choice when the first real L2
   consumer lands (likely Memory V2 step 5 or 6). Three options
   outlined in §1.1 above.
3. **Memory V2 step 3 adds no new Tauri commands.** The new
   `AppState::memory_write` / `memory_forget` / `memory_edit`
   methods have no UI surface today (by design — Memory tab is
   step 4). They are covered by unit tests; Tauri-level
   integration testing waits for step 4.
4. **Presence rot guard is not wired into CI.** Same status as
   voice/vision rot guards — they are run on demand. If the
   project lands a pre-commit or CI hook that runs the lint
   suite, add Presence to it alongside the others.
5. **NFR skeleton has no rot guard.** Intentional (see §1.3).
   When the first numeric commitment lands, consider a rot
   guard that pins the acceptance-criteria / measurement
   cross-links.
6. **Two known flaky tests remain unaddressed.** Cross-cutting
   cleanup out of scope for every track so far.

---

## 5. Decisions log (new this session)

- **35. Memory V2 writes audit via `policy.evaluate`, not a
  separate `AuditStore::append` call.** Consistency with
  Media/Mic patterns; keeps the L5 sync-audit-before-allow
  contract intact without shell-side duplication of the audit
  row shape.
- **36. L5 preset carries Memory V2 caps at `Auto`; shell
  `MemoryConfig::risk_for(domain)` is the user-facing Ask
  gate.** Parallels Decision #29 (tri-state media). L5 audits
  every attempt; the shell pauses for approval on
  user-sensitive domains before routing through L5.
- **37. L2 kernel `MemoryDomain` vs shell `MemoryDomain`
  mismatch is deferred, not solved.** Three options documented
  in §1.1; forced choice when the first L2 consumer lands.
- **38. Presence V1 is a two-axis subsystem in V1.** Session
  lifecycle axis is reserved space; additive V2 work can add it
  without reshaping existing consumers.
- **39. NFR skeleton has no rot guard yet.** Too few stable
  anchors; glossary remains the tie-breaker. Add a rot guard
  alongside the first numeric commitment.
- **40. Router tier and performance tier are orthogonal.**
  Locked in `docs/NFR.md` §4.1 against future conflation.
- **41. Security NFRs are one-way.** Latency is never a reason
  to weaken audit, consent, or privacy invariants
  (`docs/NFR.md` §6).

Carried: 1–34 from prior handoffs.

---

## 6. Remaining backlog (priority-ordered)

1. **Memory V2 step 4** — Trust drawer Memory tab. First UI
   surface to consume the gated write/forget paths.
2. **Memory V2 step 5** — retention sweep (boot + low-rate
   background tick). Emits `memory_forgotten` on eviction.
   Likely forces the L2 / shell `MemoryDomain` reconciliation.
3. **Quality-Eval v1.2** — session-log replay importer.
4. **Memory V2 step 6** — embeddings (opt-in, local-only).
5. **Memory V2 step 7** — memory rot guard.
6. **Forward-looking requirement IDs (audit gap #3).** NFR
   skeleton is now in place; this is the next spec move.
7. **OSS / Pro / Cross-system assembled views (audit gap #4).**
8. **Light RTM view from rot-guard manifests (audit gap #5).**
9. **`docs/AC-STYLE.md` (audit gap #6).**
10. **Real macOS / Linux idle probes for Presence.**
11. **Presence session-lifecycle axis (V2).**
12. **Cross-cutting test-seam cleanup** to kill the two flakes.

---

## 7. Observations worth preserving

1. **Stale-prompt pattern held up.** This session's incoming
   prompt (for Memory V2 step 3) was stale — step 3 had already
   landed in three commits before the prompt arrived. Decision
   #32 worked as designed: the agent pushed back rather than
   silently re-executing, and only the genuinely-pending work
   (Presence V1 step 4, NFR skeleton) proceeded. Worth continuing
   to include the repo-beats-prompt rule in every prompt.
2. **L3 sub-layer watch is active.** The glossary `§3` note
   lands in this session's presence doc rewrite: L3 hosts two
   orthogonal axes (assistant posture + user attention) as
   sibling types. A third axis (session lifecycle) is held open
   in §2 with shape parity; when it lands, that's the moment to
   revisit whether L3 needs an internal sub-layer partition.
3. **Memory V2 step 3 produced no new Tauri commands.** This is
   unusual for a step but correct — the API surface exists as
   `AppState` methods the Memory tab (step 4) will expose via
   commands. Unit tests carry the contract for now.
4. **NFR skeleton is intentionally number-free.** Resist the
   temptation to drop "example" numbers even as placeholders.
   They get referenced, copy-pasted, and ossify.

---

## 8. Next recommended prompt (copy-paste)

```md
You are Claude Code, continuing work on Aether.

Repo root:
C:/Users/dbhav/Projects/aether/

Branch:
dev

Execution vocabulary (do NOT invent new phase systems)
- Waves 1–4 for coarse architectural phasing.
- <Subsystem> V<N> step <N> for day-to-day execution.
- L1–L7 for dependency/moat layers (not time phases).

Current subsystem status (treat repo + latest handoff as source
of truth if anything differs):
- Vision V1, Voice V1, Presence V1: closed subsystems.
- Memory V2 steps 1, 2, 3 complete.
  - Step 4 (Trust drawer Memory tab) is NEXT.
  - Step 5 (retention sweep) and later pending.
- Quality-Eval v1.1 complete; replay importer pending.
- Spec package: glossary (gap #1) and NFR skeleton (gap #2) in.
  - Forward-looking requirement IDs (gap #3) is next spec move.

Anti-drift rule (critical)
- If this prompt's status is contradicted by git log, docs, or
  the latest handoff: STOP, verify, refuse to redo completed
  work, and update the handoff instead of silently complying.
  (Decision #32.)

Mandatory first steps
1. `git status` and `git log --oneline -30`. Verify ahead count.
2. Read `HANDOFF_2026-05-17_MEMORY_STEP3_PRESENCE_STEP4_NFR.md`
   end to end.
3. Read `docs/MEMORY-V2-ARCHITECTURE.md` §§3, 4, 6 (Memory tab
   is the headline V2 surface per §6).
4. Skim:
   - `apps/desktop/src-tauri/src/memory_service.rs` — the
     backend surface step 4 will expose.
   - `apps/desktop/src/components/TrustDrawer.tsx` — the UI
     host the Memory tab will land in.
   - `apps/desktop/src/lib/memoryTurns.ts` — TS allow-list.

Session focus: **Memory V2 step 4 — Trust drawer Memory tab.**

Scope:
- Add a Memory tab inside TrustDrawer with per-domain lanes
  (Session / Durable / Facts / Projects / Preferences /
  Artifacts).
- Per-item rows: timestamp · domain · privacy class · source ·
  content preview.
- Actions: forget item, forget-all-in-domain, edit fact.
- Read path via a new Tauri command `memory_list(domain)` that
  surfaces what the session store holds; wire the existing
  `AppState::memory_forget` and `memory_edit` methods through
  fresh Tauri commands (`memory_forget`, `memory_edit`).
- Approval surface: the existing Ask-modal pattern used for
  media/mic must handle the Memory V2 Ask flow too —
  `memory_write_after_approval` is the post-modal entry point.
- Tests: unit tests for the new commands; component tests for
  the Memory tab rendering + forget/edit flows.

Optional if step 4 lands cleanly with time to spare:
- Draft forward-looking requirement ID scheme (gap #3) — a
  short design doc keyed to glossary §11, one concrete ID per
  existing architecture doc to validate the scheme shape.

Out of scope:
- Retention sweep (step 5).
- Embeddings (step 6).
- Memory rot guard (step 7).
- Reconciling the L2 kernel vs shell `MemoryDomain` enum — that
  forcing function lands with step 5.

Hard constraints (still in force):
- No push. No release / signing.
- No `AuditRecordEvent` shape change.
- User-sensitive domains default Ask — do not flip.
- No new heavy dependencies.
- Do not destabilise vision / voice / presence rot guards.
- Dry-run evals must still be 6/6 pass.
- Do not touch the two known flaky tests
  (`yaml_persona_pack_merges_into_catalog`,
  `from_env_uses_defaults_when_vars_unset`).
- Rot guards and acceptance criteria remain conceptually
  separate (per `docs/GLOSSARY.md` §6). Do not collapse.

Process
1. Implement the `memory_list`, `memory_forget`, `memory_edit`
   Tauri commands on top of the existing `AppState` methods.
2. Build the Memory tab in `TrustDrawer.tsx` (or a new
   `MemoryTab.tsx` co-located with it).
3. Wire the approval modal for Ask-domain forgets / edits
   alongside the existing media/mic modal.
4. TS types mirroring the new commands.
5. Tests (Rust + Vitest + component).
6. Full check matrix (fmt, workspace, l4-router
   --test-threads=1, shell, lints, evals, pnpm
   typecheck/build/test).
7. Commit in scoped slices.
8. Execution report + fresh handoff.

Stay strictly on Memory V2 step 4. If tempted to do step 5
(sweep) or step 6 (embeddings), stop and write the next
handoff instead.
```

---

(end of handoff)
