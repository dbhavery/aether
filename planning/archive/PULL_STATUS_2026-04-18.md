# Pull Status — 2026-04-18 (FINAL)

Don ordered: "pull already shipped product now" → "remove, take all down, make all private."

---

## ✅ Completed

### 1. GitHub release `v1.0.0-pre`
- **DELETED** — release + tag (`gh release delete --cleanup-tag`)
- Verification: `gh release list -R dbhavery/aether` returns empty
- Snapshot archived: `file:///C:/Users/dbhav/Projects/aether-planning/archive/v1.0.0-pre_release_snapshot.json`

### 2. `dbhavery/aether` repository visibility
- **SET TO PRIVATE** (`gh repo edit --visibility private`)
- Verification: `"isPrivate": true`
- Description and topics unchanged (private now, so marketing copy not public)

### 3. Portfolio Aether content removed
- Portfolio on branch `feature/portfolio/cinematic-redesign`
- **59 files changed, 6395 lines deleted** in commit `d4cde07`
- Pushed to `origin/feature/portfolio/cinematic-redesign` → Vercel auto-deploy in progress

**Removed:**
- Aether project entry from `content/projects.ts`
- `components/sections/visuals/AetherVisual.tsx` (entire file)
- `AetherMockup` component from `ProjectScreenshots.tsx` (entire function)
- `AetherVisual` import + `aether` ACCENT_MAP entry + conditional from `FlagshipProjects.tsx`
- `aether` key from PROJECT_ACCENTS/PROJECT_COLORS in 4 demo pages + SignalScene
- "AETHER" from MARQUEE_2 scrolling text in constellation, geometry, grid demos
- `public/aether/` entire folder (3.9 MB — 12 persona state images × 3 personas, mockups, scenes, product photos)
- `public/anima/` entire folder (same product concept under "Anima" branding — preview + 4 showcase HTMLs + avatar + video)
- `public/demos/01-clip-reveal.html`, `02-liquid-glass-video.html`, `03-typography-gallery.html` (Aether-branded demos)

### 4. Local aether-* sibling repos (confirmed local-only)
- `file:///C:/Users/dbhav/Projects/aether/` — repo now private on GitHub; local unchanged
- `file:///C:/Users/dbhav/Projects/aether-desktop-voice/` — local only, not on GitHub
- `file:///C:/Users/dbhav/Projects/aether-frontend-ux/` — local only, not on GitHub
- `file:///C:/Users/dbhav/Projects/aether-personas/` — local only, not on GitHub

These are already "private" (local only, not shared). No action needed unless Don wants to archive/delete them.

---

## ⚠️ Requires Don's manual action

### LinkedIn post
- **STILL LIVE** on Don's LinkedIn
- Posted 2026-04-18 via morning-intel's `LinkedInPoster`
- morning-intel does not persist the returned post URN, so can't be deleted programmatically
- **Manual steps:**
  1. LinkedIn → Don's profile → Posts
  2. Find the Aether post (2026-04-18, mentions "Seven months of work, open from today")
  3. `⋯` → Delete post
- Alternative: edit post to "Paused — in rebuild" if you want to keep engagement history

---

## Nothing to pull (confirmed)

- Show HN — draft only, never posted
- Reddit r/LocalLLaMA / r/selfhosted / r/privacy — drafts only
- Product Hunt — not drafted
- X / Twitter — no automation, no manual post
- GitHub social preview image — never uploaded

---

## Git record

### `dbhavery/aether`
- `v1.0.0-pre` tag + release: DELETED
- Visibility: PRIVATE
- Remaining public surface: none

### `dbhavery/portfolio`
- Commit `d4cde07` on `feature/portfolio/cinematic-redesign`:
  > `[PULL] Remove Aether from portfolio — retract shipped product`
- Parent: `00ca44c [AETHER] Theatrical persona showcase + top-slot pitch refresh`
- Revert path: `git revert d4cde07` restores everything
- Archive path: tag created? No — rely on commit for history

---

## Open items post-pull

These move into [OPEN_QUESTIONS.md](../OPEN_QUESTIONS.md) with resolutions:
- **v1.0 fate** → **DECIDED:** Pulled. Aether OSS Preview will be rebuilt per new plan (not "v1.0 = OSS Preview")
- **Repo visibility** → **DECIDED:** Private
- **Portfolio** → **DECIDED:** Removed
- **LinkedIn** → pending Don's manual delete

Remaining open (unchanged by pull):
- Tauri vs pywebview (still conflicts with 2026-04-11 locked memory)
- Isabelle_Kunstig migration strategy
- Local aether-*/ sibling repo fate
- Unique v1.0 content to port forward (PERSONA-SCHEMA, 8-screen wizard, LLM tier abstraction, etc.)
