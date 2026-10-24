import json

import pytest
from google.genai import errors

import scorer

PROFILE = {"roles": ["Flutter Developer"], "skills": ["Flutter", "Dart"], "experience_years": 1,
           "locations": ["Pune"], "remote": True}


def job(title="Flutter Developer", link="https://a/1", description="x"):
    return {"title": title, "company": "Acme", "location": "Pune", "link": link,
            "description": description, "score": None, "reason": ""}


def api_error(code):
    return errors.APIError(code, {"error": {"code": code, "message": "m", "status": "s"}})


class FakeClient:
    """Plays back a list of responses: dicts (returned as JSON), strings, or exceptions."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []
        self.models = self

    def generate_content(self, model, contents, config):
        self.prompts.append(contents)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item

        class Resp:
            text = item if isinstance(item, str) else json.dumps(item)
        return Resp()


GOOD = {"score": 8, "reason": "Good fit.", "missing_skills": ["Riverpod"]}


def test_score_job_parses_result():
    assert scorer.score_job(job(), PROFILE, FakeClient([GOOD])) == GOOD


def test_score_is_clamped_to_1_10():
    result = scorer.score_job(job(), PROFILE, FakeClient([{**GOOD, "score": 42}]))
    assert result["score"] == 10


def test_prompt_uses_profile_and_trims_description():
    client = FakeClient([GOOD])
    scorer.score_job(job(description="d" * 5000), PROFILE, client)
    prompt = client.prompts[0]
    assert "Flutter, Dart" in prompt and "Years of experience: 1" in prompt
    assert "d" * scorer.DESCRIPTION_LIMIT in prompt
    assert "d" * (scorer.DESCRIPTION_LIMIT + 1) not in prompt


def test_retries_429_with_backoff():
    waits = []
    client = FakeClient([api_error(429), api_error(503), GOOD])
    assert scorer.score_job(job(), PROFILE, client, sleep=waits.append) == GOOD
    assert waits == [10, 20]


def test_quota_exhausted_after_all_retries():
    client = FakeClient([api_error(429)] * 4)
    with pytest.raises(scorer.QuotaExhausted):
        scorer.score_job(job(), PROFILE, client, sleep=lambda s: None)


@pytest.mark.parametrize("response", [api_error(400), "not json", {"reason": "no score"},
                                      TimeoutError("read timed out")])
def test_other_failures_return_none(response):
    assert scorer.score_job(job(), PROFILE, FakeClient([response])) is None


def test_score_jobs_fills_in_place_and_delays(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    waits = []
    jobs = [job(link="1"), job(link="2"), job(link="3")]
    client = FakeClient([GOOD, api_error(400), {**GOOD, "missing_skills": []}])
    scorer.score_jobs(jobs, PROFILE, client, sleep=waits.append)
    assert jobs[0]["score"] == 8 and jobs[0]["reason"] == "Good fit. Missing: Riverpod."
    assert jobs[1]["score"] is None  # failed, still kept
    assert jobs[2]["reason"] == "Good fit."
    assert waits == [scorer.DELAY_SECONDS] * 2


def test_score_jobs_stops_when_quota_exhausted(monkeypatch):
    jobs = [job(link="1"), job(link="2"), job(link="3")]
    client = FakeClient([GOOD] + [api_error(429)] * 4)
    scorer.score_jobs(jobs, PROFILE, client, sleep=lambda s: None)
    assert [j["score"] for j in jobs] == [8, None, None]
    assert client.responses == []  # job 3 never sent


def test_score_jobs_skips_jobs_not_matching_profile():
    client = FakeClient([GOOD])
    jobs = [job(title="Sales Executive", link="1"), job(link="2")]
    scorer.score_jobs(jobs, PROFILE, client, sleep=lambda s: None)
    assert [j["score"] for j in jobs] == [None, 8]
    assert len(client.prompts) == 1


def test_score_jobs_without_key_does_nothing(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    jobs = [job()]
    assert scorer.score_jobs(jobs, PROFILE) == jobs
    assert jobs[0]["score"] is None
