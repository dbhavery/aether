# whisper.cpp real inference wiring — execution report (2026-05-14)

**Status:** Shipped locally on `dev` (commits `a84e6ea`, `b2b7963`). Push not authorized.

## Goal

Replace the scaffold-only `transcribe` implementation on
`WhisperCppSpeechProvider` with a real HTTP call to
`whisper-server`'s `/inference` endpoint. Keep every contract the
shell's Voice V1 step 4 path relied on — no silent fallback,
clear user-visible errors on failure, local-first.

## Surfaces touched

### `packages/l4-router/src/providers/whispercpp_speech.rs`

- `transcribe` body replaced. Flow:
  1. Decode `req.audio_b64` via the new inline base64 decoder.
     Empty decoded payload → `L4Error::ProviderBadResponse`.
  2. Resolve language precedence: per-request hint > adapter
     config > server auto-detect (no `language` part).
  3. Build RFC 2046 multipart/form-data body with a `file` part
     (binary WAV bytes, MIME-derived filename) and an optional
     `language` part.
  4. POST to `<base_url>/inference` via `ureq`.
  5. Parse the JSON response (`{"text": "..."}`, extra fields
     dropped silently). Non-JSON responses surface as
     `ProviderBadResponse` with the parse error.
- New module-private helpers, all pure + unit-tested:
  - `WhisperResponse` — minimal serde target.
  - `derive_filename(mime)` — MIME → extension map (wav / mp3 /
    ogg, default wav).
  - `multipart_boundary()` — unique-per-call boundary
    (`----aether-whispercpp-<pid>-<nanos>-<counter>`).
  - `build_multipart_body(boundary, filename, mime, audio,
    language)` — assembles the body, CRLF-terminated, closing
    boundary included.
  - `decode_base64(input) -> Result<Vec<u8>, String>` — ~50-line
    pure-Rust decoder that tolerates whitespace and enforces
    length. Avoids adding the `base64` crate for a single call
    site.
  - `decode_base64_char(b)` — alphabet lookup.

### `apps/desktop/src-tauri/src/commands.rs`

- Replaced the shell-side sanity test
  `whispercpp_scaffold_error_still_pinned` (which grep-locked the
  old "deferred" marker) with
  `whispercpp_transport_failure_surfaces_loudly`. The new test
  hits `127.0.0.1:65535` with a 1 ms timeout and asserts the
  returned error identifies the endpoint (`127.0.0.1:65535` or
  `/inference`). This locks the **no-silent-empty-transcript**
  contract across the scaffold → real-inference transition.

### New L4 tests (+10)

- `transcribe_rejects_empty_audio`
- `transcribe_rejects_malformed_base64`
- `transcribe_surfaces_transport_error_for_unreachable_server`
- `decode_base64_round_trips_simple_payloads`
- `decode_base64_tolerates_whitespace`
- `decode_base64_rejects_bad_chars`
- `decode_base64_rejects_bad_length`
- `build_multipart_body_includes_file_part_and_boundary`
- `build_multipart_body_emits_language_part_when_provided`
- `derive_filename_defaults_to_wav`
- `multipart_boundary_is_unique_across_calls`

## Checks — all green

- `cargo fmt --all -- --check` — clean
- `cargo test --workspace` — **137 / 137**
- `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp` — **96 / 96** (was 86; +10)
- `apps/desktop/src-tauri` — 154 / 154
- `python tools/lint-layer-boundaries/check.py` — 0 violations
- `python tools/lint-vision-doc/check.py` — 51 anchors
- `python tools/lint-voice-doc/check.py` — 48 anchors
- `apps/desktop` pnpm typecheck/build/test — 145 / 145

## Hard-constraint compliance

- **No push.** ✅
- **No remote speech providers.** ✅
- **No silent fallback.** ✅ Every error path returns
  `L4Error::Provider{Unknown,BadResponse}`; the shell's
  `transcribe_utterance` maps these to visible errors.
- **No durable raw audio.** ✅ Audio lives in `Vec<u8>` only
  until the `send_bytes` call; nothing persisted.
- **No new heavy dependencies.** ✅ Inline base64 decoder — no
  new crate in `Cargo.toml`.

## Design decisions worth noting

1. **Inline base64 decoder vs `base64` crate.** One call site,
   single-utterance payloads, tolerant-of-whitespace input. 50
   lines + 4 tests beats a new dependency.
2. **Filename sniffing.** whisper-server treats the extension
   as a format hint. Defaulting unknown MIMEs to `.wav` keeps the
   sniffer honest for the Voice V1 native format.
3. **Boundary uniqueness via pid + nanos + atomic counter.**
   Cryptographic randomness isn't needed; the boundary just has
   to not collide with content and not collide across concurrent
   calls in the same process. Atomic counter guarantees intra-
   process uniqueness; pid + time handles the cross-process
   case.
4. **Language precedence.** Per-request hint beats adapter
   config beats server auto. Matches the design doc's intent and
   the shell's `TranscribeUtteranceRequest` contract (the shell
   can pass `None` and let the adapter decide).
5. **WhisperResponse deserializes only `text`.** Richer builds
   add `segments`, `language`, `duration`; serde drops them
   silently so future whisper-server version bumps stay
   compatible. Confidence / token counts are left `None` — the
   OpenAI-compatible surface doesn't report them.

## Known limitations / future work

- **No confidence signal surfaced.** Builds that expose
  segment-level logprobs could wire a min/avg into
  `SpeechResponse.confidence`; the trait already has the field.
- **No retry on transient failure.** A single POST fails loud.
  Future reliability slice could add bounded retries with
  backoff inside the adapter.
- **No live integration test.** Running a real whisper-server in
  CI is out of scope for this slice. A future
  `speech-whispercpp-live` feature flag could gate a test that
  stands one up and sends a known-good WAV.

## Next step

This closes the Voice V1 shipping gap: real whisper.cpp
inference is now wired end-to-end. The user-facing path is
ready for baseline quality measurement against the Voice V1
eval scenarios once the eval harness (landed separately) grows
live-backend support.
