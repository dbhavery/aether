# L7.1 Execution Report — Approval Surface for Ask Tickets

**Date:** 2026-04-19
**Branch:** dev
**Status:** Complete, tests green, boundary lint clean, not pushed.

---

## 1. Ask flow — before vs after

### Before

```text
user: write /tmp/foo
 → handle_turn
   → policy.evaluate → Decision::Ask { ticket }
 ← TurnResult { block: Some(AwaitingApproval), … }
[print] blocked: awaiting user approval (Ask ticket open)
[dead end — the ticket is never resolved; the turn is abandoned]
```

### After

```text
user: write /tmp/foo
 → handle_turn
   → policy.evaluate → Decision::Ask { ticket, audit_id }
 ← TurnResult { block: Some(AwaitingApproval), policy_decision: Ask{…}, … }

[cli approval surface]
  Approval required:
    ticket     : ticket-1
    capability : files.create
    scope      : path: /tmp/foo
    reason     : approval_required
  Approve? [y/N]:

  y   → policy.respond_approval(UserChoice::Allow)
        L5 issues a grant covering this capability+resource+persona
        engine.handle_turn(same request)
          → policy.evaluate → grant hits (covers()) → Decision::Allow
          → router dispatches → RouteOutcome populated
      ← TurnResult { final_state: Completed, route: Some(…), … }
        [approval] approved — resuming turn.

  n   → policy.respond_approval(UserChoice::Deny)
        L5 records deny audit
      ← TurnResult (synthesised) { final_state: PolicyDenied,
                                    policy_decision: Deny{ModeDeny, audit},
                                    block: Some(Denied), … }
        [approval] rejected — turn aborted.
```

In both resolved paths the demo treats the original Ask + resolution as a single logical turn: the memory append at the end of the loop records the final outcome (route response on approve, denial note on reject) rather than the dead-end "awaiting approval" shape.

## 2. Types / APIs added

### 2.1 `packages/l7-trust/src/approval.rs` (new module)

Narrow, synchronous approval surface that coexists with the richer (async/event-driven) `ShellAdapter` stub:

- `enum ApprovalResolution { Approve, Reject }`.
- `trait ApprovalSurface { fn resolve(&self, &ApprovalPrompt) -> Result<ApprovalResolution, L7Error>; }`.
- `CliApprovalSurface` — stdin/stdout impl; tolerant parser for `y / yes / approve / a` (case-insensitive, trimmed). Anything else rejects. Exposes `parse_line` so tests don't have to touch real stdin.
- `FixedApprovalSurface(ApprovalResolution)` — deterministic test double.
- `resolution_to_user_choice(ApprovalResolution) -> UserChoice` — maps to the richer L5 surface (`UserChoice::Allow` / `UserChoice::Deny`).
- `build_approval_response(&ApprovalTicket, ApprovalResolution, MonotonicTimestamp) -> ApprovalResponse` — leaves scope/duration/reauth overrides `None`, matching the L7.1 scope ("ticket-scoped approve once, nothing broader").
- `approval_prompt_from_ticket(ApprovalTicket, Option<StaticReasonId>) -> ApprovalPrompt` — defaults reason to `"approval_required"`.
- `render_approval_block(&ApprovalPrompt) -> String` — deterministic terminal rendering used by the CLI surface and by tests.
- `human_capability(&Capability) -> &'static str` — stable dot-path labels for every variant in the current `Capability` enum (42 variants).
- `human_scope(&ResourceScope) -> String`.

All public symbols re-exported at the crate root.

### 2.2 Demo-side orchestration — `apps/l1-cli/src/approval.rs` (new module)

Owns the "Ask + resolution = one logical turn" orchestration so `main.rs` stays short:

- `struct ApprovalOutcome { result: TurnResult, approved: bool }`.
- `fn handle_ask(&Arc<dyn PolicyEngine>, &TurnEngine, &dyn ApprovalSurface, TurnRequest, TurnResult, MonotonicTimestamp) -> Result<ApprovalOutcome, String>`:
  1. Extracts ticket from the Ask result (errors clearly if fed a non-Ask).
  2. Renders prompt, calls `surface.resolve`.
  3. Calls `policy.respond_approval` with the mapped choice.
  4. On Approve — re-runs `engine.handle_turn(request.clone())`; the freshly issued grant covers it, so the next evaluate lands in `Decision::Allow` and the router dispatches normally.
  5. On Reject — synthesises a `Decision::Deny { reason: ModeDeny, audit_id }` view re-using the original ticket's audit id and turn id, so memory/print see one continuous turn.
- `fn is_ask(&TurnResult) -> bool` — narrow helper.

### 2.3 `apps/l1-cli/src/main.rs` integration

- New `aether-l7-trust` dependency in `Cargo.toml`.
- `build_engine` now returns `(TurnEngine, Arc<dyn PolicyEngine>)` so the main loop can call `respond_approval` without reaching into the engine.
- Main loop: after `handle_turn`, if `is_ask(&first)` invoke `handle_ask(&policy, &engine, &approval_surface, request.clone(), first, MonotonicTimestamp(ts))`; otherwise keep the existing non-Ask path. Memory append + print operate on the final resolved result.
- Visible UX: `[approval] approved — resuming turn.` / `[approval] rejected — turn aborted.` lines bracket the resolution.

## 3. Where the approval loop is integrated

```text
 main loop
    │ handle_turn(req)  → first (may be Ask)
    │
    │ is_ask(first)?
    │   no  → use first
    │   yes → handle_ask(policy, engine, surface, req, first, ts)
    │          │ prompt = approval_prompt_from_ticket(ticket)
    │          │ resolution = surface.resolve(&prompt)
    │          │ policy.respond_approval(build_approval_response(...))
    │          │ approve → engine.handle_turn(req)  ← grant now covers
    │          │ reject  → synthesise Deny result
    │          ▼
    │        final_result
    │
    │ memory_store.append(user_record)
    │ memory_store.append(assistant_record(final_result))
    │ print_turn_result(final_result)
```

Layer hygiene:
- L1 unchanged — still knows nothing about approvals or L7.
- L5 unchanged — `respond_approval` was already there; L7.1 just calls it.
- L7 grew a synchronous resolution surface that is orthogonal to the existing (async/event-based) `ShellAdapter`.
- Only the apps crate (the stitch point) orchestrates.

## 4. Tests and checks

### 4.1 Tests added

**`packages/l7-trust` (7 unit tests):**

- `resolution_maps_to_user_choice`
- `build_response_echoes_ticket_id_and_choice`
- `prompt_from_ticket_copies_fields_and_defaults_reason`
- `prompt_from_ticket_honours_explicit_reason`
- `render_approval_block_contains_all_fields`
- `cli_parse_accepts_affirmative_variants` (7 spellings of yes)
- `cli_parse_rejects_anything_else` (7 non-affirmative inputs)
- `fixed_surface_returns_configured_resolution`

**`apps/l1-cli` (3 integration-style tests):**

- `ask_then_approve_resumes_turn_to_allow_via_grant` — builds a real `DefaultPolicyEngine` on `wave3_default`, sends a `FilesCreate` request (Ask in the preset), approves via `FixedApprovalSurface`, asserts the post-approval result is `Decision::Allow` with a populated route.
- `ask_then_reject_yields_denied_result` — same setup, rejects, asserts the synthesised `Decision::Deny` with `BlockReason::Denied` and no route.
- `handle_ask_rejects_non_ask_results` — feeds a synthetic Allow result in, confirms the helper errors with `"non-Ask"`.

### 4.2 Check results

| Check | Result |
|---|---|
| `cargo fmt --all -- --check` | clean |
| `cargo check --workspace` | clean (pre-existing warnings in `l5-policy/src/decision.rs` and `l1-interaction/src/events.rs` are unchanged) |
| `cargo test --workspace` | all green, 0 FAILED |
| `cargo test -p aether-l1-cli` | **17 / 17 passed** (14 prior + 3 new) |
| `cargo test -p aether-l7-trust` | **9 / 9 passed** (pre-existing smoke + 8 new approval tests) |
| `python tools/lint-layer-boundaries/check.py` | `OK (0 violations)` |

## 5. Limitations and future work

- **Two-outcome UX only.** `ApprovalResolution` is `Approve` / `Reject`. The richer L5 `UserChoice` variants — `AllowScope`, `AllowTask`, `AllowSession`, `DeferToDraft` — are not yet surfaced to the user. Each is one enum variant + one map-arm away from working.
- **Approve-once semantics.** L7.1 maps approve → `UserChoice::Allow` (duration `Once`). A UI that offers "allow for this session" / "allow for this task" is future work.
- **No re-auth.** Critical capabilities (`CostCapAdmin`, `AuditExport`) require a `reauth_token` per L5's `ApprovalResponse`; L7.1 currently leaves it `None`. If the CLI surfaces a Critical Ask, `respond_approval` will take it but the intended re-auth UX is missing.
- **Synthesised Deny result.** `respond_approval` returns only a `ChangeId`, not a `Decision`. On reject we reconstruct a plausible `Decision::Deny { ModeDeny, audit_id }` locally, reusing the ticket's audit id. This is faithful-looking but not the exact decision the policy engine recorded — acceptable for the demo's display path, not for anything that relies on a round-tripped decision.
- **Stdin surface is linear.** `CliApprovalSurface::resolve` blocks on a single line read. No timeout (L5's `deadline_hint` is ignored), no cancel, no retry.
- **No audit surfacing to user.** The user sees the resolution but not the audit id or the underlying reason code. A future trust-centre surface should show both.
- **Trait-object-only surface.** `ApprovalSurface` is synchronous. A streaming / event-driven variant (for the future desktop shell) will need a separate trait or an async wrapper.
- **Single shared session/persona.** Inherits the L2.1 single-session CLI constraint.

## 6. Recommended next session

**L3.1 — presence state machine.**

Rationale: the three biggest "not a companion yet" gaps at session start were (a) conversational amnesia, (b) Ask dead-end, and (c) no visible "state of Aether" signal for the user. L2.1 closed (a), L7.1 closes (b). The remaining one — is the system listening, thinking, speaking, waiting on approval, quiet, in reflex mode, or errored? — blocks nearly every UX decision downstream. A minimal presence state machine (enum + transitions driven off the existing `TurnState` trace, plus `ApprovalOutcome::approved`) gives the imminent avatar/UI its first real signal to bind to. It also pays off even before the desktop shell: a debug line in the CLI like `[presence: listening → thinking → awaiting_approval → ready]` would make the current REPL feel substantially more alive.

Caveat: if running the CLI with this new approval path surfaces a worse issue (e.g. the memory transcript now drifts because we append denial notes every turn and the context fills with policy ceremony), fix that first before adding a third surface.

---

**Commits (local, unpushed):** none yet on top of the existing L2.1 work. Suggested split — one commit for the L7 `approval` module + tests, one commit for the demo-side `approval` module + main.rs wiring + tests + README.
