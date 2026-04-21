# P2 — Tauri capability allowlist hardening (2026-04-25, late evening)

## Summary

The existing capability allowlist is already aggressively
default-deny: only `core:default`, `core:window:default`,
`core:event:default`, `core:app:default` are enabled. The `fs`,
`shell`, `http`, `dialog`, and `notification` plugins are absent.
Tauri commands are added explicitly by the `tauri::generate_handler!`
macro in `main.rs`.

So the "hardening" pass for this session is **documentation and
clarification**, not surface reduction — there is no smaller surface
left to ship safely.

## What changed

### `apps/desktop/src-tauri/capabilities/default.json`

- Description extended to call out that webview-level `getUserMedia`
  / `getDisplayMedia` are governed by the OS picker + the in-app
  `media_permissions.json` gate, not by a Tauri capability.
- Cross-references `docs/MEDIA-PERMISSIONS.md`.

### `docs/MEDIA-PERMISSIONS.md`

- New "Tauri / webview security model" section laying out the
  three-layer gate:
  1. Tauri capability allowlist (default-deny).
  2. Webview `getUserMedia` / `getDisplayMedia` (OS prompt
     authoritative).
  3. In-app `media_permissions.json` gate (this document).
- Notes future-distribution work (CSP, WebView2 platform-specific
  permissions).
- New "Vision provider" reference block listing the env vars
  (`AETHER_OLLAMA_VISION_MODEL`, `AETHER_OLLAMA_VISION_BASE_URL`,
  `AETHER_OLLAMA_VISION_TIMEOUT_MS`) and what enables what.

## Verification

- `pnpm build` still produces a runnable webview bundle.
- The current CSP (`default-src 'self'; script-src 'self';
  style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src
  'self' data:; connect-src 'self' ipc: http://ipc.localhost`)
  permits the in-app frame data URLs (img-src `data:`) and the IPC
  channel — both required for the camera/screen panels.
- Tauri capability set confirmed unchanged by a manual diff:
  `core:default`, `core:window:default`, `core:event:default`,
  `core:app:default`.

## Notes for review

- `connect-src` does NOT need to grow to include the Ollama daemon
  URL — the vision provider call happens inside the Rust backend
  (via `ureq`), not from the webview. The webview only ever talks
  IPC.
- If a future build embeds an HTTP-side observer (Tauri `invoke`
  emulation in the dev URL, etc.), that's the moment to revisit
  CSP `connect-src`.
