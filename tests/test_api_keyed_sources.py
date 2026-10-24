from datetime import datetime, timezone

import pytest
import requests

import sources
from sources import adzuna, jooble

PROFILE = {"roles": ["Flutter Developer", "Android Developer"], "locations": ["Pune"],
           "remote": True}
SIX_AM = datetime(2026, 1, 1, 6, tzinfo=timezone.utc)


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv("ADZUNA_APP_ID", "id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "akey")
    monkeypatch.setenv("JOOBLE_KEY", "jkey")


@pytest.fixture
def no_keys(monkeypatch):
    for name in ("ADZUNA_APP_ID", "ADZUNA_APP_KEY", "JOOBLE_KEY"):
        monkeypatch.delenv(name, raising=False)


class Resp:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def adzuna_result(id, title, location="Pune, Maharashtra"):
    return {"id": id, "title": title, "company": {"display_name": "Acme"},
            "location": {"display_name": location}, "description": "<b>Dart</b>",
            "redirect_url": f"https://www.adzuna.in/land/ad/{id}?se=abc&utm_medium=api"}


def test_adzuna(keys, monkeypatch):
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(params)
        assert url == adzuna.URL and timeout
        # Same job returned for both roles: kept once.
        return Resp({"results": [adzuna_result(1, "<strong>Flutter</strong> Developer"),
                                 adzuna_result(2, "Android Developer", "Delhi"),
                                 adzuna_result(3, "Java Developer")]})

    monkeypatch.setattr(sources.requests, "get", fake_get)
    jobs = adzuna.fetch_jobs(PROFILE, now=SIX_AM)
    assert [c["what"] for c in calls] == ["Flutter Developer", "Android Developer"]
    assert calls[0]["app_id"] == "id" and calls[0]["app_key"] == "akey"
    assert len(jobs) == 1  # Delhi fails location, Java fails roles
    assert jobs[0]["title"] == "Flutter Developer"
    assert jobs[0]["link"] == "https://www.adzuna.in/land/ad/1"
    assert jobs[0]["source"] == "adzuna" and jobs[0]["company"] == "Acme"


def test_adzuna_only_every_six_hours(keys, monkeypatch):
    monkeypatch.setattr(sources.requests, "get", lambda *a, **k: pytest.fail("called"))
    assert adzuna.fetch_jobs(PROFILE, now=SIX_AM.replace(hour=8)) == []


def test_jooble(keys, monkeypatch):
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append((url, json))
        assert timeout
        return Resp({"jobs": [
            {"id": 7, "title": "Flutter <b>Developer</b>", "company": "Beta", "location": "Remote",
             "link": "https://jooble.org/desc/7", "snippet": "Riverpod&nbsp;app"},
            {"id": 8, "title": "Sales Executive", "company": "C", "location": "Pune",
             "link": "https://jooble.org/desc/8"},
        ]})

    monkeypatch.setattr(sources.requests, "post", fake_post)
    jobs = jooble.fetch_jobs(PROFILE)
    assert calls[0] == ("https://jooble.org/api/jkey", {"keywords": "Flutter Developer",
                                                         "location": "India"})
    assert len(calls) == 2
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Flutter Developer"
    assert jobs[0]["description"] == "Riverpod app"
    assert jobs[0]["source"] == "jooble"


@pytest.mark.parametrize("fetch", [lambda: adzuna.fetch_jobs(PROFILE, now=SIX_AM),
                                   lambda: jooble.fetch_jobs(PROFILE)])
def test_missing_keys_skip_without_calls(no_keys, monkeypatch, fetch, caplog):
    monkeypatch.setattr(sources.requests, "get", lambda *a, **k: pytest.fail("called"))
    monkeypatch.setattr(sources.requests, "post", lambda *a, **k: pytest.fail("called"))
    caplog.set_level("INFO")
    assert fetch() == []
    assert "not set" in caplog.text


@pytest.mark.parametrize("failure", [requests.Timeout("slow"), requests.HTTPError("403")])
def test_errors_return_empty_and_hide_key(keys, monkeypatch, failure, caplog):
    def boom(*a, **k):
        raise failure

    monkeypatch.setattr(sources.requests, "get", boom)
    monkeypatch.setattr(sources.requests, "post", boom)
    assert adzuna.fetch_jobs(PROFILE, now=SIX_AM) == []
    assert jooble.fetch_jobs(PROFILE) == []
    assert "jkey" not in caplog.text
