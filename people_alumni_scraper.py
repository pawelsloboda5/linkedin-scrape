"""
people_alumni_scraper.py
--------------------------------------------------
• Reads an Excel file of alumni names.
• Logs into LinkedIn once.
• For each alumnus, opens the NDU “people” view with a ?keywords=<name> filter,
  grabs the first profile card, extracts the profile URL, and writes results to CSV.

ENV VARS (or prompt):
    LINKEDIN_EMAIL
    LINKEDIN_PASSWORD
INPUT  : alumni.xlsx   (sheet 0, columns must include `firstname` and `lastname`)
OUTPUT : output/alumni_linkedin_urls.csv
--------------------------------------------------
"""

import os, time, csv, urllib.parse, logging
import pandas as pd
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# ── CONFIG ────────────────────────────────────────────────────────────
INPUT_EXCEL        = "ndu_grads.xlsx"            # adjust path if needed
OUTPUT_CSV         = "output/alumni_linkedin_urls.csv"
DELAY_BETWEEN_QUERIES = 2                     # seconds
PAGE_LOAD_DELAY       = 4
SCHOOL_BASE_URL       = (
    "https://www.linkedin.com/school/national-defense-university/people/?keywords="
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logging.getLogger("selenium").setLevel(logging.WARNING)


# ── SELENIUM HELPERS ──────────────────────────────────────────────────
def init_driver() -> webdriver.Chrome:
    opts = Options()
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-notifications")
    return webdriver.Chrome(options=opts)  # Selenium‑Manager fetches driver


def linkedin_login(driver: webdriver.Chrome, email: str, pwd: str) -> None:
    driver.get("https://www.linkedin.com/login")
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "username")))
    driver.find_element(By.ID, "username").send_keys(email)
    driver.find_element(By.ID, "password").send_keys(pwd)
    driver.find_element(By.XPATH, '//button[@type="submit"]').click()
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.XPATH, '//input[contains(@placeholder,"Search")]'))
    )
    logging.info("Logged in to LinkedIn")


def build_people_url(first: str, last: str) -> str:
    query = urllib.parse.quote_plus(f"{first} {last}")
    return SCHOOL_BASE_URL + query


def extract_first_profile_url(driver: webdriver.Chrome) -> str | None:
    try:
        card_link = WebDriverWait(driver, 6).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href*="/in/"]'))
        )
        return card_link.get_attribute("href").split("?")[0]
    except TimeoutException:
        return None


# ── MAIN WORKFLOW (resume support) ────────────────────────────────────────
def main():
    email = os.getenv("LINKEDIN_EMAIL") or input("LinkedIn email: ")
    pwd   = os.getenv("LINKEDIN_PASSWORD") or input("LinkedIn password: ")

    # 1️⃣  read Excel
    df = pd.read_excel(INPUT_EXCEL)

    # 2️⃣  figure out which names we’ve already scraped
    done_names: set[str] = set()
    csv_path = Path(OUTPUT_CSV)
    if csv_path.exists():
        prev = pd.read_csv(csv_path)
        done_names = {f"{r.firstname.strip()} {r.lastname.strip()}" for r in prev.itertuples()}
        logging.info(f"Resuming run – {len(done_names)} names already processed")

    # 3️⃣  open CSV in append mode (create + header if new)
    csv_path.parent.mkdir(exist_ok=True)
    write_header = not csv_path.exists()
    csv_file = csv_path.open("a", newline="", encoding="utf-8")
    writer = csv.DictWriter(
        csv_file, fieldnames=["firstname", "lastname", "program", "linkedin_profile"]
    )
    if write_header:
        writer.writeheader()

    # 4️⃣  set up Selenium
    driver = init_driver()
    linkedin_login(driver, email, pwd)

    # 5️⃣  iterate through Excel rows, skipping completed
    for row in df.itertuples():
        first, last = str(row.firstname).strip(), str(row.lastname).strip()
        full_name = f"{first} {last}"
        if full_name in done_names:
            continue  # already scraped

        # build + visit search URL (middle name NOT used)
        driver.get(build_people_url(first, last))
        time.sleep(PAGE_LOAD_DELAY)

        profile_url = extract_first_profile_url(driver) or "NOT FOUND"
        logging.info(f"{full_name} → {profile_url}")

        writer.writerow(
            {
                "firstname": first,
                "lastname": last,
                "program": getattr(row, "Program", ""),
                "linkedin_profile": profile_url,
            }
        )
        csv_file.flush()
        time.sleep(DELAY_BETWEEN_QUERIES)

    driver.quit()
    csv_file.close()
    logging.info(f"Run complete. Results in {csv_path}")


if __name__ == "__main__":
    main()
