from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

SOURCE_URL = "https://www.fuelprice.ph"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/115.0 Safari/537.36"
        )

        page.goto(SOURCE_URL, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(10000)

        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)

    print("===== PAGE TEXT START =====")
    print(text[:5000])
    print("===== PAGE TEXT END =====")

if __name__ == "__main__":
    main()
