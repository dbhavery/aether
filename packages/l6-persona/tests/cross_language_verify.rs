//! Cross-language verifier test.
//!
//! Locks the signer ↔ verifier contract by reading a fixture
//! produced by the Python signer
//! (`infra/persona-manifest/sign_manifest.py`) and verifying it
//! through the Rust verifier (`manifest_verifier::verify_signed_manifest`).
//!
//! If either language's canonical-bytes derivation drifts, this
//! test fails. That's exactly the early-warning we want — silent
//! drift would otherwise surface as an installer-blocking
//! BadSignature in production.
//!
//! Fixture origin: see `tests/fixtures/FIXTURE_README.md`.

use std::path::PathBuf;

#[test]
fn signed_by_python_verifies_in_rust() {
    let fixtures = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures");
    let manifest = std::fs::read(fixtures.join("signed_manifest.json"))
        .expect("read signed_manifest.json fixture");
    let pk = std::fs::read(fixtures.join("release_public_key.bin"))
        .expect("read release_public_key.bin fixture");
    assert_eq!(pk.len(), 32, "public key fixture must be exactly 32 bytes");

    aether_l6_persona::verify_signed_manifest(&manifest, &pk)
        .expect("Python-signed fixture must verify under the Rust verifier");
}

#[test]
fn fixture_pubkey_b64_matches_raw_bytes() {
    // Cheap consistency check — if the .bin and .b64 fixtures drift
    // apart, the keygen.py output convention is the source of truth
    // and the fixture regen step needs to be run.
    use base64::engine::general_purpose::STANDARD as B64;
    use base64::Engine as _;

    let fixtures = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures");
    let raw = std::fs::read(fixtures.join("release_public_key.bin")).unwrap();
    let b64 = std::fs::read_to_string(fixtures.join("release_public_key.b64")).unwrap();
    let decoded = B64.decode(b64.trim()).expect("b64 decode");
    assert_eq!(decoded, raw);
}
