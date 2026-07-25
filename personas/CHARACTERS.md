# Companion Persona Cast — Design Doc

> **Delivery model:** Personas are NOT all bundled with the desktop app.
> The wizard shows lightweight previews; the chosen persona's full pack
> downloads on selection. Switching characters later = uninstall +
> install. See ADR-0012 for the full architecture.

> The roster of characters Companion ships with. Each persona is a complete
> identity package — name, face, body, voice, personality archetype,
> system prompt — that the user picks during onboarding and can switch
> between later.
>
> **Last updated:** 2026-04-28 (eve, second-pass redesign after
> face-consistency anchor critique).
> **Direction from Don:**
> - "Keep developing these characters using your own judgement for looks,
>   voice, etc. Use realistic names. Improve training before video."
> - "These will eventually be full human-like video avatars, with full
>   bodies. ... Headshots with lip-syncing now, then full body and full
>   movement video toward the end of the project."
> - "You can start the characters over. It's fine."
>
> **Standing rule:** I (the agent) make the look/voice/name calls
> autonomously. Don reviews after, can reject any individual choice
> and I'll regenerate.

---

## Why a cast (not a single assistant)

Different work calls for different conversational partners. The same
person who wants a calm grounded presence at 2am while debugging
production wants a sharp analytical sparring partner during code
review and a playful brainstorm partner when sketching a new idea.
A single assistant trying to cover every mode through prompt-only
steering reads as inconsistent. Separate personas with distinct
voices, faces, and trained behavioral profiles read as a roster
of people you actually know.

---

## Roster — 9 personas

The cast spans **conversational mode × demographic variety** so the
picker covers real work modes without anyone blurring into anyone
else.

| # | Slug | Name | Archetype | Snapshot |
|---|---|---|---|---|
| 1 | `aurora` | Aurora Nash | warm_supportive | 31 F, honey-auburn waves, hazel-green eyes, candid presence (slug stays `aurora` for code stability; display_name updated) |
| 2 | `marcus_chen` | Marcus Chen | analytical_focused | 38 M Asian-American, wire-frame glasses, technical sparring |
| 3 | `sara_reyes` | Sara Reyes | playful_creative | 28 F Latina, denim-jacket terrace energy, brainstorming |
| 4 | `james_whitfield` | James Whitfield | grounded_practical | 55 M white, weathered, "sit with it" elder |
| 5 | `nadia_volkov` | Nadia Volkov | rigorous_skeptic | 27 F Slavic, sharp features, "your premise is wrong" |
| 6 | `priya_iyer` | Priya Iyer | strategic_executive | 47 F Indian-American, polished-warm, pulls you to product altitude |
| 7 | `ray_castellano` | Ray Castellano | field_commander | 52 M Italian-American, "stop thinking, ship it" |
| 8 | `hannah_park` | Hannah Park | depth_researcher | 34 F Korean-American, glasses, knows the literature |
| 9 | `tomas_andrade` | Tomás Andrade | direct_coach | 36 M Latino, "you're avoiding the hard thing" |

**Demographic spread (intentional, not performative):**
- Gender: 5 F, 4 M
- Age range: 27 → 55
- Apparent ethnicity range: white, Asian (East/South), Latin, Slavic
- Voice pitch range: full mid-low male → mid-high female
- Each is plausibly a friend you'd actually know — none are
  archetype-by-checklist

---

## Asset schema per persona

### Phase 4 (current — "headshot"):

```
personas/<slug>/
├── persona.yaml          # id, display_name, archetype, hand-authored
│                          system prompt + voice descriptors
├── metadata.yaml         # provenance for every shipped asset
├── avatar/
│   ├── anchor.png        # 1024x1024 neutral reference (canonical
│   │                       face-consistency lock — even diffuse light,
│   │                       looking forward, neutral relaxed expression,
│   │                       mouth closed, simple/neutral background)
│   ├── portrait.png      # 1024x1024 personality shot (the picker UI's
│   │                       "this is who I am" image — candid, expressive,
│   │                       in their setting)
│   ├── profile_left.png  # 1024x1024 3/4 left angle, anchor-style
│   │                       lighting (face-consistency support)
│   ├── profile_right.png # 1024x1024 3/4 right angle, anchor-style
│   └── README.md         # provenance per asset
├── voice/
│   ├── reference.wav     # 20.0s 24kHz mono 16bit PCM (Chatterbox/Zonos
│   │                       cloning reference)
│   ├── sample.wav        # 4.0s wizard preview
│   ├── voice.yaml        # Chatterbox knobs + ElevenLabs voice_id slot
│   └── SOURCE.md         # generation provenance + reference text
```

### Phase 5+ (end-of-project — "full body + motion"):

Add to existing schema:

```
personas/<slug>/
├── avatar/
│   ├── body.png          # torso-up or full-figure, locks proportions/build
│   ├── poses/            # additional body angles
│   │   ├── front.png
│   │   ├── three_quarter_left.png
│   │   ├── three_quarter_right.png
│   │   └── (more as the cast matures)
│   └── motion/           # video clips for full-body movement
```

### What's intentionally deferred (Phase 5+, full-body):

- **Expression states (idle/listening/thinking/speaking):** deferred.
  The first-pass approach (4 still PNGs per persona) was a workaround
  and is set aside in favor of the locked-anchor schema.
- **Body shots, multi-pose, full-body motion:** Phase 5+, end of project.
- **Wardrobe variants:** locked-in single look per persona for now;
  revisit only if dogfooding shows wardrobe rotation is needed.

---

## Why anchor-shot beats personality-shot

The first-pass picks (Aurora cafe-candid, Marcus glasses+henley study,
etc.) optimize for "looks like a real photograph of a real person."
That's right for the picker UI but wrong as the canonical neutral
face reference.

A clean anchor reference works best when:
- Lighting is even and diffuse (no half-face shadow)
- Expression is neutral relaxed (mouth closed, no laughing-mouth-open)
- Gaze is forward (no off-axis or away-from-camera)
- No motion blur, no implied movement
- Background is simple / neutral / extractable

A laughing cafe-candid violates every one of those.

**Solution:** ship both. The personality shot is `portrait.png` (used
in the picker UI, where personality matters more than face geometry).
The anchor is `anchor.png` (the canonical neutral face reference).
Both are referenced from `metadata.yaml`.

---

## Status — what's generated

### Phase 4 asset schema COMPLETE 2026-04-28 night

All 9 personas now ship the full Phase 4 asset pack. Cast is closed
on the v0 release; further iteration goes through regen-not-replace.

| # | slug | anchor + 3 stills | voice ref + sample | persona.yaml | metadata.yaml ai_generated |
|---|---|---|---|---|---|
| 1 | aurora           | ✓ | ✓ | ✓ | ✓ |
| 2 | marcus_chen      | ✓ | ✓ | ✓ | ✓ |
| 3 | sara_reyes       | ✓ (anchor regen for single-subject fix) | ✓ | ✓ | ✓ |
| 4 | james_whitfield  | ✓ | ✓ | ✓ | ✓ |
| 5 | nadia_volkov     | ✓ | ✓ | ✓ | ✓ |
| 6 | priya_iyer       | ✓ | ✓ | ✓ | ✓ |
| 7 | ray_castellano   | ✓ | ✓ | ✓ | ✓ |
| 8 | hannah_park      | ✓ (anchor regen for single-subject fix) | ✓ | ✓ | ✓ |
| 9 | tomas_andrade    | ✓ | ✓ | ✓ | ✓ |

Voice picks were locked unilaterally by the cast creator (not Don)
under the 2026-04-28 night directive. See each persona's
`voice/SOURCE.md` for the steering text + reference text per pick.

---

## First-pass redo — what's archived from 2026-04-28 morning

The first cast attempt (Aurora cafe-candid, Marcus study-glasses)
shipped 2026-04-28 morning before the face-consistency critique
landed. Those assets are NOT thrown away — they're archived to
`personas/<slug>/_archived_2026-04-28_first_pass/` and the new
anchor-schema generation replaces them in the canonical paths.

Reasoning preserved in archive notes per persona.

---

## Open questions Don hasn't answered (parked, not blocking)

- Persona-specific behavioral tuning vs shared base + system-prompt
  steering? (Default: shared base + system prompt; revisit only if
  behavioral consistency falls short of the bar.)
- Personal "Don persona" for journal/scratchpad use? (Privacy
  lockdown applies — Don's likeness is private-only per locked
  feedback rule. Could exist for internal use, never public.)

## Related architecture decisions

- ADR-0012 — persona delivery (bundled previews + download-on-demand
  full packs + atomic uninstall-then-install on switch). The cast
  shipped here becomes the canonical source for v0 persona packs.
  See file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0012-persona-delivery-download-on-demand.md
