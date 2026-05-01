import os
import json
import re
from datetime import datetime

from playwright.sync_api import sync_playwright
import pandas as pd

import gspread
from google.oauth2.service_account import Credentials


SOURCE_URL = "https://www.fuelprice.ph/gasoline-price-philippines"
SHEET_NAME = "Sheet1"

HEADERS = [
    "scrape_timestamp",
    "source_url",
    "fuel_type",
    "brand",
    "avg_price_per_liter",
    "vs_previous_week",
    "status",
    "last_verified",
]


def scrape_fuelprice():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(SOURCE_URL, wait_until="domcontentloaded", timeout=90000)

        # 🔥 WAIT FOR PRICE ELEMENTS (IMPORTANT)
        page.wait_for_selector("text=₱", timeout=30000)

        content = page.content()
        browser.close()

    text = content

    # extract all rows with price pattern
    pattern = re.findall(
        r"([A-Za-z\s]+)\s+₱(\d+\.\d+)\s+([+-]₱\d+\.\d+)\s+(Settled|Pending|Updated)\s+([A-Za-z]+\s+\d+)",
        text
    )

    if not pattern:
        raise ValueError("Still no data scraped. Site likely blocking content.")

    scrape_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    records = []

    fuel_type = "Unleaded 91"

    for i, row in enumerate(pattern):
        brand, price, change, status, date = row

        # switch fuel type mid-way
        if i >= 12:
            fuel_type = "Premium 95"

        records.append({
            "scrape_timestamp": scrape_timestamp,
            "source_url": SOURCE_URL,
            "fuel_type": fuel_type,
            "brand": brand.strip(),
            "avg_price_per_liter": float(price),
            "vs_previous_week": float(change.replace("₱", "")),
            "status": status,
            "last_verified": date,
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
    sheet = client.open_by_key(sheet_id).worksheet(SHEET_NAME)

    if not sheet.get_all_values():
        sheet.append_row(HEADERS)

    df = df.fillna("").astype(str)
    sheet.append_rows(df.values.tolist(), value_input_option="USER_ENTERED")


def main():
    df = scrape_fuelprice()
    print(df)
    append_to_google_sheet(df)


if __name__ == "__main__":
    main()
