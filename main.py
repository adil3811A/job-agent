"""Job agent: Gmail alerts + free APIs -> dedupe -> score -> Google Sheet -> Telegram.

Order matters:
  1. fetch from every source (each already filtered with matches_profile)
  2. dedupe within the batch and against links already in the Sheet
  3. score only the new jobs with Gemini (saves quota)
  4. save to the Sheet; if that fails, stop: no alerts, no emails marked read
  5. alert on Telegram for score >= min_score, or score None (scoring failed/off)
  6. mark the processed Gmail alerts as read
"""
import logging
import sys

from notify import notify_jobs
from run_sources import SOURCES as API_SOURCES, collect_jobs
from scorer import score_jobs
from sheet import add_jobs, get_existing_links, normalize_link
from sources import gmail_alerts, load_profile

log = logging.getLogger("main")

SOURCES = [gmail_alerts, *API_SOURCES]


def dedupe(jobs, existing_links):
    """Drop jobs whose link is already in the Sheet or earlier in this batch."""
    seen, unique = set(existing_links), []
    for job in jobs:
        key = normalize_link(job["link"])
        if key not in seen:
            seen.add(key)
            unique.append(job)
    return unique


def should_alert(job, min_score):
    return job.get("score") is None or job["score"] >= min_score


def run():
    """Run once. Returns the process exit code (0 ok, 1 if anything failed)."""
    profile = load_profile()
    jobs = collect_jobs(profile, SOURCES)

    try:
        new = dedupe(jobs, get_existing_links())
    except Exception:
        log.exception("Reading the Sheet failed; no alerts sent, emails left unread")
        return 1

    score_jobs(new, profile)  # never raises for API errors; failed jobs keep score None
    log.info("Scored %d of %d new jobs", sum(j["score"] is not None for j in new), len(new))

    try:
        new = add_jobs(new)
    except Exception:
        log.exception("Saving to the Sheet failed; no alerts sent, emails left unread")
        return 1

    exit_code = 0
    to_alert = [j for j in new if should_alert(j, profile.get("min_score", 7))]
    try:
        notify_jobs(to_alert)
    except Exception:
        log.exception("Telegram alert failed (jobs are saved in the Sheet)")
        to_alert, exit_code = [], 1

    try:
        marked = gmail_alerts.mark_processed()
        log.info("Marked %d Gmail alerts as read", marked)
    except Exception:
        # Not fatal: next run re-reads them and dedupe drops the jobs again.
        log.exception("Marking Gmail alerts as read failed")
        exit_code = 1

    log.info("Fetched %d, new %d, alerted %d", len(jobs), len(new), len(to_alert))
    return exit_code


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    sys.exit(run())
