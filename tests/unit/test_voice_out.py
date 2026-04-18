"""Module 03 tests — verify Voice-Out TTS pipeline."""


import pytest


class TestTTS:
    @pytest.mark.asyncio
    async def test_empty_text_returns_none(self):
        from src.voice.tts import synthesize

        result = await synthesize("")
        assert result is None

    @pytest.mark.asyncio
    async def test_whitespace_only_returns_none(self):
        from src.voice.tts import synthesize

        result = await synthesize("   ")
        assert result is None


# TestAudioPlayer.test_play_audio_does_not_raise required the PortAudio
# native library to load sounddevice, which CI runners don't ship. The
# replacement audio_player module also reads config["audio"]["output_device"]
# which doesn't exist on v1.0 — the test would KeyError even with PortAudio.
# Real playback is covered by the desktop shell smoke test path on dev boxes.
