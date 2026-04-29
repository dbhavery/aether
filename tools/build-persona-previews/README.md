# tools/build-persona-previews

Builds the bundled Tier-1 preview bundle for each persona.
Per [ADR-0012](../../docs/adr/ADR-0012-persona-delivery-download-on-demand.md)
§3 Tier 1, these previews are baked into the desktop installer so the
onboarding wizard can show all 9 cast cards offline before the user
commits to downloading a full pack.

## Output

Default output dir: `apps/desktop/public/personas-previews/`.
For each persona:

```
<out>/<slug>/
├── preview.webp          # 256×256 WebP, target ≤ 100 KB
├── preview_voice.opus    # Opus 24 kbps mono, 3 s, target ≤ 30 KB
└── preview.yaml          # display_name + tagline + archetype
```

## Derivations

- **`preview.webp`** — center-square crops the 16:9 `avatar/portrait.png`
  then resizes to 256² with Lanczos. WebP quality 78, method 6.
- **`preview_voice.opus`** — first 3 s of `voice/sample.wav` encoded
  as Opus 24 kbps mono with `application=voip` (tuned for speech).
- **`preview.yaml`** — `slug`, `display_name`, `tagline`, `archetype`
  pulled from `persona.yaml`.

## Usage

```bash
# Build all 9 cast previews (default)
python tools/build-persona-previews/build.py

# Build a specific persona
python tools/build-persona-previews/build.py aurora

# Build into a custom dir
python tools/build-persona-previews/build.py --out tmp/previews
```

## Discovery rule

`build.py` (no args) discovers persona dirs that have `persona.yaml`
AND `avatar/anchor.png` AND `avatar/portrait.png` AND
`voice/sample.wav`. The `anchor.png` requirement filters out legacy
first-pass-only dirs (`caelum`, `luma`) which were cut from the
v0 cast.

## Footprint snapshot (2026-04-28 cast)

| Persona | webp | opus | yaml | total |
|---|---:|---:|---:|---:|
| aurora | 9,360 | 8,673 | 361 | 18,394 |
| hannah_park | 6,914 | 8,470 | 399 | 15,783 |
| james_whitfield | 7,562 | 7,783 | 409 | 15,754 |
| marcus_chen | 7,858 | 8,030 | 390 | 16,278 |
| nadia_volkov | 5,184 | 8,630 | 399 | 14,213 |
| priya_iyer | 6,178 | 8,610 | 402 | 15,190 |
| ray_castellano | 7,884 | 7,949 | 395 | 16,228 |
| sara_reyes | 7,890 | 7,608 | 379 | 15,877 |
| tomas_andrade | 6,598 | 9,050 | 398 | 16,046 |
| **total** | **66 KB** | **74 KB** | **3.5 KB** | **143 KB** |

143 KB across all 9 personas — far under the ADR-0012 §3 budget of
1.2 MB. ADR was conservative.

## Re-derive triggers

Re-run when:
- A persona's `avatar/portrait.png` is regenerated (rare; a portrait
  refresh changes the wizard thumbnail).
- A persona's `voice/sample.wav` is regenerated.
- A persona's `display_name`, `tagline`, or `archetype` field changes
  in `persona.yaml`.

The output is deterministic for a given source, so re-running on
unchanged source is a no-op for the bundled installer.

## Runtime dependencies

- Pillow (already in repo's Python deps for image work)
- `ffmpeg` on PATH (for the Opus encode step)
