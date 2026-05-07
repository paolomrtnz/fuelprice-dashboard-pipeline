import os
import json
import re
from datetime import datetime

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import pandas as pd

import gspread
from google.oauth2.service_account import Credentials


SOURCE_URL = "https://www.fuelprice.ph"
SHEET_NAME = "Sheet1"

HEADERS = [
    "scrape_timestamp",
    "source_url",
    "fuel_type",
    "price_range",
    "weekly_change",
    "last_verified",
]


def scrape_fuelprice():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/115.0 Safari/537.36"
        )

        page.goto(SOURCE_URL, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(8000)

        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "html.parser")

    text = soup.get_text("\n", strip=True)

    scrape_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Example matches:
    # Diesel ₱48.20 - ₱51.40 +₱1.20
    pattern = re.findall(
        r"(Diesel|Unleaded|Premium|Kerosene)\s+₱([\d\.]+\s*-\s*₱?[\d\.]+)\s+([+-]₱[\d\.]+)",
        text,
    )

    if not pattern:
        raise ValueError("No homepage fuel ranges scraped.")

    # get last verified
    verified_match = re.search(
        r"Last verified[:\s]+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        text,
    )

    last_verified = verified_match.group(1) if verified_match else ""

    records = []

    for fuel_type, price_range, weekly_change in pattern:
        records.append({
            "scrape_timestamp": scrape_timestamp,
            "source_url": SOURCE_URL,
            "fuel_type": fuel_type,
            "price_range": price_range,
            "weekly_change": weekly_change.replace("₱", ""),
            "last_verified": last_verified,
        })

    df = pd.DataFrame(records)
    df = df[HEADERS]

    return df


def append_to_google_sheet(df):
    service_account_json = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    sheet_id = os.environ["GOOGLE_SHEET_ID"]

    credentials = Credentials.from_service_account_info(
        json.loads(service_account_json),
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )

    client = gspread.authorize(credentials)
    worksheet = client.open_by_key(sheet_id).worksheet(SHEET_NAME)

    existing_values = worksheet.get_all_values()

    if not existing_values:
        worksheet.append_row(HEADERS)

    df = df.fillna("").astype(str)

    worksheet.append_rows(
        df.values.tolist(),
        value_input_option="RAW",
    )


def main():
    df = scrape_fuelprice()

    print(df)

    append_to_google_sheet(df)

    print(f"Successfully appended {len(df)} rows.")


if __name__ == "__main__":
    main()
