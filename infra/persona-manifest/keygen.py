"""Generate the offline Ed25519 release key pair for persona-manifest signing.

Per ADR-0012 §6, the master persona manifest is Ed25519-signed by the
release authority before publication. The signing key lives offline
on Don's machine; the public key is bundled into the desktop binary
at compile time.

This script generates that key pair. Run ONCE per release identity —
re-running rotates the key, which invalidates every prior manifest
signature, which means clients running an older bundled public key
cannot verify the new manifest. Treat the secret key like an SSH
key: back it up, never commit it.

Usage:
    python infra/persona-manifest/keygen.py \\
        [--out-dir ~/.aether/release-key/] \\
        [--force]

Output (under `--out-dir`):
    aether-release-ed25519.sk    # 32 raw bytes (Ed25519 secret key seed)
                                 #   + chmod 600 on POSIX
    aether-release-ed25519.pk    # 32 raw bytes (Ed25519 public key)
    aether-release-ed25519.pk.b64  # base64 of public key — the form
                                   # that gets bundled in the desktop
                                   # binary as a string literal

The default `--out-dir` is `~/.aether/release-key/` so the secret
key never lives inside the repo. `--force` overwrites existing keys
(use only when rotating).

Dependency: PyNaCl (`pip install pynacl`). PyNaCl wraps libsodium,
which is the canonical reference implementation. The cryptography
package is an alternative; PyNaCl chosen here because its
SigningKey API is the smallest plausible surface for this use case.
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
from pathlib import Path


_DEFAULT_OUT_DIR = Path.home() / ".aether" / "release-key"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=_DEFAULT_OUT_DIR,
        help=f"Where to write the key files (default: {_DEFAULT_OUT_DIR}).",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing keys. Rotates the release identity.",
    )
    args = ap.parse_args()

    try:
        from nacl.signing import SigningKey
    except ImportError:
        print(
            "[keygen] FATAL: PyNaCl not installed. `pip install pynacl` and re-run.",
            file=sys.stderr,
        )
        return 2

    out_dir: Path = args.out_dir.expanduser().resolve()
    sk_path = out_dir / "aether-release-ed25519.sk"
    pk_path = out_dir / "aether-release-ed25519.pk"
    pk_b64_path = out_dir / "aether-release-ed25519.pk.b64"

    if (sk_path.exists() or pk_path.exists()) and not args.force:
        print(
            f"[keygen] refusing to overwrite existing key at {out_dir}; "
            f"pass --force to rotate (this invalidates ALL prior signatures).",
            file=sys.stderr,
        )
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)

    sk = SigningKey.generate()
    pk = sk.verify_key

    sk_bytes = bytes(sk)  # 32 raw bytes (Ed25519 seed)
    pk_bytes = bytes(pk)  # 32 raw bytes (Ed25519 public key)

    sk_path.write_bytes(sk_bytes)
    pk_path.write_bytes(pk_bytes)
    pk_b64_path.write_text(base64.b64encode(pk_bytes).decode("ascii") + "\n", encoding="ascii")

    # Lock down the secret key on POSIX. On Windows the os.chmod is a
    # no-op; users on Windows should rely on the user-profile ACL.
    try:
        os.chmod(sk_path, 0o600)
    except OSError:
        pass

    pk_b64 = pk_b64_path.read_text(encoding="ascii").strip()

    print(f"[keygen] wrote secret key -> {sk_path}")
    print(f"[keygen] wrote public key -> {pk_path}")
    print(f"[keygen] wrote public key (base64) -> {pk_b64_path}")
    print()
    print("Next steps:")
    print(f"  1. Back up the secret key: {sk_path}")
    print("  2. Bundle the base64 public key in apps/desktop/src-tauri/src/")
    print(f"     (the contents of {pk_b64_path} go into a const string literal):")
    print()
    print(f"     pub const RELEASE_PUBLIC_KEY_B64: &str = \"{pk_b64}\";")
    print()
    print("  3. Sign manifests with:")
    print(f"     python infra/persona-manifest/sign_manifest.py "
          f"--in dist/persona-manifest.json --sk {sk_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
