from datetime import datetime, timezone

import pytest
import requests

import run_sources
import sources
from sources import arbeitnow, remoteok, remotive

PROFILE = {"roles": ["Flutter", "Android Developer"], "locations": [], "remote": True}
JOB_KEYS = {"date", "source", "title", "company", "location", "link", "description",
            "score", "reason"}
SIX_AM = datetime(2026, 1, 1, 6, tzinfo=timezone.utc)


@pytest.fixture
def api(monkeypatch):
    """Map URL -> JSON payload, a callable(params) -> payload, or an exception to raise."""
    responses = {}
    calls = []

    class Resp:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self.payload

    def fake_get(url, params=None, headers=None, timeout=None):
        assert timeout == sources.TIMEOUT
        calls.append(url)
        payload = responses[url]
        if isinstance(payload, Exception):
            raise payload
        return Resp(payload(params) if callable(payload) else payload)

    monkeypatch.setattr(sources.requests, "get", fake_get)
    responses["calls"] = calls
    return responses


def test_make_job_has_all_keys():
    job = sources.make_job("x", " T ", "C", None, "https://a/1", "<p>Hi &amp; bye</p>")
    assert set(job) == JOB_KEYS
    assert job["title"] == "T" and job["description"] == "Hi & bye"
    assert job["score"] is None and job["reason"] == ""


def test_remotive(api):
    api[remotive.URL] = {"jobs": [
        {"title": "Flutter Dev", "company_name": "A", "candidate_required_location": "Worldwide",
         "url": "https://remotive.com/1", "description": "<p>x</p>"},
        {"title": "Sales Lead", "company_name": "B", "url": "https://remotive.com/2"},
    ]}
    jobs = remotive.fetch_jobs(PROFILE, now=SIX_AM)
    assert len(jobs) == 1
    assert set(jobs[0]) == JOB_KEYS
    assert jobs[0]["source"] == "remotive"
    assert jobs[0]["location"] == "Worldwide"


@pytest.mark.parametrize("hour, called", [(0, True), (6, True), (12, True), (18, True),
                                          (2, False), (8, False), (22, False)])
def test_remotive_runs_four_times_a_day(api, hour, called):
    api[remotive.URL] = {"jobs": []}
    remotive.fetch_jobs(PROFILE, now=SIX_AM.replace(hour=hour))
    assert (remotive.URL in api["calls"]) == called


def test_arbeitnow_paginates(api):
    pages = {
        1: {"data": [{"title": "Android Developer", "company_name": "A", "location": "Berlin",
                      "remote": True, "url": "https://arbeitnow.com/1"}],
            "links": {"next": "page2"}},
        2: {"data": [{"title": "Flutter Lead", "company_name": "B", "location": "",
                      "remote": False, "url": "https://arbeitnow.com/2"},
                     {"title": "Steuerberater", "company_name": "C", "location": "Köln",
                      "remote": False, "url": "https://arbeitnow.com/3"}],
            "links": {"next": None}},
    }
    api[arbeitnow.URL] = lambda params: pages[params["page"]]
    jobs = arbeitnow.fetch_jobs(PROFILE)
    assert [j["link"] for j in jobs] == ["https://arbeitnow.com/1", "https://arbeitnow.com/2"]
    assert jobs[0]["location"] == "Berlin (Remote)"
    assert jobs[1]["source"] == "arbeitnow"


def test_remoteok_skips_legal_notice(api):
    api[remoteok.URL] = [
        {"legal": "terms"},
        {"position": "Flutter Engineer", "company": "A", "location": "",
         "url": "https://remoteok.com/1", "description": "d"},
    ]
    jobs = remoteok.fetch_jobs(PROFILE)
    assert len(jobs) == 1
    assert jobs[0]["location"] == "Remote"
    assert jobs[0]["source"] == "remoteok"


def test_sources_use_profile_filter(api):
    api[remoteok.URL] = [{"position": "Flutter Engineer", "company": "A", "location": "USA",
                          "url": "https://remoteok.com/1"}]
    assert remoteok.fetch_jobs({**PROFILE, "locations": ["India"], "remote": False}) == []


@pytest.mark.parametrize("fetch", [lambda: remotive.fetch_jobs(PROFILE, now=SIX_AM),
                                   lambda: arbeitnow.fetch_jobs(PROFILE),
                                   lambda: remoteok.fetch_jobs(PROFILE)])
@pytest.mark.parametrize("failure", [requests.Timeout("slow"), requests.ConnectionError("down"),
                                     ValueError("bad json")])
def test_errors_return_empty_list(api, fetch, failure):
    for url in (remotive.URL, arbeitnow.URL, remoteok.URL):
        api[url] = failure
    assert fetch() == []


def test_run_sources_adds_and_notifies_new_jobs(monkeypatch):
    job = {"title": "Flutter Dev", "link": "https://x/1"}

    class Broken:
        __name__ = "broken"

        def fetch_jobs(self, profile):
            raise RuntimeError("boom")

    class Good:
        __name__ = "good"

        def fetch_jobs(self, profile):
            return [job]

    notified = []
    monkeypatch.setattr(run_sources, "SOURCES", [Broken(), Good()])
    monkeypatch.setattr(run_sources, "load_profile", lambda: PROFILE)
    monkeypatch.setattr(run_sources, "add_jobs", lambda jobs: jobs)
    monkeypatch.setattr(run_sources, "notify_jobs", notified.extend)
    run_sources.main()
    assert notified == [job]
