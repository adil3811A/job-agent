"""Job alert emails from Gmail (label JobAlerts) via IMAP.

Needs GMAIL_USER and GMAIL_APP_PASSWORD. Flow:
  1. fetch_jobs() reads UNSEEN emails without marking them read (BODY.PEEK),
     parses job cards per platform and returns jobs filtered with matches_profile.
  2. After the jobs are saved, main calls mark_processed() to mark those emails read.
Job emails where the parser finds nothing are saved to failed_emails/ and left
unread, so they're retried once the parser is fixed.
"""
import email
import imaplib
import logging
import os
import re
from email import policy
from email.utils import parseaddr
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from filters import matches_profile
from sources import load_profile, make_job

log = logging.getLogger(__name__)

IMAP_HOST = "imap.gmail.com"
LABEL = "JobAlerts"
FAILED_DIR = "failed_emails"
MAX_EMAILS = 50  # per run, oldest first

# Sender domain (subdomains included) -> platform name
PLATFORMS = {
    "linkedin.com": "linkedin",
    "indeed.com": "indeed",
    "naukri.com": "naukri",
    "instahyre.com": "instahyre",
    "foundit.in": "foundit",
    "glassdoor.com": "glassdoor",
    "glassdoor.co.in": "glassdoor",
}
# Emails from these platforms that never contain job listings
NON_JOB_SENDERS = {"newsletters-noreply@linkedin.com"}
NON_JOB_SUBJECT = re.compile(r"your application|application (was )?sent|application status",
                             re.IGNORECASE)

# UIDs of emails handled by the last fetch_jobs() call, marked read by mark_processed()
_processed_uids = []


def is_job_email(sender, subject):
    """Return the platform name for a job alert email, or None if it isn't one."""
    address = parseaddr(sender or "")[1].lower()
    if address in NON_JOB_SENDERS or NON_JOB_SUBJECT.search(subject or ""):
        return None
    domain = address.rpartition("@")[2]
    for platform_domain, platform in PLATFORMS.items():
        if domain == platform_domain or domain.endswith("." + platform_domain):
            return platform
    return None


# ---------- parsers: html -> list of job dicts (unfiltered) ----------

def _card(anchor, key_of):
    """Largest ancestor of anchor whose links all point to the same job."""
    node = anchor
    while node.parent is not None:
        keys = {key_of(a["href"]) for a in node.parent.find_all("a", href=True)}
        keys.discard(None)
        if len(keys) > 1:
            break
        node = node.parent
    return node


def _card_lines(anchor, key_of):
    """Text lines of the job card, starting at the title (skips any intro text above it)."""
    lines = list(_card(anchor, key_of).stripped_strings)
    title = anchor.get_text(" ", strip=True)
    return lines[lines.index(title):] if title in lines else lines


def _linkedin_id(href):
    m = re.search(r"/jobs/view/(\d+)", href)
    return m.group(1) if m else None


def parse_linkedin(html):
    """LinkedIn job alert / similar jobs: card = title, "Company · Location", extras."""
    soup = BeautifulSoup(html, "lxml")
    jobs, seen = [], set()
    for a in soup.find_all("a", href=True):
        job_id = _linkedin_id(a["href"])
        title = a.get_text(" ", strip=True)
        if not job_id or not title or job_id in seen:
            continue
        lines = _card_lines(a, _linkedin_id)
        # The header ("Jobs similar to X at Y") links a job too, but has no "Company · Location".
        if len(lines) < 2 or " · " not in lines[1]:
            continue
        seen.add(job_id)
        company, _, location = lines[1].partition(" · ")
        jobs.append(make_job("linkedin", title, company, location,
                             f"https://www.linkedin.com/jobs/view/{job_id}/",
                             " · ".join(lines[2:])))
    return jobs


def _indeed_key(href):
    """Indeed job key: jk=... on /rc/clk and /viewjob links, or the last part of jrtk on ad links."""
    if "indeed." not in href:
        return None
    query = parse_qs(urlparse(href).query)
    if query.get("jk"):
        return query["jk"][0]
    m = re.search(r"-([0-9a-f]{16})$", query.get("jrtk", [""])[0])
    return m.group(1) if m else None


def parse_indeed(html):
    """Indeed job alert / match: card = title, company, location, salary, extras."""
    soup = BeautifulSoup(html, "lxml")
    jobs, seen = [], set()
    for a in soup.find_all("a", href=re.compile(r"/(viewjob|rc/clk|pagead/clk)")):
        key = _indeed_key(a["href"])
        title = a.get_text(" ", strip=True)
        if not key or not title or key in seen:
            continue
        lines = _card_lines(a, _indeed_key)
        if len(lines) < 3:
            continue
        seen.add(key)
        jobs.append(make_job("indeed", title, lines[1], lines[2],
                             f"https://in.indeed.com/viewjob?jk={key}", " · ".join(lines[3:])))
    return jobs


def parse_naukri(html):
    # TODO: write once a real Naukri job alert is in samples/ (only an ad so far).
    return []


PARSERS = {"linkedin": parse_linkedin, "indeed": parse_indeed, "naukri": parse_naukri}


# ---------- IMAP ----------

def _html_of(msg):
    body = msg.get_body(("html",))
    return body.get_content() if body else ""


def _save_failed(msg, raw):
    os.makedirs(FAILED_DIR, exist_ok=True)
    name = re.sub(r"[^\w.-]", "_", (msg["Message-ID"] or "no-id").strip("<>"))[:100]
    with open(os.path.join(FAILED_DIR, f"{name}.eml"), "wb") as f:
        f.write(raw)


def _connect():
    imap = imaplib.IMAP4_SSL(IMAP_HOST)
    imap.login(os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"])
    return imap


def fetch_jobs(profile=None):
    """Parse unread JobAlerts emails into jobs. Doesn't mark anything read."""
    _processed_uids.clear()
    if not (os.environ.get("GMAIL_USER") and os.environ.get("GMAIL_APP_PASSWORD")):
        log.info("Gmail skipped: GMAIL_USER / GMAIL_APP_PASSWORD not set")
        return []
    profile = profile if profile is not None else load_profile()

    jobs = []
    try:
        imap = _connect()
        try:
            imap.select(f'"{LABEL}"', readonly=True)
            uids = imap.uid("SEARCH", None, "UNSEEN")[1][0].split()[:MAX_EMAILS]
            for uid in uids:
                raw = imap.uid("FETCH", uid, "(BODY.PEEK[])")[1][0][1]
                jobs.extend(_handle_email(uid, raw))
        finally:
            imap.logout()
    except (imaplib.IMAP4.error, OSError) as e:
        log.warning("Gmail fetch failed: %s", e)
        _processed_uids.clear()
        return []
    return [j for j in jobs if matches_profile(j, profile)]


def _handle_email(uid, raw):
    msg = email.message_from_bytes(raw, policy=policy.default)
    sender, subject = str(msg["From"] or ""), str(msg["Subject"] or "")
    platform = is_job_email(sender, subject)
    if platform is None:
        log.info("Not a job alert, will mark read: %s | %s", sender, subject[:60])
        _processed_uids.append(uid)
        return []

    parser = PARSERS.get(platform)
    jobs = parser(_html_of(msg)) if parser else []
    if not jobs:
        log.warning("No jobs parsed from %s email, saved to %s/: %s",
                    platform, FAILED_DIR, subject[:60])
        _save_failed(msg, raw)
        return []

    log.info("%d jobs from %s email: %s", len(jobs), platform, subject[:60])
    _processed_uids.append(uid)
    return jobs


def mark_processed():
    """Mark the emails handled by the last fetch_jobs() as read. Call after saving jobs."""
    if not _processed_uids:
        return 0
    imap = _connect()
    try:
        imap.select(f'"{LABEL}"')
        imap.uid("STORE", b",".join(_processed_uids), "+FLAGS", "(\\Seen)")
    finally:
        imap.logout()
    count = len(_processed_uids)
    _processed_uids.clear()
    return count
