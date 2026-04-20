# Handoff — Continue the companion build

**Written:** 2026-04-19 night (unattended run)
**Branch state:** `dev`, 8 new commits tonight, **not pushed**, working
tree clean.
**Next session mode:** Don has authorized another broad unattended run
— same rules as this session (build aggressively, no push, no
distribution).

---

## 0. What you need to know in the morning before touching anything

1. **Nothing has been pushed.** `git log origin/dev..dev` will show the
   eight commits below. Review before any push.
2. **The desktop shell compiles but has not been launched.** I never
   ran `pnpm tauri dev` — first Windows launch can surface WebView2 /
   MSVC build tool gaps that are invisible to `cargo check`.
3. **Ollama integration is opt-in.** Default runs use the reflex stub.
4. **Tauri gates G2/G3/G4** in
   `planning/plans/X3_tauri_architecture.md` are still officially
   PENDING. Don's broad-autonomy authorization tonight covered
   scaffolding v0 with a default-deny capability set — don't widen
   capabilities without a coordinator pass.
5. **Nothing was deleted.** Legacy `desktop/` (Python pywebview) and
   `frontend/` (Next.js v1) are still in place and untouched. CLAUDE.md
   §2 additive-by-default rule honoured.

## 1. Commits added this session (newest first)

```
7e78828 feat(apps/desktop): [TAURI_V0A] trust drawer — first audit-surface slice
9577ed5 feat(apps/desktop): [TAURI_V0]  scaffold desktop shell around companion path
511bfcc docs(reports): L2.1, L7.1, L3.1, L4.1 execution reports
3d79c04 feat(apps):            wire L2.1/L7.1/L3.1/L4.1 into L1 CLI demo
4387e93 feat(l4):    [L4.1]    Ollama provider adapter behind feature flag
a74d973 feat(l3):    [L3.1]    session-scoped macro presence state machine
a4546bd feat(l7):    [L7.1]    approval surface for Ask tickets
99c62c0 feat(l2):    [L2.1]    session-scoped conversation memory
```

`git log --oneline -8` in the morning will confirm these.

## 2. What the product does right now

The companion stack, end to end:

```
User text
  → Tauri command (submit_turn)
    → TurnEngine.handle_turn
      → L5 PolicyEngine.evaluate
        ├ Allow → MemoryAwareRouter (loads L2 window → prepends transcript)
        │        → ModelRouterAdapter
        │        → ReflexModelRouter  | OllamaProvider (feature-gated, env-opted)
        │        → RouteOutcome
        ├ Ask   → ticket lands in pending registry
        │        → UI modal (L7.1 approval surface)
        │        → resolve_approval → PolicyEngine.respond_approval
        │        → handle_turn replays with the fresh grant
        └ Deny / NeedsUpgrade / DraftOnly → synthesized result
      → Presence transitions fire on every phase
      → L2 memory append (user + assistant/system)
      → L5 audit row (sealed, hash-chained)
    → UI renders message + refreshes memory + trust drawers
```

Visible product surfaces:

- Header with persona name, **presence dot**, **provider badge**,
  Memory / Trust / New session / About buttons.
- **Persona card** on fresh session (Aurora, tier, output mode).
- **Transcript** with tier·provider footer under assistant messages.
- **Approval modal** with capability / scope / reason / ticket id,
  Approve-once / Decline.
- **Memory drawer** — session transcript ring.
- **Trust drawer** — colour-coded decision log from the L5 audit store.
- **Disclosure banner** — one-time plain-language local-first
  statement.

## 3. What to build next — priority backlog for the next unattended run

Ordered by visible-product payoff per hour. Tackle top-down; de-scope
and continue if one blocks.

### Priority 1 — Smoke-launch the shell and fix what breaks

Half the morning-one value is confirming the shell actually runs end
to end on this machine. Run:

```bash
cd C:/Users/dbhav/Projects/aether/apps/desktop
pnpm install           # if not already
pnpm tauri dev         # launches Rust backend + Vite dev server
```

Expected: window opens, disclosure shows, persona card shows, typing
"hello" echoes through the reflex stub with tier=reflex,
provider=reflex-stub. Typing `delete /tmp/foo` (currently the engine
treats all input as FilesRead with ResourceScope::None — see "known
quirk" below) would NOT currently trigger an Ask because the shell
doesn't parse verbs like the CLI does.

**Fix the first real quirk:** `submit_turn` in `commands.rs`
hard-codes `capability = FilesRead`, `resource = None`. The CLI
parses `read / write / edit / delete / shell / browse <arg>`
prefixes. Port that parser (or something richer) into the shell so
approvals are reachable from the UI. Code to lift:
`apps/l1-cli/src/main.rs::parse_command`.

Commit: `feat(apps/desktop): [TAURI_V0B] verb-prefix parser for demo commands`.

### Priority 2 — L4.1 hardening (unchanged Task C from tonight's prompt)

Tonight I stopped just as I was about to add a mock-HTTP test for the
Ollama chat path. The unfinished sub-tasks, in order of value:

1. **Mock HTTP integration test** for `OllamaProvider::chat` using
   `std::net::TcpListener` on an ephemeral port — no new dev-deps, no
   network. Prove the request shape and response parsing
   round-trip through a real socket.
2. **Role-tagged messages** — the provider currently sends a single
   concatenated prompt (memory + user). Ollama's `/api/chat` accepts a
   proper `messages: [{role, content}, ...]` array. Add a
   `chat_with_messages(&[ChatMessage])` method and have the shell
   layer split the session transcript into role-tagged messages
   before calling. Keep the concat path for back-compat.
3. **Typed provider errors** — replace `L4Error::Provider(String)`
   usage with a richer error enum (`Timeout`, `NotRunning`,
   `ModelNotFound`, `BadResponse`, `Unknown`) so the UI can show
   useful language.
4. **Optional latency/token telemetry** — propagate timing into
   `RouteOutcome` and surface it in the transcript meta-footer.
   Cross-layer change, do last.

Commit split: one per sub-task.

### Priority 3 — Presence ↔ avatar-state bridge scaffold

Still no avatar, but the existing `packages/l3-presence/src/engine.rs`
Wave-4 stub has `BehaviorClass { Idle, Listening, Thinking, Speaking, ...}`
and `BehaviorFrame` types. Add a thin bridge that maps macro
`PresenceState` → `BehaviorClass` deterministically. Wire it into the
shell as a test-only scaffolding so when a real avatar lands there's
nothing structural in the way.

### Priority 4 — Persona policy defaults → engine config

Original Session 5 from the earlier handoff never landed. The
`CompiledPersona.policy_defaults.per_capability_defaults` field
exists and is populated, but `EngineConfig` doesn't consume it — the
engine is hard-coded to `wave3_default`. Thread the persona defaults
into engine config at build time so "Cautious" vs "Bold" stance
actually changes which capabilities go Auto vs Ask.

### Priority 5 — Second persona + picker

Add a "Companion" persona (second archetype, different tone/stance)
and a minimal in-app picker. Requires persona-pack loading from YAML,
which is beyond L6.1's compiler. Narrow first cut: two hard-coded
`PersonaProfile`s, a dropdown in the header.

### Priority 6 — Onboarding wizard slice (2 of the 7 steps)

Don't try to land the full 7-step spec. Land step 1 (welcome +
disclosure — already have the banner) and step 5 (preset picker —
Observer / Assistant / Operator) as a gate on first launch. Store
choice in `tauri-plugin-store`.

### Priority 7 — Durable-memory sketch in L2

Currently L2.1 is in-memory only. Add a feature-gated
`SqliteSessionMemoryStore` using the existing `aether-storage`
substrate + a new `0004_conversation_log.sql` migration. Keep session
as the default; opt-in durability behind a flag. This is the
foundation for "what do you remember about me?" UX.

## 4. Risks / things to review first in the morning

- **Icon is a Pillow-generated placeholder.** Not for distribution.
- **Disclosure copy is my draft.** Quick read-through before any
  demo.
- **The shell commands use my default Aurora profile.** Values in
  `apps/desktop/src-tauri/src/state.rs::default_profile` — Tone Warm,
  Stance Balanced. Trivial to change.
- **Warm-grey accent (`#c9c9d1`).** Deliberate move away from indigo.
  If you want a different neutral (warm amber, deep green, etc.), one
  file: `apps/desktop/tailwind.config.ts`.
- **TrustDrawer shows audit rows in the engine's insertion order.**
  No timestamp sort / filter UI yet.
- **The CLI has drifted from the shell slightly** — same engine
  wiring, but the CLI takes `-- --debug-memory` as a flag while the
  shell has no equivalent. Consider whether that should ever converge.
- **Vite prints a "Browserslist: caniuse-lite is outdated" warning**
  on some systems. Harmless.

## 5. How to run / validate

```bash
# Terminal 1 — Rust engine + Vite dev server combined
cd C:/Users/dbhav/Projects/aether/apps/desktop
pnpm install
pnpm tauri dev

# (Separate) to exercise Ollama path:
ollama serve
ollama pull gemma3        # or any model you have
$env:AETHER_OLLAMA_MODEL = "gemma3"
pnpm tauri dev -- --features ollama-provider

# To confirm nothing else regressed:
cd C:/Users/dbhav/Projects/aether
cargo fmt --all -- --check
cargo check --workspace
cargo test --workspace
python tools/lint-layer-boundaries/check.py
```

All four root checks were green at commit time.

---

## 6. Copy-paste starting prompt for the next unattended session

Paste everything below into a fresh Claude Code session. It is
self-contained — includes the broad-autonomy authorization, the
backlog, and the exact operating rules. Do NOT prepend anything.

````
You are Claude Code, working on Aether.

Repo root: C:/Users/dbhav/Projects/aether/
Branch:    dev (8 new commits from the previous night's run; local
           only, not pushed)

Tonight's mission is a continuation of the previous unattended run
that scaffolded the Tauri desktop shell (TAURI_V0 + TAURI_V0A). Don
will be away from the PC — you are authorized to continue making
aggressive, visible product progress without asking for input.

Read in this exact order before touching anything:

1. `HANDOFF_2026-04-20_CONTINUE_COMPANION_BUILD.md`
2. `TAURI_SHELL_V0_EXECUTION_REPORT_2026-04-19.md`
3. `apps/desktop/README.md`
4. `apps/desktop/src-tauri/src/commands.rs`
5. `apps/desktop/src/App.tsx`
6. The layer-boundary linter: `tools/lint-layer-boundaries/check.py`
7. Git state: `git status` and `git log --oneline -15`

---

### Autonomy authorization

This is a **long autonomous multi-hour build run**. Don has said:

- "Maximum productive build autonomy, zero launch/distribution
  autonomy."
- Build aggressively; don't ask routine questions.
- Make reasonable product / engineering decisions.
- If one task blocks, de-scope and continue to the next highest-value
  task.

You ARE authorized to:
- scaffold and expand the desktop shell,
- add/modify Rust, frontend, Tauri, and app integration code,
- add/modify supporting crates/modules/components,
- improve memory / approval / presence / persona / routing surfaces,
- harden provider integration,
- add tests, reports, docs, handoffs,
- create multiple local commits,
- reorganize or refine implementation details where helpful,
- mark legacy areas as deprecated if useful,
- continue through backlog items autonomously.

You are NOT authorized to:
- push anything,
- create/publish a public release,
- perform final launch/distribution actions,
- touch signing / notarization / release secrets or credentials,
- weaken tests, lint, CI, or boundary rules just to keep moving,
- do destructive cleanup of legacy trees (prefer deprecation markers
  + documentation).

Operational rule:
- Do not stop after the first completed task.
- Keep chaining tasks as long as there is safe, useful work to do.
- If blocked, move to the next valuable slice and document the
  blockage.
- Leave the repo in a reviewable state by morning.

---

### Priority backlog for this run

Work through these in order. Commit cleanly between slices.

**P1 — Smoke-launch and fix the first shell quirk.** Run
`pnpm tauri dev` (install Tauri CLI if necessary; it is a local
dev-dep so `pnpm install` is enough). If the window opens, port the
verb-prefix parser from `apps/l1-cli/src/main.rs::parse_command` into
`apps/desktop/src-tauri/src/commands.rs::submit_turn` so
`write /tmp/foo` reaches the Ask path in the UI. If the window does
NOT open, diagnose and document the environment gap (WebView2, MSVC,
capability permissions), land a small fix where possible, and move
on.

**P2 — L4.1 Ollama hardening.** In this order:
  (a) Mock-HTTP integration test for `OllamaProvider::chat` using
      `std::net::TcpListener` on an ephemeral port (no new dev-deps,
      no real network). Prove request shape + response parsing.
  (b) Role-tagged messages — add
      `chat_with_messages(&[ChatMessage])` and wire the shell layer
      to split history into `system`/`user`/`assistant` tags instead
      of one concatenated prompt. Keep the concat path for back-
      compat.
  (c) Typed provider errors — replace `L4Error::Provider(String)`
      call-sites with richer variants (`Timeout`, `NotRunning`,
      `ModelNotFound`, `BadResponse`).
  (d) Optional latency/token telemetry into `RouteOutcome` and the
      UI meta-footer. Cross-layer; do last.

**P3 — Presence → avatar-state bridge scaffold.** Thin mapping from
`PresenceState` (macro) to the Wave-4 `BehaviorClass` enum in
`packages/l3-presence/src/engine.rs`. Test-only / behind a feature.
Creates a seam for a future real avatar without blocking anything.

**P4 — Persona policy defaults → engine config.** Thread
`CompiledPersona.policy_defaults.per_capability_defaults` into
`EngineConfig` at build time so stance (Cautious / Balanced / Bold)
actually changes which capabilities are Auto vs Ask in the shell.

**P5 — Second persona + picker.** Add one more hard-coded
`PersonaProfile` (different tone/stance) and a minimal dropdown in
the shell header.

**P6 — Onboarding slice (2 of 7 steps).** Welcome+disclosure (already
scaffolded) and preset picker (Observer / Assistant / Operator).
Store choice in `tauri-plugin-store`.

**P7 — Durable-memory sketch.** Feature-gated
`SqliteSessionMemoryStore` using the existing `aether-storage`
substrate + a new `0004_conversation_log.sql` migration. Keep
in-memory as default.

---

### Work cadence

For each completed slice:

1. Implement the slice.
2. Run focused tests first.
3. Run the full check set:
   - `cargo fmt --all -- --check`
   - `cargo check --workspace`
   - `cargo test --workspace`
   - `cd apps/desktop && pnpm typecheck && pnpm build`
   - `cd apps/desktop/src-tauri && cargo check && cargo check --features ollama-provider`
   - `python tools/lint-layer-boundaries/check.py`
4. Fix failures. Don't weaken a check.
5. Write/update a per-slice report at repo root.
6. Commit with a scoped, conventional message ending with
   `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
7. Move to the next slice.

---

### End-of-run deliverables

Before stopping:

1. Clean `git status` (everything committed, nothing dangling).
2. Per-slice execution reports for everything you completed.
3. A new handoff doc: `HANDOFF_2026-04-21_CONTINUE_COMPANION_BUILD.md`
   including:
   - what was completed,
   - commit list,
   - what remains (updated priority backlog),
   - risks to review first,
   - a copy-paste starting prompt for the following session.

Do not ask Don a routine question. Use the planning corpus
(`planning/` and `plans/`), the Wave and Lx_y execution reports, the
handoff docs, and the existing code.

Governing principle: **Maximum productive build autonomy, zero
launch/distribution autonomy.**

Start by reading the four files listed above, confirming git state,
then executing P1.
````

---

That's the full next-session package. Good luck in the morning.
