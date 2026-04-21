# Handoff — Continue the companion build (2026-04-27)

**Written:** 2026-04-25 (autonomous continuation run, late-evening update).
**Branch state:** `dev`, **15** commits ahead of origin/dev, **NOT pushed**.
**Next session mode:** broad autonomous build authorization on the
multimodal/video assistant track; no push authorization assumed.

---

## 0. Morning status

1. Branch `dev` has four new local commits on top of `d02f1b2`:
   - `cdf31f8` feat(l4,apps/desktop): vision-capable provider behind analyze_frame
   - `b94a613` docs(apps/desktop): document Tauri capability + media security model
   - `3f3ba95` feat(apps/desktop): media-only filter on Trust drawer's History tab
   - (this handoff commit)
2. Working tree clean.
3. Full check set is green:
   - `cargo fmt --all -- --check`
   - `cargo check --workspace`
   - `cargo test --workspace`
   - `cargo test -p aether-l4-router --features ollama-provider` (35/35; was 21)
   - `cargo test -p aether-l5-policy` (12/12)
   - `apps/desktop/src-tauri && cargo test` (37/37 default, 43/43 with ollama-provider)
   - `python tools/lint-layer-boundaries/check.py` (0 violations)
   - `apps/desktop && pnpm typecheck && pnpm build` (clean)
4. **Not pushed.** Push authorization must be explicit.

## 1. Commits landed this run

```
cdf31f8 feat(l4,apps/desktop): vision-capable provider behind analyze_frame
b94a613 docs(apps/desktop): document Tauri capability + media security model
3f3ba95 feat(apps/desktop): media-only filter on Trust drawer's History tab
```

## 2. Execution reports

- [P1_VISION_PROVIDER_EXECUTION_REPORT_2026-04-25.md](file:///C:/Users/dbhav/Projects/aether/P1_VISION_PROVIDER_EXECUTION_REPORT_2026-04-25.md)
- [P2_TAURI_HARDENING_EXECUTION_REPORT_2026-04-25.md](file:///C:/Users/dbhav/Projects/aether/P2_TAURI_HARDENING_EXECUTION_REPORT_2026-04-25.md)
- [P3_TELEMETRY_FILTER_EXECUTION_REPORT_2026-04-25.md](file:///C:/Users/dbhav/Projects/aether/P3_TELEMETRY_FILTER_EXECUTION_REPORT_2026-04-25.md)
- Updated doc: [docs/MEDIA-PERMISSIONS.md](file:///C:/Users/dbhav/Projects/aether/docs/MEDIA-PERMISSIONS.md)

## 3. What the product does now

Everything from the morning's run, plus:

- **`analyze_frame` is vision-capable.** Set
  `AETHER_OLLAMA_VISION_MODEL=llava:latest` (or any vision-aware
  Ollama model) and restart Aether. The shell healthchecks the
  daemon at boot; on success, the next "Analyze current frame"
  call sends the actual image to the model and the assistant
  response reflects the pixels. When unset (default OSS build),
  capture still works but the response reflects only the user's
  note — the pixels are not sent.
- **A vision-status badge** appears in both the camera and screen
  panels so users can tell upfront whether the next analyze call
  is vision-capable or text-only fallback.
- **Trust drawer History tab gains a Media-only filter.** A pill
  toggle isolates camera + screen frame turns from the full
  telemetry stream. Empty state copy adapts to the active filter.
- **Tauri capability surface is documented.** The allowlist was
  already minimal; this run adds the cross-references explaining
  the three-layer media security model (Tauri caps → webview API
  → in-app gate).

## 4. What to build next — multimodal track

> **Status update:** Yesterday's three priorities (vision provider,
> Tauri hardening, telemetry filter) all shipped this run. The
> remaining priority list focuses on the next horizon — provider
> portability, capture pipeline depth, and a few pieces of polish.

### Priority 1 — Second vision provider (or a generic vision adapter)

Right now `OllamaVisionProvider` is the only `VisionProvider` impl.
A second adapter (likely a remote provider like
Anthropic / OpenAI / Gemini) would:
- prove the trait surface is right,
- give Don a path to higher-quality vision when desired,
- exercise the privacy-posture gate (`PrivacyPosture::Strict`
  should refuse remote vision; `Balanced` should allow with cost
  warning).

If staying local, a llama.cpp-based vision adapter is also a
reasonable second impl.

### Priority 2 — `AETHER_OLLAMA_VISION_MODEL` runtime swap

Today the vision model is fixed at boot. Add a Tauri command to
swap it without restart so users can A/B between LLaVA and
gemma3:vision (or change models entirely) from the Settings drawer.

### Priority 3 — Camera/Screen panels: per-call cue history

The optional "note" input is one-shot. A small per-panel history
("repeat last cue", or a `<select>` of the last 5) would speed up
iterative analysis flows ("look again", "and now?").

### Priority 4 — Microphone consent (separate track)

Out of scope for the multimodal foundation. Mirror the model used
here when the voice/STT path lands.

### Priority 5 — Native (Rust-side) capture path

The current capture surface is webview-side. A Rust-native v4l2 /
DXGI capture would let a future headless / no-webview workflow
sample frames. Lower priority until there's a concrete consumer.

## 5. Risks / things to review first

- **Vision substitution shape.** When vision succeeds, the audit
  row's recorded provider on the L5 side reads `"reflex-stub"` or
  `"ollama"` (whatever the text router was), but the telemetry
  entry and transcript message reflect `"ollama-vision"`. This is
  intentional — L5 audited the policy decision, not the provider
  call. If you want the audit row to also reflect the vision
  provider, that's a deeper L5 / L4 contract change, not a small
  ergonomics tweak.
- **Vision daemon path is additive.** When vision is enabled the
  shell still runs the text turn engine (for policy/audit) and
  THEN calls the vision provider. That's one extra local call per
  frame turn. Cheap on Ollama; would matter if a remote text
  provider is wired.
- **Image bytes never persisted.** Confirmed in code review;
  memory writes only the cue + assistant reply.
- **CSP allows `data:` for img-src.** Required for the in-panel
  `<video>` → canvas → data URL preview pipeline. Tighter CSP
  would break the camera/screen panels.
- **`MEDIA_TURN_KINDS` is the source of truth.** Adding a new
  `kind` server-side without updating this set will silently leave
  it out of the Media-only filter.

## 6. Recommended next prompt (copy-paste)

```
You are Claude Code, continuing work on Aether.

Repo root:
C:/Users/dbhav/Projects/aether/

Branch:
dev

First:
1. Read the latest HANDOFF_2026-04-27_CONTINUE_COMPANION_BUILD.md.
2. Run `git status` and `git log --oneline -30`.
3. Read P1_VISION_PROVIDER_EXECUTION_REPORT_2026-04-25.md for
   the active VisionProvider trait surface.

Session focus (multimodal/video assistant track ONLY):
- P1: Add a second VisionProvider implementation. Recommended:
      a remote vision provider (Anthropic, OpenAI, or Gemini)
      gated by PrivacyPosture::Balanced (Strict must refuse).
      Alternatively a llama.cpp-based local adapter.
- P2: Tauri command to swap AETHER_OLLAMA_VISION_MODEL at
      runtime without restart, surfaced in Settings.
- P3: Per-panel cue history ("repeat last cue" or last-5
      <select>) on Camera and Screen panels.

Rules:
- No push, no release, no weakening tests or boundary rules.
- No streaming / continuous capture modes.
- No mic / voice work.
- Reuse the existing VisionProvider trait — don't re-design it
  for the second provider unless the surface is genuinely wrong.

Before stopping:
- keep git status clean if possible,
- commit with clear scoped messages,
- update execution reports and the handoff with what you did,
  what remains, and an explicit next prompt focused on this
  same multimodal foundation track.
```
