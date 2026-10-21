"""The worker process (SERVICE_ROLE=worker): runs the pipeline on a schedule. Times are UK time.

Schedules are rebuilt from this file on every start, and the two intervals Admin can change (checking Drive and
checking Gmail) are re-read every minute, so a change takes effect without a restart. A restart loses nothing: every run picks up where the database
says it is, and outputs are keyed so a repeated step updates rather than duplicates.
"""

import logging

from apscheduler.schedulers.base import BaseScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from bide_followup import runtime_settings
from bide_followup.config import settings
from bide_followup.db import SessionLocal
from bide_followup.integrations import google_oauth
from bide_followup.pipeline import notices, outputs, run

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger(__name__)


def poll() -> None:
    with SessionLocal() as session:
        run.run(session)


def sync_gmail() -> None:
    with SessionLocal() as session:
        try:
            closed = outputs.sync_gmail(session)
        except google_oauth.GoogleAuthError:
            return  # the next poll reports the connection problem
        if closed:
            log.info("%s email drafts were sent or deleted in Gmail", closed)


def notify() -> None:
    with SessionLocal() as session:
        notices.send_due(session)


def purge() -> None:
    with SessionLocal() as session:
        log.info("purged stored note text from %s meetings", run.purge_raw_text(session))


# Job id → the setting that holds its interval in minutes.
INTERVALS = {"poll": "poll_interval_minutes", "sync_gmail": "gmail_sync_minutes"}


def intervals() -> dict[str, int]:
    with SessionLocal() as session:
        return {job: int(runtime_settings.get(session, key)) for job, key in INTERVALS.items()}


def follow_settings(scheduler: BaseScheduler, current: dict[str, int]) -> None:
    """Reschedule a job whose interval Admin changed. `current` holds the intervals the jobs run on."""
    for job, minutes in intervals().items():
        if current.get(job) != minutes:
            scheduler.reschedule_job(job, trigger=IntervalTrigger(minutes=minutes))
            current[job] = minutes
            log.info("%s now runs every %s minutes", job, minutes)


def main() -> None:
    current = intervals()
    scheduler = BlockingScheduler(timezone=settings.timezone)
    jobs = {
        "poll": (poll, IntervalTrigger(minutes=current["poll"])),
        "sync_gmail": (sync_gmail, IntervalTrigger(minutes=current["sync_gmail"])),
        "purge": (purge, CronTrigger(hour=3, minute=0)),
        # Reminders and the weekly digest: sent once per period, so checking often costs nothing.
        "notify": (notify, IntervalTrigger(minutes=10)),
    }
    for name, (job, trigger) in jobs.items():
        scheduler.add_job(job, trigger, id=name, max_instances=1, coalesce=True, misfire_grace_time=600)
    scheduler.add_job(follow_settings, IntervalTrigger(minutes=1), args=(scheduler, current), id="settings")
    log.info("worker started: polling every %s minutes", current["poll"])
    scheduler.start()


if __name__ == "__main__":
    main()
