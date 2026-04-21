# P1 — Second VisionProvider implementation (2026-04-26)

## Choice and rationale

Second provider: **llama.cpp HTTP** (`llama-server`'s OpenAI-compatible
`/v1/chat/completions`). Picked over a second-Ollama-variant because
the wire format is meaningfully different — OpenAI `image_url`
content blocks vs Ollama's `images` array — which actually validates
the [`VisionProvider`] trait surface end to end. Picked over a remote
provider because the run charter prefers local-first.

## What shipped

### L4 — `packages/l4-router/src/providers/llamacpp_vision.rs` (new)

- `LlamaCppVisionConfig { base_url, model, timeout_ms }`. Default
  base URL `http://127.0.0.1:8080`, default timeout 120 s.
- `LlamaCppVisionConfig::from_env() -> Option<Result<…>>` — returns
  `None` when `AETHER_LLAMACPP_VISION_MODEL` is unset; returns
  `Some(Err(_))` only when env opt-in is present but malformed.
- `LlamaCppConfigError` defined locally in the same module so the
  adapter can be enabled without depending on the Ollama feature.
- `LlamaCppVisionProvider` implements `VisionProvider`:
  - `id() -> "llamacpp-vision"` (distinct from Ollama),
  - `label()` references `"llama.cpp"`,
  - `healthcheck()` probes `/health`,
  - `analyze()` POSTs to `/v1/chat/completions` with the OpenAI
    content-block shape; reattaches the full `data:image/...;base64,...`
    URL locally because OpenAI's `image_url` content block expects it.
- `build_vision_payload` and `parse_vision_response` exposed for tests.

### L4 — `Cargo.toml`, `lib.rs`, `providers/mod.rs`

- New cargo feature `vision-llamacpp = ["dep:ureq"]` independent of
  `ollama-provider`. Both can be enabled or disabled separately.
- Re-exports gated under the new feature.

### Tests (10 new, all in `llamacpp_vision::tests`)

- `from_env_returns_none_without_model_var`
- `from_env_picks_up_explicit_model_with_defaults`
- `from_env_rejects_malformed_timeout`
- `build_vision_payload_uses_openai_content_blocks`
- `parse_vision_response_extracts_text_and_token_counts`
- `parse_vision_response_handles_missing_usage`
- `parse_vision_response_errors_on_empty_choices`
- `parse_vision_response_errors_on_missing_choices`
- `analyze_rejects_empty_image`
- `provider_id_and_label_are_distinct_from_ollama`

## Verification

- `cargo fmt --all -- --check` — clean.
- `cargo check --workspace` — clean.
- `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp`
  — **45 passed** (was 35; +10 llamacpp tests).
- `python tools/lint-layer-boundaries/check.py` — 0 violations.

## Notes for review

- **Independent feature flags.** `ollama-provider` and
  `vision-llamacpp` are independent. The build matrix is:
  - default (neither): no network deps,
  - `ollama-provider` only: Ollama text + vision adapters available,
  - `vision-llamacpp` only: llama.cpp vision available, no text route,
  - both: full set.
- **No new abstractions.** I deliberately did not introduce a
  provider-factory layer or a config DSL — two providers only; the
  trait + per-adapter `from_env` is enough.
- **Image bytes are still transient.** Same contract as Ollama vision
  — payload only travels through the request, never persisted.
- **`LlamaCppConfigError` mirrors the shape of `OllamaConfigError`**
  but is its own type so the two adapters do not couple at the
  feature-flag boundary.
