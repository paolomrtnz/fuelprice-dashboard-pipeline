import os
import json
import re
from datetime import datetime

from playwright.sync_api import sync_playwright
import pandas as pd
from bs4 import BeautifulSoup

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


def clean_price(value):
    if not value:
        return None
    match = re.search(r"\d+(\.\d+)?", value)
    return float(match.group()) if match else None


def clean_change(value):
    if not value:
        return None
    match = re.search(r"[+-]?\d+(\.\d+)?", value)
    return float(match.group()) if match else None


def scrape_fuelprice():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(SOURCE_URL, wait_until="networkidle", timeout=60000)
        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)

    lines = [line.strip() for line in text.split("\n") if line.strip()]

    scrape_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    records = []

    fuel_type = "Unleaded 91"
    counter = 0

    for line in lines:
        # look for lines containing price
        if "₱" in line and any(x in line for x in ["Settled", "Pending", "Updated"]):

            parts = line.split()

            # try to extract brand (skip 2-letter code like SH)
            if len(parts) >= 4:
                brand = parts[1] if len(parts[0]) == 2 else parts[0]

                price = clean_price(line)

                change_match = re.search(r"[+-]₱\d+(\.\d+)?", line)
                change = clean_change(change_match.group()) if change_match else None

                status = "Settled" if "Settled" in line else "Pending"

                last_verified = " ".join(parts[-2:])

                # switch fuel type after enough rows
                if counter >= 12:
                    fuel_type = "Premium 95"

                records.append({
                    "scrape_timestamp": scrape_timestamp,
                    "source_url": SOURCE_URL,
                    "fuel_type": fuel_type,
                    "brand": brand,
                    "avg_price_per_liter": price,
                    "vs_previous_week": change,
                    "status": status,
                    "last_verified": last_verified,
                })

                counter += 1

    df = pd.DataFrame(records)

    if df.empty:
        raise ValueError("Still no data scraped. Site structure changed heavily.")

    df = df.drop_duplicates(subset=["scrape_timestamp", "fuel_type", "brand"])
    df = df[HEADERS]

    return df


def append_to_google_sheet(df):
    service_account_json = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    sheet_id = os.environ["GOOGLE_SHEET_ID"]

    service_account_info = json.loads(service_account_json)

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    credentials = Credentials.from_service_account_info(
        service_account_info,
        scopes=scopes,
    )

    client = gspread.authorize(credentials)
    spreadsheet = client.open_by_key(sheet_id)
    worksheet = spreadsheet.worksheet(SHEET_NAME)

    existing_values = worksheet.get_all_values()

    if not existing_values:
        worksheet.append_row(HEADERS)

    df = df.fillna("").astype(str)
    worksheet.append_rows(df.values.tolist(), value_input_option="USER_ENTERED")


def main():
    df = scrape_fuelprice()
    print(df)
    append_to_google_sheet(df)


if __name__ == "__main__":
    main()
