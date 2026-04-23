"""Unit tests for the session-log replay importer (Quality-Eval v1.3).

Stdlib-only `unittest`, same discipline as `test_capture_replay.py` —
the evals tree stays dependency-free.

Run::

    python tools/evals/test_session_log_import.py
    # or
    python -m unittest tools.evals.test_session_log_import
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location(
    "aether_evals_session_log_import", HERE / "session_log_import.py"
)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("could not locate session_log_import.py")
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules["aether_evals_session_log_import"] = _mod
_SPEC.loader.exec_module(_mod)

_parse_session_log = _mod._parse_session_log
_pair_user_assistant = _mod._pair_user_assistant
_extract_scenarios = _mod._extract_scenarios
match_scenario = _mod.match_scenario
import_session_log = _mod.import_session_log
SessionTurn = _mod.SessionTurn


def _write_session_log(tmp: Path, turns: list[dict]) -> Path:
    """Serialise a list of TurnMemoryRecord-shaped dicts to a JSONL
    session log. One object per line, no trailing newline on the
    final line — the parser must tolerate both forms."""
    path = tmp / "session.jsonl"
    with path.open("w", encoding="utf-8") as fp:
        fp.write("\n".join(json.dumps(t) for t in turns))
    return path


def _write_scenarios(tmp: Path, scenarios: list[dict]) -> Path:
    """Write one or more scenario objects to a single JSONL file so
    the importer's ``_extract_scenarios`` can walk them. Returns the
    scenarios-root directory the importer CLI expects."""
    root = tmp / "scenarios"
    root.mkdir()
    path = root / "chat.jsonl"
    with path.open("w", encoding="utf-8") as fp:
        fp.write("\n".join(json.dumps(s) for s in scenarios) + "\n")
    return root


def _session_turn(
    session_id: str,
    role: str,
    content: str,
    sequence: int,
    timestamp_ms: int = 0,
) -> dict:
    return {
        "session_id": session_id,
        "role": role,
        "content": content,
        "sequence": sequence,
        "timestamp_ms": timestamp_ms or sequence * 1_000,
    }


class MatchScenarioTests(unittest.TestCase):
    def test_exact_match_after_normalisation(self) -> None:
        self.assertEqual(
            match_scenario("hi, first time", "Hi,  first time"),
            "exact",
        )

    def test_substring_match_when_scenario_prompt_fits_inside(self) -> None:
        self.assertEqual(
            match_scenario(
                "Hey — hi, first time here, what can you do?",
                "hi, first time",
            ),
            "substring",
        )

    def test_no_match_returns_none(self) -> None:
        self.assertIsNone(match_scenario("unrelated content", "hi"))
        self.assertIsNone(match_scenario("whatever", ""))


class ParseSessionLogTests(unittest.TestCase):
    def test_parses_valid_lines_and_skips_blank_and_comment_lines(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "s.jsonl"
            p.write_text(
                "\n".join(
                    [
                        json.dumps(_session_turn("s1", "user", "hi", 1)),
                        "",
                        "// a comment",
                        json.dumps(_session_turn("s1", "assistant", "hello", 2)),
                    ]
                ),
                encoding="utf-8",
            )
            turns = _parse_session_log(p)
            self.assertEqual(len(turns), 2)
            self.assertEqual(turns[0].role, "user")
            self.assertEqual(turns[1].content, "hello")

    def test_malformed_json_is_warned_and_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "s.jsonl"
            p.write_text("{not json}\n" + json.dumps(
                _session_turn("s1", "user", "ok", 1)
            ), encoding="utf-8")
            turns = _parse_session_log(p)
            # The valid line still lands; the malformed line was skipped.
            self.assertEqual(len(turns), 1)
            self.assertEqual(turns[0].content, "ok")

    def test_missing_required_fields_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "s.jsonl"
            p.write_text(
                json.dumps({"role": "user", "content": "missing everything else"}),
                encoding="utf-8",
            )
            self.assertEqual(_parse_session_log(p), [])


class PairUserAssistantTests(unittest.TestCase):
    def test_simple_alternation_yields_pairs(self) -> None:
        turns = [
            SessionTurn("s1", "user", "u1", 1, 10),
            SessionTurn("s1", "assistant", "a1", 2, 20),
            SessionTurn("s1", "user", "u2", 3, 30),
            SessionTurn("s1", "assistant", "a2", 4, 40),
        ]
        pairs = _pair_user_assistant(turns)
        self.assertEqual([p[0].content for p in pairs], ["u1", "u2"])
        self.assertEqual([p[1].content for p in pairs], ["a1", "a2"])

    def test_system_turn_does_not_break_pairing(self) -> None:
        turns = [
            SessionTurn("s1", "user", "u1", 1, 10),
            SessionTurn("s1", "system", "policy note", 2, 20),
            SessionTurn("s1", "assistant", "a1", 3, 30),
        ]
        pairs = _pair_user_assistant(turns)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0][0].content, "u1")
        self.assertEqual(pairs[0][1].content, "a1")

    def test_consecutive_users_use_the_most_recent_before_assistant(
        self,
    ) -> None:
        turns = [
            SessionTurn("s1", "user", "u1_dropped", 1, 10),
            SessionTurn("s1", "user", "u2_paired", 2, 20),
            SessionTurn("s1", "assistant", "a1", 3, 30),
        ]
        pairs = _pair_user_assistant(turns)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0][0].content, "u2_paired")

    def test_sessions_are_isolated(self) -> None:
        turns = [
            SessionTurn("s1", "user", "u1", 1, 10),
            SessionTurn("s2", "user", "u2", 1, 10),
            SessionTurn("s2", "assistant", "a2", 2, 20),
            SessionTurn("s1", "assistant", "a1", 2, 20),
        ]
        pairs = _pair_user_assistant(turns)
        paired = {(u.session_id, u.content, a.content) for u, a in pairs}
        self.assertEqual(
            paired, {("s1", "u1", "a1"), ("s2", "u2", "a2")}
        )


class EndToEndImportTests(unittest.TestCase):
    def test_matched_scenarios_emit_captures_with_v12_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            session_log = _write_session_log(
                tmp_p,
                [
                    _session_turn("s1", "user", "hi, first time", 1, 100),
                    _session_turn(
                        "s1",
                        "assistant",
                        "Hi — what would you like to do?",
                        2,
                        200,
                    ),
                ],
            )
            scenarios_root = _write_scenarios(
                tmp_p,
                [
                    {
                        "id": "chat.greeting.first_time_user",
                        "domain": "chat_realism",
                        "turns": [
                            {"role": "user", "content": "hi, first time"}
                        ],
                    }
                ],
            )
            captures = tmp_p / "captures"
            report = import_session_log(session_log, scenarios_root, captures)
            self.assertEqual(report.match_count, 1)
            self.assertEqual(report.matched[0][1], "exact")
            # The emitted capture file must carry every field the v1.2
            # replay loader expects, plus the additive metadata.
            out = captures / "chat.greeting.first_time_user.json"
            self.assertTrue(out.is_file(), f"expected {out} to be written")
            payload = json.loads(out.read_text(encoding="utf-8"))
            for k in (
                "scenario_id",
                "domain",
                "backend",
                "captured_at",
                "prompt",
                "response",
                "metadata",
            ):
                self.assertIn(k, payload, f"missing field: {k}")
            self.assertEqual(payload["backend"], "session-log")
            self.assertEqual(payload["prompt"], "hi, first time")
            self.assertEqual(
                payload["response"], "Hi — what would you like to do?"
            )
            self.assertTrue(payload["captured_at"].endswith("Z"))
            self.assertEqual(payload["metadata"]["source_session_id"], "s1")
            self.assertEqual(payload["metadata"]["match_kind"], "exact")
            # No unmatched pairs because every user turn matched.
            self.assertEqual(report.unmatched_session_pairs, 0)

    def test_substring_match_still_emits_capture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            session_log = _write_session_log(
                tmp_p,
                [
                    _session_turn(
                        "s1",
                        "user",
                        "Hey there — hi, first time here, can you help?",
                        1,
                    ),
                    _session_turn("s1", "assistant", "Of course.", 2),
                ],
            )
            scenarios_root = _write_scenarios(
                tmp_p,
                [
                    {
                        "id": "chat.greeting.first_time_user",
                        "domain": "chat_realism",
                        "turns": [
                            {"role": "user", "content": "hi, first time"}
                        ],
                    }
                ],
            )
            captures = tmp_p / "captures"
            report = import_session_log(session_log, scenarios_root, captures)
            self.assertEqual(report.match_count, 1)
            self.assertEqual(report.matched[0][1], "substring")

    def test_unmatched_scenarios_leave_report_but_no_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            session_log = _write_session_log(
                tmp_p,
                [
                    _session_turn("s1", "user", "nothing relevant", 1),
                    _session_turn("s1", "assistant", "ok", 2),
                ],
            )
            scenarios_root = _write_scenarios(
                tmp_p,
                [
                    {
                        "id": "chat.greeting.first_time_user",
                        "domain": "chat_realism",
                        "turns": [
                            {"role": "user", "content": "hi, first time"}
                        ],
                    }
                ],
            )
            captures = tmp_p / "captures"
            report = import_session_log(session_log, scenarios_root, captures)
            self.assertEqual(report.match_count, 0)
            self.assertEqual(
                report.skipped_no_match,
                ["chat.greeting.first_time_user"],
            )
            # Capture directory may not exist at all when zero files
            # were written — the importer only creates it on first
            # write. Either "no dir" or "empty dir" is a valid outcome.
            if captures.is_dir():
                self.assertEqual(list(captures.iterdir()), [])
            self.assertEqual(report.unmatched_session_pairs, 1)

    def test_first_match_wins_when_two_scenarios_share_a_prompt(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            session_log = _write_session_log(
                tmp_p,
                [
                    _session_turn("s1", "user", "hi, first time", 1),
                    _session_turn("s1", "assistant", "hello", 2),
                ],
            )
            scenarios_root = _write_scenarios(
                tmp_p,
                [
                    {
                        "id": "chat.greeting.a",
                        "domain": "chat_realism",
                        "turns": [
                            {"role": "user", "content": "hi, first time"}
                        ],
                    },
                    {
                        "id": "chat.greeting.b",
                        "domain": "chat_realism",
                        "turns": [
                            {"role": "user", "content": "hi, first time"}
                        ],
                    },
                ],
            )
            captures = tmp_p / "captures"
            report = import_session_log(session_log, scenarios_root, captures)
            # Only one of the two scenarios gets the capture; the
            # other ends up in skipped_no_match. The importer doesn't
            # promise which one wins, only that at most one does.
            self.assertEqual(report.match_count, 1)
            self.assertEqual(len(report.skipped_no_match), 1)


if __name__ == "__main__":
    unittest.main()
