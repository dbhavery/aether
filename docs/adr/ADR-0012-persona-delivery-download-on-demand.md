# ADR-0012: Persona delivery — bundled previews + download-on-demand full packs

- **Status:** **Accepted** (2026-04-28 night). Authority: cast creator under Don's 2026-04-28 directive ("you are the character creator. You choose look, voice, persona, etc. not me"). Don retains override.
- **Date:** 2026-04-28
- **Deciders:** Cast creator (Claude) records the decision as Accepted. Don retains revert/amend authority via DECISION_LOCK_PASS or new ADR.
- **Supersedes:** nothing (this is the first persona-delivery decision).
- **Superseded by:** nothing yet.
- **Related:**
  - `personas/CHARACTERS.md` — the cast roster + lock-before-scale rule.
  - `docs/adr/ADR-0001-memory-domain-reconciliation.md` — establishes that memory is user-keyed, not persona-keyed (load-bearing for §4 below).
  - `docs/adr/ADR-0006-hardware-tier-model.md` — sets the hardware envelope inside which per-pack footprint matters.

## Context

As of 2026-04-28 night, the cast is shipped: 9 personas (Aurora,
Marcus, Sara, James, Nadia, Priya, Ray, Hannah, Tomás), each with a
full asset pack — anchor + portrait + profile_left + profile_right
PNGs, voice reference + sample WAVs, voice.yaml + SOURCE.md +
metadata.yaml + persona.yaml. Total per-pack disk footprint ~15 MB.

Don's 2026-04-28 directive set the delivery posture explicitly:

> "These characters are only going to be samples when user goes
> through the onboarding wizard, they will pick one of these
> characters. That will be the character they use every time. Option
> to change characters later in options. persona and all animations,
> etc. will download only for their chosen character. Not all of them
> will download to their machine. Changing the character later will
> mean removing the first and installing new."

Without an architectural decision captured, three drift modes are
live:
1. The desktop installer balloons (9 packs × ~15 MB = ~135 MB of
   personas baked in even though the user only ever uses one).
2. Persona switching becomes a byte-shuffle the engine has to
   reason about (multiple personas live on disk, ambiguity about
   which is current).
3. Heavier per-persona model assets get added without footprint
   review, pushing per-pack from ~15 MB to ~150+ MB and making
   switching expensive.

This ADR locks the model that prevents all three.

## Decision

**Bundled previews (Tier 1) + download-on-demand full packs (Tier 2)
+ atomic uninstall-then-install on switch.**

### Tier 1 — Preview, bundled in the desktop installer

For each of the 9 personas, the installer bakes in:
- `preview.webp` — 256×256 WebP thumbnail derived from `avatar/portrait.png`.
- `preview_voice.opus` — 3-second Opus 24 kbps mono derived from `voice/sample.wav`.
- `preview.yaml` — display_name, tagline, archetype, archetype_notes excerpt.

Total budget: ≤ 130 KB per persona × 9 = ~1.2 MB bundled. Acceptable.

Bundled previews live at
`apps/desktop/public/personas-previews/<slug>/`. They
are derived at release-build time from the canonical
`personas/<slug>/` source by a new tool at
`tools/build-persona-previews/`. Persona authors do not hand-make
previews.

### Tier 2 — Full pack, downloaded on selection

The full ~15 MB pack (anchor set + voice pack + persona.yaml +
metadata.yaml + voice.yaml + SOURCE.md) is downloaded from a
manifest URL after the user commits to a persona in the wizard.

Only the chosen persona's full pack lives on disk in
`%APPDATA%/dev.aether.desktop/personas/active/<slug>/` at any given
time.

### Switch flow — atomic uninstall-then-install

Settings → Companion → Change character runs:
1. Audit: `persona.switch start (current → next)`
2. Download next pack to `cache/partial_downloads/`
3. Verify SHA-256 + Ed25519 manifest signature
4. Atomic move: extract next to `personas/active/<next>` AND
   delete `personas/active/<current>` in a single transaction
5. Audit: `persona.switch complete`
6. Hot-reload L6 persona engine
7. Failure mid-switch leaves the current persona installed and
   functional — never delete-then-download.

### User memory is persona-independent

Switching characters does not forget anything the user has shared.
The persona is a presentation layer (face, voice, archetype-shaped
system prompt). Conversation history, durable facts, and memory
lanes live in `memory.db`, which is user-keyed and never wiped on
switch. This is consistent with ADR-0001's domain reconciliation.

### Heavy per-persona model assets are explicitly deferred

Heavy per-persona model assets would push per-pack footprint from
~15 MB to ~150+ MB. Current plan: shared base model + system-prompt
steering only. Re-open this only if a downstream eval shows
system-prompt steering insufficient for at least one persona's
target register, AND the gain justifies the +10× per-pack download
cost.

### Delivery channel

- **v0 (preview / community edition):** GitHub Releases tagged
  `persona-<slug>-<version>` with the pack zip as the release
  artifact. Free, no infra, public-readable, integrity hashes
  provided by GitHub.
- **v1+ (when scale matters):** Cloudflare R2 behind
  `https://companion.dbhavery.dev/persona-manifest.json`. Egress
  free, storage cheap.

Manifest is the single source of truth. App fetches manifest before
showing the wizard, validates Ed25519 signature against the bundled
public key, then trusts the asset URLs and SHA-256 hashes inside.

### Integrity and policy

- SHA-256 verification on every downloaded pack against the
  manifest entry. Mismatch → reject, surface error, do not install.
- Ed25519 signature on the manifest itself, signed offline by Don's
  release key.
- Audit row on `persona.download`, `persona.install`,
  `persona.uninstall`, `persona.switch`. Each emits a structured
  `L5Event::PolicyDecision`.
- First download is approval-gated in the wizard ("download ~XYZ MB?"
  → user clicks Approve). Subsequent same-persona re-downloads (e.g.
  to repair corruption) skip the prompt because the prior approval
  grant is durable for that capability.

## Consequences

### Positive

- Installer stays slim (~1.2 MB persona footprint vs ~135 MB if
  baked).
- Persona engine state is unambiguous: at most one active persona
  on disk.
- Switching cost is a 15 MB download, ~30 s on typical connections.
  Cheap enough that users can experiment freely with the cast.
- User's relationship state (memory, history) is preserved across
  switches by construction. This makes "try a different persona for
  a while" a low-stakes operation.
- Per-pack footprint is small enough to ship via GitHub Releases for
  v0; no infra required.

### Negative / costs paid

- First install of any persona requires network. **Mitigation:**
  ship Aurora's full pack inside the installer as a guaranteed-
  available fallback for offline first-run. Costs ~15 MB on the
  installer; recommended for v0.
- Switching deletes the previous persona's pack. If the user
  switches back, they re-download. **Acceptable:** the network cost
  is ~15 MB and the alternative (multiple packs on disk) violates
  the "only one active" invariant.
- New build pipeline surface: `tools/build-persona-previews/` and
  `tools/build-persona-pack/`. **Acceptable:** these are
  release-only tools, not runtime.
- New L5 capabilities (`persona.download`, `persona.install`,
  `persona.uninstall`, `persona.switch`). **Acceptable:** all four
  follow the same approval pattern as existing remote capabilities.

### Trade-offs deliberately taken

- **No heavy per-persona model assets in v0.** Personas differentiate
  by system prompt + voice + face only. If a register can't be hit by
  steering alone, that's a future ADR and a future per-pack cost
  hike, not a v0 concession.
- **No background pre-fetch of "the persona you might switch to."**
  Switches are explicit and approval-gated. No speculative
  downloads.
- **No multi-persona concurrent install.** The user runs with
  exactly one persona on disk. This simplifies engine state but
  means the user can't A/B compare two personas in a single
  session.

## Build / packaging implications

| Surface | Change |
|---|---|
| `apps/desktop/public/personas-previews/` | New dir. Holds bundled preview bundles. Generated by `tools/build-persona-previews/`. |
| `personas/<slug>/` | Stays as canonical source. Full assets here are zipped into Tier-2 download. NOT directly bundled in the app. |
| `packages/l6-persona/` | Add `install_pack(slug, version)`, `uninstall(slug)`, `current() -> Option<PersonaId>`, `switch(slug)` trait methods. |
| `packages/l5-policy/` | Add capabilities `persona.download`, `persona.install`, `persona.uninstall`, `persona.switch`. |
| New `tools/build-persona-pack/` | Zips `personas/<slug>/` into `<slug>-<version>.zip`, emits SHA-256, generates manifest entry. Run as part of release. |
| New `tools/build-persona-previews/` | Crops + transcodes assets for the bundled preview bundle. Run as part of release. |
| New `infra/persona-manifest/` | Generates and signs the master manifest. Don signs offline before publishing. |

Per `aether/CLAUDE.md` §3, `packages/l6-persona/` and
`packages/l5-policy/` modifications require coordinator-gated PRs.
The new `tools/*` directories are not coordinator-gated (CLAUDE.md
§4 lists `tools/` as governance/codegen, not as packages).

## Empirical Validation (deferred)

This ADR is theoretical and accepted on design grounds. Real
validation arrives when:
1. `tools/build-persona-pack/` runs end-to-end on the 9 shipped
   packs and produces 9 valid zips.
2. The desktop wizard shows previews from
   `apps/desktop/public/personas-previews/` without
   network.
3. A user-flow test installs a persona end-to-end (download → SHA
   verify → extract → engine hot-reload).
4. A switch-flow test handles atomic uninstall+install correctly,
   including the failure-mid-switch path.

Until those checkpoints land, this ADR is the *design contract* for
the work, not proof the work landed.

## Open items (deferred to follow-on ADRs)

- **OQ-1:** Update channel semantics — auto-update vs notify-only
  when `persona-<slug>-1.1.0` ships. Default plan: notify-only.
  Confirms with the desktop-app update posture once that lands.
- **OQ-2:** Telemetry on which persona is picked. Default plan: no
  telemetry; if added, opt-in only with an explicit Settings panel
  and "share which persona I picked, anonymously" checkbox default
  off.
- **OQ-3:** Bundling Aurora's full pack inside the installer as
  offline-first-run fallback. Recommended for v0; confirms when the
  v0 installer pipeline lands.

## References

- `personas/CHARACTERS.md` — cast roster + lock-before-scale rules
- `docs/adr/ADR-0001-memory-domain-reconciliation.md` — domain
  separation that lets §4 hold
- `docs/adr/ADR-0006-hardware-tier-model.md` — hardware envelope
- 2026-04-28 night session commits c98d5f7 → 9aea4f2 — the cast
  shipping that this ADR follows
