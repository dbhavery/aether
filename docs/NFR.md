# Companion non-functional requirements

> **Status:** Skeleton. Structure and stubs only.
> **Created:** 2026-05-17 (closing audit gap #2 against the 22-section
> numbered specification outline).
> **Keystone pair.** This doc complements `docs/GLOSSARY.md` — the
> glossary holds the vocabulary, this file holds the operational
> expectations keyed off that vocabulary. When an NFR term is
> referenced from another doc, its authoritative definition is here;
> its short-form entry is in the glossary.

## 0. How to use this document

- **Spec surface.** Each numbered section is a category of
  non-functional expectation, not a test. Concrete thresholds
  arrive in later passes — the point of this skeleton is to
  settle **which categories exist and how they relate**, not to
  lock numbers.
- **Glossary-keyed.** Every term in bold here should resolve in
  `docs/GLOSSARY.md` §9. If a term is load-bearing and missing
  from the glossary, add the stub there first, then link.
- **Rot guards vs AC.** This doc carries **hard constraints** on
  the same footing as the per-subsystem architecture docs. When
  numbers and measurement harnesses land, the corresponding
  behavioural acceptance criteria live in tests and
  `tools/evals/`, not here. Per `docs/GLOSSARY.md` §6, rot guards
  and AC must not be collapsed.
- **Performance tiers are a cross-cutting lens.** §8 names the
  Lite / Balanced / Full performance tiers once; other sections
  reference it rather than restating tier-specific expectations
  inline. Companion is a single product (doctrine §6); these
  tiers describe hardware capability classes, not product SKUs.
- **No premature numbers.** Fields labelled `TODO(numbers)`
  deliberately have no value yet. Populate only when a baseline
  measurement, a Quality-Eval scenario, or an explicit design
  lock supports the number.

---

## 1. Purpose and scope

This document captures the **non-functional expectations** Companion
must satisfy across its subsystems and layers. Functional
behaviour — what Companion *does* — is scoped in the per-subsystem
architecture docs (`VISION-V1-ARCHITECTURE.md`,
`VOICE-V1-ARCHITECTURE.md`, `PRESENCE-V1-ARCHITECTURE.md`,
`MEMORY-V2-ARCHITECTURE.md`, `QUALITY-EVAL-V1-ARCHITECTURE.md`).
NFRs describe *how* it behaves.

### In scope (initial pass)

- Desktop Companion: single-user, local-only, Windows-first.
- L1–L7 engine layers + the Tauri shell.
- The provider adapters in L4 (Ollama, whisper.cpp, etc.) to the
  extent they affect latency, resource budgets, and reliability.

### Out of scope for this skeleton

- Concrete numeric budgets, SLAs, or percentiles — see §10 open
  decisions.
- Regional or fleet-wide rollout constraints — not relevant to a
  single-user desktop product.
- Cross-platform parity beyond "macOS / Linux follow Windows as
  platform probes land".
- Compliance regimes (SOC 2, HIPAA, etc.) — not in scope for a
  local-only single-user desktop product.

### Relationship to other docs

- `docs/GLOSSARY.md` §9 — vocabulary (latency budget, resource
  budget, tier, sync convergence, etc.).
- Subsystem architecture docs — enforce their own hard
  constraints; cross-reference this doc when the invariant is
  non-functional (e.g. "no silent fallback" in Voice V1 is both
  a functional and a reliability statement).
- `docs/adr/ADR-0006-hardware-tier-model.md` — existing resource
  tier scaffolding; numbers in that doc inform §4 once pulled
  forward.
- `ARCHITECTURE.md` — per-layer latency notes
  scattered today; §2 pulls them into one view.

---

## 2. Latency and responsiveness

Latency is measured at three distinct scales. Conflating them
leads to bad tradeoffs.

### 2.1 Interaction latency

Definition: time from a direct user action (keystroke, click,
push-to-talk release) to the first UI response acknowledging it.
Target: feel **immediate** — the UI should never leave the user
wondering whether the input registered.

Known inputs today:
- turn submission (text),
- push-to-talk transcription (voice),
- frame analysis (vision),
- Settings toggles.

TODO(numbers): establish a p50 / p95 target per input type.

### 2.2 Model latency

Definition: time from a fully-formed request reaching L4 to the
first streamed token (or the final response, for non-streaming
providers). Dominated by the provider (Ollama, whisper.cpp) and
the selected model.

- Reported in `TelemetryEntry.latency_ms` when the provider
  surfaces it.
- Quality-Eval v1.1 captures live backend latency for eval
  scenarios.

TODO(numbers): no target locked. Treat latency here as an
**observation**, not a contract — the provider / model / host
hardware dominate.

### 2.3 UI responsiveness

Definition: frame-rate and input-handling steadiness of the
Tauri webview during and around model work.

- Long-running model work must not block the webview main
  thread.
- Scroll / input must remain responsive while turns are in
  flight.
- The Trust drawer and Settings must open within one frame of
  the click.

TODO(numbers): no explicit target. Measurement harness TBD.

### 2.4 Background and sync latency

Placeholder for future background-sync work (cross-device).
Not active in Companion v1.

---

## 3. Availability and reliability

### 3.1 Availability model

- **Companion (v1)**: local-only. "Availability" means the
  desktop app boots and remains responsive on the user's
  machine. No uptime SLA; no remote service on the critical
  path. Single product per doctrine §6 — no separate preview /
  pro split.
- **Future opt-in remote features** (sync, shared personas, etc.)
  may eventually enter the critical path for the user who opts
  in. Availability expectations for those features live here
  when they land; they must be **scoped to the feature**
  (sync-only, not the whole companion) so local-only use
  continues to work offline.
- **Don's private / internal build**: same posture as the
  shipped Companion; additional telemetry or logging is an
  operator concern, not an NFR.

### 3.2 Degradation posture

- **No silent fallback.** Transport, HTTP, parse, and provider
  errors surface as visible errors. This is a functional
  invariant in Voice V1 and should be generalised here: a
  failing provider must not produce a plausibly-wrong output.
- **Degraded-mode policy engine.** L5's `DegradedMode` is the
  authoritative signal when policy cannot be safely evaluated.
  Code paths hitting `PolicyEngineError::Degraded` must show
  the user the degraded posture, not fall through.
- **Presence continues through idle-probe failure.** The
  `UnsupportedIdleProbe` returns `None` and the controller
  holds at `Active`. The shell surfaces "idle probe
  unavailable" rather than lying.

### 3.3 Crash and data-loss posture

- **Configs are atomic.** Every `*_config.rs` module writes
  via write-to-temp + rename. Mid-write crashes must not
  produce an unparseable file on next boot.
- **Session memory is bounded.** `RecentMemoryConfig` +
  `RetentionPolicy` (durable store) bound worst-case disk and
  RAM usage.
- **Audit log is append-only.** L5's `AuditStore` contract
  forbids `DELETE` on audit rows (see L5 interface pack).

TODO(numbers): no target locked. See §9 open decisions.

---

## 4. Resource budgets

### 4.1 Axes

The glossary calls these out as **orthogonal**:

- **Router tier** (`Reflex / Balanced / Critical`) — names the
  *routing* policy (which provider / model to use for a given
  turn). See `docs/LLM-PROVIDERS.md`.
- **Performance tier** — names the *hardware capability class*
  (VRAM, RAM, CPU) the host is assumed to have. See
  `docs/adr/ADR-0006-hardware-tier-model.md`.

A single host runs all router tiers; the performance tier
dictates which models are feasible. Do not conflate them.

### 4.2 Memory and VRAM

- VRAM budget is dominated by the active model on a given turn.
  Selection is L4's concern; NFR here is that **eviction or
  fallback must be visible** (see §3.2 degradation posture).
- RAM is dominated by the shell + webview + embedded provider
  caches.
- Shell-side caches (e.g. `ModelListCache`) must be bounded.

TODO(numbers): pull baseline from
`docs/adr/ADR-0006-hardware-tier-model.md` when the table is
stable.

### 4.3 CPU

- Background work (presence poll, retention sweep) must be
  **cheap and coarsely paced** — the presence poll is 1 Hz,
  not a tight loop. Memory V2 retention is a boot-time pass
  plus a low-rate background tick (design §8 item 4).

TODO(numbers): no target locked.

### 4.4 Disk

- SQLite growth is bounded by retention policy. See
  `sqlite_session::RetentionPolicy::default_bounded` (500 rows
  per session).
- Config files are small; atomic rewrites.
- Audit database is **append-only** but bounded by a future
  archival policy (not yet specified).

TODO(numbers): cap per session / per install.

---

## 5. Sync and convergence

Out of the critical path for Companion v1. Included here so the
category exists before cross-device sync work lands.

- **Convergence model** (CRDT vs server-authoritative) — **open
  decision**. See §10.
- **Conflict resolution** — user-first: never lose user-authored
  content without an explicit user action.
- **Offline behaviour** — Companion assumes offline is normal,
  not exceptional.

TODO: populate once the cross-device sync track has a design doc.

---

## 6. Security and trust intersection

NFRs must not erode security or trust to hit latency or resource
targets. Bright lines:

- **Audit is not negotiable for performance.** Every allowed
  side effect writes an L5 audit row synchronously before the
  effect returns (L5 interface pack §5).
- **Memory V2 user-sensitive domains default to Ask.** Latency
  is never a reason to flip a Facts or Artifacts write to Auto
  (Memory V2 architecture §8 item 3).
- **No silent fallback.** See §3.2.
- **No raw-media persistence.** Image and audio bytes never hit
  memory or disk (Memory V2 architecture §8 item 1).
- **Private assets never enter public distributables.**
  A build-time gate enforces this functional invariant, noted
  here because any perf-driven asset packaging change interacts
  with it.

Security details live in the respective subsystem architecture
docs and the (future) trust centre doc; this section is the
bridge that says "NFRs must respect those".

---

## 7. Measurement and validation

### 7.1 Sources of truth

- `TelemetryEntry` on the shell — live latency and token counts
  per turn.
- L3 presence poll loop + `presence_recent_history` — coarse
  user-attention stats (opt-in via Trust drawer toggle).
- Memory V2 sampled-read audit (`memory_retrieval` telemetry,
  design §4) — ~1 in 100 reads per domain per session.
- L5 audit log — every allowed side effect, for reliability
  analysis.
- `tools/evals/` — scripted scenarios including adversarial
  probes; baseline at `tools/evals/baseline/` per run.

### 7.2 Harness relationship

Quality-Eval V1 is the current harness for behavioural AC. NFR
validation beyond what Quality-Eval covers (long-run stability,
resource profiling) is an open question — see §10.

### 7.3 Reporting posture

Measurements are **internal** to Companion. No telemetry
leaves the device unless the user explicitly opts in. Any
future telemetry capability will be scoped as an opt-in
feature, not an always-on pipe.

---

## 8. Performance tiers and NFRs

Companion is a **single product** (doctrine §6). The tiers below
are **hardware capability classes**, not product SKUs — every
install is the same Companion; the tier dictates which models
and rendering paths are feasible. See
`docs/adr/ADR-0006-hardware-tier-model.md` for the canonical tier
definitions.

Tiering affects expectations, not categories. A tier cannot
introduce a new NFR category; it can only set or relax targets
within the categories this doc enumerates.

| Performance tier | Expectation posture                                                                                  |
| ---------------- | ---------------------------------------------------------------------------------------------------- |
| **Lite**         | Lowest-VRAM hosts; smallest model variants; aggressive remote fallback for non-reflex paths; reduced cache footprint; latency posture is best-effort. |
| **Balanced**     | Mid-range GPU or strong CPU; mid-size model variants; more work stays local; standard latency posture. |
| **Full**         | Flagship GPU hosts; largest model variants; richest avatar rendering; tightest local latency posture. |

Future opt-in remote features (e.g. sync) will carry their own
per-feature availability targets and apply across all
performance tiers; they are not a separate product tier.

TODO(numbers): no cross-tier SLA commitments until baselines per
tier are measured.

---

## 9. Relationship to measurement tooling (summary)

- Latency: `TelemetryEntry.latency_ms` on the shell; Quality-Eval
  live backend hook captures per-scenario latency.
- Availability: no automated probe yet; user-visible degradation
  surfaces are the current signal.
- Resource budgets: no automated probe yet; performance-tier
  docs carry the scaffolding.
- Convergence: deferred with the sync track.

---

## 10. Open NFR decisions

1. **Concrete latency budgets** (interaction, model, UI) — no
   target locked until we have a Quality-Eval-driven baseline
   on reference hardware.
2. **Availability targets for opt-in remote features** —
   deferred until those features have a design pass. Must be
   per-feature, not companion-wide.
3. **Resource budget numbers** — pull from
   `docs/adr/ADR-0006-hardware-tier-model.md` once that table is
   stable; mirror the performance-tier taxonomy here rather
   than duplicating numbers.
4. **Sync convergence model** — CRDT vs server-authoritative.
   Defer until the cross-device sync track starts.
5. **NFR-specific AC format** — open decision tracked alongside
   the broader `docs/AC-STYLE.md` work (see `docs/GLOSSARY.md`
   §11). NFR behavioural checks should live in tests / evals,
   not here; the style doc will say how.
6. **Resource-profiling harness** — no tool yet. Quality-Eval
   may grow a profiling mode; alternatively a separate
   `tools/nfr-profile/` script may be appropriate.
7. **Forward-looking requirement IDs** — this doc will adopt
   them once the ID scheme is settled (glossary §11 open
   decision). Retrofitting history is explicitly out of scope;
   NFR IDs begin at V2 of this doc.

Cross-links:

- `docs/GLOSSARY.md` §11 — glossary-scoped open decisions (AC
  house style, requirement ID scheme) that block later NFR
  work.
- Subsystem architecture docs — each carries §9 / §11 open
  questions; NFR-relevant ones should surface here when they
  mature.

---

## 11. How this doc stays honest

This is a **skeleton**. A rot guard (`tools/lint-nfr-doc/`) can
be added when the doc has stable anchors worth protecting;
until then the glossary is the tie-breaker if a term here ever
drifts.

When an NFR section graduates from TODO to concrete, the PR
that adds the numbers MUST:

1. Add the corresponding glossary entry if it is new.
2. Add or link the measurement harness that justifies the
   number.
3. Add or link the behavioural acceptance criteria (tests,
   evals) that verify conformance.
4. Update this doc in the same PR; do not leave the category
   with a stale `TODO(numbers)` if the category has shipped.

Rot guards and AC remain distinct per `docs/GLOSSARY.md` §6
even as NFR numbers land.
