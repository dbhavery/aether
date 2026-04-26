# UX Audit — Live Dev-Build Dogfood (Phase 6)

> **Session:** 2026-04-25 autonomous run, Phase 6 (live UX QA on the dev build).
> **Branch:** `dev`. Tip at session start: `b2b1ddf`. Working tree had ongoing
> parallel-agent edits to `backfill.rs`, `embeddings.rs`, `commands.rs`,
> `state.rs`, `hf_provider.rs`. Build succeeded after a 60s wait for the
> parallel agent to land helper functions (`cancel_aware_sleep`,
> `bump_recovered`).
> **Tester:** Front-End QA agent driving the live Tauri shell via
> `windows-app-pilot`. Window observed at (2072, 320) on Don's secondary
> monitor, 976×759.
> **Constraints:** READ-ONLY on source. Bug findings documented, not fixed.

---

## 1. Executive verdict

**NEEDS-POLISH.** The new ADR-0007/ADR-0009 surfaces *render correctly* and
match the research-backed recommendations in `AUDIT_ROW_UI_RESEARCH.md`.
What needs work is **not** the new code — it's the **header chrome** the
new code sits beside. At the 976px window width the shell ships at, the
header overflows badly: the route badge wraps to three lines and the
presence chip clips a glyph. The new Trust drawer surfaces themselves
are clean, well-copied, and accessible.

Verdict by surface:

| Surface | Verdict |
| --- | --- |
| Trust drawer / Audit tab (ADR-0009 v2 row) | **PASS** |
| Trust drawer / Memory tab | **PASS** |
| Trust drawer / Retrieval tab (ADR-0007) | **PASS** |
| Trust drawer / History tab | **PASS** |
| Toast surface (ADR-0007 D6) | **NOT TESTED** — see §6.1 |
| Header chrome (route badge + presence chip + readiness dot) | **NEEDS-FIX** |
| Empty-session COMPANION card | **PASS** |

---

## 2. By-state findings

### 2.1 Readiness state — observed: `disabled`

The Retrieval tab on the dev build's default config renders the
`disabled` branch:

> "Retrieval is off. Toggle `embeddings.enabled = true` in memory settings
> to activate."
> "Active tier: **forge**. Embedding model would be `bge-m3` (~1.2 GB)."

Screenshot: `06_retrieval_tab.png`.

**Observation.** Copy is calibrated and honest. The "would be" hedging is
the right move when retrieval is off — it tells the user what *would* run
without lying about what *is* running. Active tier is "forge" — matches
the 3090 Ti hardware (24 GB VRAM) per ADR-0008 tier detection. The
embedding-model name is the tier default (`bge-m3` / 1.2 GB) because no
explicit `memory.embeddings.provider` is configured. This is correct
behavior and matches what `activeModel()` resolves to in
`apps/desktop/src/components/RetrievalTab.tsx:101-117`.

**Could not test.** `unknown` (pre-probe), `not_ready` (Ollama down with
embeddings.enabled), `ready` (Ollama up with embeddings.enabled), or any
toast transitions. Reason: with `embeddings.enabled = false` (the dev
default), readiness probes return `disabled` regardless of Ollama state,
and the ToastContainer transition rules silently skip `disabled` ↔
anything (correct per `ToastContainer.tsx:55`). Flipping the toggle
would require editing a non-existent `memory.json` and restarting the
shell — out of scope for this read-only audit phase.

**Recommendation.** A future polish session that wants to validate the
toast surface should add a `memory.json` that flips
`embeddings.enabled = true` and replays the kill-Ollama → restart-Ollama
cycle while watching the bottom-right toast region.

### 2.2 ReadinessIndicator dot — observed: hidden when `disabled`

Per `ReadinessIndicator.tsx:58`, the dot is hidden for both `ready` and
`disabled`. In the captured header (screenshot `09_drawer_closed_header_detail.png`)
the dot left of "quiet" is the **presence indicator**, not the readiness
indicator. So the readiness dot is *correctly* invisible. But because
the presence indicator is also a tiny gray dot, this raises a future
collision risk: if Don ever places the readiness badge next to the
presence dot, two near-identical dots will read as one cluttered glyph.
Recommendation: when readiness goes visible, anchor it to the **Trust**
nav button (per ADR-0007 D6 placement options) so it reads as
"open Trust to see the problem", not "presence is weird".

---

## 3. Audit row v2 rendering — vs. AUDIT_ROW_UI_RESEARCH.md

**Observed v2 row** (screenshot `04_trust_audit_open.png`):

```
┌────────────────────────────────────────────────────────────────┐
│ ALLOWED                                                  a-1   │
│                                                                │
│ " hi "                                                         │
│                                                                │
│ files.read · (no specific resource)                            │
│                                                                │
│ ▶ Aether ran retrieval; nothing matched                        │
└────────────────────────────────────────────────────────────────┘
```

| Recommendation in research doc | As-implemented? | Comment |
| --- | --- | --- |
| §2.1 (1) Decision label colored mono uppercase top-left | **Yes** | `ALLOWED` in green mono caps. Pixel-perfect. |
| §2.1 (2) User utterance as strong signal at 12.5–13 px | **Yes (12.5px)** | Quoted with smart quotes; reads as a quote, not code. Research recommends 13 px + `leading-snug` — small future polish. |
| §2.1 (3) Provenance summary always visible | **Yes (in `<summary>`)** | Visible even when `block_present: false`. Research §2.3 recommends hoisting out of `<summary>` so meaning isn't tied to disclosure chrome — confirmed gap. |
| §2.1 (4) Capability + scope as muted secondary line | **Yes** | `files.read · (no specific resource)` reads correctly subordinate. |
| §2.1 (5) Audit ID + schema badge top-right smallest | **Yes** | `a-1` rendered top-right in the dimmest mono. |
| §2.4 Schema-v1 badge | **Could not observe** | Fresh DB — no v1 rows exist to render. Code path at `TrustDrawer.tsx:354-362` is correct by inspection but unexercised in live UI. |
| §2.6 Density 12-15 collapsed v2 rows per drawer | **Holds** | One row at ~96 px in a ~640 px scrollable region; eyeball confirms density is fine. |

**Disclosure expansion behavior (screenshot `05_audit_disclosure_expanded.png`).**
Clicking the disclosure on a row where `block_present: false` correctly
does not reveal a hit list (there's nothing to reveal). The summary line
gets a focus ring but the expanded region stays empty. This is the exact
failure mode the research doc §2.3 flagged: when there's nothing to
expand, the `<details>` chrome is misleading — it suggests there IS
more, but clicking reveals nothing. **Confirmed gap.** Hoisting the
summary out of `<summary>` (research §2.3a) and conditionally rendering
the chevron only when `block_present && hits.length > 0` (research §3.1
implication) would fix this.

---

## 4. Backfill flow

**NOT TESTABLE in current state.** With `embeddings.enabled = false` the
Retrieval tab renders the `disabled` branch and the "Backfill now" button
never appears (it's gated by `readiness.kind === "ready"` at
`RetrievalTab.tsx:289`). To validate the Phase 4D async-spawn fix and
the Phase 2 "skipped X already-embedded" surface, a follow-up session
needs to:

1. Add `memory.json` with `embeddings.enabled = true`.
2. Ensure Ollama has bge-m3 pulled (the forge tier default).
3. Launch the shell, open Trust → Retrieval, observe the `ready` branch.
4. If `unembeddedCount > 0`, click `Backfill now` and verify the progress
   strip animates (Phase 4D) and the post-run summary surfaces the
   skipped count.

**Code-review-only observations on the backfill UI** (based on
`RetrievalTab.tsx:362-403`):

- Progress strip uses the `bg-aether-ok` token with `transition-all` —
  good, will animate smoothly.
- Cancel button is rendered alongside the strip — good, gives the user
  an out without nesting menus.
- The `processed = completed + skipped_already_embedded` arithmetic
  (line 370) is honest: skips count toward the bar so 1000-row
  re-runs don't appear stuck.
- The post-run summary (lines 322-334) handles all four state combos
  (completed only, completed+skipped, +failed, +cancelled) — solid.

---

## 5. Bugs surfaced

### 5.1 [MAJOR] Header layout overflow at 976 px window width

**File.** Likely `apps/desktop/src/App.tsx` or wherever the top nav
strip lives (header was not in mandatory-reading list — code path not
read this session; locating it is left to the fix session).
**Observed in.** Every screenshot. Most clearly in `01_initial_state.png`
and `09_drawer_closed_header_detail.png`.

**Symptom.** At the dev build's default 976 px window width:
- The route badge "Reflex stub (no model)" wraps onto **three lines**
  ("Reflex" / "stub" / "(no" / "model)") inside what's clearly meant to
  be a single-line chip.
- The presence indicator + label "● quiet" reads as "● quietl" because
  the label `quiet!` (presumably) is being clipped by the next sibling
  ("Reflex...") encroaching from the right.
- This consumes ~50 px of vertical space the header was not designed for
  and pushes the layout heuristics off.

**Repro.** Launch `npm run tauri:dev`, observe header at default window
width.

**Severity.** MAJOR — this is the *first thing* a new user sees, and it
reads as broken. The chips need either:
- A wider min-width on the route chip (and the chip text formatted
  inline as `Reflex stub · no model` rather than two parenthetical
  fragments), or
- Truncation with ellipsis + tooltip on hover, or
- A responsive collapse to icon-only at narrow widths (consistent with
  the research §1 "one strong signal" principle).

### 5.2 [MAJOR] Focus management between Trust drawer and chat input

**File.** Likely `apps/desktop/src/App.tsx` or chat-input component.
**Observed in.** Screenshots 03 → 04 → 05 show stray characters
("a", "are you good?", "yo?") accumulating in the chat input
("Message Aurora…") even though the user (me) was clicking exclusively
inside the Trust drawer at coordinates well to the right of the input.

**Symptom.** When focus shifts between the chat input and the drawer,
modifier keys / accidental keystrokes that *should* be inert because
they're not over the input still register as text input. This implies
the chat input is keeping focus across drawer interactions — a focus
trap escapes outward into the input rather than staying within the
drawer.

**Repro.**
1. Send any message, getting cursor focus into the chat input.
2. Open Trust drawer.
3. Click any tab or row inside the drawer.
4. Type any character expecting it to be a hotkey.
5. Observe the character appear in the chat input rather than triggering
   a drawer-local action.

**Severity.** MAJOR — silent text accumulation in a *messaging* UI is a
trust violation. The user could send a message they didn't intend.

**Recommendation.** When the Trust drawer opens (and gets `aria-modal`
or a focus trap), the chat input should `blur()`. When the drawer
closes, focus should return to the chat input only if the user
explicitly invoked the close action via the keyboard (not via a click
elsewhere).

### 5.3 [MINOR] Disclosure chrome misleads when `block_present: false`

**File.** `apps/desktop/src/components/TrustDrawer.tsx:395-425`.
**Observed in.** `05_audit_disclosure_expanded.png`.

**Symptom.** A `<details>/<summary>` element is rendered for every v2
row regardless of whether there are hits to disclose. Clicking the
disclosure on a row with `block_present: false` reveals nothing, but
the chevron still appears and the focus ring still confirms the click
landed. The user clicked a button that did nothing visible.

**Severity.** MINOR — cosmetic, but it's exactly the failure mode
`AUDIT_ROW_UI_RESEARCH.md` §2.3 anticipated.

**Recommendation.** Adopt research §2.3a (hoist summary out of
`<summary>`) and conditionally render the chevron only when
`provenance.block_present && provenance.hits.length > 0`.

### 5.4 [MINOR] Conversation pre-population on first launch

**File.** Memory backend. Not a UI bug per se.
**Observed in.** `01_initial_state.png` and `03_after_focus.png` — fresh
boot showed pre-existing conversation history immediately scrollable.

**Symptom.** The "first session" experience is noisy because durable
memory persists across shell restarts. New users won't see the clean
empty-state COMPANION card (`09_drawer_closed_header_detail.png`) until
they explicitly click "New session". For dev / dogfood / demo workflows
this hides the polished onboarding card.

**Severity.** MINOR — by design (memory IS the product), but a
"don't show pre-existing conversation on first session of a brand-new
install" branch would help showcases.

---

## 6. Polish opportunities

### 6.1 Toast surface needs a live test

The ToastContainer lives in code (`ToastContainer.tsx`), is wired into
the App root (verified via inspection), and has the right transition
rules — but it could not be exercised in this session because the
`disabled` readiness state silences all toast transitions per design.
A 5-min follow-up that flips `embeddings.enabled = true` would let us
visually validate the bottom-right placement, the 4-second auto-dismiss,
and the warn/ok tone palettes.

### 6.2 Audit row: bump utterance to 13 px + `leading-snug`

Adopt research §2.5 — single-line class swap from `text-[12.5px]` to
`text-[13px] leading-snug` on the utterance div. Makes the quote read
as a sentence, not a code line. ~30-second change, zero risk.

### 6.3 Audit row: replace `<ul>` with inline chips

Adopt research §2.3b — when a v2 row has 3+ hits, the current `<ul>` of
hits will read as a stack of bullet points. Replace with `inline-flex
flex-wrap` chips. Could not observe this empty (no hits in current data)
but the rendering pattern is in `TrustDrawer.tsx:407-423`.

### 6.4 Retrieval tab: link "memory settings" copy to the actual settings

Current copy: "Toggle `embeddings.enabled = true` in memory settings to
activate." There is a Settings nav button visible in the header. The
phrase "memory settings" is currently un-clickable text. Make it a
button that opens the Settings panel (or the Memory tab if that's where
the toggle lives) — saves the user from hunting.

### 6.5 Empty-state COMPANION card reads beautifully — make it the "first session" hero

The COMPANION card on a fresh New session ("Aurora v1 · balanced — Warm
and grounded. A calm presence for focused work. Local-first by default.")
is the strongest piece of identity copy in the app. Consider showing
this card briefly on every fresh session start (not just after a New
session click) until the first message is sent.

### 6.6 Presence chip: use a longer, clearer label

The "quiet" label paired with a tiny dot reads as ambiguous chrome until
you know what it means. "Quiet · idle 0s" or "Active" or "Away" with a
tooltip explaining "Aether's read on whether you're actively at the
keyboard" would orient new users.

---

## 7. Accessibility findings

- Tab order: not tested with keyboard-only navigation in this session;
  Tauri shell didn't respond to programmatic key sends as cleanly as
  click sends. Recommend a follow-up keyboard-nav pass.
- ARIA roles: per code review, Trust drawer has `role="complementary"`
  and `aria-label="Trust centre"` on the wrapper, `role="tablist"` on
  the tabs, `role="tab"` + `aria-selected` on each TabButton, `role=
  "radiogroup"` on the History filter, `role="radio"` + `aria-checked`
  on each FilterPill, `role="progressbar"` + `aria-valuenow/min/max` on
  the backfill progress strip, `role="status"` + `aria-live="polite"`
  on Toast. **Strong baseline.**
- Focus trap: per Bug 5.2, focus does NOT trap in the drawer — it
  escapes back to the chat input.
- Color contrast: dark theme uses `aether-text` / `aether-muted` /
  `aether-dim` tokens consistently. Not measured against WCAG AA in
  this session; recommend a Stark or axe pass on a future polish.

---

## 8. Console errors observed

None visible — the Tauri WebView2 devtools were not opened in this
session (would require a separate console capture). Per Phase 6 scope,
this is left for a future session that opens devtools alongside the
shell.

---

## 9. What works well

- **Trust drawer copy is uniformly excellent.** "What Aether decided, in
  order" / "What Aether remembers, by domain" / "Whether Aether can find
  what it remembers" / "Recent turn timing and usage" — every header has
  a calibrated, honest one-liner.
- **Retrieval tab footer disclaimer** ("Retrieval is auxiliary. Turns
  still flow when it's off; only the 'remember what we said' quality
  drops.") is exactly the right tone — calibrated, not alarming.
- **Audit tab footer** ("Every decision is sealed in an append-only
  hash-chained log.") is a trust signal at the right altitude.
- **Memory tab card layout** with STANDARD / RISK AUTO badges, per-row
  Edit/Forget buttons, clear domain-scoped Forget all button — solid
  trust UX.
- **History tab filter pills** with live counts (All/Media/Voice/
  Presence) work as advertised; clean radio-group ARIA.
- **Empty COMPANION card** on a fresh New session is the strongest
  identity moment in the app.

---

## 10. Test coverage notes

**Tested via live shell interaction:**
- Initial state render
- Trust drawer open/close
- Audit tab v2 row layout
- Audit row disclosure click
- Retrieval tab disabled-state render
- History tab render with seeded telemetry
- Memory tab render with seeded session data
- New session click → COMPANION card

**Tested via code review only:**
- ReadinessIndicator dot for not_ready / unknown (state never reached)
- ToastContainer transition rules (no toast triggered)
- Backfill UI flow (button never visible due to disabled state)
- Schema-v1 badge rendering (no v1 rows in fresh DB)
- Backfill progress strip animation (button never reached)
- Backfill cancel flow (button never reached)

**Not tested:**
- Keyboard-only navigation through the drawer
- WCAG color contrast measurement
- Tauri WebView2 devtools console output
- Window resize / responsive breakpoints (Tauri windows don't reflow
  the way browser windows do; this needs separate validation)

---

## 11. Screenshot index

All paths absolute, forward-slash form for clickable links.

| # | File | What it shows |
| --- | --- | --- |
| 01 | file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-25/ux_audit_screenshots/01_initial_state.png | Initial Aether shell with seeded conversation |
| 03 | file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-25/ux_audit_screenshots/03_after_focus.png | After window focus; conversation scrolled |
| 04 | file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-25/ux_audit_screenshots/04_trust_audit_open.png | Trust drawer open on Audit tab; v2 row visible |
| 05 | file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-25/ux_audit_screenshots/05_audit_disclosure_expanded.png | Audit row disclosure clicked (no expansion — block_present: false) |
| 06 | file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-25/ux_audit_screenshots/06_retrieval_tab.png | Retrieval tab disabled-state |
| 07 | file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-25/ux_audit_screenshots/07_history_tab.png | History tab with two telemetry rows |
| 08 | file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-25/ux_audit_screenshots/08_memory_tab.png | Memory tab with SESSION domain card |
| 09 | file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-25/ux_audit_screenshots/09_drawer_closed_header_detail.png | Empty New-session state with COMPANION card; clearest header overflow view |

Note: filename `02_*` was deleted — that capture went to a Chrome
window with the same "Aether" title rather than the Tauri shell.
Renumbering left in place (01, 03, 04, …) so commit references stay
stable.

---

(end of audit)
