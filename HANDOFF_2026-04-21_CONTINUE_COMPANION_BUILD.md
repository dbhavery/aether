# Handoff — Continue the companion build (2026-04-21)

**Written:** 2026-04-20 (day autonomous run, Don away)
**Branch state:** `dev`, 16 new commits across two runs, **not pushed**,
working tree clean.
**Next session mode:** Don has authorized further broad unattended
runs — same rules as prior nights (build aggressively, no push, no
distribution).

---

## 0. What you need to know in the morning before touching anything

1. **Nothing has been pushed.** `git log origin/dev..dev` will show
   the sixteen local commits — eight from the 2026-04-19 night run
   and seven feat commits + 1 doc commit from the 2026-04-20 day run.
2. **The desktop shell launches.** This run smoke-tested `pnpm tauri
   dev` successfully — `aether-desktop.exe` started, WebView2 child
   processes appeared, no environment gaps on this machine. Once.
   Not again after that. If a subsequent slice breaks the launch,
   the fault is in that slice's code, not the environment.
3. **Ollama integration is opt-in and now role-tagged.** If
   `AETHER_OLLAMA_MODEL` is set and the daemon is reachable, the
   shell sends `/api/chat` a proper role-tagged message array using
   `OllamaProvider::chat_with_messages` via
   `memory_router::RoleTaggedOllamaRouter`. Reflex stub fallback is
   unchanged.
4. **Two personas exist now.** Aurora (default, Warm / Balanced) and
   Sable (Neutral / Bold / Terse / Dry). Picker in the header when
   >1 persona; switch clears session and rebuilds the engine.
5. **Legacy `desktop/` (Python) and `frontend/` (Next.js v1) are
   still untouched.** CLAUDE.md §2 additive-by-default rule honoured.
6. **Boot-override personas via `AETHER_PERSONA=<id>`.** Values:
   `aurora`, `sable`. Invalid → falls back to the first catalog
   entry (currently aurora).

## 1. Commits added in this day run (newest first)

```
bb3c8b1 feat(apps/desktop): [TAURI_V0C] second persona + header picker
405fbe4 feat(l5,l6,apps/desktop): [L4] thread persona policy defaults through EngineConfig overlay
9be5a3a feat(l3): [L3.x] presence->BehaviorClass bridge (unwired seam)
22d0935 feat(l4,apps/desktop): [L4.1] role-tagged /api/chat messages for Ollama
416bb93 feat(l4): [L4.1] typed provider error variants for UI-actionable messages
89f1bc8 feat(l4): [L4.1] mock-HTTP integration test for OllamaProvider::chat
cb43c17 feat(apps/desktop): [TAURI_V0B] verb-prefix parser for demo commands
```

Plus the 8 overnight commits from 2026-04-19 it's chained onto.

## 2. Per-slice execution reports in this run

- [TAURI_V0B_VERB_PARSER_EXECUTION_REPORT_2026-04-20.md](file:///C:/Users/dbhav/Projects/aether/TAURI_V0B_VERB_PARSER_EXECUTION_REPORT_2026-04-20.md)
- [L4_1_OLLAMA_MOCK_HTTP_EXECUTION_REPORT_2026-04-20.md](file:///C:/Users/dbhav/Projects/aether/L4_1_OLLAMA_MOCK_HTTP_EXECUTION_REPORT_2026-04-20.md)
- [L4_1_TYPED_PROVIDER_ERRORS_EXECUTION_REPORT_2026-04-20.md](file:///C:/Users/dbhav/Projects/aether/L4_1_TYPED_PROVIDER_ERRORS_EXECUTION_REPORT_2026-04-20.md)
- [L4_1_ROLE_TAGGED_MESSAGES_EXECUTION_REPORT_2026-04-20.md](file:///C:/Users/dbhav/Projects/aether/L4_1_ROLE_TAGGED_MESSAGES_EXECUTION_REPORT_2026-04-20.md)
- [L3_PRESENCE_AVATAR_BRIDGE_EXECUTION_REPORT_2026-04-20.md](file:///C:/Users/dbhav/Projects/aether/L3_PRESENCE_AVATAR_BRIDGE_EXECUTION_REPORT_2026-04-20.md)
- [L4_L5_L6_PERSONA_OVERLAY_EXECUTION_REPORT_2026-04-20.md](file:///C:/Users/dbhav/Projects/aether/L4_L5_L6_PERSONA_OVERLAY_EXECUTION_REPORT_2026-04-20.md)
- [TAURI_V0C_SECOND_PERSONA_PICKER_EXECUTION_REPORT_2026-04-20.md](file:///C:/Users/dbhav/Projects/aether/TAURI_V0C_SECOND_PERSONA_PICKER_EXECUTION_REPORT_2026-04-20.md)

## 3. What the product does now

Everything from the 2026-04-19 handoff, plus:

- Typing `write /tmp/x`, `edit /tmp/x`, `delete /tmp/x`, `shell ls`,
  `browse https://...` in the shell reaches the matching L5 decision
  path instead of being squashed into `FilesRead + None`. Ask,
  Deny, NeedsUpgrade are all reachable from the UI.
- Ollama runs use role-tagged `/api/chat` messages (system prompt +
  history + user utterance) rather than a concatenated transcript.
- Provider failures now come out as typed `L4Error` variants
  (`ProviderTimeout`, `ProviderNotRunning`, `ProviderModelNotFound`,
  `ProviderBadResponse`, `ProviderUnknown`) so a future UI pass can
  show actionable copy.
- Persona stance (Cautious / Balanced / Bold) visibly changes which
  capabilities are Auto vs Ask vs Deny via
  `EngineConfig::with_persona_overlay`.
- Aurora + Sable both selectable from the header picker or
  `AETHER_PERSONA` env var.
- L3 exposes `behavior_for_presence(PresenceState) -> BehaviorClass`
  so a future avatar has a canonical mapping to adopt on day one.

## 4. What to build next — priority backlog for the next unattended run

Ordered by visible-product payoff. Tackle top-down; de-scope if one
blocks.

### Priority 1 — P2d: latency/token telemetry

`RouteOutcome` carries `tier` + `provider` today but no timing. Thread
per-turn wall-clock ms (start of `handle_turn` → end) and, for the
Ollama path, token count extracted from the `/api/chat` response
(`eval_count`, `prompt_eval_count`) into `RouteOutcome`. Surface in
the transcript meta-footer ("tier · provider · 1.4s · 42 tok").
Cross-layer: L1 (`RouteOutcome` shape), L4 (Ollama parse), shell
(UI render). Do last within this priority-1 slot.

### Priority 2 — P6: Onboarding slice (welcome + preset picker)

Two of the 7 steps in planning/06_onboarding_spec.md:

- Step 1 — welcome + disclosure (already scaffolded via
  `Disclosure.tsx` + "About" button).
- Step 5 — autonomy preset picker (Observer / Assistant / Operator).
  Store choice in `tauri-plugin-store`.

This also gives the shell a place to gate first-launch behaviour
rather than showing the persona card on every fresh session.

### Priority 3 — P7: Durable-memory sketch

Feature-gated `SqliteSessionMemoryStore` via `aether-storage` +
`0004_conversation_log.sql` migration. In-memory stays default. This
is the foundation for "what do you remember about me?" UX.

### Priority 4 — UI language for typed provider errors

P2c shipped the typed variants in L4; the shell still propagates
engine errors as raw Tauri command failures. Add a mapping layer in
`commands.rs` that turns `L4Error::ProviderNotRunning` into
"Ollama isn't running. Start it with `ollama serve`." etc., surfaced
as a transcript system message (not a Tauri error).

### Priority 5 — Third persona ("Ember" / Cautious)

Aurora + Sable cover Balanced and Bold. Ember would cover Cautious
— `BrowserOpen` as Deny, strict posture. Tiny add inside
`state.rs::default_catalog()`.

### Priority 6 — Persona persistence

`switch_persona` today doesn't persist across app restarts. Store the
last-picked id in `tauri-plugin-store` and honour it at boot in
preference to `AETHER_PERSONA`. Small, high-UX-value.

### Priority 7 — E2E test for the Tauri command surface

The 9/12 tauri tests are unit-level (verb parser, role-tagged
message builder). The full command flow — submit_turn → Ask →
resolve_approval — is only typechecked. Add one integration test
that drives a real `AppState` through an Ask + Approve + Deny cycle.

## 5. Risks / things to review first in the morning

- **TrustDrawer clears on persona switch.** Deliberate — different
  personas are different trust surfaces — but Don may want a visible
  note in the UI ("switched to Sable · audit reset").
- **Persona dropdown uses native `<select>`.** Styled minimally; not
  a polished custom combobox. Fine for dev, will want upgrading
  before any external demo.
- **ReflexModelRouter is unchanged under Sable.** The stub echoes
  identically; only the *policy decisions* differ. Running with
  Ollama is where Sable's tonal differences surface.
- **`MemoryAwareRouter::build_prompt` is now dead code** for the
  Ollama path but alive for the reflex path. Don't remove yet — if
  we ship a second real provider without role support, the concat
  path is the fallback.
- **Persona id must match the catalog.** `AETHER_PERSONA=foo` falls
  back silently to the first catalog entry. Log this at boot?

## 6. How to run / validate

```bash
# From repo root
export PATH="$HOME/.cargo/bin:$PATH"   # if cargo not on PATH
cargo fmt --all -- --check
cargo check --workspace
cargo test --workspace
python tools/lint-layer-boundaries/check.py

cd apps/desktop/src-tauri
cargo check
cargo check --features ollama-provider
cargo test
cargo test --features ollama-provider

cd ../..
cd apps/desktop
pnpm typecheck
pnpm build
pnpm tauri dev                 # launches the real shell

# To exercise Sable:
AETHER_PERSONA=sable pnpm tauri dev

# To exercise Ollama:
ollama serve
ollama pull gemma3             # or any model you have
export AETHER_OLLAMA_MODEL=gemma3
pnpm tauri dev -- --features ollama-provider
```

---

## 7. Copy-paste starting prompt for the next unattended session

```
You are Claude Code, working on Aether.

Repo root: C:/Users/dbhav/Projects/aether/
Branch:    dev (16 new commits local only, not pushed)

Tonight's mission continues two prior unattended runs that (a)
scaffolded the Tauri desktop shell and (b) landed seven feat slices
on top. Don is away — broad autonomous build authorization, zero
launch/distribution authorization.

Read in this exact order before touching anything:

1. HANDOFF_2026-04-21_CONTINUE_COMPANION_BUILD.md
2. HANDOFF_2026-04-20_CONTINUE_COMPANION_BUILD.md (prior context)
3. TAURI_SHELL_V0_EXECUTION_REPORT_2026-04-19.md
4. apps/desktop/README.md
5. tools/lint-layer-boundaries/check.py
6. git status + git log --oneline -20

---

### Autonomy authorization

This is a long autonomous multi-hour build run. Don has said:

- Maximum productive build autonomy, zero launch/distribution autonomy.
- Build aggressively; don't ask routine questions.
- Make reasonable product / engineering decisions.
- If one task blocks, de-scope and continue to the next valuable
  slice.

You ARE authorized to:
- expand the desktop shell, engine layers, and supporting crates,
- add tests, reports, docs, handoffs,
- create multiple local commits,
- refactor implementation details where helpful,
- mark legacy areas as deprecated if useful,
- continue through backlog items autonomously.

You are NOT authorized to:
- push anything,
- publish a release,
- touch signing / notarization / release secrets,
- weaken tests, lint, CI, or boundary rules,
- do destructive cleanup of legacy trees.

Do not stop after the first completed task. Keep chaining slices.
Leave the repo in a reviewable state by morning.

---

### Priority backlog for this run

Work through these in order. Commit cleanly between slices.

P1 — Latency/token telemetry into RouteOutcome + UI meta-footer.
      Cross-layer: L1 shape, L4 Ollama parse (eval_count,
      prompt_eval_count), shell UI render.

P2 — Onboarding slice steps 1 + 5 (welcome + preset picker). Store
      choice in tauri-plugin-store.

P3 — Durable memory: SqliteSessionMemoryStore behind a feature flag,
      0004_conversation_log.sql migration. In-memory stays default.

P4 — Shell-side language for typed provider errors. Map
      L4Error::ProviderNotRunning / Timeout / ModelNotFound /
      BadResponse / Unknown to user-facing transcript system
      messages instead of Tauri command errors.

P5 — Third persona "Ember" (Cautious). Small add to
      state.rs::default_catalog().

P6 — Persist the active persona id in tauri-plugin-store so the
      next launch honours the last choice (AETHER_PERSONA stays as
      override).

P7 — E2E test for the Tauri command surface — drive a real AppState
      through submit_turn → Ask → resolve_approval cycle.

---

### Work cadence (unchanged)

Per completed slice:
1. Implement.
2. Run focused tests first.
3. Run full check set:
   - cargo fmt --all -- --check
   - cargo check --workspace
   - cargo test --workspace
   - cd apps/desktop && pnpm typecheck && pnpm build
   - cd apps/desktop/src-tauri && cargo check [ + --features ollama-provider]
   - python tools/lint-layer-boundaries/check.py
4. Don't weaken a check to keep moving.
5. Write a per-slice execution report at repo root.
6. Commit with a scoped, conventional message ending with
   Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
7. Next slice.

---

### End-of-run deliverables

Before stopping:
1. Clean git status.
2. Per-slice reports.
3. HANDOFF_2026-04-22_CONTINUE_COMPANION_BUILD.md with completed
   work, commit list, updated backlog, risks, and a copy-paste
   starting prompt.

Governing principle: Maximum productive build autonomy, zero
launch/distribution autonomy.

Start by reading the files listed above, confirming git state, then
executing P1.
```

---

Good luck in the morning.
