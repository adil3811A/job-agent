"""Adzuna India: https://developer.adzuna.com (needs ADZUNA_APP_ID and ADZUNA_APP_KEY).

Free plan limits are about 250 calls a day and 2500 a month, so like Remotive we
only call it on runs whose UTC hour is divisible by 6, with one query per role.
"""
import logging
import os

from filters import matches_profile
from sources import clean_html, get_json, load_profile, make_job, runs_now

log = logging.getLogger(__name__)

URL = "https://api.adzuna.com/v1/api/jobs/in/search/1"
RUN_EVERY_HOURS = 6
RESULTS_PER_PAGE = 50


def fetch_jobs(profile=None, now=None):
    app_id, app_key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        log.info("Adzuna skipped: ADZUNA_APP_ID / ADZUNA_APP_KEY not set")
        return []
    if not runs_now(RUN_EVERY_HOURS, now):
        log.info("Adzuna skipped (only runs at UTC hours divisible by %d)", RUN_EVERY_HOURS)
        return []
    profile = profile if profile is not None else load_profile()

    jobs, seen = [], set()
    for role in profile.get("roles", []):
        data = get_json(URL, app_id=app_id, app_key=app_key, what=role,
                        results_per_page=RESULTS_PER_PAGE, sort_by="date")
        if not isinstance(data, dict):
            continue
        for j in data.get("results", []):
            if not j.get("redirect_url") or j.get("id") in seen:
                continue
            seen.add(j.get("id"))
            jobs.append(make_job(
                "adzuna", clean_html(j.get("title")),
                (j.get("company") or {}).get("display_name"),
                (j.get("location") or {}).get("display_name"),
                # Drop tracking params so the same job keeps the same link across runs.
                j["redirect_url"].split("?")[0],
                j.get("description"),
            ))
    return [j for j in jobs if matches_profile(j, profile)]
