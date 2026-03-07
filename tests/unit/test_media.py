"""Module 09 tests — verify media pipeline."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestImageUnderstand:
    @pytest.mark.asyncio
    async def test_returns_error_for_missing_file(self):
        from src.media.image_understand import describe_image

        result = await describe_image("nonexistent_file_abc123.jpg")
        assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_graceful_failure_on_ollama_error(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"fake image data")
            tmp = f.name
        try:
            import httpx as httpx_mod

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=Exception("ollama unavailable"))
            with patch.object(httpx_mod, "AsyncClient", return_value=mock_client):
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                from src.media.image_understand import describe_image

                result = await describe_image(tmp)
                assert "couldn't analyze" in result.lower()
        finally:
            Path(tmp).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_describe_image_bytes_cleans_up_temp(self):
        from src.media.image_understand import describe_image_bytes

        with patch(
            "src.media.image_understand.describe_image", new_callable=AsyncMock, return_value="a photo of a cat"
        ):
            result = await describe_image_bytes(b"fake jpg data", "what is this?")
            assert result == "a photo of a cat"


class TestFaceRecognize:
    def test_known_faces_dir_constant(self):
        from src.media.face_recognize import _get_known_faces_dir

        assert "known_faces" in str(_get_known_faces_dir())

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_missing_image(self):
        from src.media.face_recognize import identify_faces_in_image

        mock_cv2 = MagicMock()
        mock_cv2.imread.return_value = None
        with patch("src.media.face_recognize._get_app"), patch.dict("sys.modules", {"cv2": mock_cv2}):
            result = await identify_faces_in_image("nonexistent.jpg")
            assert result == []
