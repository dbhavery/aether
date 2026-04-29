# Public Rename: Aether → Companion (planning doc)

> **Don directive 2026-04-28 night:** "Project name change! Public
> facing name now = 'Companion'. Make all necessary changes, updates
> when you get a chance in the next 24 hrs."
>
> **Status:** planning only — no code changes yet. Next session
> executes per this doc, atomic commits per surface.

---

## Scope split

### CHANGE (public-facing — what users see)

These are the surfaces a real user / GitHub visitor / new dev sees:

| # | Path | What changes |
|---|---|---|
| 1 | `README.md` | "Free Aether — Community Edition" → "Free Companion — Community Edition"; first paragraph; live showcase URL probably stays `dbhavery.dev/aether` since portfolio is a separate repo (Don's call) |
| 2 | `apps/desktop/src-tauri/tauri.conf.json` | `productName: "Aether"` → `"Companion"`; window `title: "Aether"` → `"Companion"`. Identifier `dev.aether.desktop` STAYS (changing breaks app updates + user data paths). |
| 3 | `apps/desktop/index.html` | `<title>` if it says Aether |
| 4 | `personas/CHARACTERS.md` | "Aether Persona Cast" heading and intro sentence |
| 5 | `personas/*/persona.yaml` | Header comments "Canonical persona pack for the Aether first-run wizard" → "...Companion first-run wizard" (multiple personas: aurora, caelum, luma, marcus_chen, others) |
| 6 | Persona license notes in `metadata.yaml` files | "owned by Aether under the persona pack's custom_aether license" → "owned by Companion under the persona pack's `custom_companion` license"; OR keep `custom_aether` license name and just say "owned by Companion" — see decision in §"License rename or keep" below |
| 7 | Any wizard / onboarding UI string in `apps/desktop/src/` that says "Aether" | "Companion" |
| 8 | Any system prompt or persona text that surfaces "Aether" by name to the user | "Companion" |

### KEEP (internal — invisible to users)

These should NOT change — changing them is destructive and gains
nothing user-facing:

- **Repo / directory name**: `Projects/aether/` and GitHub `dbhavery/aether`. Internal codename. (Don can rename the GitHub repo if he wants; that's a separate Don action with downstream URL implications.)
- **Tauri identifier**: `dev.aether.desktop`. Changing this breaks app auto-update channels and user data paths. Permanent codename.
- **Crate / package names**: `aether-*` Rust crates and `aether-*` TS packages stay. Internal identifiers.
- **Code identifiers / variable names / module names**: `aether_db`, `AetherEvent`, etc. all stay.
- **Database file**: `aether.db` and `aether_audit.db` stay. Renaming breaks all existing user data.
- **Internal docs (planning/, ROADMAP.md, PERSONA_ROADMAP.md, ADRs, handoffs)**: stay as "Aether." These are agent/dev artifacts, not public.
- **Git commit messages going forward**: can use either; they're a forever record. Probably "aether" for technical commits, "Companion" only when discussing user-facing strings.
- **MEMORY.md reference** to "Aether" as project name: stays (internal).
- **CLAUDE.md** at repo root: stays (internal, agent-facing).

### MAYBE (Don picks)

- **Public name on GitHub repo**: Don can rename `dbhavery/aether` → `dbhavery/companion` if he wants the public repo URL to match. That's a Don-only action (GitHub web UI). Has downstream effects on every clone command, doc link, badge URL. Recommend: keep `aether` as the public repo URL OR rename and accept the migration.
- **Portfolio showcase URL**: `dbhavery.dev/aether` — lives in the portfolio repo, not this one. Don's call whether to keep or rename to `dbhavery.dev/companion`.
- **Crate / npm package public publication names** (if/when published): could be `companion-core`, `companion-policy`, etc. — but that's only when publishing, and we're not publishing yet. Defer.

---

## License rename or keep

The persona pack license is currently called `custom_aether`. Two
options:

**(a) Rename to `custom_companion`** — consistent with new public name.
Touch every metadata.yaml. Light lift, ~7 personas × 1 string each.

**(b) Keep `custom_aether`** — license names are forever. Renaming
licenses creates legal ambiguity if the old license was attached to
prior committed work. Better to rename the license file path/name in
LICENSE.md but keep the *identifier string* stable.

Recommendation: **(b) keep `custom_aether` as the identifier string**.
Update the prose in metadata.yaml notes from "owned by Aether" →
"owned by Companion" but leave the license-identifier `custom_aether`
unchanged. This is the same pattern as Mozilla keeping `mozilla.org`
as a domain even though products are branded Firefox.

---

## Rollout (next session)

Ordered atomic commits, each independently reviewable:

1. `docs: rename public — README.md` (top-level marketing surface)
2. `apps(desktop): rename productName + window title to Companion` (the actual app the user launches)
3. `personas: rename public references to Companion in YAML headers + metadata notes` (cosmetic, no schema change)
4. `apps(desktop): rename UI strings to Companion` (wizard / onboarding / about-screen strings if any)
5. Update `personas/CHARACTERS.md` heading + intro to "Companion Persona Cast"
6. Update `RENAME_TO_COMPANION.md` (this file) to mark COMPLETE + archive

Each commit references this plan doc.

---

## Out-of-band actions (Don, optional)

- GitHub repo rename `dbhavery/aether` → `dbhavery/companion` (Don only, GitHub web UI). Preserves all stars, issues, PRs; old URL auto-redirects.
- Portfolio showcase URL update at `dbhavery.dev/aether` → `dbhavery.dev/companion` (separate repo).
- Any private branding / domain / Tailscale hostname still using "aether" (Don's call).

---

## Decision log

| When | What | Why |
|---|---|---|
| 2026-04-28 night | Plan written | Don directive: public name = Companion |
| TBD next session | §1 README rename committed | |
| TBD next session | §2 Tauri productName rename committed | |
| ... | | |

---

## Why not rename everything

The rule is: **change what users see, keep what they don't.** Internal
codenames are a normal pattern (Microsoft "Longhorn" → Windows Vista,
Apple "Mac OS X" internal → "macOS" public, etc.). Renaming internal
identifiers gains nothing except more diff and more risk of breaking
auto-update channels and user data paths.

If Don wants the internal codebase fully renamed too, that's a much
bigger effort (~500+ files, package republish, migration scripts for
existing users' data paths, GitHub URL break). Ask before doing that.
