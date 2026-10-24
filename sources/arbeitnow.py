"""Arbeitnow job board: https://www.arbeitnow.com/api/job-board-api"""
from filters import matches_profile
from sources import get_json, load_profile, make_job

URL = "https://www.arbeitnow.com/api/job-board-api"
MAX_PAGES = 3


def fetch_jobs(profile=None):
    profile = profile if profile is not None else load_profile()
    jobs = []
    for page in range(1, MAX_PAGES + 1):
        data = get_json(URL, page=page)
        if not isinstance(data, dict) or not data.get("data"):
            break
        for j in data["data"]:
            if not j.get("url"):
                continue
            location = j.get("location") or ""
            if j.get("remote") and "remote" not in location.lower():
                location = f"{location} (Remote)" if location else "Remote"
            jobs.append(make_job("arbeitnow", j.get("title"), j.get("company_name"),
                                 location, j["url"], j.get("description")))
        if not (data.get("links") or {}).get("next"):
            break
    return [j for j in jobs if matches_profile(j, profile)]
