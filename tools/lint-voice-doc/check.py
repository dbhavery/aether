#!/usr/bin/env python3
"""Aether Voice V1 architecture-doc rot guard.

Mirror of `tools/lint-vision-doc/check.py`. Keeps
`docs/VOICE-V1-ARCHITECTURE.md` honest: the doc claims specific
files, symbols, and string constants (telemetry kinds, env var
names, provider ids, config filenames) exist in code. When any
disappears (rename, delete, typo), this linter fails.

Not a prose parser. The manifest below is the contract between the
doc and the code; a Voice-V1 PR that adds / removes / renames an
anchor MUST update this manifest in the same PR.

Run:

  python tools/lint-voice-doc/check.py          # validate
  python tools/lint-voice-doc/check.py --json   # machine-readable

Run from the repo root, or set `AETHER_REPO_ROOT` to point at the
repo.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Iterable


# ---------------------------------------------------------------------------
# Anchor manifest
# ---------------------------------------------------------------------------

ANCHORS: list[tuple[str, str, str | None, str]] = [
    # ---- §1 end-to-end flow: command entry points + helpers ----
    ("file",   "apps/desktop/src-tauri/src/commands.rs", None, "§1 end-to-end flow"),
    ("symbol", "apps/desktop/src-tauri/src/commands.rs", "fn transcribe_utterance", "§1 end-to-end flow"),
    ("symbol", "apps/desktop/src-tauri/src/commands.rs", "fn maybe_apply_voice", "§1 end-to-end flow"),
    ("symbol", "apps/desktop/src-tauri/src/commands.rs", "fn validate_utterance_data_url", "§5 utterance validation"),
    ("symbol", "apps/desktop/src-tauri/src/commands.rs", "fn record_utterance_early_exit_telemetry", "§6 telemetry kinds"),
    ("symbol", "apps/desktop/src-tauri/src/commands.rs", "MIN_UTTERANCE_BODY_LEN", "§5 utterance validation"),

    # ---- §1 mic permission gate ----
    ("file",   "apps/desktop/src-tauri/src/mic_permissions.rs", None, "§1 permission gate"),
    ("symbol", "apps/desktop/src-tauri/src/mic_permissions.rs", "struct MicPermission", "§1 permission gate"),
    ("symbol", "apps/desktop/src-tauri/src/mic_permissions.rs", "fn permission_path_for", "§1 permission gate"),
    ("string", "apps/desktop/src-tauri/src/mic_permissions.rs", "mic_permissions.json", "§1 permission filename"),

    # ---- §2 provider: L4 trait + whisper.cpp adapter ----
    ("file",   "packages/l4-router/src/speech.rs", None, "§2 providers"),
    ("symbol", "packages/l4-router/src/speech.rs", "trait SpeechProvider", "§2 providers"),
    ("symbol", "packages/l4-router/src/speech.rs", "SpeechRequest", "§2 providers"),
    ("symbol", "packages/l4-router/src/speech.rs", "SpeechResponse", "§2 providers"),
    ("symbol", "packages/l4-router/src/speech.rs", "fn split_audio_data_url", "§5 validator helper"),

    ("file",   "packages/l4-router/src/providers/whispercpp_speech.rs", None, "§2 providers"),
    ("symbol", "packages/l4-router/src/providers/whispercpp_speech.rs", "WhisperCppSpeechProvider", "§2 providers"),
    ("symbol", "packages/l4-router/src/providers/whispercpp_speech.rs", "WhisperCppSpeechConfig", "§2 providers"),
    ("string", "packages/l4-router/src/providers/whispercpp_speech.rs", "whispercpp-speech", "§2 provider id"),
    ("string", "packages/l4-router/src/providers/whispercpp_speech.rs", "AETHER_WHISPERCPP_SPEECH_BASE_URL", "§2 env knobs"),
    ("string", "packages/l4-router/src/providers/whispercpp_speech.rs", "AETHER_WHISPERCPP_SPEECH_MODEL",    "§2 env knobs"),
    ("string", "packages/l4-router/src/providers/whispercpp_speech.rs", "AETHER_WHISPERCPP_SPEECH_LANGUAGE", "§2 env knobs"),

    # ---- §3-4 voice_provider.json + selection rules ----
    ("file",   "apps/desktop/src-tauri/src/voice_registry.rs", None, "§3-4 registry"),
    ("symbol", "apps/desktop/src-tauri/src/voice_registry.rs", "VoicePersistedState", "§3 persistence"),
    ("symbol", "apps/desktop/src-tauri/src/voice_registry.rs", "voice_persistence_path_for", "§3 persistence"),
    ("symbol", "apps/desktop/src-tauri/src/voice_registry.rs", "auto_select_first_if_unset", "§4 selection rules"),
    ("symbol", "apps/desktop/src-tauri/src/voice_registry.rs", "seed_missing_models_from_adapters", "§4 first-launch seeding"),
    ("symbol", "apps/desktop/src-tauri/src/state.rs",           "voice_seed_missing_models", "§4 first-launch seeding"),
    ("string", "apps/desktop/src-tauri/src/voice_registry.rs", "voice_provider.json", "§3 filename"),

    # ---- §6 telemetry kinds: present on both Rust + TS sides ----
    ("string", "apps/desktop/src-tauri/src/commands.rs", "utterance_transcribed",  "§6 telemetry kinds"),
    ("string", "apps/desktop/src-tauri/src/commands.rs", "utterance_blocked",      "§6 telemetry kinds"),
    ("string", "apps/desktop/src-tauri/src/commands.rs", "utterance_invalid",      "§6 telemetry kinds"),
    ("string", "apps/desktop/src-tauri/src/commands.rs", "mic_permission_denied",  "§6 telemetry kinds"),
    ("string", "apps/desktop/src-tauri/src/commands.rs", "mic_permission_ask",     "§6 telemetry kinds"),

    ("file",   "apps/desktop/src/lib/voiceTurns.ts", None, "§6 TS allow-list"),
    ("symbol", "apps/desktop/src/lib/voiceTurns.ts", "VOICE_TURN_KINDS", "§6 TS allow-list"),
    ("string", "apps/desktop/src/lib/voiceTurns.ts", "utterance_transcribed", "§6 TS allow-list"),
    ("string", "apps/desktop/src/lib/voiceTurns.ts", "utterance_blocked",     "§6 TS allow-list"),
    ("string", "apps/desktop/src/lib/voiceTurns.ts", "utterance_invalid",     "§6 TS allow-list"),
    ("string", "apps/desktop/src/lib/voiceTurns.ts", "mic_permission_denied", "§6 TS allow-list"),
    ("string", "apps/desktop/src/lib/voiceTurns.ts", "mic_permission_ask",    "§6 TS allow-list"),

    # ---- §7 UI surfaces: shared speech provider registry + components ----
    ("file",   "apps/desktop/src/lib/speechProviders.ts", None, "§7 UI registry"),
    ("symbol", "apps/desktop/src/lib/speechProviders.ts", "SPEECH_PROVIDER_REGISTRY", "§7 UI registry"),

    ("file",   "apps/desktop/src/components/VoiceBadge.tsx",        None, "§7 VoiceBadge"),
    ("file",   "apps/desktop/src/components/ActiveVoiceRoute.tsx",  None, "§7 ActiveVoiceRoute"),
    ("file",   "apps/desktop/src/components/VoicePanel.tsx",        None, "§7 VoicePanel"),
    ("file",   "apps/desktop/src/components/TrustDrawer.tsx",       None, "§7 TrustDrawer"),
    ("symbol", "apps/desktop/src/components/TrustDrawer.tsx",       "kindClass", "§6 TrustDrawer kindClass"),
]


DOC_PATH = Path("docs/VOICE-V1-ARCHITECTURE.md")
STATUS_RE = re.compile(r"\*\*Status:\*\*\s+Current as of\s+(\d{4}-\d{2}-\d{2})")


class Failure:
    __slots__ = ("kind", "path", "needle", "section", "reason")

    def __init__(self, kind: str, path: str, needle: str | None, section: str, reason: str) -> None:
        self.kind = kind
        self.path = path
        self.needle = needle
        self.section = section
        self.reason = reason

    def to_dict(self) -> dict[str, str | None]:
        return {
            "kind":    self.kind,
            "path":    self.path,
            "needle":  self.needle,
            "section": self.section,
            "reason":  self.reason,
        }

    def __str__(self) -> str:
        head = f"  [{self.kind}] {self.path}"
        if self.needle is not None:
            head += f"  needle={self.needle!r}"
        return f"{head}\n      ({self.section}) {self.reason}"


def _repo_root() -> Path:
    env = os.environ.get("AETHER_REPO_ROOT")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for parent in (here, *here.parents):
        cargo = parent / "Cargo.toml"
        if cargo.is_file() and "[workspace]" in cargo.read_text(encoding="utf-8"):
            return parent
    raise RuntimeError(
        "Could not locate workspace root. Run this script from the Aether repo "
        "or set AETHER_REPO_ROOT."
    )


def _check_status_line(doc_path: Path) -> tuple[str | None, Failure | None]:
    if not doc_path.is_file():
        return None, Failure(
            "doc", str(doc_path), None, "header",
            "architecture doc is missing — this linter is useless without it.",
        )
    text = doc_path.read_text(encoding="utf-8")
    m = STATUS_RE.search(text)
    if not m:
        return None, Failure(
            "doc", str(doc_path), None, "header",
            "could not find `**Status:** Current as of YYYY-MM-DD.` line near the top.",
        )
    return m.group(1), None


def _check_anchor(repo_root: Path, kind: str, rel: str, needle: str | None, section: str) -> Failure | None:
    path = repo_root / rel
    if kind == "file":
        if not path.is_file():
            return Failure(kind, rel, None, section, "file does not exist.")
        return None
    if not path.is_file():
        return Failure(
            kind, rel, needle, section,
            "host file for this anchor does not exist.",
        )
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return Failure(
            kind, rel, needle, section,
            "host file is not UTF-8; cannot check anchor.",
        )
    if needle is None:
        return Failure(
            kind, rel, needle, section,
            f"anchor kind {kind!r} requires a needle.",
        )
    if needle not in content:
        return Failure(
            kind, rel, needle, section,
            "expected substring not found in file — the doc claims it exists. "
            "Either restore the symbol/string in code, or update the doc AND "
            "the ANCHORS manifest in tools/lint-voice-doc/check.py.",
        )
    return None


def _collect(repo_root: Path) -> tuple[str | None, list[Failure]]:
    failures: list[Failure] = []
    doc_date, doc_fail = _check_status_line(repo_root / DOC_PATH)
    if doc_fail is not None:
        failures.append(doc_fail)

    for kind, rel, needle, section in ANCHORS:
        f = _check_anchor(repo_root, kind, rel, needle, section)
        if f is not None:
            failures.append(f)

    return doc_date, failures


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check Voice V1 architecture doc anchors against code.",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="emit machine-readable JSON report on stdout",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    doc_date, failures = _collect(repo_root)

    if args.json:
        print(json.dumps(
            {
                "ok":               not failures,
                "doc":              str(DOC_PATH),
                "doc_status_date":  doc_date,
                "anchor_count":     len(ANCHORS),
                "failures":         [f.to_dict() for f in failures],
            },
            indent=2,
        ))
    else:
        if failures:
            print("voice-doc rot-guard: FAIL")
            for f in failures:
                print(f)
            print(
                f"\n{len(failures)} failure(s). "
                "See tools/lint-voice-doc/README.md for how to resolve."
            )
        else:
            print("voice-doc rot-guard: OK")
            print(
                f"  doc: {DOC_PATH} (Status: Current as of {doc_date})"
                f"  checked {len(ANCHORS)} anchors across "
                f"{len({a[1] for a in ANCHORS})} files."
            )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
