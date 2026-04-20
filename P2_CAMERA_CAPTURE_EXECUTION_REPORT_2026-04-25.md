# P2 — Camera capture abstraction (2026-04-25)

## Goal

Land a camera capture surface — start, stop, sample-frame — gated by
the P1 permission model, with a simple right-side panel that mirrors
the existing Trust / Settings drawers.

## What shipped

### Frontend — `apps/desktop/src/components/CameraPanel.tsx` (new)

- Right-side drawer mirroring the Trust / Settings visual language.
- Permission gate: reads `getMediaPermissions()` on open; when the
  camera is `deny` the panel renders a disabled state and never
  touches `getUserMedia`. When `ask`, the panel surfaces a one-click
  inline "Allow camera" button that flips the stored posture so the
  user is in control.
- `start camera` / `stop camera` controls. Camera is only acquired
  when the user explicitly hits "Start camera" — default OFF.
- Live `<video>` preview element bound to the active stream. A
  red-dot indicator + label makes the ON/OFF state unmistakable.
- Cleanup is robust: closing the panel, hitting Stop, or
  unmounting all release the underlying tracks via
  `track.stop()`.
- Capture helper: draws the current frame onto a hidden canvas and
  encodes it as a JPEG data URL. Used by the P3 path; the abstraction
  itself stops here.

### Header / App wiring

- `Header.tsx` gains a "Camera" button next to "Settings".
- `App.tsx` widens the `drawer` discriminant to include `"camera"`
  and renders the panel. `onFrameAnalyzed` handler appends the
  returned transcript message into the main conversation view (used
  by P3).

## Behaviour matrix

| Permission | Panel behaviour |
| ---------- | --------------- |
| `allow`    | Start/Stop enabled. Capture allowed. |
| `ask`      | Inline "Allow camera" CTA; Start disabled until user flips state. |
| `deny`     | Disabled message; Start hidden; never calls `getUserMedia`. |

## Verification

- `cd apps/desktop && pnpm typecheck && pnpm build` — clean.
- Workspace builds and tests stay green.
- Manual UI verification deferred to a session where Don can drive
  the actual camera surface; the permission gate, start/stop, and
  cleanup paths are exercised via the build's type checker plus the
  shared abstraction's call sites.

## Notes for review

- The capture abstraction is webview-side because Tauri's permission
  model defers media device acquisition to the embedded browser, and
  the browser ships the `MediaDevices` API we already need. A
  future Rust-side capture path (e.g. native v4l2 / DXGI) would
  consult the same gate via `state.evaluate_media_permission`.
- The optional "note" input is rendered here even though it logically
  belongs to P3 — keeping it next to the capture button avoids a
  context switch.
- No continuous capture, no streaming. The only frames that leave
  this panel are the ones the user explicitly captures via the P3
  button.
