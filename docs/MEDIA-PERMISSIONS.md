# Media permissions

> **Status:** Current as of 2026-04-29. Anchored by
> [`tools/lint-media-permissions-doc/`](../tools/lint-media-permissions-doc/) —
> the rot guard fails when the symbols, commands, env vars, or UI
> components named below disappear from the code.

Companion keeps a small, **local-only** record of how much it is allowed
to look at — currently camera and (scaffolded) screen capture. This
document is the source of truth for the model.

## Model

The shell exposes a tri-state per device:

| Wire value | Meaning |
| ---------- | ------- |
| `allow`    | Capture may proceed without an in-app prompt. The OS-level permission prompt is still authoritative. |
| `ask`      | Capture must request approval first. Default for both devices. |
| `deny`     | Capture is hard-disabled. Future capture sites short-circuit instead of acquiring the device. |

Two devices are tracked:

| Wire value | Meaning |
| ---------- | ------- |
| `camera`   | Webcam frames sampled from the in-app camera panel. |
| `screen`   | On-screen content. Scaffolded for a later slice; no capture surface today. |

The Rust types live in [`apps/desktop/src-tauri/src/media_permissions.rs`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/media_permissions.rs).
The TypeScript mirrors live in [`apps/desktop/src/lib/types.ts`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/lib/types.ts).

## Persistence

The current posture is stored as JSON beside the durable session
memory file:

- Windows: `%APPDATA%/Aether/media_permissions.json`
- Linux:   `$XDG_DATA_HOME/Aether/media_permissions.json`
- macOS:   `~/Library/Application Support/Aether/media_permissions.json`

Writes are atomic (write-to-temp, then rename) so a mid-write crash
cannot leave a half-written file the next boot would reject. A
missing or malformed file falls back to `{ camera: ask, screen: ask }`
— never `allow`.

## Enforcement

Capture sites must consult the gate before touching the device:

```rust
match state.evaluate_media_permission(MediaKind::Camera) {
    CaptureGate::Proceed    => /* call getUserMedia / DXGI / etc. */,
    CaptureGate::PromptUser => /* surface in-app approval; do not capture */,
    CaptureGate::Deny       => /* surface "disabled" message; never touch device */,
}
```

The same check runs server-side in `analyze_frame` so the model is
never invoked with a frame the user has not authorised.

## Tauri command surface

| Command                  | Args                             | Returns              |
| ------------------------ | -------------------------------- | -------------------- |
| `get_media_permissions`  | —                                | `MediaPermissions`   |
| `set_media_permission`   | `kind: MediaKind`, `state_value: PermissionState` | `MediaPermissions` |
| `analyze_frame`          | `request: { kind, frame_data_url, note? }` | `FrameAnalysisOutcome` |

`analyze_frame` is the P3 single-frame path — the camera UI captures a
frame from `<video>`, encodes it as a JPEG data URL, and posts it in.
Today the active model is text-only, so the data URL is verified as
well-formed and the model is asked the user's optional note (or a
default cue). When a vision-capable provider lands, the same command
will pass the data URL straight through.

## Tauri / webview security model

Three layers gate every capture call:

1. **Tauri capability allowlist**
   ([`apps/desktop/src-tauri/capabilities/default.json`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/capabilities/default.json)).
   Default-deny — only `core:default`, `core:window:default`,
   `core:event:default`, `core:app:default`. The `fs`, `shell`,
   `http`, `dialog`, and `notification` plugins are deliberately
   absent. The IPC commands available to the webview are exactly the
   ones registered in `tauri::generate_handler!` in `main.rs`.

2. **Webview `getUserMedia` / `getDisplayMedia`**. These are standard
   browser APIs the webview hosts; they do **not** require a Tauri
   capability. They are governed by the OS-level permission prompt
   and, on Windows, by WebView2 permission policies. Companion never
   bypasses these.

3. **In-app `media_permissions.json` gate** (this document). Sits in
   front of every capture site so the user has one local control
   surface for "may Companion see anything?" independent of the OS
   prompt history.

A future distribution build will additionally:

- pin a stricter CSP (already locked to `default-src 'self'` plus
  `data:` for image previews and the IPC channel),
- consider WebView2 permission policies for camera / microphone /
  screen capture explicitly per platform.

## Vision provider

When `AETHER_OLLAMA_VISION_MODEL` is set and the daemon healthchecks
at boot, `analyze_frame` substitutes the active text-model output
with a real vision response from Ollama (LLaVA, BakLLaVA,
gemma3:vision, qwen2.5-vl, …). When unset, capture still works but
the response reflects only the user's note — the pixels are not
sent to any model.

The `vision_status` Tauri command exposes the active provider label
so the UI can tell users upfront which path is live. The
[`VisionBadge`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/components/VisionBadge.tsx)
component renders this in both the camera and screen panels.

Configuration env vars (all opt-in):

| Var                                   | Default                         | Notes |
| ------------------------------------- | ------------------------------- | ----- |
| `AETHER_OLLAMA_VISION_MODEL`          | unset (no vision)               | Required to enable vision routing. |
| `AETHER_OLLAMA_VISION_BASE_URL`       | inherit `AETHER_OLLAMA_BASE_URL`, then `http://127.0.0.1:11434` | Vision daemon endpoint. |
| `AETHER_OLLAMA_VISION_TIMEOUT_MS`     | `120000`                        | Vision models are typically slower than text. |

## What this does NOT cover

- **Microphone**. The voice/STT track owns its own consent path.
- **Always-on observation**. There is no continuous capture loop —
  every frame is explicit, user-initiated, and round-tripped through
  the `analyze_frame` command.
- **Cross-device sync**. The file lives on this machine only.
