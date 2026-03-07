"""APScheduler with SQLAlchemy job store — survives restarts, fires reliably."""

import uuid
from datetime import datetime
from pathlib import Path

from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from src.core.events import event_bus
from src.shared.config import get_settings
from src.shared.types import EventType, AetherEvent

_scheduler: AsyncIOScheduler | None = None


def _get_jobs_db() -> str:
    """Resolve scheduler jobs DB path from config. Lazy to avoid import-time issues."""
    return str(Path(get_settings().aether_data_path) / "scheduler_jobs.db")


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        jobs_db = _get_jobs_db()
        Path(jobs_db).parent.mkdir(parents=True, exist_ok=True)
        # Use forward slashes for SQLAlchemy URL even on Windows
        jobs_db_posix = Path(jobs_db).as_posix()
        jobstores = {"default": SQLAlchemyJobStore(url=f"sqlite:///{jobs_db_posix}")}
        executors = {"default": AsyncIOExecutor()}
        from src.shared.config import get_yaml_config

        tz = get_yaml_config().get("notifications", {}).get("timezone", "America/Chicago")
        _scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            timezone=tz,
        )
        logger.info(f"Scheduler: initialized (jobs db: {jobs_db})")
    return _scheduler


async def _fire_notification(title: str, message: str, job_id: str):
    """Called by APScheduler when a job fires. Publishes to EventBus."""
    logger.info(f"Scheduler: job fired -- {job_id}: {title}")
    await event_bus.publish(
        AetherEvent(
            type=EventType.NOTIFICATION_REQUEST,
            data={"title": title, "message": message, "job_id": job_id, "source": "scheduler"},
            source_module="scheduler",
        )
    )


async def _daily_briefing():
    await _fire_notification(
        title="Good morning",
        message="Daily briefing triggered -- Brain will generate summary",
        job_id="daily_briefing",
    )


async def _weekly_digest():
    await _fire_notification(
        title="Weekly digest",
        message="Weekly digest triggered",
        job_id="weekly_digest",
    )


def setup_default_jobs():
    """Register default recurring jobs. Idempotent — safe to call every startup.

    Each registration is wrapped individually so one failure doesn't block others.
    """
    scheduler = get_scheduler()

    # Daily briefing — 8:00 AM every day
    try:
        if not scheduler.get_job("daily_briefing"):
            scheduler.add_job(
                _daily_briefing,
                trigger="cron",
                hour=8,
                minute=0,
                id="daily_briefing",
                replace_existing=True,
            )
            logger.info("Scheduler: daily_briefing job registered (8:00 AM daily)")
    except Exception as e:
        logger.error(f"Scheduler: failed to register daily_briefing: {e}")

    # Daily interview — 7:00 PM every day
    try:
        if not scheduler.get_job("daily_interview"):
            from src.persona.daily_interview import start_interview_session

            scheduler.add_job(
                start_interview_session,
                trigger="cron",
                hour=19,
                minute=0,
                id="daily_interview",
                replace_existing=True,
            )
            logger.info("Scheduler: daily_interview job registered (7:00 PM daily)")
    except Exception as e:
        logger.error(f"Scheduler: failed to register daily_interview: {e}")

    # Weekly digest — Monday 9:00 AM
    try:
        if not scheduler.get_job("weekly_digest"):
            scheduler.add_job(
                _weekly_digest,
                trigger="cron",
                day_of_week="mon",
                hour=9,
                minute=0,
                id="weekly_digest",
                replace_existing=True,
            )
            logger.info("Scheduler: weekly_digest job registered (Mon 9:00 AM)")
    except Exception as e:
        logger.error(f"Scheduler: failed to register weekly_digest: {e}")


async def schedule_reminder(reminder_text: str, run_at: datetime) -> str:
    """Schedule a one-time reminder. Returns job_id.

    If run_at is in the past, fires immediately instead of silently dropping.
    """
    scheduler = get_scheduler()
    job_id = f"reminder_{run_at.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    now = datetime.now(tz=run_at.tzinfo)
    if run_at <= now:
        logger.warning(f"Scheduler: reminder time {run_at} is in the past — firing immediately")
        await _fire_notification("Reminder", reminder_text, job_id)
        return job_id

    scheduler.add_job(
        _fire_notification,
        trigger="date",
        run_date=run_at,
        args=["Reminder", reminder_text, job_id],
        id=job_id,
        replace_existing=True,
    )
    logger.info(f"Scheduler: reminder scheduled for {run_at}: '{reminder_text}'")
    return job_id


def start_scheduler():
    scheduler = get_scheduler()
    setup_default_jobs()
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler: started")


def stop_scheduler():
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler: stopped")
