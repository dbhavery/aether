"""Composition layer for the Aether eval harness — Quality-Eval V2.

Encapsulates the four composition surfaces the v1 `--backend ollama`
mode deliberately skipped:

  - **Persona** — load `personas/<id>/persona.yaml`, extract the
    canonical hand-authored `personality.system_prompt`, and emit
    the system message the live model would see at runtime. Mirrors
    the intent of `packages/l6-persona`'s compiler but reads the
    pack directly so the harness is decoupled from any Rust build.
  - **Memory** — given a scenario's `setup.memory` block (recorded
    prior turns), emit the retrieval block string Aether's
    `apps/desktop/src-tauri/src/retrieval.rs::format_retrieval_block`
    would inject. Wire-shape parity is not required; representative
    parity is. The block is what the model receives.
  - **Vision** — load a fixture image referenced by the
    `setup.frame` URI (`fixture://name.jpg`), base64-encode for
    Ollama's `/api/chat` `images` field. Substitute documented
    fallbacks when the named fixture is missing so the harness can
    still exercise the wire.
  - **Voice** — given a `setup.audio` URI, produce the transcript
    the voice path would yield. Audio-to-text via the model is not
    routed in this slice; transcripts come from a name-keyed
    manifest with a `[transcript: ...]` injection into the user
    turn so the language path runs end-to-end.

Each composer is a small, pure function on the scenario `setup`
dict + repo-rooted paths; no global state, no side effects beyond
file reads. The runner decides which composers are active per
`--compose` flag.

Resolution rules for paths and fixtures are deliberate:

  - Persona id `"aurora"` → `personas/aurora/persona.yaml` (the
    only persona shipped on tip a9a55cf). Unknown ids fall back to
    a minimal synthesized prompt + a clear note so eval results
    don't silently use the wrong identity.
  - `fixture://<name>` references resolve under
    `tools/evals/fixtures/<name>`. Missing files trigger a
    documented substitute (portrait.png for images, name-keyed
    transcript for audio) and the runner records a `note`.

This module never raises for missing optional inputs — it returns
`None` plus a note string so the harness can decide whether to run
the scenario, run it partial, or skip with explanation.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml


COMPOSER_NAMES: tuple[str, ...] = ("persona", "memory", "vision", "voice")


@dataclass(frozen=True)
class ComposedPrompt:
    """The single payload the runner forwards to the live backend.

    `system` is `None` when no system prompt was composed (no
    persona composer enabled or persona pack missing). `images` is
    a list of base64-encoded JPEG/PNG strings without the data-URL
    prefix — Ollama's `/api/chat` endpoint accepts the bare
    base64. `notes` carries human-readable provenance (e.g. "vision
    fixture substituted") so the runner can surface it in the
    scenario result.
    """

    system: str | None
    user: str
    images: list[str]
    notes: list[str]


@dataclass(frozen=True)
class CompositionContext:
    """Bundle of repo-rooted paths a composer needs. Centralized so
    the runner does not have to know which composer reads which
    directory."""

    repo_root: Path
    personas_dir: Path
    fixtures_dir: Path

    @classmethod
    def from_repo_root(cls, repo_root: Path) -> "CompositionContext":
        return cls(
            repo_root=repo_root,
            personas_dir=repo_root / "personas",
            fixtures_dir=repo_root / "tools" / "evals" / "fixtures",
        )


# ---------------------------------------------------------------------------
# Persona composer
# ---------------------------------------------------------------------------


def compose_persona(
    persona_id: str,
    ctx: CompositionContext,
) -> tuple[str | None, str | None]:
    """Return `(system_prompt, note)`.

    Reads `personas/<id>/persona.yaml` and pulls the canonical
    `personality.system_prompt`. The hand-authored Aurora prompt is
    the source of truth — `docs/PERSONA-SCHEMA.md` §6 step 8 locks
    the rule that this field is never regenerated from an LLM.

    Returns `(None, note)` when the pack is missing or malformed
    rather than raising; the runner decides whether to proceed
    persona-less or skip the scenario.
    """
    pack_path = ctx.personas_dir / persona_id / "persona.yaml"
    if not pack_path.is_file():
        return None, f"persona pack not found at {pack_path}"
    try:
        pack = yaml.safe_load(pack_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return None, f"persona pack malformed at {pack_path}: {exc}"
    if not isinstance(pack, dict):
        return None, f"persona pack at {pack_path} is not a mapping"
    personality = pack.get("personality")
    if not isinstance(personality, dict):
        return None, f"persona pack at {pack_path} missing `personality` block"
    system_prompt = personality.get("system_prompt")
    if not isinstance(system_prompt, str) or not system_prompt.strip():
        return None, f"persona pack at {pack_path} has empty `system_prompt`"
    return system_prompt.strip(), None


# ---------------------------------------------------------------------------
# Memory composer
# ---------------------------------------------------------------------------


def compose_memory(memory_turns: list[dict]) -> tuple[str | None, str | None]:
    """Return `(retrieval_block, note)`.

    Mirrors the format produced by `format_retrieval_block` in
    `apps/desktop/src-tauri/src/retrieval.rs`:

        Relevant context (memory):
        [1] user mem-1: <content>
        [2] assistant mem-2: <content>

    Wire-shape (Rust uses `<domain> <memory_id>`) is not preserved
    byte-for-byte — the harness has no Rust `MemoryDomain`. Instead
    each turn's `role` plays the domain slot and a synthesized
    `mem-<n>` plays the memory_id slot. The model sees a
    rank-numbered, role-tagged context block which is what
    `memory_appropriateness` scenarios actually probe.

    Returns `(None, note)` for an empty memory list so the runner
    can compose user-only prompts byte-identically.
    """
    if not memory_turns:
        return None, None
    lines: list[str] = ["Relevant context (memory):"]
    for i, turn in enumerate(memory_turns, start=1):
        if not isinstance(turn, dict):
            continue
        role = str(turn.get("role", "unknown")).strip() or "unknown"
        content = turn.get("content")
        if not isinstance(content, str):
            continue
        lines.append(f"[{i}] {role} mem-{i}: {content.strip()}")
    if len(lines) == 1:
        return None, "memory block had no usable turns"
    return "\n".join(lines) + "\n", None


# ---------------------------------------------------------------------------
# Vision composer
# ---------------------------------------------------------------------------


# Documented fallback chain for missing vision fixtures. The persona
# portrait is always present and exercises the multimodal wire end-to-end
# even if the scenario's content expectation can no longer be met. The
# runner surfaces the substitution in the scenario note.
_VISION_FALLBACK_RELPATH = Path("personas") / "aurora" / "avatar" / "portrait.png"


def compose_vision(
    frame_uri: str,
    ctx: CompositionContext,
) -> tuple[str | None, str | None]:
    """Return `(base64_image, note)`.

    Resolves `fixture://<name>` URIs under `tools/evals/fixtures/`.
    On miss, falls back to the persona portrait so the multimodal
    transport is still exercised; the note documents the swap.
    Returns `(None, note)` only when even the fallback is missing.
    """
    if not isinstance(frame_uri, str) or not frame_uri.startswith("fixture://"):
        return None, f"unsupported frame URI {frame_uri!r}"
    name = frame_uri[len("fixture://"):]
    if not name:
        return None, "frame URI has no fixture name"
    primary = ctx.fixtures_dir / name
    if primary.is_file():
        return _encode_image(primary), None
    fallback = ctx.repo_root / _VISION_FALLBACK_RELPATH
    if fallback.is_file():
        encoded = _encode_image(fallback)
        return (
            encoded,
            (
                f"vision fixture {primary} missing; substituted persona "
                f"portrait ({_VISION_FALLBACK_RELPATH.as_posix()}) — "
                "scene-specific content expectations may not match"
            ),
        )
    return None, f"vision fixture {primary} missing and no fallback available"


def _encode_image(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


# ---------------------------------------------------------------------------
# Voice composer
# ---------------------------------------------------------------------------


# Name-keyed transcript manifest. Keeping this in code (vs. a sidecar
# JSON) preserves the "scenarios + composer = runnable" guarantee
# without adding a fixture file the test suite must also rot-guard.
# Add new entries here when adding new voice scenarios.
_VOICE_TRANSCRIPTS: dict[str, str] = {
    "utterance_karpathy.wav": "Reminds me of Karpathy's LLM knowledge base idea.",
}


def compose_voice(audio_uri: str) -> tuple[str | None, str | None]:
    """Return `(transcript, note)`.

    The voice path in production runs the audio through a STT
    adapter; the harness short-circuits with a name-keyed
    transcript so the language pipeline downstream of STT can be
    exercised end-to-end. Unknown fixtures return `(None, note)`.

    The transcript is later spliced into the user turn as
    `[transcript: ...]` so domain-vocab expectations (e.g. preserves
    proper nouns) remain meaningful.
    """
    if not isinstance(audio_uri, str) or not audio_uri.startswith("fixture://"):
        return None, f"unsupported audio URI {audio_uri!r}"
    name = audio_uri[len("fixture://"):]
    transcript = _VOICE_TRANSCRIPTS.get(name)
    if transcript is None:
        return None, (
            f"voice fixture {name!r} has no transcript in "
            "_VOICE_TRANSCRIPTS — add an entry to tools/evals/composition.py"
        )
    return transcript, None


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------


def compose_prompt(
    user_prompt: str,
    setup: dict | None,
    enabled: Iterable[str],
    ctx: CompositionContext,
) -> ComposedPrompt:
    """Compose all enabled surfaces into a single `ComposedPrompt`.

    `enabled` is the set of composer names the runner activated for
    this run (one of `COMPOSER_NAMES`). Each composer that fires
    appends to `notes` so the runner can surface what was injected
    and what was substituted.

    The returned `user` field always carries the original last-user
    turn at minimum; memory + voice transcript (when present) are
    prepended in that order so the model sees:

        <retrieval block>
        [transcript: ...]
        <user turn>

    Persona becomes the system message. Vision images attach via
    the dedicated `images` slot.
    """
    setup = setup if isinstance(setup, dict) else {}
    enabled_set = {name for name in enabled if name in COMPOSER_NAMES}

    notes: list[str] = []
    system: str | None = None
    images: list[str] = []
    user_parts: list[str] = []

    if "persona" in enabled_set:
        persona_id = setup.get("persona")
        if isinstance(persona_id, str) and persona_id:
            sys_prompt, note = compose_persona(persona_id, ctx)
            if sys_prompt is not None:
                system = sys_prompt
            if note is not None:
                notes.append(f"persona: {note}")

    if "memory" in enabled_set:
        memory_turns = setup.get("memory")
        if isinstance(memory_turns, list) and memory_turns:
            block, note = compose_memory(memory_turns)
            if block is not None:
                user_parts.append(block)
            if note is not None:
                notes.append(f"memory: {note}")

    if "voice" in enabled_set:
        audio_uri = setup.get("audio")
        if isinstance(audio_uri, str):
            transcript, note = compose_voice(audio_uri)
            if transcript is not None:
                user_parts.append(f"[transcript: {transcript}]")
            if note is not None:
                notes.append(f"voice: {note}")

    if "vision" in enabled_set:
        frame_uri = setup.get("frame")
        if isinstance(frame_uri, str):
            encoded, note = compose_vision(frame_uri, ctx)
            if encoded is not None:
                images.append(encoded)
            if note is not None:
                notes.append(f"vision: {note}")

    user_parts.append(user_prompt)
    user = "\n".join(user_parts)

    return ComposedPrompt(system=system, user=user, images=images, notes=notes)
