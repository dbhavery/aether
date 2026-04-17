# Sync From Upstream Isabelle

**Purpose:** Isabelle_Kunstig is Aether's rolling upstream for core modules. Isabelle advances faster than Aether can productize. When we need the latest voice pipeline, avatar pipeline, or memory stack in Aether, we port — not copy. This document defines the deterministic rules for that port.

**Do not edit Isabelle_Kunstig from Aether work.** Another agent is actively developing Isabelle (per memory `project_two_agent_coordination.md`, last confirmed 2026-04-10). Reads only. Writes happen in Aether.

---

## 1. Why sync, not vendor

We could git-submodule Isabelle into Aether and import modules directly. We don't, because:

- Isabelle modules have hardcoded Don-specific assumptions (paths, reference voice, speaker verify, tool access). These MUST be stripped before public shipping.
- Isabelle's test data and asset pipeline reference `I:\IsabelleData\` — a drive path that doesn't exist on users' machines.
- Git history contains PII that was sanitized out of Aether's `dc92ba3 [SECURITY] Remove PII and generalize personal references` commit. Vendoring Isabelle would re-import that history.
- Aether needs independence to diverge. The v2 rebuild will have no Isabelle code at all.

So: **we port modules with transformations, not vendor them as-is.**

---

## 2. Module port status (as of 2026-04-17)

| Module | Aether state | Isabelle state | Action |
|--------|-------------|----------------|--------|
| `src/core/` | March snapshot | Current | Re-port in P1 |
| `src/shared/` | March snapshot | Current | Re-port in P1 |
| `src/voice/` | March snapshot (4 files) | Current (12 files) | Re-port in P1, strip wake word + speaker verify |
| `src/avatar/` | March snapshot (4 files) | Current (18+ files) | Re-port in P1, LivePortrait only, drop other engines |
| `src/brain/` | March snapshot | Current | Re-port in P1, replace custom router with litellm tier abstraction |
| `src/memory/` | March snapshot | Current | Re-port in P1, add per-persona isolation |
| `src/desktop/` | PySide6 UI | PySide6 UI | **Rename to `src/desktop_legacy/`** — do NOT port forward. Next.js replaces it. |
| `src/tools/` | March snapshot | Current | **DROP.** No tool execution in v1.0. |
| `src/agents/` | March snapshot | Current | **DROP.** No agents in v1.0. |
| `src/persona/` | March snapshot | Current | **Replace entirely** with `src/personas/` (persona pack loader, different scope). |
| `src/notifications/` | March snapshot | Current | **DROP.** No scheduled notifications in v1.0. |
| `src/media/` | March snapshot | Current | **DROP.** No vision in v1.0. |
| `src/data_server/` | March snapshot | Current | **DROP.** No REST data server in v1.0. |
| `android/` | March snapshot (spec only) | Current | **DROP.** No mobile in v1.0. |

---

## 3. Port transformations

The sync script (`scripts/sync_from_isabelle.py`, to be built in P1) applies these transformations deterministically. Manual hand-editing is forbidden — every modification must be a rule the script applies, so a re-sync gives the same result.

### 3.1 Name rewrites

| From | To |
|------|-----|
| `isabelle` (in strings, comments, paths) | `aether` |
| `Isabelle` | `Aether` |
| `ISABELLE` | `AETHER` |
| `IsabelleEvent` | `AetherEvent` |
| `isabelle_config.yaml` | `aether_config.yaml` |
| `I:\IsabelleData\...` | `<user_data_dir>/...` (path resolver injected) |
| `I:/IsabelleData/...` | `<user_data_dir>/...` |
| `src.shared.config.IsabelleConfig` | `src.shared.config.AetherConfig` |

### 3.2 Path rewrites

All occurrences of literal paths pointing to Don's filesystem get routed through `src/shared/paths.py`:

```python
# Before (Isabelle)
CHROMA_DIR = r"I:\IsabelleData\chroma"

# After (Aether)
from src.shared.paths import get_data_dir
CHROMA_DIR = get_data_dir() / "chroma"
```

`get_data_dir()` uses `platformdirs.user_data_dir("aether", "aether")` and creates the directory if missing.

### 3.3 Module deletions

The port script drops these files/directories entirely, without porting:

- `src/tools/` — all files
- `src/agents/` — all files
- `src/persona/` — all files (replaced by new `src/personas/`)
- `src/notifications/` — all files
- `src/media/` — all files
- `src/data_server/` — all files
- `android/` — entire directory
- `src/voice/wake_word.py`, `wake_context.py`, `speaker_verify.py`
- `src/avatar/ditto_engine.py`, `ditto_worker.py`, `flashhead_engine.py`, `flashhead_worker.py`, `musetalk_worker.py`, `face_animator.py`, `a2f_proto/` — keep LivePortrait only
- `src/brain/router.py` — replaced by new litellm-based router
- `src/desktop/` — renamed to `src/desktop_legacy/` and frozen

### 3.4 Conditional removal

Some files have Don-specific blocks that need targeted removal, not whole-file deletion:

- `src/voice/pipeline.py` — remove wake word integration, remove speaker verify integration, replace auto-VAD with push-to-talk events.
- `src/voice/stt.py` — remove ElevenLabs Scribe as primary (it's paid); default to faster-whisper local.
- `src/voice/tts.py` — remove hardcoded `reference_voice.wav`; load reference per active persona.
- `src/shared/config.py` — remove all Don-specific default values (voice reference path, data drive path, Picovoice key, etc.); default to placeholder values that fail loud if not set.

### 3.5 Dependency filtering

`requirements.txt` after port should NOT include:
- `pvporcupine` (wake word — removed)
- `speechbrain` (speaker verify — removed)
- `insightface` (face recognition — removed)
- `winotify` (Windows toasts — removed with notifications)
- `apscheduler` (cron — removed with notifications)
- `langgraph`, `crewai` (agents — removed)
- `pyautogui`, `psutil` (tools — removed)
- `elevenlabs` (becomes optional-extras)

Added:
- `litellm` (already upstream, keep)
- `pywebview` (new)
- `keyring` (new)
- `platformdirs` (new)

---

## 4. Script design

`scripts/sync_from_isabelle.py` usage (implemented in P1):

```
Usage:
  python scripts/sync_from_isabelle.py [--dry-run] [--module MODULE] [--isabelle-path PATH]

Options:
  --dry-run             Show what would change, don't write.
  --module NAME         Sync one module only (core | shared | voice | avatar | brain | memory).
                        Default: all allowed modules.
  --isabelle-path PATH  Path to Isabelle_Kunstig repo. Default: ../Isabelle_Kunstig.
  --verify              After sync, run ruff + pyright + bandit on synced files.
```

Flow:
1. Read `ISABELLE_ALLOWLIST` from this doc (parsed as structured config).
2. For each module in the allow-list:
   a. Copy source files to aether `src/<module>/`.
   b. Apply all transformations.
   c. Run AST-based check: no remaining `I:\`, `isabelle`, `Isabelle` references.
   d. Run tests if the module has them.
3. Report summary: X files copied, Y files transformed, Z files rejected.
4. Commit the result with a structured message: `[SYNC] Port <module> from Isabelle@<sha> on <date>`.

---

## 5. Conflict resolution

If a sync would overwrite Aether-specific changes (e.g., new code added in Aether that doesn't exist in Isabelle), the script:

1. Detects divergence via content hash.
2. Refuses to overwrite.
3. Writes a `.sync-conflict` file next to the Aether version with the Isabelle version.
4. Exits with error; human resolves.

This ensures aether-side divergence never gets silently reverted.

---

## 6. Re-sync cadence

No fixed schedule. Re-sync when:
- A module has a significant upstream improvement we want (judged case-by-case).
- A critical bug is fixed upstream.
- Never during a release candidate stabilization window.

Each re-sync is a single PR on `dev` branch with the structured commit message, so we can audit what upstream change came in.

---

## 7. Anti-drift guarantees

- The sync script is the ONLY way to move code from Isabelle to Aether. Hand-copying is forbidden.
- Every ported file is stamped with a header comment: `# ported from Isabelle_Kunstig@<sha> at <date>`.
- A CI check (`scripts/verify_no_isabelle_strings.py`) fails the build if `isabelle` or `Isabelle` appears anywhere in Aether's `src/` (except inside ported comments).
- A CI check fails if a dropped module name (`tools`, `agents`, etc.) reappears under `src/`.

---

## 8. What this doc is NOT

- Not a dependency: Aether does not require Isabelle to build, run, or install. The sync script is a developer tool.
- Not a sync of the v2 rebuild: v2 will share no code with Isabelle. This doc only governs v1.0 modules.
- Not a substitute for reviews: every re-sync is reviewed by Don before merge to `dev`.
