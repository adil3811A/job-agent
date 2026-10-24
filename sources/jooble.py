"""Jooble: https://jooble.org/api/about (needs JOOBLE_KEY). One POST per role."""
import logging
import os

from filters import matches_profile
from sources import clean_html, load_profile, make_job, post_json

log = logging.getLogger(__name__)

URL = "https://jooble.org/api/{key}"


def fetch_jobs(profile=None):
    key = os.environ.get("JOOBLE_KEY")
    if not key:
        log.info("Jooble skipped: JOOBLE_KEY not set")
        return []
    profile = profile if profile is not None else load_profile()

    jobs, seen = [], set()
    for role in profile.get("roles", []):
        data = post_json(URL.format(key=key), {"keywords": role, "location": "India"})
        if not isinstance(data, dict):
            continue
        for j in data.get("jobs", []):
            if not j.get("link") or j.get("id") in seen:
                continue
            seen.add(j.get("id"))
            jobs.append(make_job("jooble", clean_html(j.get("title")), j.get("company"),
                                 j.get("location"), j["link"], j.get("snippet")))
    return [j for j in jobs if matches_profile(j, profile)]
