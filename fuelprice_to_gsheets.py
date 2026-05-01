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

    rows = re.findall(
        r"\b[A-Z]{2}\s+([A-Za-z ]+?)\s+₱(\d+\.\d+)\s+([+-]₱\d+\.\d+)\s+(Settled|Pending|Updated)\s+([A-Za-z]{3}\s+\d{1,2})",
        text,
    )

    if not rows:
        raise ValueError("No fuel price records were scraped.")

    records = []

    for i, row in enumerate(rows):
        brand, price, change, status, last_verified = row

        fuel_type = "Unleaded 91" if i < 13 else "Premium 95"

        records.append({
            "scrape_timestamp": scrape_timestamp,
            "source_url": SOURCE_URL,
            "fuel_type": fuel_type,
            "brand": brand.strip(),
            "avg_price_per_liter": price,
            "vs_previous_week": change.replace("₱", ""),
            "status": status,
            "last_verified": last_verified,
        })

    df = pd.DataFrame(records)

    brand_order = [
        "Shell",
        "Petron",
        "Caltex",
        "Seaoil",
        "Phoenix",
        "Cleanfuel",
        "Unioil",
        "Flying V",
        "Jetti",
        "Total Energies",
        "Petro Gazz",
        "Eastern Petroleum",
        "PTT",
    ]

    df["brand"] = pd.Categorical(df["brand"], categories=brand_order, ordered=True)
    df = df.sort_values(["fuel_type", "brand"])
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

    if not worksheet.get_all_values():
        worksheet.append_row(HEADERS)

    df = df.fillna("").astype(str)

    # RAW keeps + sign in Google Sheets
    worksheet.append_rows(df.values.tolist(), value_input_option="RAW")


def main():
    df = scrape_fuelprice()

    print("Scraped records:")
    print(df)

    append_to_google_sheet(df)

    print(f"Successfully appended {len(df)} rows to Google Sheets.")


if __name__ == "__main__":
    main()
