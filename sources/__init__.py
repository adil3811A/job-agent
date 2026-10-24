"""Free job API sources. Each module exposes fetch_jobs(profile=None) returning
a list of job dicts (see make_job) already filtered with matches_profile.
"""
import html
import json
import logging
import re
from datetime import date, datetime, timezone

import requests

log = logging.getLogger(__name__)

TIMEOUT = 15
HEADERS = {"User-Agent": "Mozilla/5.0 (job-notifier)"}
DESCRIPTION_LIMIT = 2000


def load_profile(path="profile.json"):
    with open(path) as f:
        return json.load(f)


def make_job(source, title, company, location, link, description=""):
    """Build a job dict in the shared format (score/reason are filled by the scorer)."""
    return {
        "date": date.today().isoformat(),
        "source": source,
        "title": (title or "").strip(),
        "company": (company or "").strip(),
        "location": (location or "").strip(),
        "link": link.strip(),
        "description": clean_html(description),
        "score": None,
        "reason": "",
    }


def clean_html(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return text[:DESCRIPTION_LIMIT]


def runs_now(every_hours, now=None):
    """True on runs whose UTC hour is divisible by every_hours (rate-limited APIs)."""
    now = now or datetime.now(timezone.utc)
    return now.hour % every_hours == 0


def get_json(url, **params):
    """GET a JSON API; return None (and log why) on any network/parse error."""
    try:
        resp = requests.get(url, params=params or None, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError) as e:
        log.warning("Request to %s failed: %s", _hide_keys(url), e)
        return None


def post_json(url, payload):
    """POST JSON to an API; return None (and log why) on any network/parse error."""
    try:
        resp = requests.post(url, json=payload, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError) as e:
        log.warning("Request to %s failed: %s", _hide_keys(url), e)
        return None


def _hide_keys(url):
    # Jooble puts the API key in the URL path; don't write it to logs.
    return re.sub(r"(jooble\.org/api/)[^/?]+", r"\1***", url)
