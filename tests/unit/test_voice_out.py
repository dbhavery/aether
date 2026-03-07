"""Module 03 tests — verify Voice-Out TTS pipeline."""

from unittest.mock import AsyncMock, patch

import numpy as np
import pytest


class TestTTS:
    @pytest.mark.asyncio
    async def test_synthesize_falls_back_to_elevenlabs(self):
        with (
            patch("src.voice.tts.synthesize_chatterbox", new_callable=AsyncMock, return_value=None),
            patch(
                "src.voice.tts.synthesize_elevenlabs",
                new_callable=AsyncMock,
                return_value=(np.zeros(24000, dtype=np.float32), 24000),
            ),
        ):
            from src.voice.tts import synthesize

            result = await synthesize("Hello User")
            assert result is not None
            _audio, sr = result
            assert sr == 24000

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


class TestAudioPlayer:
    @pytest.mark.asyncio
    async def test_play_audio_does_not_raise(self):
        with patch("src.voice.audio_player.sd.play"):
            from src.voice.audio_player import play_audio

            audio = np.zeros(24000, dtype=np.float32)
            await play_audio(audio, 24000)
