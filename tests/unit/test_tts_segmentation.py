"""A reply is spoken one sentence at a time.

Synthesis on this box runs at several times real time, so synthesising a whole
reply before playing any of it makes the listener wait for audio that could
already have been playing. `first_audio_ms` is marked on the first chunk out,
so speaking sentence one first is what moves it.

These tests use a fake synthesizer and a fake speaker, so they assert the
ordering and the event contract rather than a wall-clock number.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.shared.types import AetherEvent, EventType
from src.voice.tts_handler import _segment_for_speech, on_response_text_ready


class TestSegmenting:
    def test_sentences_are_separated(self):
        got = _segment_for_speech("Check the tires. Then the brakes. Is the hitch locked?")
        assert got == [
            "Check the tires.",
            "Then the brakes.",
            "Is the hitch locked?",
        ]

    def test_a_normal_short_sentence_stands_alone(self):
        """Every character in the first segment is latency.

        The floor started at 25, which swallowed a 22 character opening
        sentence into the one after it and doubled the wait for first audio.
        """
        got = _segment_for_speech("Check the tires first. Then look at the brake lines.")
        assert got[0] == "Check the tires first."

    def test_a_short_opener_is_glued_to_the_next_sentence(self):
        """Synthesising 'Yes.' alone sounds clipped."""
        got = _segment_for_speech("Yes. Check the tire pressure before you roll out.")
        assert got == ["Yes. Check the tire pressure before you roll out."]

    def test_text_with_no_terminator_is_one_segment(self):
        assert _segment_for_speech("no terminator here") == ["no terminator here"]

    @pytest.mark.parametrize("text", ["", "   ", "\n\t "])
    def test_empty_input_yields_nothing(self, text):
        assert _segment_for_speech(text) == []

    def test_no_words_are_lost(self):
        """A split may move a boundary; it must never drop a word."""
        text = "First one. Second one! Third one? And a fourth without an end"
        joined = " ".join(_segment_for_speech(text))
        assert joined.split() == text.split()


@pytest.fixture
def spoken(monkeypatch):
    """Record synth calls, published events, and playback, in order."""
    calls: dict[str, list] = {"synth": [], "played": [], "events": []}

    async def fake_synthesize(text: str):
        calls["synth"].append(text)
        # 0.1 s of silence at 24 kHz, enough to produce chunks.
        return np.zeros(2400, dtype=np.float32), 24000

    async def fake_play(audio, sample_rate):
        calls["played"].append(int(audio.shape[0]))

    async def fake_publish(event):
        calls["events"].append(event.type)

    monkeypatch.setattr("src.voice.tts_handler.synthesize", fake_synthesize)
    monkeypatch.setattr("src.voice.tts_handler.play_audio", fake_play)
    monkeypatch.setattr("src.voice.tts_handler.event_bus.publish", fake_publish)
    return calls


def _voice_event(text: str) -> AetherEvent:
    return AetherEvent(
        type=EventType.RESPONSE_TEXT_READY,
        data={"text": text, "mode": "voice", "is_interim": False},
        source_module="test",
    )


@pytest.mark.asyncio
async def test_each_sentence_is_synthesised_separately_and_in_order(spoken):
    await on_response_text_ready(
        _voice_event("Check the tires first. Then look at the brake lines. Is the hitch locked?")
    )
    assert spoken["synth"] == [
        "Check the tires first.",
        "Then look at the brake lines.",
        "Is the hitch locked?",
    ]
    assert len(spoken["played"]) == 3


@pytest.mark.asyncio
async def test_audio_end_is_published_exactly_once_and_last(spoken):
    """Per sentence it would tell the avatar the reply had finished early."""
    await on_response_text_ready(
        _voice_event("Check the tires first. Then look at the brake lines. Is the hitch locked?")
    )
    ends = [e for e in spoken["events"] if e is EventType.RESPONSE_AUDIO_END]
    assert len(ends) == 1
    assert spoken["events"][-1] is EventType.RESPONSE_AUDIO_END


@pytest.mark.asyncio
async def test_one_failed_segment_does_not_silence_the_rest(monkeypatch, spoken):
    """The middle sentence fails to synthesise; the other two still speak."""

    async def flaky(text: str):
        if "brake" in text:
            return None
        return np.zeros(2400, dtype=np.float32), 24000

    monkeypatch.setattr("src.voice.tts_handler.synthesize", flaky)

    await on_response_text_ready(
        _voice_event("Check the tires first. Then look at the brake lines. Is the hitch locked?")
    )
    assert len(spoken["played"]) == 2
    assert [e for e in spoken["events"] if e is EventType.RESPONSE_AUDIO_END]


@pytest.mark.asyncio
async def test_a_failing_last_segment_still_ends_the_audio(monkeypatch, spoken):
    """The regression this shape invites.

    Tying RESPONSE_AUDIO_END to the last segment skips it whenever that
    segment's synthesis fails, and the avatar never stops speaking.
    """

    async def fails_last(text: str):
        if "hitch" in text:
            return None
        return np.zeros(2400, dtype=np.float32), 24000

    monkeypatch.setattr("src.voice.tts_handler.synthesize", fails_last)

    await on_response_text_ready(
        _voice_event("Check the tires first. Then look at the brake lines. Is the hitch locked?")
    )
    ends = [e for e in spoken["events"] if e is EventType.RESPONSE_AUDIO_END]
    assert len(ends) == 1, "the reply ended with no RESPONSE_AUDIO_END"


@pytest.mark.asyncio
async def test_total_audio_ends_with_every_segment_counted(spoken):
    """total_samples on the end event covers the whole reply, not the last bit."""
    captured: list[dict] = []

    async def capture(event):
        spoken["events"].append(event.type)
        if event.type is EventType.RESPONSE_AUDIO_END:
            captured.append(event.data)

    import src.voice.tts_handler as handler

    handler.event_bus.publish = capture  # type: ignore[assignment]
    await on_response_text_ready(
        _voice_event("Check the tires first. Then look at the brake lines. Is the hitch locked?")
    )
    assert captured and captured[0]["total_samples"] == 3 * 2400


@pytest.mark.asyncio
async def test_text_mode_never_speaks(spoken):
    """The control. If this passes while the others fail, nothing was wired."""
    await on_response_text_ready(
        AetherEvent(
            type=EventType.RESPONSE_TEXT_READY,
            data={"text": "Check the tires. Then the brakes.", "mode": "text"},
            source_module="test",
        )
    )
    assert spoken["synth"] == []
    assert spoken["played"] == []
