# Audit-Row UI Research — ADR-0009 v2 Rendering

> **Session:** 2026-04-25 autonomous run, Phase 1 follow-up.
> **Scope:** Research-backed visual design recommendations for `AuditList` /
> `AuditRow` in `apps/desktop/src/components/TrustDrawer.tsx` after ADR-0009
> landed `original_utterance`, `model_input_utterance`, and
> `retrieval_provenance` on v2 audit rows.
> **Status:** Research only. No code changes in this phase. A future
> implementation session will refine `AuditRow` against these recommendations.

---

## 1. Patterns observed

### 1.1 Linear / generic activity-feed pattern — "one strong signal per row"

The dominant pattern across modern audit UIs (Linear, HighLevel's redesigned
audit log, Untitled UI's activity-feed components) is **one strong signal per
row, everything else collapsed**. Each row gets a single dominant line — usually
the human-readable subject of the action — plus a thin metadata strip
(timestamp, actor, tiny status badge). Detail lives behind a row click that
opens a right-side drawer or expand-in-place disclosure, so the user never
loses scroll position in the table. HighLevel's 2024 audit-log redesign
explicitly cites "drawer view + keyboard navigation (←/→) + consistent design
system spacing" as the friction-reducers that made their log usable for triage.
The implication for Aether: the v2 row's user-utterance line *is* the strong
signal; everything else (capability, scope, provenance) is secondary and
should compete less for attention.

Sources:
- https://help.gohighlevel.com/support/solutions/articles/155000006667-audit-logs-introducing-the-new-design-experience
- https://appmaster.io/blog/audit-logging-internal-tools-activity-feed
- https://www.untitledui.com/components/activity-feeds

### 1.2 Notion / GitHub — actor + verb + object as the dominant phrase

Notion's page-history surface and GitHub's PR review timeline both phrase each
event as a sentence: "Don edited *Recipe* 3 hours ago", "claude-bot pushed 2
commits", "alice approved this pull request". The verb is the strong signal
and is usually color-coded subtly. GitHub additionally distinguishes
**review comments** (live in the conversation timeline) from **commit
comments** (now suppressed from the PR timeline as of August 2022 because
they were polluting the conversation surface — exactly the failure mode
ADR-0009 is correcting on Aether). The lesson is that mixing two semantic
classes of content into one row breeds confusion; better to keep one clean
class as the row body and push the other behind a disclosure that the user
opts into. Aether's `original_utterance` (what the user said) and
`retrieval_provenance` (what the system also saw) are exactly this kind of
two-class mix. ADR-0009's design — utterance prominent, provenance under
`<details>` — already aligns with the GitHub-2022 lesson.

Sources:
- https://github.blog/changelog/2022-08-03-commit-comments-no-longer-appear-in-the-pull-request-timeline/
- https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests

### 1.3 Carbon Design System — high-vs-low-contrast notification styling

Carbon Design System does not ship a dedicated "activity log" component, but
its notification-pattern guidance is the most rigorous public guidance on
visual hierarchy for log-style surfaces. The key principle: **default to
low-contrast styling; reserve high-contrast for genuinely critical rows**.
Carbon also recommends keeping notification body copy to two lines and
exposing longer detail behind a "View more" affordance (their actionable-
notification pattern). For status indication, Carbon uses small subtle
badges with numbers as the entry-point cue — never as the dominant element.
For Aether, this argues for: (a) keep the `pre-ADR-0009` schema-v1 badge
small and warm-colored (it currently is); (b) keep the decision label
(`allowed`/`denied`/etc.) as the row's only colored element; (c) avoid any
new colored chip for retrieval — use a glyph or muted text instead so the
row stays calm.

Sources:
- https://carbondesignsystem.com/patterns/notification-pattern/
- https://carbondesignsystem.com/components/notification/usage/
- https://v10.carbondesignsystem.com/patterns/status-indicator-pattern/

### 1.4 Stripe events log — "what the system saw vs what the user did"

Stripe's developer dashboard splits this almost identically to Aether's
ADR-0009 split. The **API request log** answers "what did the user/client
send?" — verb, endpoint, status code, timing. The **events view** answers
"what did Stripe's system materialize from that request?" — typed event
objects with their full payload. Both views share a row, but each has its
own column and its own filter chip. The user can pivot from an API request
to its emitted events with one click. The lesson: surface the two
representations as **siblings, not parent/child**. Don't force the user to
expand a row to see the system's interpretation — give it a fixed slot in
the row layout, and let detail expand from there. Aether's current ADR-0009
implementation does this with the collapsed `<details>` summary line that's
always visible ("Aether also saw 3 memories from durable, facts") even when
the disclosure is closed. That's the right shape; the recommendation below
just tightens the typography.

Source: https://docs.stripe.com/development/dashboard/events

### 1.5 Linear's "internal/external" comment differentiation

Linear marks internal-only comments with a small lock glyph + a muted yellow
tint on the row background. The differentiator is **subtle but always
visible** — never hidden behind a hover. The principle generalizes: when a
row carries a content class the user cares about ("this comment is
internal-only", "this audit row also includes retrieval context"), surface
it as a stable affordance the eye can scan for, not a hover-only badge.
Aether benefit: the "Aether also saw N memories" summary line is already
this affordance. It just needs to read as a stable visual element, not as
toggle chrome.

(Linear's UI is closed-source; the pattern is documented across UX
case-studies and Linear's own changelog posts. No single canonical URL.)

---

## 2. Recommended treatment for Aether's `AuditList`

The current implementation (commits `16a3db2` + `b577105`) already gets the
shape right. The recommendations below are **refinements**, not rewrites.
Each is independently adoptable.

### 2.1 Visual hierarchy (priority order)

1. **Decision label** (`allowed`/`denied`/`asked`/etc.) — colored, mono,
   uppercase, top-left. **Already correct.**
2. **User utterance** (v2 only) — the row's strong signal. `text-aether-text`
   at 12.5–13 px. **Already correct;** consider bumping to 13 px and slightly
   tightening line-height (`leading-snug`) so the quote reads as a sentence,
   not a code line.
3. **Provenance summary line** — always visible when v2 + retrieval block
   present. Currently lives inside `<summary>`; recommend hoisting it out so
   it reads as a fixed metadata row rather than disclosure chrome (see 2.3).
4. **Capability + scope** — secondary mono line, `text-aether-muted`.
   **Already correct.**
5. **Audit ID + schema badge** — top-right, smallest, dimmest. **Already
   correct.**

### 2.2 Default view

**Recommendation:** original_utterance prominent + provenance summary line
visible (one line) + provenance detail behind disclosure. Do *not* attempt
side-by-side rendering of `original_utterance` and `model_input_utterance` —
ADR-0009 §Open Item 3 already deferred showing the full
`model_input_utterance` to a future ADR, and the side-by-side layout would
double row height for marginal clarity. Stripe's pivot model (sibling views,
not parent/child) is the right end-state, but it requires UI surface beyond
a single drawer row; defer until a dedicated "audit detail view" lands.

### 2.3 Provenance treatment (compactness)

Two small refinements over the current `<details>/<summary>` shape:

- **Hoist the summary text out of `<summary>`.** Current rendering ties the
  human-readable summary ("Aether also saw 3 memories from durable, facts")
  to the disclosure widget. That couples meaning to chrome. Render the
  summary line as a normal flex row with a small chevron-glyph button to
  the right; the button toggles the hit list. The summary text reads the
  same whether or not the user can expand it.
- **Compact hit list as a single wrapping line, not a `<ul>`.** Each hit
  becomes a small chip: `durable · mem_a1b2…f9 · 0.87`. Wrap inline so 3
  hits fit on one line for short memory IDs, two lines for long ones.
  Avoids the "stack of bullet points" visual weight the current `<ul>`
  carries. Use `truncateMiddleForDisplay` (already imported) for IDs.

Carbon's "two-line maximum body" rule is the cap to design against.

### 2.4 Schema-v1 badge

The current `pre-ADR-0009` warning-tinted badge is correct per Carbon's
status-indicator guidance: small, colored, hover-titled with explanation.
**No change recommended.** It signals "this row uses an older schema; the
utterance field may include retrieval context" without dominating the row.

### 2.5 Color & typography hierarchy summary

| Field | Color | Size | Weight | Notes |
| --- | --- | --- | --- | --- |
| Decision label | `aether-ok/warn/err/muted` | 11 px mono | normal | Top-left, uppercase, tracked |
| User utterance (v2) | `aether-text` | 13 px sans (bump from 12.5) | normal | Quoted, `leading-snug`, primary read target |
| Provenance summary | `aether-muted` | 11 px sans | normal | Always visible when v2 + block; chevron button toggles detail |
| Provenance hit chips | `aether-muted` / domain in `aether-dim` | 10.5 px mono | normal | Inline-wrap, not `<ul>` |
| Capability · scope | `aether-muted` / `aether-dim` | 11 px mono | normal | Secondary line under utterance |
| Audit ID | `aether-dim` | 10 px mono | normal | Top-right |
| Schema-v1 badge | `aether-warn` border + tint | 10 px sans | normal | Top-right, only when present |

### 2.6 Density

Existing rows render at ~76–96 px depending on content. The Trust drawer
viewport on Don's hardware (1440-tall display, drawer at ~80% height ≈
1150 px scrollable) fits 12–15 collapsed v2 rows without scroll. That
matches the audit-log usability target ("see one screen of recent
decisions at a glance"). The recommended typography bump in 2.5 adds
~2 px to v2 rows; still within target. No density warning.

### 2.7 Search / filter affordances

**Defer.** The audit list is currently fixed at 100 rows from
`auditRecent(100)`. At that size, scroll + ⌘F covers the search use case.
Filter pills ("v2 only", "with retrieval", "denied only") become valuable
only once `auditRecent` paginates beyond ~200 rows or the user requests
audit-search by phrasing. The History tab's existing filter-pill pattern
(`HistoryFilter`) is the template to mirror when that day comes.

One filter is worth considering even at current scale: **"denied / asked
only"**, because the trust-drawer's emotional purpose ("did Aether do
something I didn't expect?") privileges the non-`allow` rows. Punt to a
later session unless Don signals it's wanted.

### 2.8 Wireframe (ASCII)

```
┌─ AUDIT ROW (v2) ────────────────────────────────────────────────┐
│ ALLOWED                                  pre-ADR-0009  audit_id │  ← only when v1
│                                                                 │
│ "What did we say about the trip planning yesterday?"            │  ← user utterance, primary
│                                                                 │
│ conversation · session_001                                      │  ← capability · scope, secondary
│                                                                 │
│ Aether also saw 3 memories from durable, facts          ⌃       │  ← provenance summary + toggle
│   durable · mem_a1b2…f9 · 0.87  facts · mem_c3d4…11 · 0.81      │  ← hit chips, when expanded
│   durable · mem_e5f6…22 · 0.74                                  │
└─────────────────────────────────────────────────────────────────┘

┌─ AUDIT ROW (v1, legacy) ────────────────────────────────────────┐
│ DENIED                                  pre-ADR-0009  audit_id  │
│                                                                 │
│ vision.frame_capture                                            │  ← capability, primary (no utterance available)
│ session_001                                                     │  ← scope
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Specific React component changes

These describe what a future implementation session would touch. No code in
this phase.

### 3.1 `AuditRow` (in `TrustDrawer.tsx`)

- **Hoist provenance summary out of `<summary>`.** Replace the current
  `<details><summary>...</summary>...</details>` with a `<div>` that holds
  the summary line + a chevron `<button>` whose `aria-expanded` state
  drives whether the hit list renders below. Preserves the testid
  (`audit-model-saw`) and the "always-visible summary text" affordance
  while decoupling meaning from disclosure chrome.
- **Bump utterance line to 13 px + `leading-snug`.** Single class swap on
  the existing `text-[12.5px]` div. Adds a sentence-y quality to the
  primary read target.
- **Replace `<ul>` of hits with a wrapping inline list of chips.** Each
  chip is a `<span>` with `inline-flex` + small horizontal padding. Wraps
  with `flex-wrap`. Existing `truncateMiddleForDisplay(h.memory_id, 24)`
  call stays.
- **Add a `data-retrieval-fired` attribute** on the row root — `"true"` if
  v2 + `provenance.block_present`, else `"false"`. Makes future filter
  pills implementable as pure CSS or a one-line `.filter()`. No visual
  change today.

### 3.2 `AuditList`

- **No structural change.** When/if pagination + filter pills land, this is
  where they go (mirror `HistoryView`'s `FilterPill` row shape, including
  ARIA `role="radiogroup"`).

### 3.3 `formatDomains` helper

- **No change.** Current dedup + sort + comma-join is correct for the chip
  rendering above.

### 3.4 Tests to add when the changes land

- `AuditRow renders summary line outside of <summary> chrome` — guard
  against re-coupling.
- `AuditRow chevron button toggles hits visibility via aria-expanded` —
  accessibility regression guard.
- `AuditRow chips wrap inline when 3+ hits` — visual-density regression.
- Existing `v2 row never renders the augmented model-input string itself`
  test (per ADR-0009 §Open Item 3 lock) **must continue to pass**.

---

## 4. Edge cases

### 4.1 Schema-v1 rows
Already handled. No utterance available → render capability as primary.
Schema badge surfaces the older shape. **No change recommended.**

### 4.2 Retrieval fired but no hits (`block_present: false`)
Current copy: "Aether ran retrieval; nothing matched". Correct shape; under
the recommendations above this becomes a non-disclosure line (no chevron,
because there's nothing to expand). Render as muted text only.

### 4.3 Retrieval deadline exceeded
ADR-0009 doesn't currently distinguish "deadline exceeded" from "no hits"
in the on-row payload — both surface as `block_present: false` with empty
`hits`. **Open question for Don** (see §5.1). If we want to distinguish,
provenance shape needs a `deadline_exceeded: bool` field and the row needs
a third copy variant: "Aether tried to look something up but ran out of
time".

### 4.4 Provenance present but `hits.len() == 0`
Should not occur if `block_present: true`, but defensive: render the
summary as "Aether also saw 0 memories" — current `formatDomains` returns
"no domain" which is awkward. Consider: when `block_present && hits.len()
== 0`, use the same copy as deadline-exceeded ("nothing matched").

### 4.5 Long utterances
v2 users may send multi-paragraph prompts. Current `break-words` on the
utterance div handles wrapping but row height balloons. Consider clamping
to ~4 lines with a "Show more" link inside the row body. Not urgent — most
turns are short — but worth a `line-clamp-4` Tailwind class as a
defensive measure.

### 4.6 Schema mixing within the same `AuditList`
During the transition window, the list interleaves v1 and v2 rows. Current
rendering handles this (per-row `isV2` branch). Visual cohesion holds
because both variants share the same outer card chrome. **No change
recommended.**

### 4.7 Provenance referencing a forgotten memory
A memory may have been forgotten between when the audit row was sealed
and when the user opens the drawer. The row should still render the hit
(provenance is historical truth). Current rendering does not attempt to
link `memory_id` to the live memory store, which is correct — the audit
row is sealed. If a future change adds a "jump to this memory" affordance,
it must handle the dead-link case gracefully ("memory has been forgotten
since this decision").

---

## 5. Open questions for Don

### 5.1 Should the row distinguish "retrieval deadline exceeded" from "retrieval ran, no hits"?

These are different facts. Deadline-exceeded means Aether wanted context
and didn't get it (a quality concern, possibly worth surfacing as a
warning). No-hits means Aether ran retrieval and the corpus genuinely had
nothing relevant (normal). Distinguishing requires a `deadline_exceeded`
boolean on `RetrievalProvenance`. **Recommendation:** add the field; copy
becomes "Aether ran retrieval but ran out of time" vs "Aether ran
retrieval; nothing matched". Cheap, increases trust calibration.

### 5.2 Is "denied / asked only" filter pill worth adding now?

The trust-drawer's emotional purpose privileges non-`allow` rows. A single
filter pill ("Surprises only" or "Non-allow only") would let Don skim for
the rows that matter. Trade-off: adds chrome to a list that's currently
clean. **Recommendation:** wait until Don asks for it; the History tab
already has a filter-pill template if/when it lands.

### 5.3 Should the `model_input_utterance` ever be visible?

ADR-0009 §Open Item 3 deferred this. The argument for showing it: developer
debugging ("what did the model actually see?"). The argument against:
re-introduces the retrieval-block pollution this ADR removed, and the
provenance summary already answers the question at the level of detail a
trust audit needs. **Recommendation:** keep the deferral. If
power-user-debug visibility is wanted later, surface it via a separate
"prompt replay" view (modeled on Stripe's request-log pivot), not on the
audit row itself.

### 5.4 Drawer-vs-disclosure for full audit detail

HighLevel's pattern (right-side drawer for full row detail) is the
strongest activity-log pattern observed. Aether's audit list lives
*inside* a drawer already, so the right-side-drawer-from-table pattern
doesn't compose. The current expand-in-place disclosure is the right
fit. **No change recommended,** but flag for future "full-screen audit
view" if the trust-centre ever gets a non-drawer surface.

---

## 6. Summary of recommendations

| # | Change | Risk | Adopt now? |
| --- | --- | --- | --- |
| 2.3a | Hoist provenance summary out of `<summary>` | Low | Yes — small refactor |
| 2.3b | Replace hit `<ul>` with inline chips | Low | Yes |
| 2.5 | Bump utterance to 13 px + `leading-snug` | Low | Yes |
| 3.1 | Add `data-retrieval-fired` row attribute | Zero | Yes — preps future filtering |
| 5.1 | Add `deadline_exceeded` to `RetrievalProvenance` | Medium (touches l5-policy schema) | Discuss with Don |
| 5.2 | "Non-allow only" filter pill | Low | Defer until requested |
| 5.3 | Surface `model_input_utterance` | Reintroduces ADR-0009 problem | No — keep deferred |
| 4.5 | `line-clamp-4` defensive on long utterances | Zero | Yes |
| 4.4 | Tighten `formatDomains` for `block_present + 0 hits` | Zero | Yes |

A future implementation session can land 2.3a + 2.3b + 2.5 + 3.1 + 4.4 +
4.5 in one focused commit (estimated ~30 min, frontend-only). 5.1 needs a
Don-ratification + cross-layer change to the policy crate.

---

(end of research)
