"""Verify a signed persona master manifest with the bundled Ed25519 public key.

This is the reference verifier — useful for CI gating, for sanity-
checking a manifest before publication, and as documentation of what
the desktop client must reproduce in Rust at runtime.

Usage:
    python infra/persona-manifest/verify_manifest.py \\
        --in dist/persona-manifest.json \\
        --pk infra/persona-manifest/RELEASE_PUBLIC_KEY.pk
        # OR
        --pk-b64 "<base64 of public key>"

Returns exit 0 if signature checks out, non-zero with a diagnostic
otherwise. The canonical signed bytes are the JSON-serialized
`personas` array with keys sorted, no trailing newline, UTF-8 — same
function the signer uses, so a drift between signer and verifier
produces a verifier failure rather than a silent bad signature.

Dependency: PyNaCl (`pip install pynacl`).
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path


def canonical_personas_bytes(manifest: dict) -> bytes:
    personas = manifest.get("personas")
    if not isinstance(personas, list):
        raise ValueError("manifest missing a 'personas' array")
    return json.dumps(
        personas, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--in", dest="input", type=Path, required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--pk", type=Path, help="Path to the 32-byte raw Ed25519 public key.")
    g.add_argument("--pk-b64", help="Base64-encoded Ed25519 public key.")
    args = ap.parse_args()

    try:
        from nacl.signing import VerifyKey
        from nacl.exceptions import BadSignatureError
    except ImportError:
        print(
            "[verify] FATAL: PyNaCl not installed. `pip install pynacl` and re-run.",
            file=sys.stderr,
        )
        return 2

    if args.pk is not None:
        pk_bytes = args.pk.read_bytes()
    else:
        pk_bytes = base64.b64decode(args.pk_b64)
    if len(pk_bytes) != 32:
        print(
            f"[verify] FATAL: expected 32-byte Ed25519 public key, got {len(pk_bytes)} bytes.",
            file=sys.stderr,
        )
        return 2

    manifest = json.loads(args.input.read_text(encoding="utf-8"))
    sig_field = manifest.get("signature")
    if not isinstance(sig_field, str) or not sig_field.startswith("ed25519:"):
        print(
            f"[verify] FAIL: manifest signature field is missing or not "
            f"prefixed 'ed25519:' (got {sig_field!r})",
            file=sys.stderr,
        )
        return 1
    sig_b64 = sig_field[len("ed25519:"):]
    try:
        sig = base64.b64decode(sig_b64)
    except Exception as e:
        print(f"[verify] FAIL: signature is not valid base64: {e}", file=sys.stderr)
        return 1
    if len(sig) != 64:
        print(
            f"[verify] FAIL: Ed25519 signature must be 64 bytes, got {len(sig)}",
            file=sys.stderr,
        )
        return 1

    body = canonical_personas_bytes(manifest)
    try:
        VerifyKey(pk_bytes).verify(body, sig)
    except BadSignatureError:
        print("[verify] FAIL: signature does not match the personas array under this key.",
              file=sys.stderr)
        return 1

    print(f"[verify] OK — manifest at {args.input} verifies under the supplied public key.")
    print(f"[verify] signed bytes: {len(body)} (personas array, canonical JSON)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
