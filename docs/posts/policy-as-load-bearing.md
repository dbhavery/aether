# Policy as load-bearing structure

*A note on why Aether puts a non-bypassable authorization gate underneath every AI action, and what that costs.*

---

The first serious bug I ever shipped to production was a one-line config change that revoked a feature flag nobody knew was still wired to billing. I didn't cause it. A teammate did. But it went through code review — mine — and we all agreed the blast radius was fine, because the system had "approvals" in three places and it would be caught upstream.

It was not caught upstream. The three places were all reachable around. One of them was commented out. One of them existed only in tests. The third was real, but the code path that hit production had acquired a fast-mode flag six months earlier and was now skipping it on purpose.

Three approvals. Zero enforcement. The kind of story every mature engineer has.

I've been thinking about that story again while building Aether, because Aether has an unusual architectural commitment: **every action that touches the world first clears a policy gate.** No exceptions. No admin mode. No fast path. There is exactly one place where authorization happens, and nothing in the system can reach around it.

This post is about why that's load-bearing, what it looks like in practice, and what it costs.

---

## The shape of most AI-assistant architectures

If you read the architecture diagrams for most "AI agent" frameworks, you'll see something like:

```
user → LLM → tool → effect
```

The LLM picks a tool. The tool runs. Maybe there's a guardrail in the LLM prompt. Maybe there's a human-in-the-loop step at the top. Maybe the tool's own code decides to do nothing. Maybe the framework offers a `before_tool_call` hook.

The common shape is: **the language model is trusted to dispatch, and permission is a runtime concern that various layers agree to opt into.**

That works fine for a demo. It breaks as soon as you care about:

- A user who has been burned once and wants to know exactly which tool made a mess.
- A regulatory posture where "oops the prompt was jailbroken" is not a valid post-mortem line.
- A system that you want to still work, conservatively, when half of it is broken.
- A multi-year relationship with the assistant, where today's grant of "yes you can read my files" is not the same as tomorrow's.

The shape you want is different. It has one gate. Everything routes through the gate. If the gate is broken, the system refuses. If the gate says no, there is no second opinion.

---

## What the gate actually is

In Aether, the gate is a crate called `aether-l5-policy`. It exports exactly one trait that callers depend on:

```rust
pub trait PolicyEngine: Send + Sync {
    fn evaluate(&self, req: ActionRequest) -> Result<Decision, PolicyEngineError>;
    // …
}
```

Every other engine — turn orchestration, memory, router, persona, trust UX — holds an `Arc<dyn PolicyEngine>` and must present a `Decision::Allow` before any side effect runs. The layer-boundary linter runs in CI and refuses any sibling-to-sibling import that would let one engine reach around the gate. Rust doesn't enforce architecture, but CI can.

A decision is a typed value, not a boolean:

```rust
pub enum Decision {
    Allow        { grant_ref, audit_id },
    Ask          { ticket, audit_id },
    DraftOnly    { source, audit_id, reason },
    Deny         { reason, audit_id },
    NeedsUpgrade { capability_path, audit_id, suggested_preset },
}
```

Five states cover the space. `Ask` means a human must approve before the call proceeds. `DraftOnly` means produce the draft but do not commit side effects. `NeedsUpgrade` means the capability exists at a higher preset the user hasn't enabled — useful for Aether's tiered approval model, where "read files" and "delete files" live in different postures.

Every decision carries an `audit_id`. The row is written synchronously, *before* the decision returns. If the audit write fails, the decision becomes `Deny { reason: AuditWriteFailed }`. A broken audit log cannot silently authorize anything. That's the deny-by-default posture, and it's the part most systems don't commit to.

---

## Five stages, eight triggers

Inside `evaluate`, an action request walks five stages:

1. **Pre-gates.** Degraded modes deny everything. Hardcoded blocks reject at the door.
2. **Feature.** Is this capability in the active preset? If not, `NeedsUpgrade`.
3. **Action/resource.** Does an existing grant cover `(capability, resource, persona)`? If yes, reuse.
4. **Mode.** The capability's approval mode — Auto, Ask, Deny, DraftOnly — decides what happens when no grant covers.
5. **Duration.** Grants get Once, TaskScoped, Session, or Persistent-with-TTL.

Grants are what keep the system usable. Once you say "yes, read files in `/tmp`", Aether won't ask again on the same session. But grants aren't forever. Eight things trigger a re-evaluation:

```
CapabilityDiffers     — the request wants a different capability
ResourceOutsidePattern— the request targets a different scope
PersonaSwapped        — the active persona changed
RemoteEscalationUncovered — a local grant cannot cover a remote-tier call
ProvenanceElevated    — tainted context entered the prompt
CostThresholdHit      — BYOK cost cap fired
GrantOrEmergencyRevoked — a grant was revoked mid-turn
TtlExpired            — grant aged out
```

Those triggers are not a loose guideline. They're enumerated. Each produces a re-evaluation. Each has a test.

The tenth time you ask Aether to read something, it will feel immediate — because the grant covers it. The first time it wants to escalate to a remote model, you will be asked — because the grant didn't cover that.

---

## The audit chain

`policy_audit_log` is append-only by SQL trigger. The triggers reject `UPDATE` and `DELETE` unconditionally. That catches the naive attacker, which is not an interesting one.

The interesting attacker opens the SQLite file with another tool. So every row also stores `prev_hash`, `event_hash`, and `record_hmac`:

- `event_hash = SHA256(prev_hash || canonical_payload)` — links this row to the previous one.
- `record_hmac = HMAC-SHA256(key, event_hash)` — signs the link.

A singleton row tracks the current chain tip. `verify_chain` walks the log, recomputes every hash and HMAC, and compares the computed tip to the stored one. Edit a payload, and the hash for that row no longer matches. Delete a row out-of-band, and the next row's `prev_hash` no longer lines up. Roll the chain tip back, and the tip comparison fails.

None of this is new. It's the boring, 1990s-era tamper-evident-log pattern you'd find in any auditor-grade system. The point is not novelty. The point is that it sits underneath everything Aether does, so you cannot rewrite history after the fact without leaving a visible break in the chain.

The key storage is currently preview-grade. A 32-byte file sits next to the DB, generated on first run from `OsRng`. You can override it with an environment variable. An OS-keyring integration is a later wave, and so is asymmetric checkpoint signatures that a third party could verify. Those are real gaps, and they're named as gaps in the docs.

---

## What it costs

Architecture has a price. This one's is:

- **Every action is slower by one synchronous policy evaluate and one synchronous audit write.** Sub-millisecond on in-memory backends. Storage-bound when sealed audit is on. Not free.
- **Grants accumulate.** A long session with a "Bold" persona generates many session-scoped grants. They clear on revoke, TTL, or persona swap, but the steady-state ledger is larger than a "just call the tool" design.
- **A broken audit log takes the system down.** Deny-by-default is correct, but it is also unforgiving. Operations needs to treat `verify_chain` failure as a paging event, not a warning.
- **Every new capability is a schema change.** Capabilities are typed enums, not strings. Adding one means editing an enum, adding preset defaults, writing tests, and — if it's side-effectful — a hardcoded block entry. Deliberate friction.

None of those are bugs. They're the shape of a system that takes authorization seriously.

---

## Why now

Three things made me commit to this design:

1. **Local-first models are good enough for most of what I actually want from an assistant.** That means the "remote LLM call" is now an *escalation*, not a default, and the system has to be built to tell the difference.

2. **The consumer AI market is about to meet its first wave of serious audit requirements.** Not because any one regulator is coming. Because a hundred small incidents will force the shape. Anyone building for the next decade should start from the shape, not retrofit it.

3. **I wanted something I could still use in ten years.** A companion is a long-lived relationship. The permissions you granted in year one are not the permissions you want in year five. The audit log is what makes that renegotiation honest.

---

## Where the code is

Aether is MIT-licensed and lives at [github.com/dbhavery/aether](https://github.com/dbhavery/aether). The current tag is `v0.1.0-oss-preview.0`, which ships the seven-layer workspace, the first real logic in L5 (evaluator, grants, audit, the sealed chain), stub shells for the other six engines, and an L1 turn FSM that walks a full turn through L5 and into a router adapter. There's a tiny CLI in `apps/l1-cli/` that demonstrates the whole path.

If you want the serious document, read `ARCHITECTURE.md`. If you want the doctrine, read `planning/00_VISION_AND_GUARDRAILS.md`. If you want to run it:

```bash
git clone https://github.com/dbhavery/aether.git
cd aether
cargo run -p aether-l1-cli
```

Type `read /tmp/x`. Type `shell ls`. Type `delete /tmp/y`. Three different decisions, three different audit trails, all visible.

---

*The project is a solo build, preview-grade, MIT. Issues and contributor PRs are welcome. The layer-boundary linter is not negotiable.*
