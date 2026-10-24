import os
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

load_dotenv()

scopes = ["https://www.googleapis.com/auth/spreadsheets"]
creds = Credentials.from_service_account_file("creds.json", scopes=scopes)
client = gspread.authorize(creds)

sheet = client.open_by_key(os.environ["SHEET_ID"]).sheet1
sheet.append_row(["2026-10-22", "test", "Test Job", "Test Co", "https://example.com", 8, "test", "New", ""])
print("Done! Check your sheet.")
