"""Google Sheets helpers: add new jobs, skip duplicate links, read Approved rows.

Credentials come from GOOGLE_CREDS_JSON, then GOOGLE_CREDS_FILE, then creds.json; either var may hold
the key JSON content (GitHub Actions secret) or a path to the key file (local).
"""
import json
import os
from datetime import date

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
HEADERS = ["Date", "Source", "Title", "Company", "Link", "Score", "Reason", "Status", "Cover Letter"]
LINK_COL = HEADERS.index("Link") + 1
STATUS_COL = HEADERS.index("Status") + 1
COVER_COL = HEADERS.index("Cover Letter") + 1


def _get_sheet():
    # Either var may hold the key's JSON content (GitHub secret) or a file path (local).
    value = (os.environ.get("GOOGLE_CREDS_JSON") or os.environ.get("GOOGLE_CREDS_FILE")
             or "creds.json").strip()
    if value.startswith("{"):
        creds = Credentials.from_service_account_info(json.loads(value), scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file(value, scopes=SCOPES)
    return gspread.authorize(creds).open_by_key(os.environ["SHEET_ID"]).sheet1


def normalize_link(link):
    return link.strip().rstrip("/").lower()


def get_existing_links(sheet=None):
    """Return the set of (normalized) links already in the sheet."""
    sheet = sheet or _get_sheet()
    return {normalize_link(v) for v in sheet.col_values(LINK_COL)[1:] if v}


def add_jobs(jobs, sheet=None):
    """Append jobs whose link isn't already in the sheet, in one batch call.

    Each job is a dict with keys: date, source, title, company, link, score, reason
    (date defaults to today). Returns the list of jobs that were actually new.
    """
    sheet = sheet or _get_sheet()
    seen = get_existing_links(sheet)
    today = date.today().isoformat()

    added, rows = [], []
    for job in jobs:
        key = normalize_link(job["link"])
        if key in seen:
            continue
        seen.add(key)  # also dedupe within this batch
        rows.append([
            job.get("date") or today,
            job.get("source", ""),
            job.get("title", ""),
            job.get("company", ""),
            job["link"],
            job.get("score", ""),
            job.get("reason", ""),
            "New",
            "",
        ])
        added.append(job)

    if rows:
        # Write at an explicit row instead of append_rows: append lets Sheets guess
        # where the table is, which shifts columns when the sheet has gaps.
        next_row = len(sheet.get_all_values()) + 1
        last_row = next_row + len(rows) - 1
        if last_row > sheet.row_count:
            sheet.add_rows(last_row - sheet.row_count)
        sheet.update(rows, f"A{next_row}", value_input_option="USER_ENTERED")
    return added


def get_approved(sheet=None):
    """Return rows with Status == 'Approved', each with its sheet row number."""
    sheet = sheet or _get_sheet()
    approved = []
    for i, record in enumerate(sheet.get_all_records(expected_headers=HEADERS), start=2):
        if str(record["Status"]).strip().lower() == "approved":
            approved.append({**record, "row": i})
    return approved


def update_job(row, status=None, cover_letter=None, sheet=None):
    """Update the Status and/or Cover Letter of a given sheet row."""
    sheet = sheet or _get_sheet()
    if status is not None:
        sheet.update_cell(row, STATUS_COL, status)
    if cover_letter is not None:
        sheet.update_cell(row, COVER_COL, cover_letter)


if __name__ == "__main__":
    print(f"{len(get_existing_links())} links in sheet")
    for job in get_approved():
        print(f"Approved: row {job['row']} - {job['Title']} @ {job['Company']}")
