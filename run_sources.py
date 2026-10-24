"""Fetch jobs from the free API sources, save new ones to the sheet, notify on Telegram.

API-only runner (handy for debugging); main.py runs everything including Gmail.
"""
import logging

from notify import notify_jobs
from sheet import add_jobs
from sources import adzuna, arbeitnow, jooble, load_profile, remoteok, remotive

log = logging.getLogger("run_sources")

SOURCES = [remotive, arbeitnow, remoteok, adzuna, jooble]


def collect_jobs(profile, sources=None):
    """Run each source; a source that crashes is logged and skipped."""
    jobs = []
    for source in sources if sources is not None else SOURCES:
        try:
            found = source.fetch_jobs(profile)
        except Exception:  # one broken source shouldn't stop the others
            log.exception("%s failed", source.__name__)
            continue
        log.info("%s: %d matching jobs", source.__name__, len(found))
        jobs.extend(found)
    return jobs


def main():
    jobs = collect_jobs(load_profile())
    new = add_jobs(jobs)
    notify_jobs(new)
    log.info("Fetched %d, new %d, alerted %d", len(jobs), len(new), len(new))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    main()
