"""
scheduler.py — APScheduler jobs.

Two daily jobs:
  • 8:00 AM CT — Morning: score overnight picks → query models (day) → send morning email
  • 6:00 PM CT — Evening: score day picks → query models (overnight) → send evening email

The scheduler is started by app.py when the Flask server boots.
It can also be run standalone: `python scheduler.py`
"""

import logging
from datetime import date, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config import MORNING_HOUR, MORNING_MINUTE, EVENING_HOUR, EVENING_MINUTE, TIMEZONE

logger = logging.getLogger(__name__)


def _prev_trading_date(today: date) -> str:
    """Return the most recent weekday before today (handles weekends)."""
    d = today - timedelta(days=1)
    while d.weekday() >= 5:   # 5=Sat, 6=Sun
        d -= timedelta(days=1)
    return d.isoformat()


# ── Morning job ───────────────────────────────────────────────────────────────

def morning_job():
    """
    8 AM CT:
      1. Score previous evening's overnight picks (close → today's open)
      2. Query all models for DAY session picks
      3. Send morning email with day picks
      4. Auto-backup all predictions
    """
    from models.runner import run_all_models
    from email_service.emailer import send_daily_digest
    from accuracy.tracker import score_overnight_picks, update_overnight_portfolios
    from database.db import backup_all_to_csv

    today      = date.today()
    today_str  = today.isoformat()
    today_fmt  = today.strftime("%A, %B %d, %Y")
    prev_str   = _prev_trading_date(today)

    logger.info("=== Morning job started for %s ===", today_str)
    try:
        # 1. Score previous evening's overnight picks + update overnight portfolio
        try:
            logger.info("Scoring overnight picks from %s...", prev_str)
            score_overnight_picks(pick_date=prev_str, next_open_date=today_str)
            update_overnight_portfolios(pick_date=prev_str, next_open_date=today_str)
        except Exception as exc:
            logger.warning("Overnight scoring/portfolio failed (non-fatal): %s", exc)

        # 2. Run DAY session models
        day_picks = run_all_models(today_str, session="day")

        # 3. Send morning email
        send_daily_digest(day_picks, today_fmt, session="day")

        # 4. Auto-backup
        try:
            paths = backup_all_to_csv()
            logger.info("Auto-backup written: %s", list(paths.values()))
        except Exception as bex:
            logger.warning("Auto-backup failed (non-fatal): %s", bex)

        # 5. Auto-commit + push backups/ so Railway redeploys can restore.
        #    No-op unless BACKUP_GIT_PUSH=1 and GH_TOKEN are set.
        try:
            from git_backup import git_autocommit_backups
            git_autocommit_backups(label="morning")
        except Exception as gex:
            logger.warning("git_autocommit_backups failed (non-fatal): %s", gex)

        logger.info("=== Morning job complete ===")
    except Exception as exc:
        logger.error("Morning job failed: %s", exc, exc_info=True)


# ── Evening job ───────────────────────────────────────────────────────────────

def evening_job():
    """
    6 PM CT:
      1. Fetch EOD prices for today
      2. Score today's DAY session picks (open → close)
      3. Query all models for OVERNIGHT session picks
      4. Send evening email with overnight picks
      5. Auto-backup
    """
    from accuracy.tracker import run_evening_tasks
    from models.runner import run_all_models
    from email_service.emailer import send_daily_digest
    from database.db import backup_all_to_csv

    today_str = date.today().isoformat()
    today_fmt = date.today().strftime("%A, %B %d, %Y")

    logger.info("=== Evening job started for %s ===", today_str)
    try:
        # 1 & 2. Fetch EOD + score day picks + update day portfolios
        run_evening_tasks(today_str, session="day")

        # 3. Run OVERNIGHT session models
        overnight_picks = run_all_models(today_str, session="overnight")

        # 4. Send evening email
        send_daily_digest(overnight_picks, today_fmt, session="overnight")

        # 5. Auto-backup
        try:
            paths = backup_all_to_csv()
            logger.info("Auto-backup written: %s", list(paths.values()))
        except Exception as bex:
            logger.warning("Auto-backup failed (non-fatal): %s", bex)

        # 6. Auto-commit + push backups/ (see morning_job for context).
        try:
            from git_backup import git_autocommit_backups
            git_autocommit_backups(label="evening")
        except Exception as gex:
            logger.warning("git_autocommit_backups failed (non-fatal): %s", gex)

        logger.info("=== Evening job complete ===")
    except Exception as exc:
        logger.error("Evening job failed: %s", exc, exc_info=True)


# ── Scheduler factory ─────────────────────────────────────────────────────────

def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=TIMEZONE)

    scheduler.add_job(
        morning_job,
        trigger=CronTrigger(hour=MORNING_HOUR, minute=MORNING_MINUTE, timezone=TIMEZONE),
        id="morning_job",
        name="Score overnight + query day models + send morning email",
        replace_existing=True,
        misfire_grace_time=300,
    )

    scheduler.add_job(
        evening_job,
        trigger=CronTrigger(hour=EVENING_HOUR, minute=EVENING_MINUTE, timezone=TIMEZONE),
        id="evening_job",
        name="Score day picks + query overnight models + send evening email",
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
