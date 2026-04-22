# Voice V1 Step 2 — `SpeechProvider` trait + whisper.cpp adapter scaffold — execution report (2026-05-10)

**Status:** Shipped locally on `dev`. Push not authorized.
**Scope:** Provider abstraction + one local adapter scaffold.
**Healthcheck only.** No transcription wiring. No audio capture. No
commands. No UI. No registry. No persistence.

## Goal

Stand up the Voice V1 provider abstraction in L4 so later steps can
plug transcription in without reshaping the interface. The real
`transcribe` wire call lands in step 4 alongside the
`transcribe_utterance` Tauri command.

## Surfaces touched

### P1 — Provider abstraction

- **`packages/l4-router/src/speech.rs`** (new, 298 lines including
  tests). Mirrors `packages/l4-router/src/vision.rs` section by
  section:
  - `SpeechRequest { audio_b64, mime, sample_rate, channels, language }`.
  - `SpeechResponse { text, confidence, prompt_tokens, completion_tokens }`.
  - `trait SpeechProvider: Send + Sync` with `id`, `label`,
    `healthcheck`, `transcribe`, `list_models` (default empty),
    `set_model` (default no-op `Ok`), `current_model` (default
    `None`).
  - `split_audio_data_url` pure helper, analogous to
    `split_data_url` but pins MIME to `audio/*`.
  - Compile-time object-safety assertion via
    `_assert_object_safe(p: Arc<dyn SpeechProvider>)`.
- **`packages/l4-router/src/lib.rs`**: new `pub mod speech;` plus
  re-exports of `SpeechProvider` / `SpeechRequest` / `SpeechResponse`
  / `split_audio_data_url`.

### P2 — Whisper.cpp adapter scaffold

- **`packages/l4-router/src/providers/whispercpp_speech.rs`** (new,
  ~395 lines including tests). Mirrors `llamacpp_vision.rs`:
  - `WhisperCppConfigError` enum — distinct from
    `OllamaConfigError` / `LlamaCppConfigError`, as required.
  - `WhisperCppSpeechConfig` struct + `from_env` returning
    `Option<Result<Self, WhisperCppConfigError>>` (same shape as
    `LlamaCppVisionConfig::from_env`).
  - `WhisperCppSpeechProvider` struct with `base_url: String`,
    `model: RwLock<String>`, `language: Option<String>`,
    `timeout_ms: u64`, and a preconfigured `ureq::Agent`.
  - Full `SpeechProvider` impl:
    - `id() = "whispercpp-speech"`.
    - `label()` = `whisper.cpp · <model> · <base_url>`.
    - `healthcheck()` probes the root `/` (whisper.cpp's HTTP
      server does not expose a single canonical health endpoint
      across builds; `/` always responds with either the demo
      page or a JSON index, and any non-transport-error response
      is treated as "daemon is up"). Errors include the full URL
      and a `whispercpp-speech` marker so operators can diagnose
      without guessing.
    - `transcribe()` returns
      `Err(L4Error::ProviderUnknown { detail: "whispercpp-speech: transcription wiring deferred to Voice V1 step 4 (transcribe_utterance)" })`
      so any accidental caller before step 4 gets a loud signal
      instead of a silent empty transcript — lines up with the
      "no silent STT fallback" constraint from the design doc.
    - `set_model` rejects empty / whitespace ids; round-trips
      through the `RwLock<String>`.
    - `current_model` reports the active id.
    - `list_models` inherits the trait default (empty vec) —
      real probing is deferred until step 3 when registry
      persistence + the runtime-swap surface land.
- **`packages/l4-router/src/providers/mod.rs`**: new
  `#[cfg(feature = "speech-whispercpp")] pub mod
  whispercpp_speech;` and re-exports.

### Feature flag

- **`packages/l4-router/Cargo.toml`**: new feature
  `speech-whispercpp = ["dep:ureq"]`. Independent of
  `ollama-provider` and `vision-llamacpp` so users can enable any
  combination.

## Env configuration

| Env var | Required | Default | Notes |
| ------- | -------- | ------- | ----- |
| `AETHER_WHISPERCPP_SPEECH_MODEL` | yes | — | Opt-in gate. If unset, `from_env` returns `None` so the shell falls back cleanly. Trimmed-empty also returns `None`. |
| `AETHER_WHISPERCPP_SPEECH_BASE_URL` | no | `http://127.0.0.1:8081` | Empty-string is rejected (`EmptyBaseUrl`). |
| `AETHER_WHISPERCPP_SPEECH_LANGUAGE` | no | `None` (auto) | ISO-639-1 hint. Trimmed-empty is rejected (`EmptyLanguage`) — distinct from "unset". |
| `AETHER_WHISPERCPP_SPEECH_TIMEOUT_MS` | no | `60_000` | Bad parse → `InvalidTimeout(raw)`. |

## Tests added (29 new, all green)

### `packages/l4-router/src/speech.rs::tests` (13 tests)

- `default_list_models_is_empty`.
- `default_set_model_is_noop_ok`.
- `default_current_model_is_none`.
- `default_transcribe_is_required` — locks the trait's "every
  adapter must consciously implement transcription" contract.
- `dyn_speech_provider_is_callable` — runtime dynamic dispatch
  round-trip through `Arc<dyn SpeechProvider>`.
- `split_audio_data_url_parses_wav`.
- `split_audio_data_url_rejects_non_data_url`.
- `split_audio_data_url_rejects_missing_separator`.
- `split_audio_data_url_rejects_non_base64_encoding`.
- `split_audio_data_url_rejects_empty_mime`.
- `split_audio_data_url_rejects_non_audio_mime` — prevents
  accidentally routing image payloads through the speech pipeline.
- `speech_request_struct_roundtrips_defaults`.
- `speech_response_optional_fields_default_to_none`.
- `_assert_object_safe` is a compile-time check, not a runtime
  test, but it ships alongside the module.

### `packages/l4-router/src/providers/whispercpp_speech.rs::tests` (16 tests)

Env-reading tests share a process-wide `ENV_MUTEX` and call
`unset_env()` before/after — pattern lifted verbatim from
`llamacpp_vision.rs::tests`.

- `from_env_returns_none_without_model_var`.
- `from_env_returns_none_for_whitespace_model`.
- `from_env_picks_up_explicit_model_with_defaults`.
- `from_env_picks_up_explicit_language`.
- `from_env_rejects_empty_base_url`.
- `from_env_rejects_empty_language` — the "empty vs unset"
  distinction.
- `from_env_rejects_malformed_timeout`.
- `from_env_accepts_valid_timeout`.
- `provider_id_is_stable`.
- `label_reflects_model_and_base_url`.
- `set_model_round_trips_and_label_reflects_new_model`.
- `set_model_rejects_empty_id`.
- `transcribe_returns_scaffold_error` — pinned to the exact
  "deferred to Voice V1 step 4" marker so a future accidental
  "fix" by removing the scaffold error without wiring real
  inference fails loudly.
- `language_accessor_reflects_config`.
- `healthcheck_fails_cleanly_against_unreachable_daemon` — points
  at `http://127.0.0.1:1` with a 500 ms timeout; verifies the error
  shape is `ProviderUnknown`, the detail contains the
  `whispercpp-speech` marker, and the probe does not hang the
  test.
- `default_list_models_is_empty_for_scaffold`.

### Full check matrix — all green

- `cargo fmt --all -- --check` — clean (applied once to reformat
  new file per `rustfmt` defaults).
- `cargo check --workspace` — clean (pre-existing warnings only).
- `cargo check -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp` — clean.
- `cargo test --workspace` — **133 passed / 0 failed**.
- `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp` — **86 / 86** (was 57; +29).
- `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp` — **107 / 107** unchanged.
- `python tools/lint-layer-boundaries/check.py` — 0 violations.
- `python tools/lint-vision-doc/check.py` — OK, 51 anchors.
- `apps/desktop && pnpm typecheck` — clean.
- `apps/desktop && pnpm build` — clean, `built in 1.39s`.
- `apps/desktop && pnpm test` — **86 / 86** unchanged.

## Hard-constraint compliance

- No Tauri commands.
- No frontend UI.
- No `voice_provider.json` work.
- No `VoiceRegistry`.
- No `transcribe_utterance`.
- No audio capture.
- No real STT inference (transcribe scaffold errors loudly).
- No streaming or continuous listening.
- No wake word / VAD.
- No TTS.
- No new vision providers.
- No unification of `LlamaCppConfigError` / `OllamaConfigError`
  with `WhisperCppConfigError`.
- No L5 `AuditRecordEvent` changes.
- No widening of `vision_provider.json`.
- No new test dependencies — `ureq`, `thiserror`, `serde_json`,
  and the standard-library `env` / `sync` / `time` modules were
  already present. Tests use only `std` + types already in scope.
- Mic permissions (step 1) untouched.

## Divergences from the design doc

One refinement, which extends the design rather than contradicting
it:

- **`WhisperCppConfigError::EmptyLanguage`** — the design doc only
  lists invalid-timeout and empty-base-URL errors; I added
  `EmptyLanguage` because "language env var set to whitespace" is
  semantically different from "unset". An `""` language set by a
  broken shell script should not silently fall through to
  auto-detect — the user asked for a specific language and the
  adapter should say "that value is malformed". Keeps the contract
  honest. The design doc says "adapter owns its own taxonomy", so
  this is inside the envelope.

No other divergences. The trait shape, request/response fields, env
names, and feature flag all match §2 of `docs/VOICE-V1-ARCHITECTURE.md`.

## Design decisions worth reviewing

1. **`transcribe` returns a scaffold error rather than being absent
   from the trait.** Keeps the interface stable across steps 2–4 so
   the registry work in step 3 can depend on the final shape. The
   error detail is pinned to the literal string
   `"deferred to Voice V1 step 4 (transcribe_utterance)"` so step
   4 can grep the codebase for it to verify no accidental shadow
   implementations got left behind.
2. **Healthcheck probes `/`, not `/health` or `/v1/models`.**
   whisper.cpp's HTTP server wrappers vary a lot between builds;
   `/` is the one thing every build serves. Trade-off: a server
   that accepts HTTP but is internally broken will pass this
   healthcheck. That's acceptable because step 4's `transcribe`
   call is the authoritative "can this provider do work?" signal
   — the healthcheck only needs to catch "daemon unreachable".
3. **`list_models` uses the trait default (empty vec).** Real
   model discovery (filesystem scan for `ggml-*.bin` under the
   models dir, or `/v1/models` if the wrapper exposes it) is a
   step 3 concern because that's where the runtime-swap UI lands.
   Shipping an empty default now avoids locking in the wrong
   discovery shape.

## What is deliberately NOT in this slice

- No `VoiceRegistry` — step 3.
- No `voice_provider.json` — step 3.
- No Tauri commands — step 4.
- No `transcribe_utterance` — step 4.
- No real STT inference — step 4.
- No `VoicePanel` UI — step 5.
- No Trust drawer voice rows — step 5.
- No rot guard for `VOICE-V1-ARCHITECTURE.md` — step 6.
- No integration with the mic permission surface from step 1 —
  that happens at the capture site in step 4, not in the provider.

## Next step (after this one)

Voice V1 step 3 — `voice_provider.json` + `VoiceRegistry`. Mirrors
`vision_registry.rs` and `vision_provider.json`. Additive-default-
safe contract, tests, registry that the shell's AppState holds
behind an `Arc<dyn SpeechProvider>`.
