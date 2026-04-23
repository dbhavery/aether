# Memory V2 step 7 execution report — 2026-04-23

**Run 4 of six-run roadmap (2026-04-23).** Rot guard + doc flip.
Mirrors the pattern now proven four times
(`lint-vision-doc`, `lint-voice-doc`, `lint-presence-doc`,
`lint-quality-doc`).

## What shipped

| SHA | Subject |
| --- | --- |
| `120b6d0` | feat(tools): lint-memory-doc rot guard + flip Memory V2 doc to Current |
| `09df5b0` | docs(memory): mark V2 §10 items 6+7 as shipped |

- `tools/lint-memory-doc/check.py` — mirror of
  `tools/lint-quality-doc/check.py`. Same CLI (`--json`), same
  output, same exit codes.
- `tools/lint-memory-doc/README.md` — adapted from the sibling
  READMEs.
- **60 anchors across 12 files.** Covers:
  - §1 six-domain taxonomy (ADR-0001 relocation —
    `packages/l2-memory/src/domain.rs` + all six variants).
  - §3 memory.json surface (`MemoryConfig`, `MemoryRisk`,
    `EmbeddingsConfig`, `retention_for`, `risk_for`).
  - §4 L5 capabilities (all five — Memory{Read,Write,Forget,Edit,Embed}).
  - §5 telemetry kinds (all seven strings including
    `memory_embedded`).
  - §6 UI surfaces (`MemoryTab.tsx`, `TrustDrawer.tsx`,
    `SettingsDrawer.tsx`).
  - §10 step 4 (`SessionMemoryStore::remove`,
    `SessionMemoryStore::update`), step 5 (`prune_before`,
    `list_sessions`, `run_retention_sweep`,
    `RETENTION_SWEEP_INTERVAL_MS`,
    `run_retention_sweep_loop`), step 6 (`embeddings.rs` module +
    two traits + flat-file + Ollama provider + env vars).
  - ADR-0001 + ADR-0002 existence.
- `docs/MEMORY-V2-ARCHITECTURE.md` flipped from
  `Design-only as of 2026-05-11` to **`Current as of 2026-04-23`**.
  §11 rewritten to describe live rot-guard enforcement.
- §10 items 6 and 7 in the implementation-sequencing list moved
  to ✅ with pointers to `embeddings.rs` and ADR-0002.

## Check matrix

All five Memory / Vision / Voice / Presence / Quality rot guards
green simultaneously:

| Rot guard | Status |
| --- | --- |
| `lint-vision-doc` | OK (51 anchors / 12 files) |
| `lint-voice-doc` | OK (48 anchors / 12 files) |
| `lint-presence-doc` | OK (39 anchors / 10 files) |
| `lint-quality-doc` | OK (60 anchors / 19 files) |
| `lint-memory-doc` (NEW) | OK (60 anchors / 12 files) |

Plus `lint-layer-boundaries` clean and all prior-run tests still
pass (nothing outside `docs/` and `tools/lint-memory-doc/` was
touched in Run 4's commit).

## Done-when checklist

- [x] `python tools/lint-memory-doc/check.py` prints `OK` with an
      anchor count.
- [x] `docs/MEMORY-V2-ARCHITECTURE.md` reads as current (no
      "design-only" claims; §10 steps marked ✅).
- [x] All five rot guards pass together.
- [x] Memory V2 qualifies as a **closed subsystem** in future
      handoffs' Subsystem Status section.

## Subsystem closure

Memory V2 now joins Vision V1, Voice V1, Presence V1, and
Quality-Eval V1 as rot-guarded closed subsystems. Five
subsystems, five rot guards, zero design-only drift.

## Out of scope (post-closure backlog)

- **5.5a Domain-typed durable store** — would populate the five
  trace-skipped domains in the retention sweep and extend the
  embedding path beyond the opt-in flag's current scope.
- **5.5b Per-item sweep telemetry opt-in** — explicit reopen of
  Decision #56. Waits on Memory tab behaviour to surface a
  genuine need.
- **Retrieval wiring** — the turn engine consuming
  `EmbeddingStore::query_nearest` for semantic recall. Separate
  slice; ADR-0002 §Out-of-scope documents the rationale.
