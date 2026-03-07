"""Tests for Batch 11 — persona system, [SILENT] protocol, and response sanitizer."""

import pytest

from src.brain.sanitizer import sanitize_response


class TestSanitizer:
    def test_strips_how_can_i_help(self):
        text = "Here's the weather forecast. How can I help you with anything else?"
        result = sanitize_response(text)
        assert "how can i help" not in result.lower()

    def test_strips_is_there_anything_else(self):
        text = "The file has been saved. Is there anything else you need?"
        result = sanitize_response(text)
        assert "is there anything else" not in result.lower()

    def test_strips_happy_to_help(self):
        text = "Done! Happy to help with anything else."
        result = sanitize_response(text)
        assert "happy to help" not in result.lower()

    def test_strips_hope_this_helps(self):
        text = "Here's the info you asked about. Hope this helps!"
        result = sanitize_response(text)
        assert "hope this helps" not in result.lower()

    def test_strips_let_me_know(self):
        text = "The meeting is at 3pm.\nLet me know if you need anything else."
        result = sanitize_response(text)
        assert "let me know" not in result.lower()

    def test_strips_feel_free(self):
        text = "Your document is ready. Feel free to ask if you have questions."
        result = sanitize_response(text)
        assert "feel free" not in result.lower()

    def test_strips_great_question(self):
        text = "Great question! The answer is 42."
        result = sanitize_response(text)
        assert "great question" not in result.lower()
        assert "42" in result

    def test_strips_absolutely_standalone(self):
        text = "Absolutely! I'll check that right now."
        result = sanitize_response(text)
        assert not result.lower().startswith("absolutely")

    def test_preserves_normal_content(self):
        text = "The weather in Seattle is 65F and partly cloudy."
        result = sanitize_response(text)
        assert result == text

    def test_strips_multiple_banned_phrases(self):
        text = "Great question! Here's the answer. Hope this helps! Let me know if you need anything."
        result = sanitize_response(text)
        assert "great question" not in result.lower()
        assert "hope this helps" not in result.lower()
        assert "let me know" not in result.lower()

    def test_empty_string_returns_empty(self):
        assert sanitize_response("") == ""

    def test_preserves_multiline_structure(self):
        text = "Line one.\n\nLine three.\n\nLine five."
        result = sanitize_response(text)
        assert result == text

    def test_strips_dont_hesitate(self):
        text = "Here's the report. Don't hesitate to reach out if you need changes."
        result = sanitize_response(text)
        assert "don't hesitate" not in result.lower()

    def test_strips_im_here_to_help(self):
        text = "Got it. I'm here to help whenever you need me."
        result = sanitize_response(text)
        assert "i'm here to help" not in result.lower()

    def test_strips_what_can_i_do_for_you(self):
        text = "What can I do for you?"
        result = sanitize_response(text)
        assert result.strip() == ""

    def test_cleanup_double_spaces(self):
        text = "Hello  world"
        result = sanitize_response(text)
        assert "  " not in result


class TestSilentGate:
    def test_gate_creation(self):
        from src.voice.silent_gate import SilentGate

        gate = SilentGate()
        assert gate.is_manual_silent is False

    def test_gate1_blocks_non_don(self):
        from src.voice.silent_gate import SilentGate

        gate = SilentGate()
        assert gate.gate1_speaker_verified(is_don=False) is False

    def test_gate1_passes_don(self):
        from src.voice.silent_gate import SilentGate

        gate = SilentGate()
        assert gate.gate1_speaker_verified(is_don=True) is True

    def test_manual_toggle_activate(self):
        from src.voice.silent_gate import SilentGate

        gate = SilentGate()
        result = gate.check_manual_toggle("silent mode")
        assert result is not None
        assert gate.is_manual_silent is True

    def test_manual_toggle_deactivate(self):
        from src.voice.silent_gate import SilentGate

        gate = SilentGate()
        gate._manual_silent = True
        result = gate.check_manual_toggle("we're alone")
        assert result is not None
        assert gate.is_manual_silent is False

    def test_gate2_directed_aether_name(self):
        from src.voice.silent_gate import SilentGate

        gate = SilentGate()
        result = gate.gate2_intent_prefilter("Aether, what time is it?")
        assert result is True

    def test_gate2_directed_tool_command(self):
        from src.voice.silent_gate import SilentGate

        gate = SilentGate()
        result = gate.gate2_intent_prefilter("open chrome please")
        assert result is True

    def test_gate2_not_directed_plural(self):
        from src.voice.silent_gate import SilentGate

        gate = SilentGate()
        result = gate.gate2_intent_prefilter("you guys want pizza?")
        assert result is False

    def test_gate2_ambiguous_returns_none(self):
        from src.voice.silent_gate import SilentGate

        gate = SilentGate()
        result = gate.gate2_intent_prefilter("I wonder about that")
        assert result is None

    def test_gate2_manual_silent_blocks(self):
        from src.voice.silent_gate import SilentGate

        gate = SilentGate()
        gate._manual_silent = True
        result = gate.gate2_intent_prefilter("what time is it?")
        assert result is False

    @pytest.mark.asyncio
    async def test_should_respond_non_don(self):
        from src.voice.silent_gate import SilentGate

        gate = SilentGate()
        result = await gate.should_respond("hello", is_don=False)
        assert result is False

    @pytest.mark.asyncio
    async def test_should_respond_directed(self):
        from src.voice.silent_gate import SilentGate

        gate = SilentGate()
        result = await gate.should_respond("Aether, play some music", is_don=True)
        assert result is True

    def test_singleton_get_silent_gate(self):
        from src.voice.silent_gate import get_silent_gate

        gate1 = get_silent_gate()
        gate2 = get_silent_gate()
        assert gate1 is gate2

    def test_people_around_activates(self):
        from src.voice.silent_gate import SilentGate

        gate = SilentGate()
        result = gate.check_manual_toggle("people around")
        assert result is not None
        assert gate.is_manual_silent is True


class TestPersonaPrompt:
    def test_system_prompt_has_all_sections(self):
        from src.brain.persona import build_system_prompt
        from src.shared.types import InteractionMode

        prompt = build_system_prompt(mode=InteractionMode.TEXT)
        assert "Aether" in prompt
        assert "COMMUNICATION STYLE" in prompt
        assert "KNOWLEDGE" in prompt
        assert "BEHAVIORAL RULES" in prompt
        assert "TOOL USE" in prompt
        assert "CONTEXT INTEGRATION" in prompt

    def test_voice_mode_mentions_voice(self):
        from src.brain.persona import build_system_prompt
        from src.shared.types import InteractionMode

        prompt = build_system_prompt(mode=InteractionMode.VOICE)
        assert "Voice mode" in prompt or "speaking" in prompt.lower()

    def test_flirtiness_in_prompt(self):
        from src.brain.persona import build_system_prompt
        from src.shared.types import InteractionMode

        prompt = build_system_prompt(mode=InteractionMode.TEXT)
        assert "flirtiness" in prompt.lower()

    def test_silent_protocol_in_prompt(self):
        from src.brain.persona import build_system_prompt
        from src.shared.types import InteractionMode

        prompt = build_system_prompt(mode=InteractionMode.TEXT)
        assert "SILENT" in prompt

    def test_bilingual_in_prompt(self):
        from src.brain.persona import build_system_prompt
        from src.shared.types import InteractionMode

        prompt = build_system_prompt(mode=InteractionMode.TEXT)
        assert "Mexican" in prompt or "Spanish" in prompt
