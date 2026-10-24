import email
import glob
import os
from email.message import EmailMessage
from email import policy

import pytest

import sources.gmail_alerts as g

SAMPLES = sorted(glob.glob("samples/*.eml"))
PROFILE = {"roles": ["Flutter", "Android Developer"], "locations": [], "remote": True}


# ---------- is_job_email ----------

@pytest.mark.parametrize("sender, subject, expected", [
    ("LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>", "Flutter Developer Intern", "linkedin"),
    ("LinkedIn <jobs-noreply@linkedin.com>", "New jobs similar to X", "linkedin"),
    ("LinkedIn <jobs-noreply@linkedin.com>", "Your application to Dev at Co", None),
    ("LinkedIn <jobs-noreply@linkedin.com>", "Adil, your application was sent to Me100", None),
    ("Quik Hire via LinkedIn <newsletters-noreply@linkedin.com>", "Remote gigs", None),
    ('"Indeed" <donotreply@jobalert.indeed.com>', "Mobile Developer at X", "indeed"),
    ('"Indeed" <donotreply@match.indeed.com>', "fire design engineer", "indeed"),
    ('"Co" <noreply@indeed.com>', "An update on your application from Co", None),
    ("Naukri <info@naukri.com>", "Jobs for you", "naukri"),
    ("Foundit <alerts@mailer.foundit.in>", "Jobs", "foundit"),
    ("Someone <x@notlinkedin.com>", "Jobs", None),
    ("", "", None),
])
def test_is_job_email(sender, subject, expected):
    assert g.is_job_email(sender, subject) == expected


# ---------- parsers on small hand-written HTML (always run) ----------

LINKEDIN_HTML = """
<table><tr><td><h1><a href="https://www.linkedin.com/comm/jobs/view/111?x=1">Jobs similar to
  Dev at Old</a></h1></td></tr></table>
<table><tr><td><a href="https://www.linkedin.com/comm/jobs/view/222/?trackingId=a"><img></a></td>
  <td><a href="https://www.linkedin.com/comm/jobs/view/222/?trackingId=b">Flutter Developer</a>
  <p>Acme · Pune (Remote)</p><p>Easy Apply</p></td></tr></table>
<table><tr><td><a href="https://www.linkedin.com/comm/jobs/view/333/">Android Developer</a>
  <p>Beta · India (Hybrid)</p></td></tr></table>
"""

INDEED_HTML = """
<p>It looks like your background could be a match.</p>
<table><tr><td><h2><a href="https://in.indeed.com/rc/clk/dl?jk=aaaa1111bbbb2222&from=ja">Flutter Developer</a></h2>
  <p>Acme</p><p>Mumbai, Maharashtra</p><p>₹30,000 a month</p></td></tr></table>
<table><tr><td><a href="https://in.indeed.com/pagead/clk/dl?jrtk=5-cmh1-1-xyz-cccc3333dddd4444&ad=1">Android Developer</a>
  <p>Beta</p><p>Pune</p></td></tr></table>
"""


def test_parse_linkedin_html():
    jobs = g.parse_linkedin(LINKEDIN_HTML)
    assert [(j["title"], j["company"], j["location"], j["link"]) for j in jobs] == [
        ("Flutter Developer", "Acme", "Pune (Remote)", "https://www.linkedin.com/jobs/view/222/"),
        ("Android Developer", "Beta", "India (Hybrid)", "https://www.linkedin.com/jobs/view/333/"),
    ]
    assert jobs[0]["description"] == "Easy Apply"
    assert jobs[0]["source"] == "linkedin"


def test_parse_indeed_html():
    jobs = g.parse_indeed(INDEED_HTML)
    assert [(j["title"], j["company"], j["location"], j["link"]) for j in jobs] == [
        ("Flutter Developer", "Acme", "Mumbai, Maharashtra",
         "https://in.indeed.com/viewjob?jk=aaaa1111bbbb2222"),
        ("Android Developer", "Beta", "Pune", "https://in.indeed.com/viewjob?jk=cccc3333dddd4444"),
    ]
    assert jobs[0]["description"] == "₹30,000 a month"


def test_parsers_ignore_other_links():
    html = '<a href="https://www.linkedin.com/feed/">Home</a><a href="https://in.indeed.com/">Indeed</a>'
    assert g.parse_linkedin(html) == [] and g.parse_indeed(html) == []


# ---------- parsers on the real emails in samples/ (skipped when samples/ is missing) ----------

def load_sample(path):
    msg = email.message_from_bytes(open(path, "rb").read(), policy=policy.default)
    return msg, g.is_job_email(str(msg["From"]), str(msg["Subject"]))


@pytest.mark.skipif(not SAMPLES, reason="samples/ is empty or missing")
@pytest.mark.parametrize("path", [p for p in SAMPLES if "naukri" not in p] or ["none"])
def test_real_samples_parse(path):
    msg, platform = load_sample(path)
    assert platform in ("linkedin", "indeed")
    jobs = g.PARSERS[platform](g._html_of(msg))
    assert jobs, f"no jobs parsed from {path}"
    for job in jobs:
        assert job["title"] and job["company"] and job["location"]
        assert job["link"].startswith(("https://www.linkedin.com/jobs/view/",
                                       "https://in.indeed.com/viewjob?jk="))
        assert "?" not in job["link"] or job["link"].count("=") == 1  # no tracking params
        assert "background could be a match" not in job["company"]


@pytest.mark.skipif(not os.path.exists("samples/linkedin_job_alert.eml"), reason="no sample")
def test_linkedin_alert_sample_details():
    msg, _ = load_sample("samples/linkedin_job_alert.eml")
    jobs = g.parse_linkedin(g._html_of(msg))
    assert len(jobs) == 6
    assert (jobs[0]["title"], jobs[0]["company"], jobs[0]["location"]) == (
        "Flutter Developer Intern", "Purple Business", "Hyderabad (Remote)")


# ---------- fetch_jobs / mark_processed with a fake IMAP server ----------

def make_email(sender, subject, html, msg_id):
    msg = EmailMessage()
    msg["From"], msg["Subject"], msg["Message-ID"] = sender, subject, msg_id
    msg.set_content("plain")
    msg.add_alternative(html, subtype="html")
    return msg.as_bytes()


class FakeIMAP:
    def __init__(self, messages):
        self.messages = messages  # uid -> raw bytes
        self.stored, self.readonly = [], None
        self.fetch_cmds = []

    def select(self, mailbox, readonly=False):
        assert mailbox == '"JobAlerts"'
        self.readonly = readonly
        return "OK", [b"1"]

    def uid(self, command, *args):
        if command == "SEARCH":
            assert args == (None, "UNSEEN")
            return "OK", [b" ".join(self.messages)]
        if command == "FETCH":
            self.fetch_cmds.append(args[1])
            return "OK", [(b"x", self.messages[args[0]])]
        if command == "STORE":
            assert not self.readonly
            self.stored.append(args)
            return "OK", [b""]
        raise AssertionError(command)

    def logout(self):
        pass


@pytest.fixture
def imap(monkeypatch, tmp_path):
    monkeypatch.setenv("GMAIL_USER", "me@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pw")
    monkeypatch.setattr(g, "FAILED_DIR", str(tmp_path / "failed"))
    fake = FakeIMAP({
        b"1": make_email("LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>", "Alert",
                         LINKEDIN_HTML, "<a@x>"),
        b"2": make_email("Naukri <info@naukri.com>", "Jobs for you", "<p>ad</p>", "<b@x>"),
        b"3": make_email("LinkedIn <newsletters-noreply@linkedin.com>", "News", "<p>hi</p>", "<c@x>"),
        b"4": make_email('"Indeed" <donotreply@jobalert.indeed.com>', "Jobs", INDEED_HTML, "<d@x>"),
    })
    monkeypatch.setattr(g, "_connect", lambda: fake)
    return fake


def test_fetch_jobs_parses_filters_and_keeps_unread(imap, tmp_path):
    jobs = g.fetch_jobs(PROFILE)
    assert [j["link"] for j in jobs] == [
        "https://www.linkedin.com/jobs/view/222/", "https://www.linkedin.com/jobs/view/333/",
        "https://in.indeed.com/viewjob?jk=aaaa1111bbbb2222",
        "https://in.indeed.com/viewjob?jk=cccc3333dddd4444",
    ]
    assert imap.readonly is True
    assert all(cmd == "(BODY.PEEK[])" for cmd in imap.fetch_cmds)
    assert imap.stored == []  # nothing marked read yet
    # Naukri (no jobs parsed) saved for debugging and not marked processed
    assert os.listdir(tmp_path / "failed") == ["b_x.eml"]
    assert g._processed_uids == [b"1", b"3", b"4"]


def test_fetch_jobs_applies_profile(imap):
    jobs = g.fetch_jobs({"roles": ["Android Developer"]})
    assert [j["title"] for j in jobs] == ["Android Developer", "Android Developer"]
    assert g._processed_uids == [b"1", b"3", b"4"]  # still processed: emails were parsed fine


def test_mark_processed_marks_only_handled_emails(imap):
    g.fetch_jobs(PROFILE)
    assert g.mark_processed() == 3
    assert imap.stored == [(b"1,3,4", "+FLAGS", "(\\Seen)")]
    assert g.mark_processed() == 0  # nothing pending any more


def test_missing_credentials_skip(monkeypatch):
    monkeypatch.delenv("GMAIL_USER", raising=False)
    monkeypatch.setattr(g, "_connect", lambda: pytest.fail("connected"))
    assert g.fetch_jobs(PROFILE) == []


def test_imap_error_returns_empty(monkeypatch):
    monkeypatch.setenv("GMAIL_USER", "me@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pw")

    def boom():
        raise g.imaplib.IMAP4.error("LOGIN failed")

    monkeypatch.setattr(g, "_connect", boom)
    assert g.fetch_jobs(PROFILE) == []
    assert g._processed_uids == []
