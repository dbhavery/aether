# Vision v1 — architecture reference

> **Status:** Current as of 2026-05-07.
> **Scope:** The local-only single-frame vision assistant — Ollama
> and llama.cpp adapters, frame validation, provider/model selection,
> persistence, TTL cache, and UI surfaces.
> **Out of scope:** Remote vision providers, microphone/voice/STT/TTS,
> streaming/continuous capture, mobile.

This doc captures the contracts and end-to-end flow of the Vision v1
slice so future work — remote providers, voice, privacy posture —
has a stable reference. When code drifts from this doc, update the
doc; it's not authoritative the moment it lies.

---

## 1. End-to-end flow

```
[user]
  │ enables Camera or Screen permission in Settings
  │
[CameraPanel / ScreenPanel — apps/desktop/src/components/]
  │ captures a single frame as data:image/...;base64,<body>
  │ invokes `analyze_frame` over Tauri IPC
  │
[analyze_frame — apps/desktop/src-tauri/src/commands.rs]
  │ 1. parse + validate `kind` (camera|screen)
  │ 2. evaluate media permission gate (Allow|Ask|Deny)
  │    - Deny / Ask → telemetry("permission_denied"|"permission_ask"),
  │      memory record (Deny only), short-circuit
  │ 3. validate_frame_data_url(payload)
  │    - Err → telemetry("frame_invalid"), short-circuit
  │ 4. record user-role memory: "[frame analysis · {kind}] {cue}"
  │ 5. invoke turn engine with capability MediaCamera|MediaScreenCapture
  │    (resource scope none)
  │
[TurnEngine — packages/* through L5/L6]
  │ runs the persona prompt + L5 policy. No provider info enters L5.
  │
[maybe_apply_vision — apps/desktop/src-tauri/src/commands.rs]
  │ a. require an active vision provider; else fall back to text
  │ b. require a non-blocked route; else respect the block
  │ c. mirror validate_frame_data_url (defense in depth, debug-only
  │    log on rejection — no duplicate WARN)
  │ d. split_data_url → (mime, base64 body)
  │ e. provider.analyze(VisionRequest { cue, image_b64, mime })
  │    - Ok → overwrite route.response_text, route.provider, route.tier;
  │      merge token counts when present
  │    - Err → WARN, fall back to text-only output
  │
[provider — packages/l4-router/src/providers/{ollama,llamacpp}_vision.rs]
  │ HTTP call to local Ollama / llama.cpp daemon.
  │ Reports current_model() back through VisionStatus.
  │
[result assembly — back in analyze_frame]
  │ build assistant TranscriptMessage with MessageMeta
  │   { tier, provider, model, latency_ms, tokens }
  │ record telemetry kind="frame_analyzed" | "frame_blocked"
  │ emit to UI via Tauri event
  │
[Transcript / TrustDrawer — apps/desktop/src/components/]
  │ render the assistant turn + footer chips
  │   provider · model · latency · tokens (tier omitted on vision turns)
  │ Trust drawer History tab annotates with provider · model
  │   (long ids middle-truncate, full id in title tooltip)
```

Image bytes are **transient** at every layer: they exist only inside
the IPC frame, the `VisionRequest`, and the provider HTTP body.
Nothing persists them to disk, the audit log, the durable memory
store, or any structured telemetry field.

---

## 2. Providers

Two adapters ship today; a third would follow the same interface.

### Ollama (`OllamaVisionProvider`)

- `id() = "ollama-vision"`
- Crate: `aether-l4-router`, gated by feature `ollama-provider`.
- Config via env (`OllamaVisionConfig::from_env`):
  - `AETHER_OLLAMA_VISION_BASE_URL` (default `http://127.0.0.1:11434`)
  - `AETHER_OLLAMA_VISION_MODEL` (e.g. `llava:latest`)
  - timeouts/temperature follow the rest of the Ollama family.
- Boot WARN includes the base URL when the healthcheck fails.
- Model discovery: `GET /api/tags`.

### llama.cpp (`LlamaCppVisionProvider`)

- `id() = "llamacpp-vision"`
- Crate: `aether-l4-router`, gated by feature `vision-llamacpp`.
- Config via env (`LlamaCppVisionConfig::from_env`):
  - `AETHER_LLAMACPP_VISION_BASE_URL`
  - `AETHER_LLAMACPP_VISION_MODEL`
- Boot WARN includes the base URL when the healthcheck fails.
- Model discovery: server-specific `/v1/models`-style endpoint.

Both adapters implement `VisionProvider` (see
`packages/l4-router/src/vision.rs`):
- `id() -> &'static str`
- `label() -> String`
- `analyze(VisionRequest) -> Result<VisionResponse, L4Error>`
- `set_model(id) -> Result<(), L4Error>`
- `current_model() -> Option<String>`
- `healthcheck() -> Result<(), L4Error>`
- `list_models() -> Result<Vec<String>, L4Error>`

Their config errors are intentionally **not** unified — each provider
owns its own error taxonomy so a future remote provider can have its
own without surgery on the others.

---

## 3. `vision_provider.json` contract

Path: `<app_data>/vision_provider.json` (alongside
`media_permissions.json`).

Shape (see `VisionPersistedState` in `vision_registry.rs`):

```json
{
  "active": "ollama-vision",
  "model_per_provider": {
    "ollama-vision":   "llava:latest",
    "llamacpp-vision": "qwen2.5-vl-7b"
  }
}
```

Contract:

- **Additive** — new fields may be added by future builds.
- **Default-safe on read** — `model_per_provider` has a `serde`
  default; `active` is `Option<String>`. Old files that lack a field
  load cleanly.
- **Unknown fields are silently ignored on read.** No
  `#[serde(deny_unknown_fields)]` on the struct.
- **Unknown fields are dropped on rewrite.** The struct has no
  `serde(flatten)` extras bag, so any future build's added field is
  lost the first time an older shell saves the file. Documented
  limitation; locked by test
  (`vision_registry::tests::unknown_fields_are_dropped_on_rewrite`).
- **Malformed JSON falls back to default state with a WARN that
  names the file path** — the shell still boots cleanly.
- **Persistence is single-writer through `VisionRegistry`.**

A `vision_persistence_path_for(app_data_dir)` helper gives tests a
deterministic file path under `TempDir`.

---

## 4. Provider / model selection rules

Implemented in `VisionRegistry`
(`apps/desktop/src-tauri/src/vision_registry.rs`).

### Active provider

- The persisted `active` id wins on boot.
- Unknown persisted id → fall back to **first registered** provider
  (insertion order).
- Explicit `None` → respected (text-only mode).
- `set_active(None)` clears the selection and persists.
- `auto_select_first_if_unset()` runs once at boot when no active id
  has been chosen and at least one provider is registered.

### Per-provider model

- `model_per_provider` survives provider swaps — switching
  Ollama → llama.cpp → Ollama restores the Ollama model the user had
  picked, not the adapter default.
- `set_active_model(id)` writes through both the in-memory map and
  the active adapter (`provider.set_model(id)`), then persists.
- Persisted entries for unregistered provider ids are **retained but
  not applied** — a future build that registers the missing
  provider inherits the pick.
- First-launch seeding (`vision_seed_missing_models`): when an
  adapter is registered but its id has no entry in
  `model_per_provider`, the adapter's `current_model()` is written
  through. Idempotent on subsequent boots.

### TTL cache

`ModelListCache` (`apps/desktop/src-tauri/src/vision_cache.rs`):

- Default TTL: **60 seconds**.
- Env override: `AETHER_VISION_MODEL_TTL_SECS`.
- Bounded `[5, 3600]` seconds. Invalid values (`"0"`, garbage)
  warn and fall back to default.
- TTL is read **once at boot** — no hot reload.
- Boot log line is unconditional INFO:
  `vision model-list cache TTL: <n>s (<source>)`
  where source is `default | env override | default after invalid env`.
- UI exposes a manual `↻` refresh that bypasses the TTL.

---

## 5. Frame validation

Two enforcement points; same rules.

### Shell side — `validate_frame_data_url`

`apps/desktop/src-tauri/src/commands.rs`. Returns
`Result<&str, String>` (the `Ok` is the body slice).

Rules in order:

1. URL must start with `data:image/`.
2. URL must contain a comma (the base64 body separator).
3. The substring after the comma, once trimmed, must be non-empty.
4. The trimmed body must be at least `MIN_FRAME_BODY_LEN = 4` chars
   (the floor for any non-empty base64 payload).

On `Err`, `analyze_frame` returns
`{detail}. Try capturing a new frame.` to the UI **and** records a
`frame_invalid` telemetry entry.

### Vision side — `maybe_apply_vision`

Mirrors `validate_frame_data_url` before delegating to the L4
`split_data_url`. On `Err`:

- Logs at **debug**, not WARN. The shell-side gate already owned
  this case in production; the mirror keeps the function safe
  regardless of caller, without duplicating the WARN.
- Returns `None` so the text-only fallback runs.

---

## 6. Telemetry kinds (vision-related)

The `analyze_frame` path emits exactly five kinds. The TS allow-list
in `apps/desktop/src/lib/mediaTurns.ts::MEDIA_TURN_KINDS` mirrors
this list and is unit-tested for parity.

| kind                | when                                                                                  | in audit?    |
| ------------------- | ------------------------------------------------------------------------------------- | ------------ |
| `frame_analyzed`    | provider returned a response (or text-only fallback completed)                        | yes (turn)   |
| `frame_blocked`     | L5 policy blocked the turn after the permission gate passed                           | yes (turn)   |
| `frame_invalid`     | `validate_frame_data_url` rejected the payload                                        | **no**       |
| `permission_denied` | media permission set to Deny                                                          | **no**       |
| `permission_ask`    | media permission still on Ask                                                         | **no**       |

The three early-exit kinds carry no provider/model/tier/latency/
tokens — only the persona id and timestamp.

One early-exit of `analyze_frame` is **intentionally absent** from
this list: `MediaKind::from_wire(&request.kind)` returning `None`
short-circuits with a hard error (`"unknown media kind: {kind}"`)
and emits **no** telemetry. That branch represents an IPC contract
violation (the frontend sent a `kind` that is neither `"camera"` nor
`"screen"`), not a user-attempted analysis. Keeping it out of
History avoids mixing user-facing trust events with internal code
bugs. See
`P1_MEDIAKIND_FROM_WIRE_TELEMETRY_DECISION_EXECUTION_REPORT_2026-05-07.md`
for the full rationale and the conditions that would reopen the
decision.

The TrustDrawer `kindClass` colors `frame_analyzed` as `text-aether-ok`,
the three error kinds (`frame_blocked`, `frame_invalid`,
`permission_denied`) as `text-aether-err`, and `permission_ask` as
`text-aether-warn`.

---

## 7. UI surfaces

All read from the same source-of-truth registry
(`apps/desktop/src/lib/visionProviders.ts::VISION_PROVIDER_REGISTRY`).

| Surface                           | What it shows                                                       |
| --------------------------------- | ------------------------------------------------------------------- |
| `VisionBadge`                     | dot + provider + model + status                                     |
| `ActiveVisionRoute` (per panel)   | "→ provider · model" hint above the Analyze button                  |
| `Transcript` footer (per turn)    | provider · model · latency · tokens (tier omitted on vision turns)  |
| `TrustDrawer` History tab         | per-turn annotation; long model ids middle-truncated, full in tooltip |
| `TrustDrawer` Audit tab           | capability + scope; provider/model intentionally absent             |

Long model id rendering uses
`truncateMiddleForDisplay(s, max=28, suffixLen=8)` so quantization
tags like `q4_k_m` survive.

---

## 8. Hard constraints (operative for every Vision-v1 PR)

These are codified across sessions and enforced by either tests, the
layer-boundary lint, or by review:

1. **Local-only providers.** No remote vision adapter exists; adding
   one is its own track and triggers the privacy-posture work
   (see §9 below).
2. **Image bytes stay transient.** No persistence to durable memory,
   no inclusion in audit, no leak into telemetry.
3. **Additive config evolution.** Any new
   `vision_provider.json` field must default-safe on read AND
   tolerate being absent from a freshly-rewritten file.
4. **No provider info in L5 audit.** `AuditRecordEvent` does not
   carry provider/model — the capability + scope is the audit
   contract.
5. **No streaming or continuous capture.** Single-frame only.
6. **Provider config errors are not unified across adapters.**
7. **No Tauri-shell telemetry of raw payloads.** Only structured
   metadata.

---

## 9. Open questions for future tracks

These are intentionally not answered here — they are answered when
the relevant track is being scoped.

### Remote vision adapter

See `P3_DEFERRALS_EXECUTION_REPORT_2026-05-03.md` and
`P2_TS_RS_CODEGEN_DECISION_EXECUTION_REPORT_2026-05-05.md` for the
specific seven open questions to answer at that time. Highlights:

- Per-provider remote consent — does the existing media permission
  cover network egress, or does each remote adapter require its own
  opt-in?
- Host allowlist — where is it stored, who edits it, how is it
  audited?
- "Calls out to the internet" badge in the UI?
- Image-on-the-wire format and retention guarantees?

### Microphone / voice (separate track)

Mirror the camera/screen permission tri-state when the mic path
lands. Reuse the early-exit telemetry pattern (`mic_invalid`,
`mic_permission_denied`, `mic_permission_ask`) so the History tab
stays coherent across both modalities.

### Rust↔TS provider id codegen

Defer until a third adapter or until TS registry consumers exceed
~7–8 (currently five). Likely approach: `ts-rs` from a shared Rust
enum.

---

## 10. Reference reports

Selected execution reports that justify the current shape (most
recent first):

- `P1_VISION_DOC_ROT_GUARD_EXECUTION_REPORT_2026-05-08.md`
- `P1_MEDIAKIND_FROM_WIRE_TELEMETRY_DECISION_EXECUTION_REPORT_2026-05-07.md`
- `CHUNK_A_FRAME_EARLY_EXIT_TELEMETRY_EXECUTION_REPORT_2026-05-06.md`
- `CHUNK_B_LOG_CLARITY_EXECUTION_REPORT_2026-05-06.md`
- `CHUNK_C_VISION_V1_ARCHITECTURE_DOC_EXECUTION_REPORT_2026-05-06.md`
- `P1_VISION_PROVIDER_JSON_SCHEMA_TOLERANT_READ_EXECUTION_REPORT_2026-05-05.md`
- `P1_MAYBE_APPLY_VISION_GUARD_SYMMETRY_EXECUTION_REPORT_2026-05-04.md`
- `P2_MIDDLE_TRUNCATION_EXECUTION_REPORT_2026-05-04.md`
- `P1_ANALYZE_FRAME_EMPTY_BODY_GUARD_EXECUTION_REPORT_2026-05-03.md`
- `P2_TRUST_DRAWER_MODEL_ID_TRUNCATION_EXECUTION_REPORT_2026-05-03.md`
- `P3_VISION_CACHE_TTL_BOOT_LOG_EXECUTION_REPORT_2026-05-02.md`
- `P2_PROVIDER_ID_DEDUP_EXECUTION_REPORT_2026-05-02.md`
- `P1_TRANSCRIPT_TIER_DEDUP_EXECUTION_REPORT_2026-05-02.md`

Handoffs are dated `HANDOFF_2026-05-0X_CONTINUE_COMPANION_BUILD.md`
in the repo root.

---

## 11. Rot guard

This doc is guarded by `tools/lint-vision-doc/check.py`. The guard
carries a curated anchor manifest — files, symbols, and string
constants (telemetry kinds, env var names, provider ids, config
filenames) that this doc claims exist. If any anchor disappears from
the code (rename, delete, typo), the guard fails.

Run it:

```
python tools/lint-vision-doc/check.py
```

What the guard DOES check:

- every FILE anchor resolves to an actual file,
- every SYMBOL anchor (literal snippet like `fn analyze_frame`)
  appears at least once in its named file,
- every STRING anchor (`"frame_analyzed"`, `AETHER_VISION_MODEL_TTL_SECS`,
  `ollama-vision`, `vision_provider.json`, ...) appears at least once
  in its named file,
- this doc has a parseable `**Status:** Current as of YYYY-MM-DD.`
  header line.

What the guard does NOT check:

- prose accuracy,
- whether a new code behavior has been reflected in the doc,
- whether a newly-added telemetry kind has been added to the doc.

**When you change anything this doc names:**

1. Update the doc prose.
2. Update the anchor manifest in `tools/lint-vision-doc/check.py`
   if you add, remove, or rename an anchor.
3. Bump the `Status: Current as of YYYY-MM-DD.` line.
4. Run the guard before commit.

The guard is deliberately not wired into `cargo test` or `pnpm
test` — it is a doc linter, not a code test. Run it manually or
from the session check set; a future CI config will run it on
every PR that touches any anchor file.
