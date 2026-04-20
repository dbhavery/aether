//! Wave 4.6 — audit hash-chain + HMAC sealing.
//!
//! Feature-gated behind `sqlite-backend` alongside the rest of the durable
//! audit path. Stays out of the default OSS-preview build entirely.
//!
//! ## Sealing model (per row)
//!
//! 1. Canonicalize the audit payload excluding its own chain fields
//!    (`prev_hash`, `record_hmac`, `key_id`) so the hash is over stable
//!    content, never over itself.
//! 2. Compute `event_hash = SHA256(prev_hash || canonical_payload_bytes)`.
//!    The previous row's `event_hash` is the current row's `prev_hash`; the
//!    first row uses the 32-byte genesis constant.
//! 3. Compute `record_hmac = HMAC-SHA256(key, event_hash)`.
//! 4. Store `prev_hash`, `event_hash`, `record_hmac`, and `key_id` alongside
//!    the row.
//! 5. Update the singleton `policy_audit_chain_head` to point at this row's
//!    `event_hash`.
//!
//! Verification re-walks the log in insertion order (`rowid ASC`) and
//! recomputes each row's `event_hash` and HMAC from the stored payload, the
//! prior row's `event_hash`, and the configured key. Any mismatch produces
//! a specific `AuditVerifyError` carrying the offending row index.
//!
//! ## What this protects
//!
//! - Local DB mutation (e.g. someone editing `payload` to rewrite history):
//!   detected, because `event_hash` no longer matches the canonical payload.
//! - Row splicing (inserting or deleting in the middle): detected, because
//!   the next row's stored `prev_hash` no longer matches the recomputed
//!   `event_hash` of the prior row.
//! - Chain-tip swap (rolling back to an earlier head): detected, because
//!   the final computed head no longer matches the stored
//!   `policy_audit_chain_head.head_hash`.
//!
//! ## What it does NOT protect (yet)
//!
//! - **Key compromise.** If an attacker reads the key file, they can re-seal
//!   any tampered history. A future wave wires an OS-keyring integration.
//! - **Host-level compromise.** Root on the machine can tamper with the
//!   running process. Out of scope for OSS preview.
//! - **Remote attestation.** No third-party can currently verify a chain
//!   without the local key; a public `AuditCheckpoint` signed with an
//!   asymmetric key is a future wave.

#![cfg(feature = "sqlite-backend")]

use std::path::{Path, PathBuf};

use hmac::{Hmac, Mac};
use rand::RngCore;
use serde::Serialize;
use sha2::{Digest, Sha256};

use crate::audit::{AuditRecordEvent, KeyId};

/// Genesis constant used as `prev_hash` for the very first row. Arbitrary
/// but fixed; keeping it here instead of zeros makes accidental collisions
/// with all-zero buffers less likely.
pub const GENESIS_PREV_HASH: [u8; 32] = [
    0x41, 0x65, 0x74, 0x68, 0x65, 0x72, 0x20, 0x61, 0x75, 0x64, 0x69, 0x74, 0x20, 0x67, 0x65, 0x6e,
    0x65, 0x73, 0x69, 0x73, 0x20, 0x76, 0x31, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01,
];

/// Environment variable read by [`HmacKey::load_or_create`] before falling
/// back to the on-disk file. Useful for tests and ephemeral runs.
pub const HMAC_KEY_ENV: &str = "AETHER_AUDIT_HMAC_KEY_HEX";

/// HMAC signing key used to seal audit rows. 32 bytes (SHA-256 block-aligned).
///
/// **Storage model for the OSS preview.** The key lives either in
/// `AETHER_AUDIT_HMAC_KEY_HEX` (hex-encoded 32 bytes) or in a sibling file
/// next to the DB — e.g. `aether.db` → `aether.db.hmac.key`. File mode is
/// not currently restricted to 0600 because Windows semantics differ; this
/// is documented as a known gap.
#[derive(Clone)]
pub struct HmacKey {
    bytes: [u8; 32],
    id: KeyId,
}

impl HmacKey {
    /// Build a key from raw bytes and a caller-provided id. Prefer
    /// [`load_or_create`](Self::load_or_create) in normal use.
    pub fn from_bytes(bytes: [u8; 32], id: KeyId) -> Self {
        Self { bytes, id }
    }

    /// Load the HMAC key from the env var if present; otherwise read (or
    /// create) `<db_path>.hmac.key` next to the DB. Generates 32 random
    /// bytes with `rand::rngs::OsRng` on first run.
    pub fn load_or_create(db_path: impl AsRef<Path>) -> std::io::Result<Self> {
        if let Ok(hex) = std::env::var(HMAC_KEY_ENV) {
            if let Some(bytes) = decode_hex32(&hex) {
                return Ok(Self::from_bytes(bytes, KeyId(String::from("env-v1"))));
            }
        }

        let key_path = key_file_path(db_path.as_ref());
        match std::fs::read(&key_path) {
            Ok(bytes) if bytes.len() == 32 => {
                let mut arr = [0u8; 32];
                arr.copy_from_slice(&bytes);
                Ok(Self::from_bytes(arr, KeyId(String::from("file-v1"))))
            }
            Ok(_) => {
                // Wrong length: rewrite with a fresh key rather than
                // silently accepting the corrupt file.
                let key = generate_random_key();
                std::fs::write(&key_path, key)?;
                Ok(Self::from_bytes(key, KeyId(String::from("file-v1"))))
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                let key = generate_random_key();
                if let Some(parent) = key_path.parent() {
                    if !parent.as_os_str().is_empty() {
                        std::fs::create_dir_all(parent)?;
                    }
                }
                std::fs::write(&key_path, key)?;
                Ok(Self::from_bytes(key, KeyId(String::from("file-v1"))))
            }
            Err(e) => Err(e),
        }
    }

    /// Key bytes (32).
    pub fn bytes(&self) -> &[u8; 32] {
        &self.bytes
    }

    /// Key id (e.g. `"file-v1"`, `"env-v1"`).
    pub fn id(&self) -> &KeyId {
        &self.id
    }
}

impl std::fmt::Debug for HmacKey {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        // Never render the key bytes — debug output ends up in logs and
        // crash reports.
        f.debug_struct("HmacKey")
            .field("id", &self.id)
            .field("bytes", &"<redacted 32 bytes>")
            .finish()
    }
}

fn key_file_path(db_path: &Path) -> PathBuf {
    let mut p = db_path.as_os_str().to_os_string();
    p.push(".hmac.key");
    PathBuf::from(p)
}

fn generate_random_key() -> [u8; 32] {
    let mut k = [0u8; 32];
    rand::rngs::OsRng.fill_bytes(&mut k);
    k
}

fn decode_hex32(hex: &str) -> Option<[u8; 32]> {
    let trimmed = hex.trim();
    if trimmed.len() != 64 {
        return None;
    }
    let mut out = [0u8; 32];
    for (i, chunk) in trimmed.as_bytes().chunks(2).enumerate() {
        let s = std::str::from_utf8(chunk).ok()?;
        out[i] = u8::from_str_radix(s, 16).ok()?;
    }
    Some(out)
}

/// Canonical payload for hashing. Mirrors [`AuditRecordEvent`] but strips
/// the three self-referential / integrity fields (`prev_hash`,
/// `record_hmac`, `key_id`) so the hash is deterministic over content the
/// writer actually chose.
#[derive(Serialize)]
struct CanonicalAuditPayload<'a> {
    audit_id: &'a crate::audit::AuditId,
    timestamp_monotonic: &'a crate::common::MonotonicTimestamp,
    timestamp_wall: &'a crate::common::WallTimestamp,
    actor: &'a crate::common::ActorRef,
    capability: &'a crate::capability::Capability,
    resource: &'a crate::capability::ResourceScope,
    decision: &'a crate::decision::DecisionKind,
    change_id: &'a crate::common::ChangeId,
    seq: u64,
    reason: &'a Option<crate::decision::StaticReasonId>,
    stage_trace: &'a Vec<crate::audit::StageTrace>,
    privileged_profile: bool,
}

impl<'a> From<&'a AuditRecordEvent> for CanonicalAuditPayload<'a> {
    fn from(r: &'a AuditRecordEvent) -> Self {
        Self {
            audit_id: &r.audit_id,
            timestamp_monotonic: &r.timestamp_monotonic,
            timestamp_wall: &r.timestamp_wall,
            actor: &r.actor,
            capability: &r.capability,
            resource: &r.resource,
            decision: &r.decision,
            change_id: &r.change_id,
            seq: r.seq,
            reason: &r.reason,
            stage_trace: &r.stage_trace,
            privileged_profile: r.privileged_profile,
        }
    }
}

/// Canonical serialization used for hashing. `serde_json` with no pretty
/// printing is stable enough for this use: we control both the writer and
/// the verifier, and the struct is frozen by `CanonicalAuditPayload`.
pub fn canonical_bytes(row: &AuditRecordEvent) -> Result<Vec<u8>, serde_json::Error> {
    let view: CanonicalAuditPayload<'_> = row.into();
    serde_json::to_vec(&view)
}

/// Compute `event_hash = SHA256(prev_hash || canonical_payload)`.
pub fn compute_event_hash(prev_hash: &[u8], canonical_payload: &[u8]) -> [u8; 32] {
    let mut hasher = Sha256::new();
    hasher.update(prev_hash);
    hasher.update(canonical_payload);
    hasher.finalize().into()
}

/// Compute `HMAC-SHA256(key, event_hash)`.
pub fn compute_event_hmac(key: &HmacKey, event_hash: &[u8]) -> [u8; 32] {
    type HmacSha256 = Hmac<Sha256>;
    let mut mac = HmacSha256::new_from_slice(key.bytes()).expect("HMAC accepts any key length");
    mac.update(event_hash);
    mac.finalize().into_bytes().into()
}

/// Constant-time equality check. `hmac` crate's `verify_slice` would also
/// work; this is a tiny local helper to avoid extending the public API.
pub fn ct_eq(a: &[u8], b: &[u8]) -> bool {
    if a.len() != b.len() {
        return false;
    }
    let mut acc = 0u8;
    for (x, y) in a.iter().zip(b.iter()) {
        acc |= x ^ y;
    }
    acc == 0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hex_roundtrip_decodes_exact_32_bytes() {
        let mut k = [0u8; 32];
        for (i, b) in k.iter_mut().enumerate() {
            *b = i as u8;
        }
        let hex: String = k.iter().map(|b| format!("{b:02x}")).collect();
        let back = decode_hex32(&hex).expect("decodes");
        assert_eq!(back, k);
    }

    #[test]
    fn hex_decoder_rejects_wrong_length() {
        assert!(decode_hex32("deadbeef").is_none());
    }

    #[test]
    fn event_hash_is_deterministic() {
        let a = compute_event_hash(b"prev", b"payload");
        let b = compute_event_hash(b"prev", b"payload");
        assert_eq!(a, b);
    }

    #[test]
    fn event_hash_changes_with_payload() {
        let a = compute_event_hash(b"prev", b"payload-1");
        let b = compute_event_hash(b"prev", b"payload-2");
        assert_ne!(a, b);
    }

    #[test]
    fn hmac_changes_with_key() {
        let k1 = HmacKey::from_bytes([1u8; 32], KeyId("k1".into()));
        let k2 = HmacKey::from_bytes([2u8; 32], KeyId("k2".into()));
        let h = [0xaau8; 32];
        assert_ne!(compute_event_hmac(&k1, &h), compute_event_hmac(&k2, &h));
    }

    #[test]
    fn ct_eq_matches_basic_eq() {
        assert!(ct_eq(b"abc", b"abc"));
        assert!(!ct_eq(b"abc", b"abd"));
        assert!(!ct_eq(b"abc", b"abcd"));
    }
}
