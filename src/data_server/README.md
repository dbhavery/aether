# Data Storage Server

FastAPI REST API for local media cataloging and tagging (port 8766).

## Responsibility

Scans local folders for media files, computes SHA-256 hashes, classifies them
by type (image, video, audio, document), and stores metadata in a SQLite database
at `./data\media_catalog.db`. Provides search across file names,
descriptions, tags, and face names. All endpoints require a bearer token except
`GET /health`. Ingest runs as a FastAPI background task so it does not block
other requests.

## Key Files

- `app.py` — the entire module. Contains `create_data_server_app() -> FastAPI`
  which initialises the database, registers all routes, and returns the app
  instance. Also contains `_ingest_folder_task()` (background scanner), the
  `_classify_media_type()` helper, and the SQLite schema (`media_items` table
  with indexes on `content_hash` and `media_type`).
- `__init__.py` — single-line docstring; no public exports.

## Interface Contract

All routes require `Authorization: Bearer <token>` (verified by `src.core.auth.verify_token`).

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Status + current ingest progress (no auth required) |
| POST | `/ingest` | Start background folder scan; restricted to `AetherData` paths |
| GET | `/ingest/status` | Poll background ingest progress |
| GET | `/items` | Paginated item list; optional `media_type` filter |
| GET | `/items/{id}` | Single item metadata |
| POST | `/items/{id}/tag` | Append tags to an item |
| GET | `/search?q=` | Full-text search across name, description, tags, faces |
| GET | `/tasks` | Delegate to `src.agents.task_registry.get_task_summary()` |
| POST | `/tasks/clear` | Clear completed agent tasks |

Does not subscribe to or publish EventBus events. It is a standalone HTTP service.

## Dependencies

- `fastapi` — web framework
- `pydantic` — request/response models
- `uvicorn` — ASGI server (started externally, not from within this module)
- `sqlite3` (stdlib) — database; WAL mode enabled
- `hashlib` (stdlib) — SHA-256 content hashing
- `loguru` — structured logging
- `src.core.auth` — `verify_token()` for bearer auth
- `src.shared.config` — `get_settings()` for `aether_data_path`
- `src.agents.task_registry` — `get_task_summary()`, `clear_completed_tasks()`
