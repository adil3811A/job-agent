"""Shared job filter: does a job fit the roles/keywords/location in profile.json?"""
import re

REMOTE_WORDS = ("remote", "worldwide", "anywhere")


def _has_phrase(text, phrase):
    """Whole-word match (an optional plural "s" is allowed): "bloc" won't match "blockchain"."""
    pattern = r"(?<!\w)" + re.escape(phrase.lower()) + r"s?(?!\w)"
    return re.search(pattern, text) is not None


def _has_all_words(text, phrase):
    return all(_has_phrase(text, word) for word in phrase.split())


def matches_profile(job, profile):
    """True if the job passes the profile's exclude, role/keyword and location checks.

    - Any exclude_keywords word in the title rejects the job.
    - Otherwise it must match a role (every word of the role in the title) or a
      keyword (in the title). Empty roles and keywords accept all.
      The description is left to the scorer: generic skills like "AWS" appear in
      almost every tech job description.
    - All matching is case-insensitive and whole-word.
    - Location passes if the job's location is empty, contains one of the
      profile locations, or (when profile remote is true) looks remote.
      Empty profile locations accept all.
    """
    title = (job.get("title") or "").lower()
    location = (job.get("location") or "").lower()

    if any(_has_phrase(title, word) for word in profile.get("exclude_keywords", [])):
        return False

    roles = profile.get("roles", [])
    keywords = profile.get("keywords", [])
    if roles or keywords:
        role_hit = any(_has_all_words(title, role) for role in roles)
        keyword_hit = any(_has_phrase(title, word) for word in keywords)
        if not (role_hit or keyword_hit):
            return False

    locations = profile.get("locations", [])
    if not locations or not location:
        return True
    if any(_has_phrase(location, place) for place in locations):
        return True
    return bool(profile.get("remote")) and any(_has_phrase(location, w) for w in REMOTE_WORDS)
