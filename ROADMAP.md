# Aether — Roadmap

> Early, evolving roadmap for Free Aether — Community Edition. Priorities in
> this document can change between waves; the `WAVE*_EXECUTION_REPORT_*.md`
> files at the repo root are always the authoritative record of what actually
> landed.
>
> **Last updated:** 2026-04-19, after Wave 3.5 (storage substrate).

---

## Ordering principle

The roadmap reflects how the architecture was staged, not marketing priorities:

1. **Architecture first.** `ARCHITECTURE.md` and the ADR log under `docs/adr/`
   are the source of truth.
2. **Scaffolds before logic.** Every layer lands as stub shell + smoke test
   before any first-logic slice.
3. **L5 before everything else.** The policy engine is the non-bypassable gate;
   other engines depend on its contracts being real.
4. **Substrate before integration.** Storage, event-bus, and governance lints
   have to be real before apps can lean on them.
5. **Apps last.** `apps/desktop`, `apps/guest`, and `apps/docs-site` are
   intentionally empty until the engines are credible on their own.

---

## Completed

- **Wave 0 — Monorepo genesis.** Workspace manifests, planning import, root
  governance docs. Report: `WAVE0_ASSIMILATION_REPORT_2026-04-19.md`.
- **Wave 1 — Shared infra + governance.** `packages/event-bus`,
  `packages/types`, `packages/storage` (no driver), `packages/ui-kit`,
  `packages/telemetry`, `packages/media-engine`; `tools/` lint scaffolds.
  Report: `WAVE1_EXECUTION_REPORT_2026-04-19.md`.
- **Wave 2 — L5 scaffold.** `packages/l5-policy` types, traits, IPC surface.
  `packages/l5-policy-ts` hand-written mirror. Report:
  `WAVE2_EXECUTION_REPORT_2026-04-19.md`.
- **Wave 3 — First L5 logic slice.** In-memory ledger + audit store, five-stage
  evaluator, 10 integration tests, audit-before-Allow invariant. Report:
  `WAVE3_EXECUTION_REPORT_2026-04-19.md`.
- **Wave 4 — Engine stub shells.** L1, L2, L3, L4, L6, L7 traits + core enums
  + smoke tests. The seven-layer architecture in `ARCHITECTURE.md` elevated to
  doctrine. Report: `WAVE4_EXECUTION_REPORT_2026-04-19.md`.
- **Wave 3.5 — Storage substrate.** `rusqlite` bundled into
  `packages/storage`, `open_with_migrations()` runs the drafted DDL,
  integration test proves it. L5 persistence still in-memory — this wave
  delivers the substrate only. Report:
  `WAVE3_5_EXECUTION_REPORT_2026-04-19.md`.
- **Final pre-publication hardening + push.** CI rewired onto Rust +
  pnpm + governance jobs, licence metadata normalised, `cargo fmt --all`
  applied, `dev` pushed to `origin/dev`. Reports:
  `FINAL_PUBLICATION_CHECKPOINT_2026-04-19.md`,
  `SESSION_HANDOFF_2026-04-19_END_OF_DAY.md`.
- **First OSS preview tag.** `v0.1.0-oss-preview.0` created locally on
  the pushed HEAD; release notes at
  `RELEASE_NOTES_OSS_PREVIEW_2026-04-19.md`. Tag push deferred to a
  future session.
- **Wave 4.1 — Layer-boundary enforcement.** `tools/lint-layer-boundaries/`
  now runs a real linter over `cargo metadata`; the CI `layer-boundaries`
  job rejects any forbidden `packages/*/Cargo.toml` edge. No current
  violations. Report: `WAVE4_1_EXECUTION_REPORT_2026-04-19.md`.
- **Wave 4.5 — L5 durable persistence (opt-in).** `SqliteGrantLedger`
  + `SqliteAuditStore` implementing the existing `GrantLedger` /
  `AuditStore` traits behind a new `sqlite-backend` cargo feature on
  `aether-l5-policy`; `DurableBackends::open(path)` convenience builder;
  migration `0002_audit_chain.sql` (payload columns, `key_id`,
  `privileged_profile`, `policy_audit_chain_head` singleton).
  `DefaultPolicyEngine` refactored to accept `Arc<dyn GrantLedger>` +
  `Arc<dyn AuditStore>` so either backend plugs in. Default build stays
  in-memory. 5 SQLite integration tests (grant + revoke + audit survival
  across restart, append-only trigger enforcement, engine smoke). Report:
  `WAVE4_5_EXECUTION_REPORT_2026-04-19.md`.

---

## Next — in priority order

### 1. First engine first-logic slice

- Candidate A: **L1 turn FSM** — unlocks the first end-to-end demo path.
- Candidate B: **L4 provider adapter + L5 gate wire-through** — unlocks a real
  remote call going through the policy engine.
- Pick one; produce a `WAVE*_EXECUTION_REPORT_*.md` alongside.

### 2. Community demo slice

- Smallest runnable surface: one `apps/` binary that exercises the policy
  engine, the storage substrate, and one engine slice.
- Intentionally not a full desktop app. Its purpose is to make the
  architecture legible to a contributor in under fifteen minutes.

### 3. Hash-chain + HMAC audit sealing

- Extend `SqliteAuditStore::append` to compute `prev_hash = SHA256(prev_canonical)`
  and seal each row with an HMAC using a per-install key from the OS
  keyring.
- Populate `policy_audit_chain_head` on every append; verify on boot.
- Flip `verify_chain()` from the Wave 4.5 `Ok(())` stub to a real walk of
  the chain.
- Wire `AuditWriteError::MissingKey` handling into the posture transitions
  (`AuditBroken` → deny-all).

### 4. Public-release polish

- Expand docs/ with per-layer deep dives beyond `REPO_TOUR.md`.
- Retire the legacy Python tree once capability parity is verified per X2/X4
  plans.

---

## Further out — not yet scheduled

- L2 memory kernel first-logic slice (embeddings, provenance).
- L3 presence / avatar scheduler first-logic slice.
- L6 persona compiler real pipeline (YAML → compiled artifacts, hot-reload).
- L7 trust UX real flows.
- Tauri shell integration (apps/desktop).
- Guest mode (apps/guest, Cloudflare Worker + Groq path).
- Docs site (apps/docs-site).

These will be slotted into the priority list above once the lower-numbered
items land.

---

## Not on the roadmap

- Chatbot-style UI that bypasses the seven-layer stack.
- General-purpose LLM wrapper features unrelated to the companion
  architecture.
- Hosted / SaaS edition of the Community preview — the project is
  local-first on purpose.
- Feature work inside the legacy v1.0 Python tree beyond what X2 and X4
  explicitly port forward.
