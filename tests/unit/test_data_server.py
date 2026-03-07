"""Tests for Data Storage Server — REST API, database, search."""

import sqlite3


class TestMediaClassification:
    """Test file type classification."""

    def test_image_types(self):
        from src.data_server.app import _classify_media_type

        for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic"]:
            assert _classify_media_type(ext) == "image", f"Failed for {ext}"

    def test_video_types(self):
        from src.data_server.app import _classify_media_type

        for ext in [".mp4", ".mkv", ".avi", ".mov", ".webm"]:
            assert _classify_media_type(ext) == "video", f"Failed for {ext}"

    def test_audio_types(self):
        from src.data_server.app import _classify_media_type

        for ext in [".mp3", ".wav", ".flac", ".aac", ".ogg"]:
            assert _classify_media_type(ext) == "audio", f"Failed for {ext}"

    def test_document_types(self):
        from src.data_server.app import _classify_media_type

        for ext in [".pdf", ".doc", ".docx", ".txt", ".md"]:
            assert _classify_media_type(ext) == "document", f"Failed for {ext}"

    def test_unknown_type(self):
        from src.data_server.app import _classify_media_type

        assert _classify_media_type(".xyz") == "other"

    def test_case_insensitive(self):
        from src.data_server.app import _classify_media_type

        assert _classify_media_type(".JPG") == "image"
        assert _classify_media_type(".MP4") == "video"


class TestRowToDict:
    """Test sqlite Row to dict conversion."""

    def test_splits_tags(self):
        from src.data_server.app import _row_to_dict

        # Create a mock sqlite Row
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE t (id INTEGER, tags TEXT, faces TEXT)")
        conn.execute("INSERT INTO t VALUES (1, 'cat,dog,bird', 'don,alice')")
        row = conn.execute("SELECT * FROM t").fetchone()
        d = _row_to_dict(row)
        assert set(d["tags"]) == {"cat", "dog", "bird"}
        assert set(d["faces"]) == {"don", "alice"}
        conn.close()

    def test_empty_tags(self):
        from src.data_server.app import _row_to_dict

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE t (id INTEGER, tags TEXT, faces TEXT)")
        conn.execute("INSERT INTO t VALUES (1, '', '')")
        row = conn.execute("SELECT * FROM t").fetchone()
        d = _row_to_dict(row)
        assert d["tags"] == []
        assert d["faces"] == []
        conn.close()

    def test_null_tags(self):
        from src.data_server.app import _row_to_dict

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE t (id INTEGER, tags TEXT, faces TEXT)")
        conn.execute("INSERT INTO t VALUES (1, NULL, NULL)")
        row = conn.execute("SELECT * FROM t").fetchone()
        d = _row_to_dict(row)
        assert d["tags"] == []
        assert d["faces"] == []
        conn.close()


class TestDatabaseInit:
    """Test database initialization."""

    def test_init_creates_tables(self, tmp_path):
        from src.data_server import app as data_app_mod

        db_path = tmp_path / "test_media.db"
        original = data_app_mod._db_path
        data_app_mod._db_path = db_path
        try:
            data_app_mod._init_db()
            assert db_path.exists()
            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='media_items'")
            assert cursor.fetchone() is not None
            conn.close()
        finally:
            data_app_mod._db_path = original

    def test_init_idempotent(self, tmp_path):
        from src.data_server import app as data_app_mod

        db_path = tmp_path / "test_media.db"
        original = data_app_mod._db_path
        data_app_mod._db_path = db_path
        try:
            data_app_mod._init_db()
            data_app_mod._init_db()  # Should not error on second call
            assert db_path.exists()
        finally:
            data_app_mod._db_path = original
