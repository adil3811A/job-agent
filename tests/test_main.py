import pytest

import main


def job(link, score=None):
    return {"title": "Flutter Dev", "link": link, "score": score}


@pytest.fixture
def world(monkeypatch):
    """Fake every outside dependency of main.run() and record what happens."""
    state = {"jobs": [], "existing": set(), "saved": [], "alerted": [], "marked": 0,
             "save_error": None, "notify_error": None, "mark_error": None}

    class Source:
        __name__ = "fake"

        def fetch_jobs(self, profile):
            return state["jobs"]

    def add_jobs(jobs):
        if state["save_error"]:
            raise state["save_error"]
        state["saved"].extend(jobs)
        return jobs

    def notify_jobs(jobs):
        if state["notify_error"]:
            raise state["notify_error"]
        state["alerted"].extend(jobs)

    def mark_processed():
        if state["mark_error"]:
            raise state["mark_error"]
        state["marked"] += 1
        return 1

    monkeypatch.setattr(main, "SOURCES", [Source()])
    monkeypatch.setattr(main, "load_profile", lambda: {"min_score": 7})
    monkeypatch.setattr(main, "get_existing_links", lambda: state["existing"])
    monkeypatch.setattr(main, "add_jobs", add_jobs)
    monkeypatch.setattr(main, "notify_jobs", notify_jobs)
    monkeypatch.setattr(main.gmail_alerts, "mark_processed", mark_processed)
    monkeypatch.setattr(main, "score_jobs", lambda jobs, profile: state["scored"].extend(jobs))
    state["scored"] = []
    return state


def test_dedupe_against_sheet_and_batch():
    jobs = [job("https://a/1"), job("https://A/1/"), job("https://a/2"), job("https://a/3")]
    assert [j["link"] for j in main.dedupe(jobs, {"https://a/2"})] == ["https://a/1", "https://a/3"]


def test_should_alert():
    assert main.should_alert(job("x", None), 7)
    assert main.should_alert(job("x", 7), 7)
    assert not main.should_alert(job("x", 6), 7)


def test_run_saves_alerts_and_marks_read(world, caplog):
    caplog.set_level("INFO")
    world["jobs"] = [job("https://a/1"), job("https://a/1"), job("https://a/2", 9),
                     job("https://a/3", 3), job("https://old/1")]
    world["existing"] = {"https://old/1"}
    assert main.run() == 0
    assert [j["link"] for j in world["saved"]] == ["https://a/1", "https://a/2", "https://a/3"]
    assert [j["link"] for j in world["alerted"]] == ["https://a/1", "https://a/2"]  # 3 scored low
    assert world["marked"] == 1
    assert "Fetched 5, new 3, alerted 2" in caplog.text
    # only new, deduped jobs are sent to the scorer
    assert [j["link"] for j in world["scored"]] == ["https://a/1", "https://a/2", "https://a/3"]


def test_sheet_failure_stops_before_alerts_and_mark_read(world):
    world["jobs"] = [job("https://a/1")]
    world["save_error"] = RuntimeError("quota")
    assert main.run() == 1
    assert world["alerted"] == [] and world["marked"] == 0


def test_telegram_failure_still_marks_read(world):
    world["jobs"] = [job("https://a/1")]
    world["notify_error"] = RuntimeError("telegram down")
    assert main.run() == 1
    assert world["saved"] and world["marked"] == 1


def test_mark_read_failure_is_reported(world):
    world["jobs"] = [job("https://a/1")]
    world["mark_error"] = OSError("imap down")
    assert main.run() == 1
    assert world["alerted"]


def test_main_includes_gmail_and_api_sources():
    names = [s.__name__ for s in main.SOURCES]
    assert names[0] == "sources.gmail_alerts"
    assert {"sources.remotive", "sources.arbeitnow", "sources.remoteok",
            "sources.adzuna", "sources.jooble"} <= set(names)
