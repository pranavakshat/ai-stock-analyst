"""
scheduler.py — APScheduler jobs.

Two daily jobs:
  • 5:00 AM  — Query all models → save predictions → send email digest
  • 6:00 PM  — Fetch EOD prices → score accuracy → update portfolios

The scheduler is started by app.py when the Flask server boots.
It can also be run standalone: `python scheduler.py`
"""

import logging
from datetime import date

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config import MORNING_HOUR, MORNING_MINUTE, EVENING_HOUR, EVENING_MINUTE, TIMEZONE

logger = logging.getLogger(__name__)


# ── Job functions ─────────────────────────────────────────────────────────────

def morning_job():
    """5 AM: Query all 5 models and send the email digest."""
    from models.runner import run_all_models
    from email_service.emailer import send_daily_digest

    today_str  = date.today().isoformat()
    today_fmt  = date.today().strftime("%A, %B %d, %Y")

    logger.info("=== Morning job started for %s ===", today_str)
    try:
        all_picks = run_all_models(today_str)
        send_daily_digest(all_picks, today_fmt)
        logger.info("=== Morning job complete ===")
    except Exception as exc:
        logger.error("Morning job failed: %s", exc, exc_info=True)


def evening_job():
    """6 PM: Fetch EOD prices, score predictions, update portfolios."""
    from accuracy.tracker import run_evening_tasks

    today_str = date.today().isoformat()
    logger.info("=== Evening job started for %s ===", today_str)
    try:
        run_evening_tasks(today_str)
        logger.info("=== Evening job complete ===")
    except Exception as exc:
        logger.error("Evening job failed: %s", exc, exc_info=True)


# ── Scheduler factory ─────────────────────────────────────────────────────────

def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=TIMEZONE)

    scheduler.add_job(
        morning_job,
        trigger=CronTrigger(
            hour=MORNING_HOUR,
            minute=MORNING_MINUTE,
            timezone=TIMEZONE,
        ),
        id="morning_job",
        name="Query models & send email",
        replace_existing=True,
        misfire_grace_time=300,   # fire up to 5 min late if server was down
    )

    scheduler.add_job(
        evening_job,
        trigger=CronTrigger(
            hour=EVENING_HOUR,
            minute=EVENING_MINUTE,
            timezone=TIMEZONE,
        ),
        id="evening_job",
        name="Fetch EOD prices & score accuracy",
        replace_existing=True,
        misfire_grace_time=600,
    )

    return scheduler


# ── Standalone entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    import time
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    from database.db import init_db
    init_db()

    scheduler = create_scheduler()
    scheduler.start()

    logger.info(
        "Scheduler running. Next morning job: %s | Next evening job: %s",
        scheduler.get_job("morning_job").next_run_time,
        scheduler.get_job("evening_job").next_run_time,
    )

    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("Scheduler stopped.")
