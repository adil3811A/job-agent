"""Telegram notifications via the Bot API.

Needs TELEGRAM_TOKEN and TELEGRAM_CHAT_ID in the environment (or .env locally).
"""
import os

import requests
from dotenv import load_dotenv

load_dotenv()

MAX_LEN = 4096  # Telegram's per-message limit
SUMMARY_THRESHOLD = 5


def send_telegram(text):
    """Send one message, splitting it if it's over Telegram's length limit."""
    url = f"https://api.telegram.org/bot{os.environ['TELEGRAM_TOKEN']}/sendMessage"
    for chunk in _split(text):
        resp = requests.post(url, json={
            "chat_id": os.environ["TELEGRAM_CHAT_ID"],
            "text": chunk,
            "disable_web_page_preview": True,
        }, timeout=15)
        resp.raise_for_status()


def _split(text):
    chunks = []
    while len(text) > MAX_LEN:
        cut = text.rfind("\n", 0, MAX_LEN)
        if cut <= 0:
            cut = MAX_LEN
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    chunks.append(text)
    return chunks


def format_job(job):
    lines = [f"{job.get('title', '')} @ {job.get('company', '')}"]
    if job.get("score") not in (None, ""):
        lines[0] += f" (score {job['score']})"
    if job.get("reason"):
        lines.append(job["reason"])
    lines.append(job["link"])
    return "\n".join(lines)


def notify_jobs(jobs):
    """One message per job, or a single summary if there are more than 5."""
    if not jobs:
        return
    if len(jobs) > SUMMARY_THRESHOLD:
        body = "\n\n".join(f"{i}. {format_job(j)}" for i, j in enumerate(jobs, 1))
        send_telegram(f"{len(jobs)} new jobs\n\n{body}")
    else:
        for job in jobs:
            send_telegram(f"New job\n{format_job(job)}")


if __name__ == "__main__":
    send_telegram("Test message from job notifier")
    print("Sent! Check Telegram.")
