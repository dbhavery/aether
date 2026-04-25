"""Unit tests for the Quality-Eval V2 composition layer.

Stdlib-only `unittest`, matching `test_capture_replay.py` discipline.
Covers the pure-function surface — no live backend, no real Ollama.

Run:

  python tools/evals/test_composition.py
  # or
  python -m unittest tools.evals.test_composition
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import composition  # noqa: E402


def _make_ctx(tmp: Path) -> composition.CompositionContext:
    """Build an isolated CompositionContext rooted at `tmp` so tests
    can stage their own personas/ and fixtures/ trees without
    depending on the live repo state."""
    ctx = composition.CompositionContext.from_repo_root(tmp)
    ctx.personas_dir.mkdir(parents=True, exist_ok=True)
    ctx.fixtures_dir.mkdir(parents=True, exist_ok=True)
    return ctx


class PersonaComposerTests(unittest.TestCase):
    def test_loads_system_prompt_from_pack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            ctx = _make_ctx(tmp)
            (ctx.personas_dir / "demo").mkdir()
            (ctx.personas_dir / "demo" / "persona.yaml").write_text(
                "personality:\n  system_prompt: |\n    You are Demo. Speak plainly.\n",
                encoding="utf-8",
            )
            prompt, note = composition.compose_persona("demo", ctx)
            self.assertIsNone(note)
            self.assertIsNotNone(prompt)
            assert prompt is not None  # for the type checker
            self.assertIn("You are Demo", prompt)

    def test_missing_pack_returns_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            ctx = _make_ctx(Path(tmp_str))
            prompt, note = composition.compose_persona("nope", ctx)
            self.assertIsNone(prompt)
            self.assertIsNotNone(note)

    def test_empty_system_prompt_returns_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            ctx = _make_ctx(Path(tmp_str))
            (ctx.personas_dir / "demo").mkdir()
            (ctx.personas_dir / "demo" / "persona.yaml").write_text(
                "personality:\n  system_prompt: ''\n",
                encoding="utf-8",
            )
            prompt, note = composition.compose_persona("demo", ctx)
            self.assertIsNone(prompt)
            self.assertIsNotNone(note)


class MemoryComposerTests(unittest.TestCase):
    def test_renders_role_tagged_block(self) -> None:
        block, note = composition.compose_memory(
            [
                {"role": "user", "content": "my dog's name is Pepper"},
                {"role": "assistant", "content": "Noted — Pepper."},
            ]
        )
        self.assertIsNone(note)
        self.assertIsNotNone(block)
        assert block is not None
        self.assertIn("Relevant context (memory):", block)
        self.assertIn("[1] user mem-1: my dog's name is Pepper", block)
        self.assertIn("[2] assistant mem-2: Noted — Pepper.", block)

    def test_empty_list_returns_none(self) -> None:
        block, note = composition.compose_memory([])
        self.assertIsNone(block)
        self.assertIsNone(note)

    def test_skips_malformed_turns(self) -> None:
        block, _ = composition.compose_memory(
            [
                {"role": "user"},  # missing content
                "not a dict",  # type: ignore[list-item]
                {"role": "user", "content": "kept"},
            ]
        )
        assert block is not None
        self.assertIn("kept", block)
        self.assertNotIn("mem-2", block)  # the bad rows do not advance index visually


class VisionComposerTests(unittest.TestCase):
    def test_loads_real_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            ctx = _make_ctx(Path(tmp_str))
            (ctx.fixtures_dir / "scene.jpg").write_bytes(b"fake-image-bytes")
            encoded, note = composition.compose_vision("fixture://scene.jpg", ctx)
            self.assertIsNone(note)
            self.assertIsNotNone(encoded)
            assert encoded is not None
            # base64 of "fake-image-bytes"
            self.assertEqual(encoded, "ZmFrZS1pbWFnZS1ieXRlcw==")

    def test_falls_back_to_portrait(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            ctx = _make_ctx(tmp)
            portrait = tmp / "personas" / "aurora" / "avatar"
            portrait.mkdir(parents=True)
            (portrait / "portrait.png").write_bytes(b"portrait-bytes")
            encoded, note = composition.compose_vision("fixture://missing.jpg", ctx)
            self.assertIsNotNone(encoded)
            self.assertIsNotNone(note)
            assert note is not None
            self.assertIn("substituted", note)

    def test_missing_with_no_fallback_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            ctx = _make_ctx(Path(tmp_str))
            encoded, note = composition.compose_vision("fixture://missing.jpg", ctx)
            self.assertIsNone(encoded)
            self.assertIsNotNone(note)

    def test_rejects_non_fixture_uri(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            ctx = _make_ctx(Path(tmp_str))
            encoded, note = composition.compose_vision("https://example.com/x.jpg", ctx)
            self.assertIsNone(encoded)
            self.assertIsNotNone(note)


class VoiceComposerTests(unittest.TestCase):
    def test_known_fixture_returns_transcript(self) -> None:
        transcript, note = composition.compose_voice(
            "fixture://utterance_karpathy.wav"
        )
        self.assertIsNone(note)
        self.assertIsNotNone(transcript)
        assert transcript is not None
        self.assertIn("Karpathy", transcript)

    def test_unknown_fixture_returns_note(self) -> None:
        transcript, note = composition.compose_voice("fixture://unknown.wav")
        self.assertIsNone(transcript)
        self.assertIsNotNone(note)


class ComposePromptTests(unittest.TestCase):
    def test_persona_only_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            ctx = _make_ctx(tmp)
            (ctx.personas_dir / "demo").mkdir()
            (ctx.personas_dir / "demo" / "persona.yaml").write_text(
                "personality:\n  system_prompt: 'You are Demo.'\n",
                encoding="utf-8",
            )
            out = composition.compose_prompt(
                user_prompt="hi",
                setup={"persona": "demo"},
                enabled=("persona",),
                ctx=ctx,
            )
            self.assertEqual(out.system, "You are Demo.")
            self.assertEqual(out.user, "hi")
            self.assertEqual(out.images, [])

    def test_full_compose_orders_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            ctx = _make_ctx(tmp)
            (ctx.personas_dir / "demo").mkdir()
            (ctx.personas_dir / "demo" / "persona.yaml").write_text(
                "personality:\n  system_prompt: 'You are Demo.'\n",
                encoding="utf-8",
            )
            (ctx.fixtures_dir / "scene.jpg").write_bytes(b"img")
            out = composition.compose_prompt(
                user_prompt="what now?",
                setup={
                    "persona": "demo",
                    "memory": [{"role": "user", "content": "earlier"}],
                    "audio": "fixture://utterance_karpathy.wav",
                    "frame": "fixture://scene.jpg",
                },
                enabled=composition.COMPOSER_NAMES,
                ctx=ctx,
            )
            self.assertEqual(out.system, "You are Demo.")
            # Memory block first, then transcript, then user prompt.
            mem_pos = out.user.find("Relevant context (memory):")
            tr_pos = out.user.find("[transcript:")
            user_pos = out.user.find("what now?")
            self.assertGreaterEqual(mem_pos, 0)
            self.assertGreater(tr_pos, mem_pos)
            self.assertGreater(user_pos, tr_pos)
            self.assertEqual(len(out.images), 1)

    def test_unknown_composer_names_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            ctx = _make_ctx(Path(tmp_str))
            out = composition.compose_prompt(
                user_prompt="x",
                setup={},
                enabled=("nonsense", "persona"),
                ctx=ctx,
            )
            self.assertIsNone(out.system)  # no persona pack staged
            self.assertEqual(out.user, "x")


if __name__ == "__main__":
    unittest.main()
