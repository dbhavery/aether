//! Ed25519 manifest verifier — runtime counterpart to
//! `infra/persona-manifest/sign_manifest.py`.
//!
//! Closes the security loop from ADR-0012 §6: at install time the
//! desktop client receives a master persona manifest from the release
//! channel; before any pack is downloaded, this module verifies the
//! manifest's Ed25519 signature against the public key bundled in the
//! desktop binary at compile time. Pack-by-pack SHA-256 verification
//! happens after extract via [`crate::install::verify_zip_sha256`].
//!
//! # Canonical signed bytes
//!
//! The signature covers ONLY the `personas` array, NOT the wrapper
//! (`generated`, `manifest_version`, `schema_version`, etc.). That
//! decision is documented in `infra/persona-manifest/sign_manifest.py`
//! and is reflected in this verifier so signer + verifier reproduce
//! the exact same byte sequence:
//!
//! - JSON serialization with **sorted keys** at every nesting level
//! - **No** whitespace in separators (`,` and `:`, not `, ` and `: `)
//! - **No** trailing newline
//! - UTF-8 encoding
//!
//! `serde_json::Value` uses a `BTreeMap`-backed `Map` by default
//! (without the `preserve_order` feature), so `to_vec(&value)`
//! produces sorted-key output. `serde_json`'s default formatter is
//! `CompactFormatter`, which uses no-space separators. Both
//! requirements are satisfied by a plain `serde_json::to_vec` call.
//!
//! # Cross-language compatibility
//!
//! The Python signer (`sign_manifest.py`) calls
//! `json.dumps(personas, sort_keys=True, separators=(",", ":"),
//!  ensure_ascii=False).encode("utf-8")`. That matches the bytes
//! Rust produces here. A regression on either side surfaces as a
//! `BadSignature` from this verifier, which the
//! `signed_by_python_verifies_in_rust` test locks.

use base64::engine::general_purpose::STANDARD as B64;
use base64::Engine as _;
use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use serde_json::Value;
use thiserror::Error;

/// Errors surfaced by [`verify_signed_manifest`].
#[derive(Debug, Error)]
pub enum ManifestVerifyError {
    /// The bytes did not parse as JSON.
    #[error("manifest is not valid JSON: {source}")]
    Json {
        /// Underlying parse error.
        #[source]
        source: serde_json::Error,
    },
    /// Manifest top-level is not a JSON object.
    #[error("manifest top-level is not a JSON object")]
    NotAnObject,
    /// `personas` field is missing or not an array.
    #[error("manifest missing 'personas' array (or it isn't a JSON array)")]
    PersonasMissing,
    /// `signature` field is missing, not a string, or wrong shape.
    #[error("signature field is missing or not 'ed25519:<base64>' (got {got:?})")]
    SignatureShape {
        /// Stringified form of whatever we found.
        got: String,
    },
    /// Base64 of the signature did not decode.
    #[error("signature base64 did not decode: {source}")]
    SignatureBase64 {
        /// Underlying base64 error.
        #[source]
        source: base64::DecodeError,
    },
    /// Decoded signature was not 64 bytes.
    #[error("signature must be 64 bytes after base64-decode, got {got}")]
    SignatureLength {
        /// Decoded length.
        got: usize,
    },
    /// Public key passed in was not 32 bytes.
    #[error("public key must be 32 bytes, got {got}")]
    PublicKeyLength {
        /// Provided length.
        got: usize,
    },
    /// Public key bytes were not a valid Ed25519 verifying key.
    #[error("public key is not a valid Ed25519 verifying key")]
    PublicKeyInvalid,
    /// Signature did not verify against the personas array under the supplied key.
    #[error("manifest signature does not match personas under the supplied key")]
    BadSignature,
}

/// Verify a signed persona manifest against a 32-byte public key.
///
/// Returns `Ok(())` on a verified signature; returns the appropriate
/// [`ManifestVerifyError`] otherwise. The verifier is read-only — it
/// does not mutate the manifest bytes or the caller's state.
///
/// `manifest_json` is the full JSON document (the file produced by
/// `sign_manifest.py`, with `signature: "ed25519:<base64>"`
/// populated). `public_key_32` is the raw 32-byte Ed25519 public
/// key — typically loaded from a string baked into the binary at
/// compile time via `include_str!` + base64 decode.
pub fn verify_signed_manifest(
    manifest_json: &[u8],
    public_key_32: &[u8],
) -> Result<(), ManifestVerifyError> {
    if public_key_32.len() != 32 {
        return Err(ManifestVerifyError::PublicKeyLength {
            got: public_key_32.len(),
        });
    }
    let mut pk_arr = [0u8; 32];
    pk_arr.copy_from_slice(public_key_32);
    let verifying_key =
        VerifyingKey::from_bytes(&pk_arr).map_err(|_| ManifestVerifyError::PublicKeyInvalid)?;

    let manifest: Value = serde_json::from_slice(manifest_json)
        .map_err(|source| ManifestVerifyError::Json { source })?;
    let obj = manifest
        .as_object()
        .ok_or(ManifestVerifyError::NotAnObject)?;

    let personas = obj
        .get("personas")
        .filter(|v| v.is_array())
        .ok_or(ManifestVerifyError::PersonasMissing)?;

    let sig_field = obj
        .get("signature")
        .and_then(|v| v.as_str())
        .ok_or_else(|| ManifestVerifyError::SignatureShape {
            got: format!("{:?}", obj.get("signature")),
        })?;
    let sig_b64 =
        sig_field
            .strip_prefix("ed25519:")
            .ok_or_else(|| ManifestVerifyError::SignatureShape {
                got: sig_field.to_string(),
            })?;
    let sig_bytes = B64
        .decode(sig_b64)
        .map_err(|source| ManifestVerifyError::SignatureBase64 { source })?;
    if sig_bytes.len() != 64 {
        return Err(ManifestVerifyError::SignatureLength {
            got: sig_bytes.len(),
        });
    }
    let mut sig_arr = [0u8; 64];
    sig_arr.copy_from_slice(&sig_bytes);
    let signature = Signature::from_bytes(&sig_arr);

    // Canonical bytes: serialize the personas array with serde_json's
    // default settings — sorted keys (BTreeMap-backed Map without the
    // preserve_order feature) + CompactFormatter (no whitespace) —
    // which matches the Python signer's
    // `json.dumps(personas, sort_keys=True, separators=(",", ":"))`.
    let body =
        serde_json::to_vec(personas).map_err(|source| ManifestVerifyError::Json { source })?;

    verifying_key
        .verify(&body, &signature)
        .map_err(|_| ManifestVerifyError::BadSignature)
}

#[cfg(test)]
mod tests {
    use super::*;
    use ed25519_dalek::{Signer, SigningKey};

    fn fixture_manifest_unsigned() -> serde_json::Value {
        serde_json::json!({
            "schema_version": 1,
            "generated": "2026-04-29T00:00:00Z",
            "manifest_version": "0.0.1",
            "signature": null,
            "personas": [
                {
                    "slug": "alice",
                    "version": "1.0.0",
                    "display_name": "Alice",
                    "archetype": "warm_supportive",
                    "size_bytes": 1234,
                    "shared_deps": [],
                    "asset_url": "https://example/test/alice-1.0.0.zip",
                    "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                }
            ]
        })
    }

    fn sign_in_test(sk: &SigningKey, manifest: &mut serde_json::Value) {
        // Mirror what the Python signer does: serialize the personas
        // array compactly with sorted keys, sign it, write
        // "ed25519:<base64>" back.
        let personas = manifest.get("personas").unwrap();
        let body = serde_json::to_vec(personas).unwrap();
        let sig: Signature = sk.sign(&body);
        let sig_b64 = B64.encode(sig.to_bytes());
        manifest["signature"] = serde_json::Value::String(format!("ed25519:{sig_b64}"));
    }

    fn fresh_keypair() -> SigningKey {
        // Deterministic seed for test reproducibility — never use a
        // hard-coded seed for a real release key.
        SigningKey::from_bytes(&[7u8; 32])
    }

    #[test]
    fn round_trip_signature_verifies() {
        let sk = fresh_keypair();
        let mut m = fixture_manifest_unsigned();
        sign_in_test(&sk, &mut m);
        let body = serde_json::to_vec(&m).unwrap();
        let pk = sk.verifying_key().to_bytes();
        verify_signed_manifest(&body, &pk).expect("verify should succeed on fresh signature");
    }

    #[test]
    fn tampered_persona_array_fails_verify() {
        let sk = fresh_keypair();
        let mut m = fixture_manifest_unsigned();
        sign_in_test(&sk, &mut m);
        // After signing, mutate the personas array — the signature
        // covers personas, so any change must invalidate.
        m["personas"][0]["sha256"] = serde_json::Value::String("f".repeat(64));
        let body = serde_json::to_vec(&m).unwrap();
        let pk = sk.verifying_key().to_bytes();
        let err = verify_signed_manifest(&body, &pk).unwrap_err();
        assert!(
            matches!(err, ManifestVerifyError::BadSignature),
            "got {err:?}"
        );
    }

    #[test]
    fn wrapper_metadata_changes_do_not_invalidate() {
        // The signature covers only `personas`. Updating wrapper
        // fields (e.g. `generated` timestamp on a republish) must
        // remain a valid signed manifest under the same signature.
        let sk = fresh_keypair();
        let mut m = fixture_manifest_unsigned();
        sign_in_test(&sk, &mut m);
        m["generated"] = serde_json::Value::String("2099-01-01T00:00:00Z".into());
        m["manifest_version"] = serde_json::Value::String("9.9.9".into());
        let body = serde_json::to_vec(&m).unwrap();
        let pk = sk.verifying_key().to_bytes();
        verify_signed_manifest(&body, &pk).expect("wrapper changes shouldn't invalidate");
    }

    #[test]
    fn signature_under_wrong_key_fails() {
        let sk = fresh_keypair();
        let mut m = fixture_manifest_unsigned();
        sign_in_test(&sk, &mut m);
        let body = serde_json::to_vec(&m).unwrap();
        // Verify under a DIFFERENT key.
        let other = SigningKey::from_bytes(&[42u8; 32]);
        let err = verify_signed_manifest(&body, &other.verifying_key().to_bytes()).unwrap_err();
        assert!(
            matches!(err, ManifestVerifyError::BadSignature),
            "got {err:?}"
        );
    }

    #[test]
    fn public_key_wrong_length_returns_typed_error() {
        let m = serde_json::to_vec(&fixture_manifest_unsigned()).unwrap();
        let err = verify_signed_manifest(&m, &[0u8; 31]).unwrap_err();
        assert!(matches!(
            err,
            ManifestVerifyError::PublicKeyLength { got: 31 }
        ));
    }

    #[test]
    fn missing_personas_array_returns_typed_error() {
        let body = b"{\"schema_version\":1,\"signature\":\"ed25519:AAAA\"}";
        let pk = fresh_keypair().verifying_key().to_bytes();
        let err = verify_signed_manifest(body, &pk).unwrap_err();
        assert!(
            matches!(err, ManifestVerifyError::PersonasMissing),
            "got {err:?}"
        );
    }

    #[test]
    fn malformed_signature_prefix_returns_typed_error() {
        let mut m = fixture_manifest_unsigned();
        m["signature"] = serde_json::Value::String("not-an-ed25519-prefix:zzz".into());
        let body = serde_json::to_vec(&m).unwrap();
        let pk = fresh_keypair().verifying_key().to_bytes();
        let err = verify_signed_manifest(&body, &pk).unwrap_err();
        assert!(matches!(err, ManifestVerifyError::SignatureShape { .. }));
    }

    #[test]
    fn signature_short_returns_typed_error() {
        let mut m = fixture_manifest_unsigned();
        // Valid base64 but only 8 bytes when decoded.
        m["signature"] = serde_json::Value::String(format!("ed25519:{}", B64.encode([1u8; 8])));
        let body = serde_json::to_vec(&m).unwrap();
        let pk = fresh_keypair().verifying_key().to_bytes();
        let err = verify_signed_manifest(&body, &pk).unwrap_err();
        assert!(matches!(
            err,
            ManifestVerifyError::SignatureLength { got: 8 }
        ));
    }
}
