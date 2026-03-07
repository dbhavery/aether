# Module 12: Notifications

Scheduled reminders, Windows toast notifications, and Android FCM push delivery.

## Responsibility

Manages two concerns: time-based scheduling (APScheduler with a SQLite job store
that survives restarts) and multi-channel delivery (Windows toasts via winotify,
Android push via Firebase Cloud Messaging). The handler bridges the EventBus to
the delivery layer and suppresses notifications when the busy detector says the user
is unavailable.

## Key Files

- `scheduler.py` — singleton `AsyncIOScheduler` backed by
  `./data\scheduler_jobs.db`. Registers three default recurring jobs:
  daily briefing (8:00 AM), daily interview (7:00 PM), weekly digest (Monday
  9:00 AM). Exposes `schedule_reminder(text, datetime) -> job_id` for one-off
  reminders. Jobs fire by publishing `NOTIFICATION_REQUEST` to the EventBus.
- `handler.py` — `on_notification_request(event)`: the EventBus subscriber that
  receives `NOTIFICATION_REQUEST` events, checks `BusyDetector.should_notify()`,
  then calls both `show_notification()` and `send_push_notification()` in sequence.
  `register_notification_handlers()` wires this up at startup.
- `windows_notify.py` — `show_notification(title, message)`: renders a silent
  Windows toast via winotify (no audio, by the user's preference). Messages are
  truncated to 250 characters.
- `fcm_notify.py` — `send_push_notification(title, body, device_token)`: lazy-
  initializes the Firebase Admin SDK from
  `./data\firebase-service-account.json` and sends a high-priority FCM
  message to the user's Android device token (read from settings).

## Interface Contract

- Subscribes to: `EventType.NOTIFICATION_REQUEST`
- Publishes: `EventType.NOTIFICATION_REQUEST` (scheduler fires into the bus;
  handler consumes from the bus)
- Exported functions:
  - `start_scheduler()` / `stop_scheduler()` — called by startup orchestration
  - `schedule_reminder(reminder_text: str, run_at: datetime) -> str` — returns job_id
  - `register_notification_handlers()` — subscribe handler to EventBus at startup

## Dependencies

- `apscheduler` — async job scheduler with SQLAlchemy job store
- `sqlalchemy` — required by APScheduler's SQLAlchemy job store
- `winotify` — Windows 10/11 toast notification library
- `firebase-admin` — Firebase Admin SDK for FCM v1 push
- `loguru` — structured logging
- `src.core.events` — EventBus
- `src.persona.busy_detector` — availability gating before delivery
- `src.shared.config` — `get_settings()` for device token and data path
- `src.shared.types` — `EventType`, `AetherEvent`
