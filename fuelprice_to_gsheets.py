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
    "brand",
    "avg_price_per_liter",
    "vs_previous_week",
    "status",
    "last_verified",
]


def extract_visible_table(page, fuel_type):
    html = page.content()
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    records = []
    scrape_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    start_index = None

    for i in range(len(lines) - 4):
        if (
            lines[i] == "Brand"
            and lines[i + 1] == "Price/L"
            and lines[i + 2] == "vs Last Week"
            and lines[i + 3] == "Status"
            and lines[i + 4] == "Verified"
        ):
            start_index = i + 5
            break

    if start_index is None:
        raise ValueError(f"Could not find table header for {fuel_type}.")

    i = start_index

    while i + 5 < len(lines):
        code = lines[i]
        brand = lines[i + 1]
        price_text = lines[i + 2]
        change_text = lines[i + 3]
        status = lines[i + 4]
        verified = lines[i + 5]

        if status not in ["Settled", "Pending", "Updated", "Staggered"]:
            break

        price_match = re.search(r"₱?([\d,]+(?:\.\d+)?)", price_text)
        change_match = re.search(r"([↑↓+-])\s*₱?([\d,]+(?:\.\d+)?)", change_text)

        if price_match:
            price = price_match.group(1).replace(",", "")

            if change_match:
                direction = change_match.group(1)
                value = change_match.group(2).replace(",", "")

                if direction in ["↑", "+"]:
                    weekly_change = f"+{value}"
                elif direction in ["↓", "-"]:
                    weekly_change = f"-{value}"
                else:
                    weekly_change = value
            else:
                weekly_change = ""

            records.append({
                "scrape_timestamp": scrape_timestamp,
                "source_url": SOURCE_URL,
                "fuel_type": fuel_type,
                "brand": brand,
                "avg_price_per_liter": price,
                "vs_previous_week": weekly_change,
                "status": status,
                "last_verified": verified,
            })

        i += 6

    return records


def scrape_fuelprice():
    all_records = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/115.0 Safari/537.36"
            )
        )

        page.goto(SOURCE_URL, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(10000)

        # Scrape default visible tab: Unleaded 91
        all_records.extend(extract_visible_table(page, "Unleaded 91"))

        # Click Premium 95 tab, then scrape again
        page.get_by_text("Premium 95", exact=True).click()
        page.wait_for_timeout(3000)

        all_records.extend(extract_visible_table(page, "Premium 95"))

        browser.close()

    if not all_records:
        raise ValueError("No fuel price records were scraped.")

    df = pd.DataFrame(all_records)

    df = df.drop_duplicates(
        subset=["scrape_timestamp", "fuel_type", "brand"],
        keep="first"
    )

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

    # RAW keeps + and - signs
    worksheet.append_rows(df.values.tolist(), value_input_option="RAW")


def main():
    df = scrape_fuelprice()

    print("Scraped records:")
    print(df)

    append_to_google_sheet(df)

    print(f"Successfully appended {len(df)} rows.")


if __name__ == "__main__":
    main()
