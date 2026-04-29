# Persona Delivery Model — Design Doc

> **Status:** GRADUATED to ADR-0012 on 2026-04-28 night. The decision is
> Accepted; this doc remains as the rationale-rich source-of-truth that
> the ADR points back to. Updates to the *decision* go through a new
> ADR; updates to the *rationale documentation* update this file.
>
> **ADR:** file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0012-persona-delivery-download-on-demand.md
>
> Originally captured Don's directive 2026-04-28 night about persona
> packaging and delivery.
>
> **Scope:** How personas reach the user's machine, what's bundled in the
> desktop app, what's downloaded later, how character switching works,
> and what this implies for build, network, storage, and wizard UX.

---

## 1. Don's directive (verbatim)

> "These characters are only going to be samples when user goes through
> the onboarding wizard, they will pick one of these characters. That
> will be the character they use every time. Option to change characters
> later in options. persona and all animations, etc. will download only
> for their chosen character. Not all of them will download to their
> machine. Changing the character later will mean removing the first
> and installing new. Take this into consideration when designing and
> building the characters, platform, wizard, memory usage, etc."

---

## 2. The model in one paragraph

The desktop app ships with **lightweight previews of all 9 personas**
(thumbnail + ~3-second voice clip + tagline + archetype label) so the
onboarding wizard can show the cast without a network round-trip. The
user picks one. The **full pack for that persona** (anchor set + voice
references + lipsync rigging + any persona-specific weights) is
downloaded on commit. Only the chosen persona's full pack lives on disk
at any given time. Changing characters later (Settings → Change
Character) deletes the current pack and downloads the new one.

---

## 3. Asset tiers

Each persona has two asset tiers:

### Tier 1 — Preview (bundled in desktop app)

Lightweight, offline-capable. Total footprint across all 9 personas
should fit comfortably under 2 MB so the app installer stays small.

| Asset | Format | Size budget | Purpose |
|---|---|---|---|
| `preview.webp` | WebP, 256×256 | ≤ 100 KB | Wizard thumbnail (the "hello, I'm Aurora" picker card) |
| `preview_voice.opus` | Opus 24 kbps mono, 3 s | ≤ 30 KB | Wizard voice button — "tap to hear me" |
| `preview.yaml` | YAML | < 4 KB | display_name, tagline, archetype, archetype_notes excerpt |

**9 personas × ~130 KB ≈ 1.2 MB bundled.** Acceptable.

### Tier 2 — Full pack (downloaded on selection)

The everything bundle for the chosen persona. Downloaded once, kept on
disk while active, deleted on switch.

| Asset | Format | Size estimate | Source |
|---|---|---|---|
| `avatar/anchor.png` | PNG 1024×1024 | 1.5–2 MB | Phase 4a anchor-set generation |
| `avatar/portrait.png` | PNG 1024×1024 | 1.5–2 MB | Phase 4a |
| `avatar/profile_left.png` | PNG 1024×1024 | 1.5–2 MB | Phase 4a |
| `avatar/profile_right.png` | PNG 1024×1024 | 1.5–2 MB | Phase 4a |
| `avatar/visemes/*.png` | PNG 512×512 × ~12 phonemes | ~6 MB total | Phase 4b lipsync gen |
| `voice/reference.wav` | 24 kHz mono 16-bit, 20 s | ~1 MB | Phase 3 |
| `voice/sample.wav` | 24 kHz mono 16-bit, 4 s | ~200 KB | Phase 3 |
| `persona.yaml` | YAML | ~5 KB | Hand-authored |
| `metadata.yaml` | YAML | ~3 KB | Provenance |
| `voice/voice.yaml` | YAML | ~2 KB | Chatterbox knobs |
| `voice/SOURCE.md` | Markdown | ~2 KB | Voice provenance |
| **Optional:** persona-specific LoRA | `.safetensors` | 80–200 MB | Phase 5+ if needed |
| **Optional:** lipsync model | `.safetensors` / `.onnx` | 100–400 MB | Phase 4b |

**Without per-persona models: ~15 MB.**
**With shared lipsync model + no persona LoRAs: ~15 MB + ~200 MB shared (downloaded once for any persona) = ~215 MB first persona, ~15 MB on subsequent switches if model is cached.**
**With per-persona LoRA: +100 MB per pack.**

**Per-persona LoRAs are deferred** per `PERSONA_ROADMAP.md` — default is
shared base + system-prompt steering. This keeps the per-pack download
small and switching cheap.

---

## 4. Storage layout on user's machine

Tauri identifier `dev.aether.desktop` (preserved across the Companion
rename) determines the AppData path. On Windows:

```
%APPDATA%/dev.aether.desktop/
├── preferences.json
├── audit.db                          # L5 audit chain
├── memory.db                         # L2 memory kernel (user-keyed,
│                                       NOT persona-keyed — preserved
│                                       across persona switches)
├── personas/
│   └── active/
│       └── <slug>/                   # current persona's full pack
│           ├── persona.yaml
│           ├── metadata.yaml
│           ├── avatar/
│           ├── voice/
│           └── (optional) lora.safetensors
├── shared/                           # cross-persona shared assets
│   └── lipsync_model.safetensors     # downloaded once if needed
└── cache/
    └── partial_downloads/            # in-flight pack downloads,
                                        cleaned on success/cancel
```

The bundled previews live inside the app's own resource path
(`apps/desktop/public/personas-previews/`), not in
AppData. They don't move when the user picks one — the wizard just
records "user picked X" and triggers the Tier-2 download into
AppData/personas/active/X.

**User memory is persona-independent.** Switching characters does not
forget anything the user has shared. The persona is a presentation
layer (face, voice, tone, archetype-shaped system prompt); the
relationship state lives one layer down.

---

## 5. Delivery channel

### v0 (preview / community edition)

**GitHub Releases** as the asset host. Each persona pack is a tagged
release artifact at `github.com/dbhavery/aether/releases/persona-<slug>-<version>/<slug>.zip`.

Pros: free, no account, no infra, public-readable, integrity hashes
provided by GitHub, redistributable.

Cons: rate-limited for unauthenticated downloads (~60/hr from same IP
unauthenticated, ~5000/hr authenticated). Acceptable at preview-edition
scale.

### v1+ (when scale matters)

**Cloudflare R2** behind a stable manifest URL on Don's domain.
R2 egress is free, storage ~$0.015/GB/month. At ~200 MB per pack and
9 personas, even 10000 downloads/persona = ~$2/month. Cheap.

The manifest is the single source of truth. The desktop app pulls
`https://companion.dbhavery.dev/persona-manifest.json` (or however
that URL settles) before showing the wizard. The manifest entry per
persona:

```json
{
  "slug": "aurora",
  "version": "1.0.0",
  "display_name": "Aurora Nash",
  "archetype": "warm_supportive",
  "size_bytes": 15728640,
  "shared_deps": ["lipsync_v1"],
  "asset_url": "https://companion.dbhavery.dev/personas/aurora-1.0.0.zip",
  "sha256": "a3b1...",
  "signature": "ed25519:5f8c..."
}
```

---

## 6. Integrity and policy

Every download is a remote action. Per L5 doctrine, remote actions are
policy-gated and audit-logged.

- **SHA-256 verification** on every downloaded pack against the
  manifest entry. Mismatch → reject, surface error, do not install.
- **Ed25519 signature** on the manifest itself, signed offline by
  Don's release key. The app ships the public key; download verifies
  the manifest signature before trusting any URL inside.
- **Audit row** on download start, completion, switch, and uninstall.
  Each emits a structured `L5Event::PolicyDecision` with capability
  `persona.download` / `persona.install` / `persona.uninstall`.
- **First download is approval-gated** in the wizard ("download
  ~XYZ MB?" → user clicks Approve). Subsequent same-persona
  re-downloads (e.g., to repair corruption) skip the prompt because
  the prior approval grant is durable for that capability.

---

## 7. Wizard flow (preview-only → committed download)

```
┌─────────────────────────────────────────────────────┐
│  Onboarding wizard step: pick your companion         │
│                                                       │
│  [9 cards, each shows preview thumb + name + tagline] │
│                                                       │
│  Hover/tap a card → playback of preview voice clip    │
│  (the bundled 3-second sample, no network)            │
│                                                       │
│  Click "Choose" on Aurora                             │
│        ↓                                              │
│  Confirmation: "Aurora's full pack is about 15 MB.    │
│                  Download now to continue?"           │
│        ↓                                              │
│  User approves                                        │
│        ↓                                              │
│  Progress UI (cancellable):                           │
│      - Verify manifest signature                      │
│      - Download zip                                   │
│      - Verify SHA-256                                 │
│      - Extract to %APPDATA%/.../personas/active/aurora │
│      - Validate persona.yaml schema                   │
│      - Audit row "persona.install Aurora 1.0.0"      │
│        ↓                                              │
│  First-run handoff: "You're with Aurora. Type 'hi'." │
└─────────────────────────────────────────────────────┘
```

Cancellation at any point in the download leaves no half-installed
state — the partial download lives in `cache/partial_downloads/` and
is cleaned. The user returns to the picker.

---

## 8. Switch flow (in Settings)

```
Settings → Companion → Change character

  Current: Aurora Nash (warm_supportive)
  Disk usage: 14.8 MB

  [Browse cast] → [Marcus Chen | analytical_focused] preview UI

  User clicks "Switch to Marcus"

  Confirm dialog:
    "This will remove Aurora (14.8 MB) and download Marcus
     (16.2 MB). About 30 seconds on a typical connection.
     Your conversation history and memory will be preserved.
     Continue?"

  User approves → atomic uninstall+install:
    1. Audit: persona.switch start (Aurora → Marcus)
    2. Download Marcus pack to cache/partial_downloads/
    3. Verify SHA-256 + signature
    4. Atomic move: remove personas/active/aurora;
       extract Marcus to personas/active/marcus_chen
    5. Audit: persona.switch complete
    6. Hot-reload L6 persona engine — pick up new persona.yaml,
       voice/voice.yaml, avatar paths
    7. Optional: emit L1 turn "Switched to Marcus. Different feel,
       same memory of you."

  Failure mid-switch (network drop, signature fail):
    - Aurora stays installed and active
    - Failed Marcus pack discarded
    - User notified, no data loss
```

**Atomic uninstall+install** is critical. If the new pack fails to
download or verify, the old persona must remain functional. Implement
as: download-and-verify-then-swap, never delete-then-download.

---

## 9. Build / packaging implications

| Surface | Change |
|---|---|
| `apps/desktop/public/personas-previews/` | New dir. Holds the 9 preview bundles (thumb + 3s opus + minimal yaml) baked into the app. Generated by a new `tools/build-persona-previews/` script that crops the full anchor PNG to 256² webp, transcodes the 4-second sample WAV to a 3-second opus, and copies preview-relevant fields out of `persona.yaml`. |
| `personas/<slug>/` | Stays as the canonical source. The full assets here are what gets zipped into the Tier-2 download. NOT directly bundled in the app. |
| `packages/l6-persona/` | Add download/install/uninstall capability to the persona engine. New trait methods: `install_pack(slug, version) -> Result<()>`, `uninstall(slug) -> Result<()>`, `current() -> Option<PersonaId>`. |
| `packages/l5-policy/` | Add capability `persona.download`, `persona.install`, `persona.uninstall`, `persona.switch`. Each gated. |
| New `tools/build-persona-pack/` | Zips a persona dir into `<slug>-<version>.zip`, emits SHA-256, generates manifest entry. Run as part of release. |
| New `infra/persona-manifest/` | Generates and signs the master manifest from per-pack manifest entries. Don signs offline before publishing. |

---

## 10. Open questions

1. **Lipsync model: shared or per-persona?** A single persona-agnostic
   lipsync model is much smaller-footprint than 9 per-persona ones.
   Probably the right call — verify in Phase 4b. If verified, lipsync
   model is a one-time `shared/` download triggered by the first
   persona install.

2. **Pre-rendered viseme stills vs runtime lipsync?** Tradeoff: shipping
   ~12 PNG visemes per persona (~6 MB) vs runtime lipsync rendering
   (zero shipped frames, ~200 MB shared model, GPU/CPU at runtime).
   Runtime is more flexible (any phoneme sequence) and cheaper per
   persona; pre-rendered is lower latency. Phase 4b decides.

3. **Persona-specific voice cloning weights?** Current plan: ship 20s
   voice reference, runtime cloning via Chatterbox/Zonos against the
   reference. No per-persona TTS weights shipped. Confirms the small
   per-pack footprint.

4. **Update channel semantics?** When persona pack v1.1 ships, does
   the user auto-update? Probably "notify, don't auto-update" — same
   posture as the desktop app proper.

5. **Offline first install?** What if the user is offline during the
   onboarding wizard? Options: (a) require network for first-run,
   (b) ship Aurora's full pack inside the app installer as a
   guaranteed-available fallback. (b) costs ~15 MB on the installer
   and is friendlier. Recommend (b) for v0.

6. **Telemetry on which persona is picked?** Privacy doctrine says
   "no remote without explicit consent." So either no usage telemetry
   on persona picks, or an explicit opt-in panel in Settings with a
   "share which persona I picked, anonymously" checkbox. Default off.

---

## 11. What this changes about today's persona work

- **Each persona dir is the canonical source** for that persona's full
  pack. Nothing in `personas/` ever ships embedded in the desktop app.
  This is already the structure — just confirms it.
- **Preview generation is a new build artifact**. Add `previews/`
  generation to the release pipeline, not part of the persona-author
  workflow. Persona authors don't hand-make previews; the build
  derives them from full assets.
- **Per-persona LoRAs stay deferred.** The download cost would push
  per-pack from ~15 MB to ~150+ MB, making switching expensive. Stick
  with shared base + system-prompt steering as PERSONA_ROADMAP says.
- **Lipsync delivery becomes a Phase 4b deliverable** — the spec for
  Phase 4b (verify lipsync on Aurora) now has a downstream
  consequence: the choice between shared model + runtime visemes vs
  pre-rendered stills determines per-pack footprint.
- **Documentation cross-link**: `personas/CHARACTERS.md` and
  `PERSONA_ROADMAP.md` should both reference this doc.

---

## 12. Decision log

| When | What | Why |
|---|---|---|
| 2026-04-28 night | Doc written | Don directive: persona is download-on-demand, only one active at a time, switching is uninstall+install. Captured before architecture drift sets in. |
| 2026-04-28 night | Graduated to ADR-0012 (Accepted) | Cast creator authority under Don's "you choose" directive. ADR is the load-bearing decision; this doc remains as rationale source. Don retains override via new ADR or DECISION_LOCK_PASS. |
