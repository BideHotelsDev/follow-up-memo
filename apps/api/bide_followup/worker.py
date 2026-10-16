"""The worker process (SERVICE_ROLE=worker): runs the pipeline on a schedule. Times are UK time.

Schedules are rebuilt from this file on every start. A restart loses nothing: every run picks up where the database
says it is, and outputs are keyed so a repeated step updates rather than duplicates.
"""

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from bide_followup import runtime_settings
from bide_followup.config import settings
from bide_followup.db import SessionLocal
from bide_followup.pipeline import run

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger(__name__)


def poll() -> None:
    with SessionLocal() as session:
        run.run(session)


def purge() -> None:
    with SessionLocal() as session:
        log.info("purged stored note text from %s meetings", run.purge_raw_text(session))


def main() -> None:
    with SessionLocal() as session:
        minutes = int(runtime_settings.get(session, "poll_interval_minutes"))
    scheduler = BlockingScheduler(timezone=settings.timezone)
    jobs = {"poll": (poll, IntervalTrigger(minutes=minutes)), "purge": (purge, CronTrigger(hour=3, minute=0))}
    for name, (job, trigger) in jobs.items():
        scheduler.add_job(job, trigger, id=name, max_instances=1, coalesce=True, misfire_grace_time=600)
    log.info("worker started: polling every %s minutes", minutes)
    scheduler.start()


if __name__ == "__main__":
    main()
