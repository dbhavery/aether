# Aether Desktop Shell

Native window that hosts the Aether Next.js frontend. Wraps WebView2 via
[pywebview](https://pywebview.flowrl.com/). Used as the dev container while
iterating on the UI and as the shipping product shell in the installer.

## Two run modes, auto-detected

The shell probes `http://127.0.0.1:3000/` on launch (1 s timeout):

- **Dev mode** — if the dev server answers, load it directly. Changes to
  `frontend/` hot-reload inside the window.
- **Packaged mode** — otherwise load `frontend/out/index.html` produced by
  `cd frontend && npm run build`.

No explicit flag needed; start (or stop) the dev server to switch modes.

## Running locally

From the repo root, with a Python 3.13 `.venv` created and `pywebview`,
`sounddevice`, and `soundfile` installed:

**Dev mode** (recommended while editing the UI):

```powershell
# Terminal 1 — start Next.js dev server
cd frontend
npm install --legacy-peer-deps
npm run dev
```

```powershell
# Terminal 2 — launch the shell (from repo root)
.\desktop\launcher.ps1
```

**Packaged mode** (closer to the shipped product):

```powershell
cd frontend; npm run build; cd ..
.\desktop\launcher.ps1
```

For debugging the shell itself (logs on stderr instead of hidden):

```powershell
.\.venv\Scripts\python.exe -m desktop.main
```

## Backend supervision

| Situation at launch | Shell behavior |
|---|---|
| Port 8765 already in use | Attach to the existing backend. Do not spawn. Do not stop on close. |
| Port 8765 free | Spawn `python -m src.main` as a child. Terminate it when the window closes. |

This means running the shell while a separate `python -m src.main` is active
is safe — the shell will never kill a backend it didn't start.

## JavaScript bridge

The frontend can call `window.pywebview.api.<method>(...)`:

| Method | Signature | Purpose |
|---|---|---|
| `open_file_dialog` | `(options) -> string[] \| null` | Native open/save dialog |
| `get_keyring_token` | `() -> string \| null` | Short-lived WS auth token (proxied via `/auth/token`) |
| `open_external` | `(url) -> boolean` | Open `http(s)://` URL in the default browser |
| `get_app_info` | `() -> {version, build, platform, data_dir}` | About-panel metadata |

`open_external` refuses non-web URLs so a page loaded in the webview cannot
use the bridge to launch arbitrary local files.

## Window chrome

- Size: 1280x860 (resizable).
- Minimum: 1024x720.
- Background color: `#0B0B0F` (matches the dark theme).
- Text selection enabled.
- No close confirmation dialog — closing the window shuts down the shell.

## Rebuilding after frontend edits

- In dev mode: nothing — Next.js hot-reloads.
- In packaged mode: `cd frontend && npm run build`, then relaunch the shell.

## Troubleshooting

**Blank window.** The shell found neither a dev server nor a static export.
Start `npm run dev` in `frontend/`, or build the export with `npm run build`.

**"WebView2 Runtime not installed" (Windows).** Install the
[Evergreen WebView2 Runtime](https://developer.microsoft.com/en-us/microsoft-edge/webview2/).
The v1.0 Inno Setup installer will bundle the bootstrapper so this error
won't surface for end users.

**"Port 8765 already in use" at backend startup.** Another Aether is already
running. The shell attaches to it rather than failing — open the existing
window, or close the other process if you want a fresh backend.

**Closing the window doesn't kill the backend.** Expected only when the
shell *attached* to an already-running backend. If the shell spawned the
backend itself, the child is terminated on window close and again via
`atexit` as a belt-and-braces fallback.

**Shell launches but the window never appears.** Look for a stuck
`pythonw.exe` in Task Manager. Run the shell in foreground
(`python -m desktop.main`) to see the error on stderr.
