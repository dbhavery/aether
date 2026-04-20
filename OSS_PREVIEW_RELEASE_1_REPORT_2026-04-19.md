# OSS Preview 0 — Release Report

**Date:** 2026-04-19
**Tag:** `v0.1.0-oss-preview.0` (commit `e27cb0c`)
**Release URL:** https://github.com/dbhavery/aether/releases/tag/v0.1.0-oss-preview.0
**Branch pushed:** `dev` (now at `3ba3ce0`)

---

## 1. What was pushed

- `git push origin dev` — advanced `origin/dev` from `e27cb0c` to `3ba3ce0` (9 commits, spanning Wave 4.1, Wave 4.5, Wave 4.6, L1.1, community demo slice, L6.1, L6.2).
- `git push origin v0.1.0-oss-preview.0` — first public preview tag, pointing at `e27cb0c` as originally placed.
- GitHub Release created as **prerelease** with body from `RELEASE_NOTES_OSS_PREVIEW_2026-04-19.md`.

The tag intentionally sits at the "clean preview" commit — before Waves 4.1/4.5/4.6 landed on dev. Dev carries the newer work; the preview tag snapshots a reviewable foundation.

## 2. What's in the release

Per `RELEASE_NOTES_OSS_PREVIEW_2026-04-19.md`:

- Planning corpus (doctrine, 17 numbered specs, per-layer system designs, interface packs, SQLite schema pack, test matrix, locked control-plane decisions).
- Cargo workspace with 11 members + pnpm workspace with 3 TS packages.
- Governance tooling scaffolds (`tools/lint-*`, `tools/ts-bindings-gen`).
- L5 first-logic slice — 5-stage evaluator, typed decisions, in-memory ledger + audit, 18 tests.
- Engine stub shells for L1 / L2 / L3 / L4 / L6 / L7.
- Storage substrate (`rusqlite` bundled, `0001_init.sql` migration runner, append-only triggers).
- OSS launch pack (README, LICENSE/MIT, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, SUPPORT, ROADMAP, REPO_TOUR, issue/PR templates).
- CI workflow (rust / typescript / governance / legacy-python).
- All tests green at tag time.

## 3. What landed AFTER the preview tag (on `dev`)

Not part of the tagged release; already merged into `dev` and pushed to origin:

- **Wave 4.1** — layer-boundary linter activated + CI job blocking.
- **Wave 4.5** — `SqliteGrantLedger` + `SqliteAuditStore` behind `sqlite-backend` feature; `DurableBackends::open`.
- **L1.1** — first turn FSM slice (`TurnEngine`, `TurnRequest`/`TurnResult`, L1-owned `TurnRouter` trait).
- **Community demo** — `apps/l1-cli/` bridges L1+L4+L6 via adapter.
- **Wave 4.6** — audit hash-chain + HMAC sealing (`0003_audit_seal.sql`, `audit_seal` module, `verify_chain` walking).
- **L6.1** — `DefaultPersonaCompiler` + `PersonaProfile` (deterministic compilation).
- **L6.2** — persona wired into the L1 CLI demo (routing tier + system prompt + output verbosity from compiled persona).

Readers who want the newer surface should check out `dev`; the tag is the stable review point.

## 4. README / docs fixes

Quick sanity pass:

- All wave/L-report links in README resolve (`WAVE1…WAVE4_6`, `L1_1`, `L6_1`, `L6_2` all exist).
- `cargo run -p aether-l1-cli` command is live and matches the demo crate name.
- Wave 4.1 / 4.5 / 4.6 sections already describe the durable + sealed audit path.
- Tamper-evident audit log section (README §5) matches the shipped Wave 4.6 implementation.

No README edits required.

## 5. Known limitations / public-facing TODOs

Carried forward from the release notes plus things noticed during this push:

- **Windows-username paths in wave reports.** `file:///C:/Users/dbhav/...` appears throughout the historical wave reports; cosmetic cleanup candidate.
- **clippy gate is advisory.** CI runs `cargo clippy` with `continue-on-error: true` because of pre-existing `missing_docs` warnings on Wave 4 stubs (`packages/l1-interaction/src/events.rs` lines 46 / 62, and a similar `unused_imports` on `l5-policy/src/decision.rs`). Tightening is a <30-line follow-up PR.
- **Release body references the tag's state, not dev's.** Anyone reading the GitHub Release body needs to know `dev` has already moved past the tag. Adding a short "on the dev branch now" banner as a release asset or a top-of-release note is a candidate improvement.
- **No signed tag / release.** `v0.1.0-oss-preview.0` is lightweight-signed by the author key only; no GPG / sigstore yet.
- **Secret scanning.** Best-effort internal sweep only; a `gitleaks` / `trufflehog` run before announcing broadly is still recommended.
- **No binaries attached.** The release is source-only; there is no runnable app to bundle. The L1 CLI demo is cargo-only by design.
- **Documentation links inside release notes resolve only on master / dev.** GitHub renders them relative to the tag's tree, which is correct — no fix needed, but it's worth confirming during next release.

## 6. Remaining release hygiene (optional follow-ups)

- Enable GitHub Discussions (referenced from `SUPPORT.md` but not configured).
- Pin CI badge(s) to README.
- Add `CHANGELOG.md` so future tags (v0.1.0-oss-preview.1 etc.) link back to a per-version history.
- Configure GitHub's "security" tab policy pulling from `SECURITY.md`.
- Consider moving the release notes file into `docs/releases/` so newer previews don't visually collide in the repo root.

---

**Status:** OSS Preview 0 release is live and reachable. No engine code changes were made in this session. Working tree clean.
