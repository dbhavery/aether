# infra/

Build, bundling, and operational config. Empty in Wave 1.

Planned (see `ARCHITECTURE.md` §1 and `docs/DISTRIBUTION.md`):

- `tauri/` — Tauri bundling config per target OS.
- `installer-inno/` — Windows Inno Setup scaffold for OSS Preview.
- `updater/` — signed updater channels.
- `codesign/` — code-signing key management (references external secure storage).

Wave 3 lands the first infra entries alongside `apps/desktop/`.
