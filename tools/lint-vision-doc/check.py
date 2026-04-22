#!/usr/bin/env python3
"""Aether Vision V1 architecture-doc rot guard.

Keeps `docs/VISION-V1-ARCHITECTURE.md` honest. The doc claims specific
files exist, specific symbols exist in those files, and specific string
constants (telemetry kinds, env var names, provider ids, config filenames)
appear in code. If any of those claims silently becomes false — a file
is renamed, a function is removed, a telemetry kind is retired — this
linter fails.

This is NOT a doc parser. It does not try to understand prose. Instead
it carries a curated anchor manifest in this file. When a Vision-V1 PR
adds, removes, or renames an anchor, it MUST update this manifest in
the same PR. That's the whole enforcement mechanism: the manifest is
the contract between the doc and the code.

What this linter checks (hard failures):

  1. `docs/VISION-V1-ARCHITECTURE.md` exists and has a parseable
     `> **Status:** Current as of YYYY-MM-DD.` line.
  2. Every FILE anchor resolves to an actual file.
  3. Every SYMBOL anchor (a literal snippet like `fn analyze_frame`)
     appears at least once in its named file.
  4. Every STRING anchor (a bare token like `"frame_analyzed"` or
     `AETHER_VISION_MODEL_TTL_SECS`) appears at least once in its
     named file.

What this linter does NOT check:

  - Semantic correctness of the doc's prose.
  - Whether the behavior described still matches the code.
  - Whether a newly-added telemetry kind in code is also in the doc.
    (The doc already lists the five-kind contract; adding a sixth kind
    in code without updating the manifest and the doc is caught by a
    code review, not by this linter.)

Usage:

  python tools/lint-vision-doc/check.py          # validate
  python tools/lint-vision-doc/check.py --json   # machine-readable

Run from the repo root, or set `AETHER_REPO_ROOT` to point at the repo.

When adding, renaming, or removing a Vision-V1 anchor:

  - Update `ANCHORS` below.
  - Update `docs/VISION-V1-ARCHITECTURE.md` in the same PR.
  - Bump the doc's `Status: Current as of YYYY-MM-DD` date.
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
#
# Each anchor is a tuple:
#
#   (kind, path_relative_to_repo, needle, section_hint)
#
# - kind:      "file" | "symbol" | "string"
# - path:      POSIX path relative to repo root
# - needle:    None for "file"; for "symbol" and "string" a literal substring
#              (no regex) that must appear at least once in the file
# - section:   a short hint of which doc section names this anchor, used in
#              failure messages
#
# Keep this sorted by file and grouped by section for readability.
# ---------------------------------------------------------------------------

ANCHORS: list[tuple[str, str, str | None, str]] = [
    # ---- §1 end-to-end flow: command entry points and helpers ----
    ("file",   "apps/desktop/src-tauri/src/commands.rs", None, "§1 end-to-end flow"),
    ("symbol", "apps/desktop/src-tauri/src/commands.rs", "fn analyze_frame", "§1 end-to-end flow"),
    ("symbol", "apps/desktop/src-tauri/src/commands.rs", "fn maybe_apply_vision", "§1 end-to-end flow"),
    ("symbol", "apps/desktop/src-tauri/src/commands.rs", "fn validate_frame_data_url", "§5 frame validation"),
    ("symbol", "apps/desktop/src-tauri/src/commands.rs", "fn record_frame_early_exit_telemetry", "§6 telemetry kinds"),
    ("symbol", "apps/desktop/src-tauri/src/commands.rs", "MIN_FRAME_BODY_LEN", "§5 frame validation"),

    # ---- §2 providers: L4 trait + two local adapters ----
    ("file",   "packages/l4-router/src/vision.rs",                       None, "§2 providers"),
    ("symbol", "packages/l4-router/src/vision.rs", "trait VisionProvider",        "§2 providers"),
    ("symbol", "packages/l4-router/src/vision.rs", "VisionRequest",               "§2 providers"),
    ("symbol", "packages/l4-router/src/vision.rs", "VisionResponse",              "§2 providers"),

    ("file",   "packages/l4-router/src/providers/ollama_vision.rs",      None, "§2 providers"),
    ("symbol", "packages/l4-router/src/providers/ollama_vision.rs", "OllamaVisionProvider", "§2 providers"),
    ("symbol", "packages/l4-router/src/providers/ollama_vision.rs", "OllamaVisionConfig",   "§2 providers"),
    ("string", "packages/l4-router/src/providers/ollama_vision.rs", "ollama-vision",        "§2 provider id"),
    ("string", "packages/l4-router/src/providers/ollama_vision.rs", "AETHER_OLLAMA_VISION_BASE_URL", "§2 env knobs"),
    ("string", "packages/l4-router/src/providers/ollama_vision.rs", "AETHER_OLLAMA_VISION_MODEL",    "§2 env knobs"),

    ("file",   "packages/l4-router/src/providers/llamacpp_vision.rs",    None, "§2 providers"),
    ("symbol", "packages/l4-router/src/providers/llamacpp_vision.rs", "LlamaCppVisionProvider", "§2 providers"),
    ("symbol", "packages/l4-router/src/providers/llamacpp_vision.rs", "LlamaCppVisionConfig",   "§2 providers"),
    ("string", "packages/l4-router/src/providers/llamacpp_vision.rs", "llamacpp-vision",        "§2 provider id"),
    ("string", "packages/l4-router/src/providers/llamacpp_vision.rs", "AETHER_LLAMACPP_VISION_BASE_URL", "§2 env knobs"),
    ("string", "packages/l4-router/src/providers/llamacpp_vision.rs", "AETHER_LLAMACPP_VISION_MODEL",    "§2 env knobs"),

    # ---- §3-4 vision_provider.json + selection rules + TTL cache ----
    ("file",   "apps/desktop/src-tauri/src/vision_registry.rs",          None, "§3-4 registry"),
    ("symbol", "apps/desktop/src-tauri/src/vision_registry.rs", "VisionPersistedState",        "§3 persistence"),
    ("symbol", "apps/desktop/src-tauri/src/vision_registry.rs", "vision_persistence_path_for", "§3 persistence"),
    ("symbol", "apps/desktop/src-tauri/src/vision_registry.rs", "auto_select_first_if_unset",  "§4 selection rules"),
    ("symbol", "apps/desktop/src-tauri/src/state.rs",           "vision_seed_missing_models",  "§4 first-launch seeding"),
    ("symbol", "apps/desktop/src-tauri/src/vision_registry.rs", "seed_missing_models_from_adapters", "§4 first-launch seeding"),
    ("string", "apps/desktop/src-tauri/src/vision_registry.rs", "vision_provider.json",        "§3 filename"),

    ("file",   "apps/desktop/src-tauri/src/vision_cache.rs",             None, "§4 TTL cache"),
    ("symbol", "apps/desktop/src-tauri/src/vision_cache.rs", "ModelListCache",                "§4 TTL cache"),
    ("string", "apps/desktop/src-tauri/src/vision_cache.rs", "AETHER_VISION_MODEL_TTL_SECS",  "§4 env override"),

    # ---- §6 telemetry kinds: appear in both the shell (Rust) and the UI (TS)
    # allow-list. Every kind must be present on both sides.
    ("string", "apps/desktop/src-tauri/src/commands.rs", "frame_analyzed",     "§6 telemetry kinds"),
    ("string", "apps/desktop/src-tauri/src/commands.rs", "frame_blocked",      "§6 telemetry kinds"),
    ("string", "apps/desktop/src-tauri/src/commands.rs", "frame_invalid",      "§6 telemetry kinds"),
    ("string", "apps/desktop/src-tauri/src/commands.rs", "permission_denied",  "§6 telemetry kinds"),
    ("string", "apps/desktop/src-tauri/src/commands.rs", "permission_ask",     "§6 telemetry kinds"),

    ("file",   "apps/desktop/src/lib/mediaTurns.ts",                     None, "§6 TS allow-list"),
    ("symbol", "apps/desktop/src/lib/mediaTurns.ts", "MEDIA_TURN_KINDS",        "§6 TS allow-list"),
    ("string", "apps/desktop/src/lib/mediaTurns.ts", "frame_analyzed",    "§6 TS allow-list"),
    ("string", "apps/desktop/src/lib/mediaTurns.ts", "frame_blocked",     "§6 TS allow-list"),
    ("string", "apps/desktop/src/lib/mediaTurns.ts", "frame_invalid",     "§6 TS allow-list"),
    ("string", "apps/desktop/src/lib/mediaTurns.ts", "permission_denied", "§6 TS allow-list"),
    ("string", "apps/desktop/src/lib/mediaTurns.ts", "permission_ask",    "§6 TS allow-list"),

    # ---- §7 UI surfaces: shared registry + truncation helper + components ----
    ("file",   "apps/desktop/src/lib/visionProviders.ts",                None, "§7 UI registry"),
    ("symbol", "apps/desktop/src/lib/visionProviders.ts", "VISION_PROVIDER_REGISTRY", "§7 UI registry"),

    ("file",   "apps/desktop/src/lib/displayString.ts",                  None, "§7 truncation helper"),
    ("symbol", "apps/desktop/src/lib/displayString.ts", "truncateMiddleForDisplay", "§7 truncation helper"),

    ("file",   "apps/desktop/src/components/VisionBadge.tsx",            None, "§7 VisionBadge"),
    ("file",   "apps/desktop/src/components/TrustDrawer.tsx",            None, "§7 TrustDrawer"),
    ("symbol", "apps/desktop/src/components/TrustDrawer.tsx", "kindClass", "§6 TrustDrawer kindClass"),
]


DOC_PATH = Path("docs/VISION-V1-ARCHITECTURE.md")
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
            "the ANCHORS manifest in tools/lint-vision-doc/check.py.",
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
        description="Check Vision V1 architecture doc anchors against code.",
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
            print("vision-doc rot-guard: FAIL")
            for f in failures:
                print(f)
            print(
                f"\n{len(failures)} failure(s). "
                "See tools/lint-vision-doc/README.md for how to resolve."
            )
        else:
            print("vision-doc rot-guard: OK")
            print(
                f"  doc: {DOC_PATH} (Status: Current as of {doc_date})"
                f"  checked {len(ANCHORS)} anchors across "
                f"{len({a[1] for a in ANCHORS})} files."
            )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
