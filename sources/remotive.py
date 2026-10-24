"""Remotive remote jobs: https://remotive.com/api/remote-jobs

Remotive asks for at most 4 calls a day, so we only call it when the UTC hour
is divisible by 6 (00, 06, 12, 18); the 2-hourly runs in between skip it.
"""
import logging

from filters import matches_profile
from sources import get_json, load_profile, make_job, runs_now

log = logging.getLogger(__name__)

URL = "https://remotive.com/api/remote-jobs"
RUN_EVERY_HOURS = 6


def fetch_jobs(profile=None, now=None):
    if not runs_now(RUN_EVERY_HOURS, now):
        log.info("Remotive skipped (only runs at UTC hours divisible by %d)", RUN_EVERY_HOURS)
        return []
    profile = profile if profile is not None else load_profile()
    data = get_json(URL)
    if not isinstance(data, dict):
        return []
    jobs = [make_job("remotive", j.get("title"), j.get("company_name"),
                     j.get("candidate_required_location"), j["url"], j.get("description"))
            for j in data.get("jobs", []) if j.get("url")]
    return [j for j in jobs if matches_profile(j, profile)]
