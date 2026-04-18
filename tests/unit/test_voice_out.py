"""Module 03 tests — verify Voice-Out TTS pipeline."""

from unittest.mock import patch

import numpy as np
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


class TestAudioPlayer:
    @pytest.mark.asyncio
    async def test_play_audio_does_not_raise(self):
        # CI runners have `sounddevice` the Python wrapper but no PortAudio
        # native library. Skip when the sd module can't even load.
        sd = pytest.importorskip(
            "sounddevice", reason="sounddevice requires PortAudio native lib"
        )
        try:
            sd.query_devices()
        except OSError:
            pytest.skip("PortAudio not installed on this runner")
        with patch("src.voice.audio_player.sd.play"):
            from src.voice.audio_player import play_audio

            audio = np.zeros(24000, dtype=np.float32)
            await play_audio(audio, 24000)
