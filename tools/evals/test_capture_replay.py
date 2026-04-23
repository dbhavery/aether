"""Unit tests for the v1.2 capture/replay machinery.

Stdlib-only (`unittest`) so the harness stays dependency-free —
the evals tree is explicitly small and must not pull pytest into
the Aether tool chain.

Run:

  python tools/evals/test_capture_replay.py
  # or
  python -m unittest tools.evals.test_capture_replay

The CLI end-to-end path (argparse + main()) is covered by the
harness's own `--dry-run` invocation in the standard check
matrix. These tests focus on the capture/replay unit surface:
stable filenames, structured JSON shape, round-trip fidelity,
and graceful handling of missing / malformed captures.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


# Load `tools/evals/__main__.py` as a distinct module.  Importing
# by the name `__main__` clashes with whichever script invokes the
# test, so we load the file by path under a different module name.
HERE = Path(__file__).resolve().parent
_HARNESS_SPEC = importlib.util.spec_from_file_location(
    "aether_evals_harness", HERE / "__main__.py"
)
if _HARNESS_SPEC is None or _HARNESS_SPEC.loader is None:
    raise RuntimeError("could not locate tools/evals/__main__.py")
# Put the evals dir on sys.path so the harness's own sibling
# imports (`from expectations import …`, `from report import …`)
# resolve correctly when loaded from anywhere.
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
_harness = importlib.util.module_from_spec(_HARNESS_SPEC)
# Python 3.14's dataclass decorator looks the owning module up in
# sys.modules while processing class bodies; registering before
# exec_module keeps that lookup from crashing on the Scenario and
# ScenarioResult dataclasses.
sys.modules["aether_evals_harness"] = _harness
_HARNESS_SPEC.loader.exec_module(_harness)

Scenario = _harness.Scenario
_capture_filename = _harness._capture_filename
_load_replay_capture = _harness._load_replay_capture
_write_capture_json = _harness._write_capture_json


def _make_scenario(scenario_id: str, domain: str = "chat_realism") -> Scenario:
    """Build a minimal Scenario suitable for capture tests. The
    capture code only reads `id`, `domain`, and uses the prompt /
    response we pass in; a stub path + line number is enough."""
    return Scenario(
        path=Path("synthetic.jsonl"),
        line_no=1,
        raw={"id": scenario_id, "domain": domain},
    )


class CaptureFilenameTests(unittest.TestCase):
    def test_plain_id_passthrough(self) -> None:
        self.assertEqual(_capture_filename("chat.greeting"), "chat.greeting")

    def test_slashes_become_underscores(self) -> None:
        # Scenario ids occasionally use "/" as a namespace separator;
        # the capture filename must stay on a single filesystem path
        # segment.
        self.assertEqual(
            _capture_filename("domain/sub.case"),
            "domain_sub.case",
        )

    def test_spaces_become_underscores(self) -> None:
        self.assertEqual(
            _capture_filename("memory honors forget"),
            "memory_honors_forget",
        )


class WriteCaptureJsonTests(unittest.TestCase):
    def test_shape_includes_all_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = _write_capture_json(
                Path(tmp),
                _make_scenario("chat.first_turn", "chat_realism"),
                backend="ollama",
                prompt="hi",
                response="Hi — what would you like to do?",
            )
            self.assertTrue(out.is_file())
            payload = json.loads(out.read_text(encoding="utf-8"))
            for key in (
                "scenario_id",
                "domain",
                "backend",
                "captured_at",
                "prompt",
                "response",
                "metadata",
            ):
                self.assertIn(key, payload, f"missing field: {key}")
            self.assertEqual(payload["scenario_id"], "chat.first_turn")
            self.assertEqual(payload["domain"], "chat_realism")
            self.assertEqual(payload["backend"], "ollama")
            self.assertEqual(payload["prompt"], "hi")
            self.assertEqual(
                payload["response"],
                "Hi — what would you like to do?",
            )
            # captured_at is UTC ISO-8601 ending in Z so consumers
            # don't need to guess the timezone.
            self.assertTrue(
                payload["captured_at"].endswith("Z"),
                f"captured_at not UTC-Z: {payload['captured_at']!r}",
            )

    def test_ollama_metadata_is_populated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = _write_capture_json(
                Path(tmp),
                _make_scenario("x"),
                backend="ollama",
                prompt="p",
                response="r",
            )
            meta = json.loads(out.read_text(encoding="utf-8"))["metadata"]
            self.assertIn("ollama_model", meta)
            self.assertIn("ollama_base_url", meta)
            self.assertIn("ollama_timeout_s", meta)

    def test_non_ollama_metadata_is_empty(self) -> None:
        # A future capture path (e.g. a direct-against-Aether-shell
        # backend) should not accidentally leak Ollama env vars into
        # the capture's metadata.
        with tempfile.TemporaryDirectory() as tmp:
            out = _write_capture_json(
                Path(tmp),
                _make_scenario("x"),
                backend="custom-stub",
                prompt="p",
                response="r",
            )
            meta = json.loads(out.read_text(encoding="utf-8"))["metadata"]
            self.assertEqual(meta, {})

    def test_creates_parent_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            nested = Path(tmp) / "deeply" / "nested"
            out = _write_capture_json(
                nested,
                _make_scenario("x"),
                backend="ollama",
                prompt="p",
                response="r",
            )
            self.assertTrue(out.is_file())
            self.assertEqual(out.parent, nested)


class LoadReplayCaptureTests(unittest.TestCase):
    def test_missing_file_is_skip_note_not_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            text, note = _load_replay_capture(Path(tmp), "no-such-scenario")
            self.assertIsNone(text)
            self.assertIsNotNone(note)
            self.assertIn("no capture", note)

    def test_malformed_json_is_skip_note_not_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "broken.json").write_text("{not json", encoding="utf-8")
            text, note = _load_replay_capture(Path(tmp), "broken")
            self.assertIsNone(text)
            self.assertIsNotNone(note)
            self.assertIn("not valid JSON", note)

    def test_missing_response_field_is_skip_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "x.json").write_text(
                json.dumps({"scenario_id": "x"}),
                encoding="utf-8",
            )
            text, note = _load_replay_capture(Path(tmp), "x")
            self.assertIsNone(text)
            self.assertIsNotNone(note)
            self.assertIn("response", note)


class RoundTripTests(unittest.TestCase):
    def test_write_then_load_returns_identical_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scenario = _make_scenario("round.trip.case", "memory_appropriateness")
            _write_capture_json(
                Path(tmp),
                scenario,
                backend="ollama",
                prompt="please forget my name",
                response="Ok, I'll forget that.",
            )
            text, note = _load_replay_capture(Path(tmp), scenario.id)
            self.assertIsNone(note, f"unexpected note: {note!r}")
            self.assertEqual(text, "Ok, I'll forget that.")

    def test_round_trip_survives_slashed_ids(self) -> None:
        # A scenario id with a slash must not escape the capture
        # directory; both write and load use `_capture_filename`.
        with tempfile.TemporaryDirectory() as tmp:
            scenario = _make_scenario("memory/honors forget")
            _write_capture_json(
                Path(tmp),
                scenario,
                backend="ollama",
                prompt="p",
                response="OK.",
            )
            # No stray files outside tmp.
            children = sorted(Path(tmp).iterdir())
            self.assertEqual(
                [c.name for c in children],
                ["memory_honors_forget.json"],
            )
            text, note = _load_replay_capture(Path(tmp), "memory/honors forget")
            self.assertIsNone(note)
            self.assertEqual(text, "OK.")

    def test_unknown_fields_are_preserved_readable(self) -> None:
        # Additive schema promise: replay ignores unknown top-level
        # fields so future captures emitted by a newer harness still
        # replay against the current one.
        with tempfile.TemporaryDirectory() as tmp:
            payload = {
                "scenario_id": "x",
                "domain": "chat_realism",
                "backend": "ollama",
                "captured_at": "2026-05-17T00:00:00Z",
                "prompt": "hi",
                "response": "hello",
                "metadata": {},
                "future_knob": {"nested": True},
            }
            (Path(tmp) / "x.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
            text, note = _load_replay_capture(Path(tmp), "x")
            self.assertIsNone(note)
            self.assertEqual(text, "hello")


if __name__ == "__main__":
    unittest.main()
