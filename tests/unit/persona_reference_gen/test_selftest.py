"""Unit tests for the Doctrine §8 multimodal-vision self-test pass.

Exercises the stub path (default; no OpenAI spend) and the verdict
roll-up rules. Live mode is gated behind `PERSONA_REFGEN_SELFTEST_LIVE`
and not exercised here — see README.md §"What's stubbed".
"""

from __future__ import annotations

from pathlib import Path

import pytest
import selftest  # type: ignore[import-not-found]
from output_schema import SelfTestRow  # type: ignore[import-not-found]


def _stub_image(path: Path, *, byte: int = 0) -> Path:
    """Write a tiny placeholder file. selftest stub doesn't read the
    bytes (no live model), so any non-empty file works."""
    path.write_bytes(bytes([byte]))
    return path


def test_stub_returns_pass_verdict_with_deterministic_shape(tmp_path, monkeypatch):
    """Default (no env var) → stub path, every row passes with score 8."""
    monkeypatch.delenv("PERSONA_REFGEN_SELFTEST_LIVE", raising=False)

    cand = _stub_image(tmp_path / "cand.png", byte=42)
    anchor = _stub_image(tmp_path / "anchor.png", byte=1)

    row = selftest.score_candidate(
        cand,
        anchor,
        prompt_id="abc",
        candidate_index=0,
        prompt_text="Aurora full body",
        persona_slug="aurora",
    )

    assert row.prompt_id == "abc"
    assert row.candidate_index == 0
    assert row.verdict == "pass"
    assert row.photoreal_score == 8
    assert row.framing_match == "yes"
    assert row.identity_match == "yes"
    assert row.backend == "stub"
    # JSONL round-trip preserves every field.
    rt = SelfTestRow.from_jsonl(row.to_jsonl())
    assert rt == row


@pytest.mark.parametrize(
    "photoreal,framing,identity,expected",
    [
        # Baseline pass.
        (8, "yes", "yes", "pass"),
        # Photoreal below threshold (locked at 6) → flag.
        (5, "yes", "yes", "flag"),
        (6, "yes", "yes", "pass"),  # exactly threshold = pass
        # Framing miss → flag (doctrine §5).
        (9, "no", "yes", "flag"),
        # Identity miss → flag.
        (9, "yes", "no", "flag"),
        # Identity uncertain ≠ flag (Don sees with note).
        (9, "yes", "maybe", "pass"),
        # Multiple failures still produce a single flag.
        (3, "no", "no", "flag"),
    ],
)
def test_verdict_roll_up_rules(photoreal, framing, identity, expected):
    """Verdict gate is a single audited locked-rule chokepoint."""
    assert (
        selftest._roll_up_verdict(photoreal, framing, identity)
        == expected
    )


def test_write_selftest_jsonl_round_trips(tmp_path):
    """Bulk writer produces a JSONL the per-row reader handles."""
    rows = [
        SelfTestRow(
            prompt_id="p1",
            candidate_index=0,
            timestamp="2026-05-02T00:00:00+00:00",
            photoreal_score=8,
            framing_match="yes",
            identity_match="yes",
            verdict="pass",
            notes="ok",
            backend="stub",
        ),
        SelfTestRow(
            prompt_id="p2",
            candidate_index=0,
            timestamp="2026-05-02T00:00:01+00:00",
            photoreal_score=4,
            framing_match="no",
            identity_match="maybe",
            verdict="flag",
            notes="cropped + uncertain",
            backend="stub",
        ),
    ]
    path = selftest.write_selftest_jsonl(rows, tmp_path)
    assert path.name == "selftest.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    rt0 = SelfTestRow.from_jsonl(lines[0])
    rt1 = SelfTestRow.from_jsonl(lines[1])
    assert rt0 == rows[0]
    assert rt1 == rows[1]


def test_is_live_mode_env_gate(monkeypatch):
    """`PERSONA_REFGEN_SELFTEST_LIVE` accepts the same truthy set as the
    fal.ai live gate. Locking the spelling here so the two gates stay
    parallel."""
    for v in ("1", "true", "yes", "on", "True", "YES"):
        monkeypatch.setenv("PERSONA_REFGEN_SELFTEST_LIVE", v)
        assert selftest.is_live_mode(), f"truthy {v!r} should enable live"
    for v in ("0", "false", "no", "off", "", "  "):
        monkeypatch.setenv("PERSONA_REFGEN_SELFTEST_LIVE", v)
        assert not selftest.is_live_mode(), f"falsy {v!r} should not enable live"
    monkeypatch.delenv("PERSONA_REFGEN_SELFTEST_LIVE", raising=False)
    assert not selftest.is_live_mode()
