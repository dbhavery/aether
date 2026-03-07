"""Tests for false wake-up context evaluator."""

from src.voice.wake_context import evaluate_wake_context


def test_short_transcript_is_false_wake():
    assert evaluate_wake_context("hi") is False
    assert evaluate_wake_context("") is False


def test_activation_phrase_activates():
    assert evaluate_wake_context("can you check the weather") is True
    assert evaluate_wake_context("what time is it") is True
    assert evaluate_wake_context("please set a reminder") is True
    assert evaluate_wake_context("help me with something") is True


def test_third_party_indicator_suppresses():
    assert evaluate_wake_context("she is pretty smart actually") is False
    assert evaluate_wake_context("the assistant can do that") is False
    # "it" was removed from indicators — too common, blocks "fix it", "look it up"
    assert evaluate_wake_context("my assistant handles that well") is False


def test_default_activates():
    # Unrecognized long text defaults to activation
    assert evaluate_wake_context("schedule meeting tomorrow at noon") is True
