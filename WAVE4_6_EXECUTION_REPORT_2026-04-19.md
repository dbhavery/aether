# Wave 4.6 — L5 Audit Hash-Chain + HMAC Sealing (Execution Report)

**Date:** 2026-04-19
**Branch:** `dev`
**Scope:** L5 durable audit path only. In-memory default unchanged.

---

## 1. Schema changes

New migration: `packages/storage/migrations/0003_audit_seal.sql`.

- Adds `event_hash BLOB` column (nullable) to `policy_audit_log`.
- Adds `idx_policy_audit_event_hash` index for fast lookup.
- Records itself in `schema_migrations`.

`MIGRATIONS` slice extended in `packages/storage/src/migrations.rs` (new constant `MIGRATION_0003_AUDIT_SEAL`). Migration head check updated to expect `"0003_audit_seal"`.

Columns `prev_hash`, `record_hmac`, `key_id`, and the singleton `policy_audit_chain_head` already existed from 0001/0002 — 0003 only fills the remaining gap (the per-row event hash). Pre-Wave-4.6 rows (if any) remain readable because `event_hash` is nullable; `verify_chain` skips them explicitly.

## 2. How hashes and HMACs are computed and stored

Implementation lives in `packages/l5-policy/src/audit_seal.rs` (feature-gated).

- **Canonical payload.** `CanonicalAuditPayload<'a>` is a non-owning view of `AuditRecordEvent` that excludes the three self-referential fields (`prev_hash`, `record_hmac`, `key_id`). Serialized with `serde_json::to_vec` — stable because both writer and verifier go through the same typed view.
- **Event hash.** `compute_event_hash(prev_hash, canonical_payload) = SHA256(prev_hash || canonical_payload)` using `sha2::Sha256`.
- **HMAC.** `compute_event_hmac(key, event_hash) = HMAC-SHA256(key, event_hash)` using `hmac::Hmac<Sha256>`.
- **Genesis.** First row uses a fixed 32-byte constant `GENESIS_PREV_HASH` (the ASCII bytes `"Aether audit genesis v1"` padded with a `0x01` sentinel) as `prev_hash`.
- **Constant-time compare.** `ct_eq` performs the final equality check so recomputed hashes/HMACs are not compared with short-circuiting `==`.

On append (`SqliteAuditStore::append`):

1. Read `policy_audit_chain_head.head_hash` (or genesis if null).
2. Clone the caller's row; overwrite `prev_hash` and `key_id` — callers can't forge sealing fields.
3. Canonicalize, compute `event_hash`, compute `record_hmac`.
4. INSERT the row with `prev_hash`, `record_hmac`, `event_hash`, and serialized payload.
5. UPDATE `policy_audit_chain_head` to point at the new `event_hash`.

## 3. Chain maintenance and verification

`SqliteAuditStore::verify_chain()` walks `policy_audit_log ORDER BY rowid ASC`:

1. Read each row's `payload`, `prev_hash`, `record_hmac`, `event_hash`.
2. For each sealed row:
   - Assert `stored.prev_hash == expected_prev` (where `expected_prev` is `GENESIS_PREV_HASH` for the first sealed row, and the previous row's stored `event_hash` afterwards). Mismatch → `ChainBreak { row_id }`.
   - Parse `payload` as `AuditRecordEvent`, recompute canonical bytes, recompute `event_hash`, assert it equals the stored one. Mismatch → `ChainBreak { row_id }`.
   - Recompute `HMAC-SHA256(key, event_hash)`, assert it equals stored `record_hmac`. Mismatch → `HmacMismatch { row_id }`.
3. After the walk: if any sealed row was seen, assert the final computed hash equals `policy_audit_chain_head.head_hash`. Mismatch → `ChainBreak { row_id: u64::MAX }` (tip-rollback marker).
4. Rows with `event_hash IS NULL` are skipped (legacy pre-4.6 rows); a future `0004_audit_seal_backfill` migration can close this window.

## 4. Configuration & invocation

Sealing is active whenever `sqlite-backend` is on. No separate toggle — the point of durable audit is to be tamper-evident.

Key sourcing, in priority:

1. `AETHER_AUDIT_HMAC_KEY_HEX` env var (64-char hex → 32 bytes).
2. File at `<db_path>.hmac.key` (auto-created on first run with `rand::rngs::OsRng`).

Callers:

```rust
// Auto-load / auto-create key (normal use):
let backends = DurableBackends::open("./aether.db")?;

// Explicit key (tests, advanced deployments):
let key = HmacKey::from_bytes(bytes, KeyId("my-key".into()));
let backends = DurableBackends::open_with_key("./aether.db", key)?;

// Manual verify:
backends.audit.verify_chain()?;
```

Error surface: `AuditVerifyError::{ChainBreak { row_id }, HmacMismatch { row_id }, Io(String)}` from `storage_hooks.rs` — unchanged, just now actually used.

## 5. Tests & checks

New file: `packages/l5-policy/tests/audit_seal.rs` — 5 tests, all gated behind `sqlite-backend`:

| Test                                                    | Verifies                                                  |
|---------------------------------------------------------|-----------------------------------------------------------|
| `verify_chain_passes_on_fresh_sealed_log`               | Happy path: 3 appended rows verify clean.                 |
| `verify_chain_detects_payload_tampering`                | Drop append-only triggers, UPDATE `payload`, expect `ChainBreak`. |
| `verify_chain_detects_wrong_key`                        | Reopen DB with a different `HmacKey`, expect `HmacMismatch`. |
| `verify_chain_detects_chain_head_rollback`              | Zero out `policy_audit_chain_head.head_hash`, expect `ChainBreak`. |
| `second_insertion_chains_from_prior_head_across_restart`| Close + reopen DB + append → chain continues and verifies.|

Plus `audit_seal.rs` inline unit tests cover hex decode, hash determinism, HMAC-varies-with-key, and `ct_eq`.

| Check                                                          | Result              |
|----------------------------------------------------------------|---------------------|
| `cargo fmt --all -- --check`                                   | clean               |
| `cargo test -p aether-l5-policy --features sqlite-backend`     | 23 passed (5 new)   |
| `cargo test -p aether-storage`                                 | clean (migrations order test updated) |
| `cargo test --workspace`                                       | all green           |
| `python tools/lint-layer-boundaries/check.py`                  | OK, 0 violations    |

## 6. Limitations & future work

- **Key management is preview-grade.** Plain file / env var. No OS-keyring, no 0600 file-mode enforcement on Windows, no key rotation. A compromised host = compromised chain.
- **No backfill for pre-4.6 rows.** Existing unsealed rows are skipped by `verify_chain`. A `0004_audit_seal_backfill.sql` + one-shot rehash utility is a natural follow-up.
- **No asymmetric checkpoint signatures.** A third party can't verify without the local key. Wave-future work: periodic `AuditCheckpoint` row signed with a keypair + publish of the public half.
- **Canonical JSON is `serde_json::to_vec`.** Stable in practice because the writer and verifier share the `CanonicalAuditPayload` struct, but not a formal canonicalization spec. If cross-implementation verifiers ever become a goal, adopt something like RFC 8785 JCS.
- **Verify walks the full log.** Fine at preview scale; for larger logs, add incremental checkpoints so startup verification is bounded.
- **Chain break localization.** `row_id: u64::MAX` signals "tip rollback" — a cleaner variant (`AuditVerifyError::TipMismatch`) would be nicer, but stayed within the existing enum this wave.

## 7. Recommended next session

Per the prompt sequence: **L3.1 / L6.1 first presence/persona slice.** The engine-side sealing work opens up the audit log as a pressure test surface for whatever comes next.

---

**Status:** Wave 4.6 complete. Working tree ready for commit.
