"""Score jobs against profile.json with Gemini (needs GEMINI_API_KEY).

score_job() returns {"score": 1-10, "reason": str, "missing_skills": [str]} or None.
score_jobs() fills job["score"] / job["reason"] in place; a job that can't be
scored keeps score None and is still alerted.
"""
import json
import logging
import os
import time

from google import genai
from google.genai import errors, types

from filters import matches_profile

log = logging.getLogger(__name__)

# flash-lite answers in ~2s; full gemini-3.8-flash took ~2 min per call on the free tier.
DEFAULT_MODEL = "gemini-3.5-flash-lite"
TIMEOUT_MS = 60_000
DESCRIPTION_LIMIT = 1500
DELAY_SECONDS = 4  # between calls, to stay under the free-tier per-minute limit
RETRY_WAITS = (10, 20, 40)  # seconds to wait after each 429 / 503 before retrying
RETRY_CODES = {429, 503}  # rate limited / model overloaded

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "score": {"type": "INTEGER"},
        "reason": {"type": "STRING"},
        "missing_skills": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["score", "reason", "missing_skills"],
}

PROMPT = """You are screening job listings for one candidate. Use ONLY the candidate
profile below; do not assume any skill or experience that isn't listed.

Candidate profile:
- Target roles: {roles}
- Skills: {skills}
- Years of experience: {experience_years}
- Preferred locations: {locations} (open to remote: {remote})

Job:
- Title: {title}
- Company: {company}
- Location: {location}
- Description: {description}

Score how well this job fits the candidate from 1 (no fit) to 10 (perfect fit),
considering role, required skills, seniority vs experience, and location.
Give a one-sentence reason, and list required skills from the job that are
missing from the candidate's skills (empty list if none or unknown)."""


class QuotaExhausted(Exception):
    """Gemini kept returning 429/503 after all retries."""


def _client():
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"],
                        http_options=types.HttpOptions(timeout=TIMEOUT_MS))


def _model():
    return os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL


def build_prompt(job, profile):
    return PROMPT.format(
        roles=", ".join(profile.get("roles", [])) or "not given",
        skills=", ".join(profile.get("skills", [])) or "not given",
        experience_years=profile.get("experience_years", "not given"),
        locations=", ".join(profile.get("locations", [])) or "any",
        remote="yes" if profile.get("remote") else "no",
        title=job.get("title", ""),
        company=job.get("company", ""),
        location=job.get("location", "") or "not given",
        description=(job.get("description") or "not given")[:DESCRIPTION_LIMIT],
    )


def _parse(text):
    data = json.loads(text)
    score = max(1, min(10, int(data["score"])))
    return {"score": score, "reason": str(data.get("reason", "")).strip(),
            "missing_skills": [str(s) for s in data.get("missing_skills", [])]}


def score_job(job, profile, client=None, sleep=time.sleep):
    """Score one job. Returns the result dict, or None if it failed.

    Raises QuotaExhausted if Gemini is still rate limiting after all retries.
    """
    client = client or _client()
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=RESPONSE_SCHEMA,
        # A fit score doesn't need deep thinking; keep calls fast and cheap.
        thinking_config=types.ThinkingConfig(thinking_level="low"),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    for attempt in range(len(RETRY_WAITS) + 1):
        try:
            resp = client.models.generate_content(
                model=_model(), contents=build_prompt(job, profile), config=config)
            return _parse(resp.text)
        except errors.APIError as e:
            if e.code not in RETRY_CODES:
                log.warning("Scoring failed for %s: %s", job.get("link"), e)
                return None
            if attempt == len(RETRY_WAITS):
                raise QuotaExhausted(str(e)) from e
            log.info("Gemini %s, retrying in %ds", e.code, RETRY_WAITS[attempt])
            sleep(RETRY_WAITS[attempt])
        except (ValueError, KeyError, TypeError) as e:  # bad JSON / missing fields
            log.warning("Unreadable score for %s: %s", job.get("link"), e)
            return None
        except Exception as e:  # timeout / network error: keep the job unscored
            log.warning("Scoring failed for %s: %s", job.get("link"), e)
            return None


def score_jobs(jobs, profile, client=None, sleep=time.sleep):
    """Fill score/reason on each job in place. Jobs that fail keep score None."""
    if not jobs:
        return jobs
    if not os.environ.get("GEMINI_API_KEY") and client is None:
        log.info("Scoring skipped: GEMINI_API_KEY not set")
        return jobs
    client = client or _client()

    for i, job in enumerate(jobs):
        if not matches_profile(job, profile):  # sources filter already; don't spend quota
            continue
        if i:
            sleep(DELAY_SECONDS)
        try:
            result = score_job(job, profile, client, sleep)
        except QuotaExhausted as e:
            log.warning("Gemini quota exhausted, %d jobs left unscored: %s", len(jobs) - i, e)
            break
        if result:
            job["score"] = result["score"]
            reason = result["reason"]
            if result["missing_skills"]:
                reason += f" Missing: {', '.join(result['missing_skills'])}."
            job["reason"] = reason
    return jobs
