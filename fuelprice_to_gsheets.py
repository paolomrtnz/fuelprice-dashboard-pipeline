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
    if value is None:
        return None

    text = str(value)
    text = text.replace("₱", "").replace("/L", "").replace(",", "").strip()

    match = re.search(r"\d+(\.\d+)?", text)
    if match:
        return float(match.group())

    return None


def clean_change(value):
    if value is None:
        return None

    text = str(value)
    text = text.replace("₱", "").replace("/L", "").replace(",", "").strip()

    match = re.search(r"[+-]?\d+(\.\d+)?", text)
    if match:
        return float(match.group())

    return None


def get_last_verified(soup):
    text = soup.get_text(" ", strip=True)

    match = re.search(r"Last verified:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})", text)
    if match:
        return match.group(1)

    match = re.search(r"Last updated:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})", text)
    if match:
        return match.group(1)

    return ""


def scrape_fuelprice():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0 Safari/537.36"
        )
        page.goto(SOURCE_URL, wait_until="networkidle", timeout=60000)
        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "html.parser")

    last_verified = get_last_verified(soup)
    scrape_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    page_text = soup.get_text("\n", strip=True)

    fuel_types = ["Unleaded 91", "Premium 95"]
    brands = [
        "Cleanfuel",
        "Flying V",
        "Jetti",
        "Phoenix",
        "PTT",
        "RePhil",
        "Seaoil",
        "Shell",
        "Petron",
        "Caltex",
        "Unioil",
        "TotalEnergies",
        "SeaOil",
    ]

    records = []

    lines = [line.strip() for line in page_text.split("\n") if line.strip()]

    current_fuel_type = None

    for i, line in enumerate(lines):
        if line in fuel_types:
            current_fuel_type = line

        if line in brands and current_fuel_type:
            nearby_text = " ".join(lines[i:i + 8])

            price_match = re.search(r"₱?\s*(\d+(\.\d+)?)\s*/?L", nearby_text)
            change_match = re.search(r"([+-]₱?\s*\d+(\.\d+)?)\s*vs last week", nearby_text)

            price = clean_price(price_match.group(1)) if price_match else None
            change = clean_change(change_match.group(1)) if change_match else None

            if price is not None:
                records.append({
                    "scrape_timestamp": scrape_timestamp,
                    "source_url": SOURCE_URL,
                    "fuel_type": current_fuel_type,
                    "brand": line,
                    "avg_price_per_liter": price,
                    "vs_previous_week": change,
                    "status": "scraped",
                    "last_verified": last_verified,
                })

    df = pd.DataFrame(records)

    if df.empty:
        raise ValueError("No fuel price records were scraped. Website structure may have changed.")

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

    df = df.fillna("")
    worksheet.append_rows(df.values.tolist(), value_input_option="USER_ENTERED")

def main():
    df = scrape_fuelprice()

    print("Scraped records:")
    print(df)

    append_to_google_sheet(df)

    print(f"Successfully appended {len(df)} rows to Google Sheets.")


if __name__ == "__main__":
    main()
