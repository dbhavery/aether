# P2 — Per-provider model discovery in vision dropdown (2026-04-27)

## What shipped

### L4 — `vision::VisionProvider` trait

- New default-implemented method:
  ```rust
  fn list_models(&self) -> Result<Vec<String>, L4Error> {
      Ok(Vec::new())
  }
  ```
- Adapters that don't expose listings inherit the default and the UI
  renders "models unavailable" without changing.

### L4 — `OllamaVisionProvider`

- `list_models()` does GET `<base>/api/tags` and parses
  `models[].name`.
- `parse_tags_response(json)` exposed as a pure helper for tests.
- 3 new unit tests: ordered name extraction, missing root key,
  entries missing `name` skipped.

### L4 — `LlamaCppVisionProvider`

- `list_models()` does GET `<base>/v1/models` and parses `data[].id`
  (OpenAI-compatible shape).
- `parse_models_response(json)` exposed as a pure helper for tests.
- 3 new unit tests: ordered id extraction, missing root key,
  entries missing `id` skipped.

### Shell — `commands.rs`

- New `list_vision_models` Tauri command. Returns
  `VisionModelList { provider_id, models, error }`. Errors are
  returned **in-band** as a plain-language string so the dropdown
  never spams the user with modal noise.

### Shell — `main.rs`

- Command registered in `invoke_handler!`.

### Frontend — `lib/types.ts`, `lib/api.ts`

- `VisionModelList` type + `listVisionModels()` typed wrapper.

### Frontend — `components/VisionBadge.tsx`

- Fetches the model list whenever the active provider id changes
  (or first renders with one).
- New `ModelListSection` — shows
  - "Loading models on this provider…" while fetching,
  - "Models unavailable for this provider." on failure / empty,
  - a row of pill-shaped chips (one per model id) on success.
- The chips are **informational only**; selecting a specific model
  is a follow-up.

## Verification

- `cargo fmt --all -- --check` — clean.
- `cargo check --workspace` — clean.
- `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp`
  — **51 / 51** (was 45; +6 model parse).
- `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp`
  — 54 / 54.
- `python tools/lint-layer-boundaries/check.py` — 0 violations.
- `pnpm typecheck && pnpm build && pnpm test` — clean (41 / 41 with
  P3's helpers added in the same `mediaTurns` module).

## Decisions for review

- **Default trait method vs sealed trait.** `list_models` defaults
  to `Ok(vec![])` so adapter authors don't have to opt in. The
  alternative (require every impl to implement) was rejected as
  needless friction for adapters that genuinely have no listing
  endpoint.
- **In-band errors over Tauri Err.** The Tauri command never returns
  an `Err` — failures collapse to `{ models: [], error: "…" }`.
  Keeps the dropdown logic linear and unmuddied by exception
  handling.
- **No model selection inside a provider.** This slice surfaces
  what's available; flipping the active model on a provider would
  require a per-adapter "set model" path and a runtime config swap
  (different from "switch provider"). Documented as next-session
  follow-up.
- **`/api/tags` is also the Ollama healthcheck endpoint.** Two
  separate calls; the daemon is fine with this and we get
  independent failure semantics.
