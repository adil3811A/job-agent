from filters import matches_profile

PROFILE = {
    "roles": ["Android Developer", "Flutter"],
    "keywords": ["kotlin"],
    "exclude_keywords": ["Senior", "Lead"],
    "locations": ["India", "Bangalore"],
    "remote": True,
}


def job(title, location="", description=""):
    return {"title": title, "location": location, "description": description}


def test_role_needs_every_word_in_title():
    assert matches_profile(job("Android App Developer"), PROFILE)
    assert not matches_profile(job("Android QA Tester"), PROFILE)


def test_keyword_matches_title_only():
    assert matches_profile(job("Kotlin Engineer"), PROFILE)
    assert not matches_profile(job("Backend Engineer", description="We use Kotlin"), PROFILE)


def test_whole_words_only():
    profile = {"roles": [], "keywords": ["Bloc"], "exclude_keywords": ["Staff", "Lead"]}
    assert not matches_profile(job("Blockchain Engineer"), profile)
    assert matches_profile(job("Flutter Bloc Developer"), profile)
    assert matches_profile(job("Bloc Developer, Staffing Partner"), profile)
    assert not matches_profile(job("Staff Bloc Engineer"), profile)


def test_role_allows_plural():
    assert matches_profile(job("Android Developers wanted"), PROFILE)


def test_real_profile_rejects_noise():
    import json
    profile = json.load(open("profile.json"))
    for title in ["Executive Recruiting Director", "Blockchain Engineer", "Backend Engineer",
                  "People Operations Coordinator", "Senior Flutter Developer"]:
        assert not matches_profile(job(title, "Remote"), profile), title
    assert matches_profile(job("Flutter Developer", "Pune, Maharashtra"), profile)


def test_exclude_keywords_reject_by_title():
    assert not matches_profile(job("Senior Flutter Developer"), PROFILE)
    assert matches_profile(job("Flutter Developer", description="report to the lead"), PROFILE)


def test_location():
    assert matches_profile(job("Flutter Dev", "Bangalore, Karnataka"), PROFILE)
    assert matches_profile(job("Flutter Dev", ""), PROFILE)
    assert not matches_profile(job("Flutter Dev", "Berlin"), PROFILE)


def test_remote_location_depends_on_profile_remote():
    assert matches_profile(job("Flutter Dev", "Worldwide"), PROFILE)
    assert not matches_profile(job("Flutter Dev", "Remote (US)"), {**PROFILE, "remote": False})


def test_case_insensitive():
    assert matches_profile(job("FLUTTER ENGINEER", "INDIA"), PROFILE)


def test_empty_profile_accepts_everything():
    assert matches_profile(job("Anything", "Anywhere"), {})
    assert matches_profile({"title": None}, {"roles": [], "keywords": []})
