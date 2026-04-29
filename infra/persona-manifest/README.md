# infra/persona-manifest

Master persona manifest builder. Aggregates per-persona pack
manifest entries from `dist/personas/` (produced by
`tools/build-persona-pack/`) into a single
`dist/persona-manifest.json` ready for Ed25519 signing.

Per [ADR-0012](../../docs/adr/ADR-0012-persona-delivery-download-on-demand.md)
§5, the master manifest is the single source of truth that the
desktop app fetches before showing the wizard.

## Usage

```bash
# After running tools/build-persona-pack/build.py:
python infra/persona-manifest/build_manifest.py \
    --base-url https://github.com/dbhavery/aether/releases/download
```

Or for a custom output / subset:

```bash
python infra/persona-manifest/build_manifest.py \
    --in dist/personas \
    --out dist/persona-manifest.json \
    --manifest-version 1.0.0 \
    --base-url https://companion.dbhavery.dev/personas
```

## What's NOT here yet

**Ed25519 signing.** The manifest is produced with `signature: null`.
Signing requires Don's offline release key, which isn't set up yet.
A separate `sign_manifest.py` will:

1. Read the unsigned manifest
2. Compute `sha256` of `personas` array (sorted, canonical-JSON
   serialized)
3. Sign that hash with Don's offline Ed25519 secret key
4. Write the signature back into the manifest's `signature` field
   in the form `ed25519:<base64-of-sig>`
5. Re-serialize and emit the signed manifest

The desktop app ships the corresponding **public** key bundled in
its binary. App fetches the manifest, recomputes the hash over the
`personas` array, verifies the signature against the bundled public
key, then trusts the URLs and SHA-256s inside.

Until signing exists:
- The manifest produced here is structurally complete and good for
  testing the desktop-app fetch + parse path.
- It is NOT trustworthy for production (no integrity guarantee on
  the manifest itself; the per-pack SHA-256 verification still
  works as a per-pack check).

## Output schema

```jsonc
{
  "schema_version": 1,
  "manifest_version": "1.0.0",        // bump on every release
  "generated": "2026-04-28T22:59:00Z", // ISO-8601 UTC
  "signature": null,                   // ed25519:<base64> after signing
  "personas": [
    {
      "slug": "aurora",
      "version": "1.0.0",
      "display_name": "Aurora Nash",
      "archetype": "warm_supportive",
      "size_bytes": 11936738,
      "shared_deps": [],
      "asset_url": "https://github.com/dbhavery/aether/releases/download/persona-aurora-1.0.0/aurora-1.0.0.zip",
      "sha256": "6e0c3ada147ce8d319efb5685ffed24124d705705611532f9fd273fe9555f7d8"
    },
    /* … 8 more entries … */
  ]
}
```

## Pipeline

The full release pipeline for personas (v0):

```
personas/<slug>/                                    [canonical source]
        │
        │  python tools/build-persona-pack/build.py
        ▼
dist/personas/<slug>-<version>.zip                  [pack zip]
dist/personas/<slug>-<version>.sha256               [hash]
dist/personas/<slug>-<version>.manifest.json        [per-pack entry]
        │
        │  python infra/persona-manifest/build_manifest.py
        │      --base-url https://…/releases/download
        ▼
dist/persona-manifest.json                          [unsigned master]
        │
        │  python infra/persona-manifest/sign_manifest.py  ← NOT YET BUILT
        │      --secret-key ~/.aether/release-key.ed25519
        ▼
dist/persona-manifest.signed.json                   [signed master]
        │
        │  Upload to GitHub Releases / Cloudflare R2
        ▼
https://…/persona-manifest.json                     [live]
```

In parallel, `tools/build-persona-previews/` writes the bundled
Tier-1 previews under
`apps/desktop/public/personas-previews/`, which the
installer build step picks up automatically.

## Why infra/ and not tools/

`tools/` per `aether/CLAUDE.md` §4 is governance + codegen
infrastructure (boundary linters, ts-rs codegen). The build artefact
chain (zip, hash, manifest, sign) is **release infrastructure**, not
governance, so it lives under `infra/`.
