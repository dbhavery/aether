"""Sign the persona master manifest with the offline Ed25519 release key.

Per ADR-0012 §6 the master manifest is signed before publication so
clients can verify integrity end-to-end (manifest signed, each pack's
SHA-256 listed inside the signed manifest, each pack hash-checked
on-disk before extract).

Pipeline:
    tools/build-persona-pack/build.py            # zips per persona
    infra/persona-manifest/build_manifest.py     # aggregates → unsigned
    infra/persona-manifest/sign_manifest.py      # ← THIS — signs in place
                                                 #   or to --out

Signing surface:
    Canonical bytes  =  the JSON-serialized `personas` array, with
                        keys sorted, no trailing newline, UTF-8.
                        We sign the personas array specifically — NOT
                        the whole manifest — so adding metadata to
                        the wrapper (generated timestamp, tooling
                        version) doesn't invalidate prior signatures.
    Signature shape  =  "ed25519:<base64>" written into the manifest's
                        top-level `signature` field. Base64-encodes
                        the raw 64-byte Ed25519 signature.

Usage:
    python infra/persona-manifest/sign_manifest.py \\
        --in dist/persona-manifest.json \\
        --sk ~/.aether/release-key/aether-release-ed25519.sk \\
        [--out dist/persona-manifest.signed.json]

When `--out` is omitted, the signed manifest is written back to
`--in` (in-place sign). Either way the original file's `signature`
field MUST have been `null` — re-signing a signed manifest requires
explicit `--allow-resign`.

Dependency: PyNaCl (`pip install pynacl`).
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path


def canonical_personas_bytes(manifest: dict) -> bytes:
    """Bytes that get signed.

    Deterministic JSON serialization of the `personas` array. Keys
    sorted within each entry, no trailing newline, UTF-8. The exact
    byte sequence the verifier reconstructs.
    """
    personas = manifest.get("personas")
    if not isinstance(personas, list):
        raise ValueError(
            "manifest is missing a 'personas' array — refusing to sign"
        )
    return json.dumps(
        personas, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--in", dest="input", type=Path, required=True,
                    help="Path to the unsigned manifest (signature: null).")
    ap.add_argument("--sk", type=Path, required=True,
                    help="Path to the 32-byte Ed25519 secret key file.")
    ap.add_argument("--out", type=Path, default=None,
                    help="Output path. Defaults to in-place over --in.")
    ap.add_argument("--allow-resign", action="store_true",
                    help="Permit signing a manifest that already carries a signature.")
    args = ap.parse_args()

    try:
        from nacl.signing import SigningKey
    except ImportError:
        print(
            "[sign] FATAL: PyNaCl not installed. `pip install pynacl` and re-run.",
            file=sys.stderr,
        )
        return 2

    sk_bytes = args.sk.read_bytes()
    if len(sk_bytes) != 32:
        print(
            f"[sign] FATAL: expected 32-byte Ed25519 secret key at {args.sk}, "
            f"got {len(sk_bytes)} bytes. Did you point at the right file?",
            file=sys.stderr,
        )
        return 2
    sk = SigningKey(sk_bytes)

    raw = args.input.read_text(encoding="utf-8")
    manifest = json.loads(raw)

    if manifest.get("signature") is not None and not args.allow_resign:
        print(
            f"[sign] manifest at {args.input} already carries a signature; "
            f"pass --allow-resign to overwrite (this invalidates older clients "
            f"who cached the prior signature).",
            file=sys.stderr,
        )
        return 1

    body = canonical_personas_bytes(manifest)
    signed = sk.sign(body)
    sig_b64 = base64.b64encode(signed.signature).decode("ascii")
    manifest["signature"] = f"ed25519:{sig_b64}"

    out = args.out or args.input
    out.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"[sign] signed manifest written to {out}")
    print(f"[sign] signed bytes (canonical personas array): {len(body)} bytes")
    print(f"[sign] signature: ed25519:{sig_b64[:16]}…{sig_b64[-8:]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
