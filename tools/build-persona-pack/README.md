# tools/build-persona-pack

Builds a single persona pack zip + SHA-256 + manifest entry from the
canonical `personas/<persona_id>/` source tree. Produces the Tier-2
download artifact described in
[ADR-0012](../../docs/adr/ADR-0012-persona-delivery-download-on-demand.md)
§5.

## Usage

```bash
# Build all 9 cast personas (default)
python tools/build-persona-pack/build.py

# Build a specific persona
python tools/build-persona-pack/build.py aurora

# Build with a non-default version tag
python tools/build-persona-pack/build.py aurora --version 1.2.0

# Build into a custom output directory
python tools/build-persona-pack/build.py --out dist/release-2026-04-28
```

## What's in the zip

The pack contains the canonical persona dir, scoped to runtime-needed files:

```
<persona_id>/
├── persona.yaml          # system prompt + traits
├── metadata.yaml         # asset provenance
├── avatar/
│   ├── anchor.png        # canonical face-consistency reference
│   ├── portrait.png      # personality picker shot
│   ├── profile_left.png  # 3/4 left for face-lock
│   └── profile_right.png # 3/4 right for face-lock
└── voice/
    ├── reference.wav     # ~20 s, for Chatterbox cloning
    ├── sample.wav        # ~4 s, wizard preview
    ├── voice.yaml        # Chatterbox/ElevenLabs knobs
    └── SOURCE.md         # voice provenance + steering
```

Excluded from the zip but kept in the repo:
- `avatar/anchor_set_raw_2026-04-28/` — raw JPGs for re-cropping
- `avatar/_archived_2026-04-28_first_pass/` — historical
- `avatar/README.md` — generation log

## Discovery rule

`build.py` (no args) discovers persona dirs that have BOTH
`persona.yaml` AND `avatar/anchor.png`. This excludes legacy
first-pass-only dirs (e.g., `_example`, `caelum`, `luma`) that never
received the anchor-set redesign. To include them, pass them
explicitly as arguments.

## Outputs

For each persona, three files in the output dir:

| File | Purpose |
|---|---|
| `<slug>-<version>.zip` | The pack — Tier-2 download artifact |
| `<slug>-<version>.sha256` | One-line SHA-256 hash for ad-hoc verification |
| `<slug>-<version>.manifest.json` | Single manifest entry, ready to splice into the master persona-manifest.json |

The manifest entry's `asset_url` is a `TODO://` placeholder — the
release pipeline (`infra/persona-manifest/`, not yet built) replaces
it with the real GitHub Releases or Cloudflare R2 URL before signing
the master manifest.

## Reproducibility

The zip is built with `ZIP_DEFLATED` at `compresslevel=6` with
filenames sorted alphabetically inside the archive, so two builds of
the same source tree produce byte-identical zips and therefore
matching SHA-256s. This matters for the ADR-0012 §6 integrity guarantee.

## Output footprint snapshot (2026-04-28 cast at v1.0.0)

| Persona | Pack size |
|---|---:|
| nadia_volkov     | 7.4 MB |
| hannah_park      | 9.9 MB |
| sara_reyes       | 10.2 MB |
| tomas_andrade    | 10.1 MB |
| marcus_chen      | 10.2 MB |
| priya_iyer       | 10.5 MB |
| james_whitfield  | 11.8 MB |
| aurora           | 12.0 MB |
| ray_castellano   | 13.0 MB |

Cast average: ~10.6 MB. ADR-0012 §3's "~15 MB" estimate was conservative.

## Open work

- `infra/persona-manifest/` — combine entries, fill `asset_url`,
  Ed25519-sign the master manifest. Not yet built.
- `tools/build-persona-previews/` — derive the bundled Tier-1
  preview bundle (256² webp + 3 s opus + minimal yaml) for installer
  embedding. Not yet built.
