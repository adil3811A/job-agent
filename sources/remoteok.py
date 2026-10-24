"""RemoteOK: https://remoteok.com/api (first element is a legal notice, not a job)."""
from filters import matches_profile
from sources import get_json, load_profile, make_job

URL = "https://remoteok.com/api"


def fetch_jobs(profile=None):
    profile = profile if profile is not None else load_profile()
    data = get_json(URL)
    if not isinstance(data, list):
        return []
    jobs = [make_job("remoteok", j.get("position"), j.get("company"),
                     j.get("location") or "Remote", j["url"], j.get("description"))
            for j in data
            if isinstance(j, dict) and j.get("url") and j.get("position")]
    return [j for j in jobs if matches_profile(j, profile)]
