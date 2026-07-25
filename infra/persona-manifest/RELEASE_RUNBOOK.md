# Persona-Manifest Release Runbook

> Operational sequence for producing a signed `persona-manifest.json` and
> publishing it to the release channel. Closes ADR-0012 §6 (manifest
> signing contract). Read this before cutting any persona release.
>
> **Scope:** This runbook covers the persona master manifest only. Pack
> SHA-256 verification (post-extract) is owned by `verify_zip_sha256`
> in `packages/l6-persona/src/install/` and is not part of this loop.

---

## 0. Cast of files

| Role | Path |
|---|---|
| Secret release key (offline only) | file:///C:/Users/dbhav/.aether/release-key/aether-release-ed25519.sk |
| Public release key (raw 32 bytes) | file:///C:/Users/dbhav/.aether/release-key/aether-release-ed25519.pk |
| Public key (base64, for bundling) | file:///C:/Users/dbhav/.aether/release-key/aether-release-ed25519.pk.b64 |
| Bundled pubkey const in desktop binary | file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/main.rs |
| Keygen tool | file:///C:/Users/dbhav/Projects/aether/infra/persona-manifest/keygen.py |
| Manifest builder | file:///C:/Users/dbhav/Projects/aether/infra/persona-manifest/build_manifest.py |
| Manifest signer | file:///C:/Users/dbhav/Projects/aether/infra/persona-manifest/sign_manifest.py |
| Python verifier | file:///C:/Users/dbhav/Projects/aether/infra/persona-manifest/verify_manifest.py |
| Rust verifier | file:///C:/Users/dbhav/Projects/aether/packages/l6-persona/src/manifest_verifier.rs |
| Release pipeline orchestrator | file:///C:/Users/dbhav/Projects/aether/tools/release-personas.py |
| Build output dir (gitignored) | file:///C:/Users/dbhav/Projects/aether/dist/ |

The `dist/` directory is gitignored (`.gitignore` line 81: `**/dist/`).
Confirm with `git check-ignore -v dist/persona-manifest.json` before
running the build. **No file under `dist/` is ever committed.**

---

## 1. Keygen — already done, do NOT re-run

The release key was generated 2026-04-29 (T1.5):

```
python infra/persona-manifest/keygen.py --out ~/.aether/release-key
```

This created:

- `aether-release-ed25519.sk` — 32-byte raw secret seed. **Offline only.**
  Never commit. Never copy into the repo. Never paste into chat. Never
  log. The signer reads this file only at sign time.
- `aether-release-ed25519.pk` — 32-byte raw public key.
- `aether-release-ed25519.pk.b64` — same public key, base64-encoded for
  bundling into source.

The bundled `RELEASE_PUBLIC_KEY_B64` const at
file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/main.rs
is locked at the production pubkey value
`d5MxCr5Z7VRiJkqBqP7Hm3eg/2k7oDYQshiCsa5jMzQ=`.

If the release key is ever lost, rotated, or compromised, see §6.

---

## 2. Build the unsigned manifest

From repo root:

```
python tools/release-personas.py
```

That orchestrator runs the full pipeline: validate persona source dirs,
build Tier-2 packs (`dist/personas/*-1.0.0.zip`), build Tier-1 bundled
previews, then aggregate the master manifest at
`dist/persona-manifest.json` with `"signature": null`.

Sanity check the output:

```
python -c "import json; m=json.load(open('dist/persona-manifest.json')); \
  print('signature:', repr(m.get('signature'))); \
  print('personas:', len(m['personas']))"
```

Expected: `signature: None` and at least 9 personas (current cast).

If you only want the manifest stage (e.g., re-signing without
rebuilding packs), run `python infra/persona-manifest/build_manifest.py`
directly.

---

## 3. Sign the manifest

```
python infra/persona-manifest/sign_manifest.py \
  --in dist/persona-manifest.json \
  --sk ~/.aether/release-key/aether-release-ed25519.sk \
  --out dist/persona-manifest.signed.json
```

The signer:

- Canonicalises the `personas` array (sorted keys, no whitespace, UTF-8,
  no trailing newline) — see `manifest_verifier.rs` §"Canonical signed
  bytes" for the exact contract.
- Signs those bytes with the offline secret key.
- Writes the manifest with `"signature": "ed25519:<base64>"` populated.

Expected last line: `[sign] signature: ed25519:<...>==`.

If the input already carries a signature, the signer refuses unless you
pass `--allow-resign`. Default refusal is intentional — re-signing is
almost always wrong (you should rebuild from sources instead).

---

## 4. Verify (Python — local sanity check)

```
python infra/persona-manifest/verify_manifest.py \
  --in dist/persona-manifest.signed.json \
  --pk ~/.aether/release-key/aether-release-ed25519.pk
```

Expected: `[verify] OK — manifest at ... verifies under the supplied
public key.`

This catches local-machine signer bugs and key/manifest mismatches
before publication. If verification fails here, **do not publish** —
re-run §3, and if still failing, investigate signer/canonicalisation
drift (see `infra/persona-manifest/test_sign_verify.py`).

---

## 5. Cross-language verify (Rust — production roundtrip)

The desktop binary verifies signed manifests at install time using the
bundled `RELEASE_PUBLIC_KEY_B64` const. To prove the production loop is
intact end-to-end, run the locked-in cross-language test:

```
cargo test -p aether-l6-persona --test cross_language_verify
```

That test reads a Python-signed fixture and verifies through
`aether_l6_persona::verify_signed_manifest`. It runs in CI on every
push and locks the canonicalisation contract between the Python signer
and the Rust verifier.

For a one-shot real-key roundtrip (verifying the freshly signed
`dist/persona-manifest.signed.json` against the bundled pubkey value
copied from `apps/desktop/src-tauri/src/main.rs`), use a temporary
ad-hoc test or `cargo run --example` harness (not committed). The
roundtrip was last exercised on the date this runbook landed; details
in the corresponding commit message.

---

## 6. Publish

After §3 + §4 + §5 all pass:

1. Upload `dist/personas/*-1.0.0.zip` to the GitHub release for the
   manifest's `manifest_version`.
2. Upload `dist/persona-manifest.signed.json` (renamed to
   `persona-manifest.json`) to the same release as a top-level asset.
3. Confirm the asset URLs match the `download_url` fields baked into
   the manifest (`https://github.com/dbhavery/aether/releases/download/...`).

The desktop client fetches the manifest, verifies it under the bundled
pubkey before any pack download, then pulls each pack and verifies its
SHA-256 from the manifest entry post-extract. All three guards
(manifest signature, pack SHA, atomic install) must pass for a Tier-2
install to succeed.

---

## 7. Rollback

There is no key-side rollback. If a bad manifest ships:

- The bundled real pubkey in already-installed clients is correct, so
  any tampered or mis-signed manifest will be **rejected** at install
  time with a `BadSignature` error. Existing users are not at risk
  from a single bad publish.
- The fix is to **re-sign correctly and re-publish.** Rebuild the
  manifest (§2), sign with the canonical secret key (§3), verify (§4
  + §5), and replace the published asset. There is no "revert the
  signature" — Ed25519 signatures are a function of the bytes; either
  the bytes match what was signed or they don't.
- If the secret key itself is compromised, that is a different failure
  mode. The bundled pubkey in shipped binaries cannot be rotated
  remotely. A compromise requires a desktop release with a new bundled
  pubkey, plus a re-sign of every manifest under the new key. Treat
  the secret key file as the most sensitive artifact in this repo's
  operational chain.

---

## 8. Hard rules (do not violate)

- **Never commit** anything under `dist/` (signed or unsigned manifests,
  packs, sha files). The directory is gitignored — confirm with
  `git check-ignore -v dist/persona-manifest.json` before each release.
- **Never commit** the secret key, never copy it into the repo, never
  paste it into chat, never log it.
- **Never modify** `RELEASE_PUBLIC_KEY_B64` in
  `apps/desktop/src-tauri/src/main.rs` outside an explicit key-rotation
  release (which itself requires a fresh keygen + recompile + re-sign
  of every active manifest).
- **Never `--allow-resign`** without a documented reason. Default is
  rebuild-and-re-sign, not patch-and-re-sign.
