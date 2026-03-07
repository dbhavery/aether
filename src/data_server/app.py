"""Data Storage Server — FastAPI REST API for media management.

Endpoints:
- POST /ingest — trigger folder scan + indexing
- GET /search — search media by query (text, tags, faces)
- POST /items/{id}/tag — add tags to a media item
- GET /items — browse all indexed items with pagination
- GET /items/{id} — get a single item's metadata
- GET /health — server health check
"""

import hashlib
import sqlite3
import time
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from loguru import logger
from pydantic import BaseModel

from src.core.auth import verify_token
from src.shared.config import get_settings

# Database path — lazily resolved to avoid import-time get_settings() call
_db_path: Path | None = None


def _get_db_path() -> Path:
    """Lazily resolve DB path — avoids calling get_settings() at import time."""
    global _db_path
    if _db_path is None:
        _db_path = Path(get_settings().aether_data_path) / "media_catalog.db"
    return _db_path


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_get_db_path()), timeout=10)  # Wait up to 10s for write lock
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db() -> None:
    """Create tables if they don't exist."""
    conn = _get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS media_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT UNIQUE NOT NULL,
            file_name TEXT NOT NULL,
            content_hash TEXT,
            file_size INTEGER,
            media_type TEXT,
            description TEXT,
            tags TEXT DEFAULT '',
            faces TEXT DEFAULT '',
            created_at REAL,
            indexed_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_media_hash ON media_items(content_hash);
        CREATE INDEX IF NOT EXISTS idx_media_type ON media_items(media_type);
    """)
    conn.close()
    logger.info(f"DataServer: database initialized at {_get_db_path()}")


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _classify_media_type(suffix: str) -> str:
    suffix = suffix.lower()
    if suffix in (
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".webp",
        ".heic",
        ".heif",
        ".svg",
        ".ico",
        ".jfif",
    ):
        return "image"
    if suffix in (
        ".mp4",
        ".mkv",
        ".avi",
        ".mov",
        ".wmv",
        ".flv",
        ".webm",
        ".ts",
        ".vob",
        ".mts",
    ):
        return "video"
    if suffix in (
        ".mp3",
        ".wav",
        ".flac",
        ".aac",
        ".ogg",
        ".m4a",
        ".wma",
        ".aif",
        ".mid",
        ".midi",
        ".alac",
    ):
        return "audio"
    if suffix in (".pdf", ".doc", ".docx", ".txt", ".md", ".pptx", ".xlsx", ".csv"):
        return "document"
    return "other"


# ── Pydantic models ─────────────────────────────────────────


class TagRequest(BaseModel):
    tags: list[str]


class IngestRequest(BaseModel):
    folder: str
    recursive: bool = True


class MediaItemResponse(BaseModel):
    id: int
    file_path: str
    file_name: str
    content_hash: str | None
    file_size: int | None
    media_type: str
    description: str | None
    tags: list[str]
    faces: list[str]
    indexed_at: float


# ── Background tasks ────────────────────────────────────────

_ingest_status = {"running": False, "total": 0, "processed": 0, "last_error": None}


def _ingest_folder_task(folder: Path, recursive: bool) -> None:
    """Scan folder and index media files."""
    # NOTE: _ingest_status["running"] is set to True by the /ingest endpoint
    # before this task is queued, to prevent TOCTOU race conditions.
    _ingest_status["processed"] = 0
    _ingest_status["last_error"] = None

    extensions = {
        # Images
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".webp",
        ".heic",
        ".heif",
        ".svg",
        ".ico",
        ".jfif",
        # Video
        ".mp4",
        ".mkv",
        ".avi",
        ".mov",
        ".wmv",
        ".flv",
        ".webm",
        ".ts",
        ".vob",
        ".mts",
        # Audio
        ".mp3",
        ".wav",
        ".flac",
        ".aac",
        ".ogg",
        ".m4a",
        ".wma",
        ".aif",
        ".mid",
        ".midi",
        ".alac",
        # Documents
        ".pdf",
        ".doc",
        ".docx",
        ".txt",
        ".md",
        ".pptx",
        ".xlsx",
        ".csv",
    }

    try:
        pattern = "**/*" if recursive else "*"
        files = [f for f in folder.glob(pattern) if f.is_file() and f.suffix.lower() in extensions]
        _ingest_status["total"] = len(files)
        logger.info(f"DataServer: ingesting {len(files)} files from {folder}")

        conn = _get_db()
        try:
            for i, file_path in enumerate(files):
                try:
                    # Skip if already indexed
                    existing = conn.execute(
                        "SELECT id FROM media_items WHERE file_path = ?", (str(file_path),)
                    ).fetchone()
                    if existing:
                        _ingest_status["processed"] = i + 1
                        continue

                    content_hash = _hash_file(file_path)
                    media_type = _classify_media_type(file_path.suffix)
                    stat = file_path.stat()

                    conn.execute(
                        """INSERT INTO media_items
                           (file_path, file_name, content_hash, file_size, media_type, created_at, indexed_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            str(file_path),
                            file_path.name,
                            content_hash,
                            stat.st_size,
                            media_type,
                            stat.st_ctime,
                            time.time(),
                        ),
                    )
                    _ingest_status["processed"] = i + 1

                    # Batch commit every 100 files for performance
                    if (i + 1) % 100 == 0:
                        conn.commit()

                except Exception as e:
                    logger.error(f"DataServer: failed to index {file_path}: {e}")
                    _ingest_status["last_error"] = str(e)

            conn.commit()
            logger.info(f"DataServer: ingest complete. {_ingest_status['processed']}/{_ingest_status['total']} files.")
        finally:
            conn.close()

    except Exception as e:
        logger.error(f"DataServer: ingest task failed: {e}")
        _ingest_status["last_error"] = str(e)
    finally:
        _ingest_status["running"] = False


# ── App factory ─────────────────────────────────────────────


async def _verify_auth(request: Request) -> None:
    """FastAPI dependency — verify bearer token on every request except /health."""
    if request.url.path == "/health":
        return
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        token = request.query_params.get("token", "")
    if not token or not verify_token(token):
        raise HTTPException(status_code=401, detail="Unauthorized")


def create_data_server_app() -> FastAPI:
    """Create the Data Storage Server FastAPI app."""
    _init_db()

    app = FastAPI(
        title="Aether Data Storage",
        version="1.0.0",
        dependencies=[Depends(_verify_auth)],
    )

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "service": "data_storage_server",
            "ingest_status": _ingest_status,
        }

    @app.post("/ingest")
    async def ingest(request: IngestRequest, bg: BackgroundTasks):
        folder = Path(request.folder).resolve()
        # Restrict ingest to allowed base directories
        allowed_bases = [Path(get_settings().aether_data_path).resolve()]
        if not any(folder.is_relative_to(base) for base in allowed_bases):
            raise HTTPException(
                403,
                "Folder not in allowed paths. Only AetherData directories permitted.",
            )
        if not folder.exists():
            raise HTTPException(404, f"Folder not found: {request.folder}")
        if _ingest_status["running"]:
            raise HTTPException(409, "Ingest already running")
        # Set running=True HERE (not in the task) to prevent TOCTOU race
        _ingest_status["running"] = True
        bg.add_task(_ingest_folder_task, folder, request.recursive)
        return {"status": "started", "folder": str(folder)}

    @app.get("/ingest/status")
    async def ingest_status():
        return _ingest_status

    @app.get("/items")
    async def list_items(
        media_type: str | None = None,
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ):
        conn = _get_db()
        try:
            if media_type:
                rows = conn.execute(
                    "SELECT * FROM media_items WHERE media_type = ? ORDER BY indexed_at DESC LIMIT ? OFFSET ?",
                    (media_type, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM media_items ORDER BY indexed_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
            return {"items": [_row_to_dict(r) for r in rows], "count": len(rows)}
        finally:
            conn.close()

    @app.get("/items/{item_id}")
    async def get_item(item_id: int):
        conn = _get_db()
        try:
            row = conn.execute("SELECT * FROM media_items WHERE id = ?", (item_id,)).fetchone()
            if not row:
                raise HTTPException(404, f"Item {item_id} not found")
            return _row_to_dict(row)
        finally:
            conn.close()

    @app.post("/items/{item_id}/tag")
    async def tag_item(item_id: int, request: TagRequest):
        conn = _get_db()
        try:
            row = conn.execute("SELECT * FROM media_items WHERE id = ?", (item_id,)).fetchone()
            if not row:
                raise HTTPException(404, f"Item {item_id} not found")
            existing_tags = set(row["tags"].split(",")) if row["tags"] else set()
            existing_tags.discard("")
            # Strip commas from tag values to prevent CSV corruption on round-trip
            clean_new_tags = [t.replace(",", "").strip() for t in request.tags if t.strip()]
            existing_tags.update(clean_new_tags)
            new_tags = ",".join(sorted(existing_tags))
            conn.execute("UPDATE media_items SET tags = ? WHERE id = ?", (new_tags, item_id))
            conn.commit()
            return {"id": item_id, "tags": sorted(existing_tags)}
        finally:
            conn.close()

    @app.get("/tasks")
    async def list_tasks():
        from src.agents.task_registry import get_task_summary

        return {"tasks": get_task_summary()}

    @app.post("/tasks/clear")
    async def clear_tasks():
        from src.agents.task_registry import clear_completed_tasks

        count = clear_completed_tasks()
        return {"cleared": count}

    @app.get("/search")
    async def search(
        q: str = Query(..., min_length=1, max_length=500),
        media_type: str | None = None,
        limit: int = Query(20, ge=1, le=100),
    ):
        conn = _get_db()
        try:
            # Escape LIKE wildcards to prevent injection (% and _ are special in LIKE)
            escaped_q = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            query_pattern = f"%{escaped_q}%"
            if media_type:
                rows = conn.execute(
                    """SELECT * FROM media_items
                       WHERE media_type = ? AND (
                           file_name LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\'
                           OR tags LIKE ? ESCAPE '\\' OR faces LIKE ? ESCAPE '\\'
                       ) ORDER BY indexed_at DESC LIMIT ?""",
                    (
                        media_type,
                        query_pattern,
                        query_pattern,
                        query_pattern,
                        query_pattern,
                        limit,
                    ),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM media_items
                       WHERE file_name LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\'
                       OR tags LIKE ? ESCAPE '\\' OR faces LIKE ? ESCAPE '\\'
                       ORDER BY indexed_at DESC LIMIT ?""",
                    (query_pattern, query_pattern, query_pattern, query_pattern, limit),
                ).fetchall()
            return {"results": [_row_to_dict(r) for r in rows], "count": len(rows)}
        finally:
            conn.close()

    return app


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["tags"] = [t for t in (d.get("tags", "") or "").split(",") if t]
    d["faces"] = [f for f in (d.get("faces", "") or "").split(",") if f]
    return d
