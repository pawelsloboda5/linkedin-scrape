"""
alumni_profile_scraper.py
-----------------------------------------------
• Requires alumni_linkedin_urls.csv (urls column MUST be named linkedin_profile)
• Collects: firstname, lastname, program, url, title, company,
            location, connections, headline, profile_pic
• Saves incrementally to output/alumni_profile_details.csv
-----------------------------------------------
"""

import os, csv, time, logging
import pandas as pd
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

SRC_CSV   = "output/alumni_linkedin_urls_FOUND.csv"
DEST_CSV  = "output/alumni_profile_details.csv"
PAGE_DELAY = 3         # seconds between profile loads

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logging.getLogger("selenium").setLevel(logging.WARNING)


# ── helpers ──────────────────────────────────────────────────────────
def init_driver() -> webdriver.Chrome:
    opts = Options()
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-notifications")
    return webdriver.Chrome(options=opts)


def linkedin_login(driver: webdriver.Chrome, email: str, pwd: str):
    driver.get("https://www.linkedin.com/login")
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "username")))
    driver.find_element(By.ID, "username").send_keys(email)
    driver.find_element(By.ID, "password").send_keys(pwd)
    driver.find_element(By.XPATH, '//button[@type="submit"]').click()
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.XPATH, '//input[contains(@placeholder,"Search")]'))
    )
    logging.info("Logged in.")


def safe_text(elem) -> str:
    try:
        return elem.text.strip()
    except Exception:
        return ""


def first_or_empty(parent, by, selector):
    """Return .text of the first matching element or ''."""
    try:
        return parent.find_element(by, selector).text.strip()
    except NoSuchElementException:
        return ""

def grab_profile_data(driver):
    data = {
        "current_title": "",
        "current_company": "",
        "location": "",
        "connections": "",
        "headline": "",
        "profile_pic": "",
        "email": "",
    }

    # ---------- top-card block ----------
    try:
        top = WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.ph5"))
        )

        data["headline"]    = first_or_empty(top, By.CSS_SELECTOR, "div.text-body-medium")
        data["location"]    = first_or_empty(top, By.CSS_SELECTOR, "span.text-body-small")
        data["connections"] = first_or_empty(top, By.CSS_SELECTOR, "span.t-black--light")

        # profile picture: try 3 selectors in order
        for pic_sel in [
            "img.pv-top-card-profile-picture__image",
            "img.evi-image",
            'img[width="200"][title][src]',
        ]:
            try:
                data["profile_pic"] = top.find_element(By.CSS_SELECTOR, pic_sel).get_attribute("src")
                if data["profile_pic"]:
                    break
            except NoSuchElementException:
                continue
    except TimeoutException:
        pass  # couldn’t load top card; leave fields empty

    # ---------- experience section ----------
    try:
        exp_first = driver.find_element(By.CSS_SELECTOR, "section[id*=experience] li")
        data["current_title"]   = first_or_empty(exp_first, By.CSS_SELECTOR, "span[aria-hidden='true']")
        data["current_company"] = first_or_empty(exp_first, By.CSS_SELECTOR, "span.t-14.t-normal")
    except NoSuchElementException:
        pass

    # ---------- contact info (email) ----------
    try:
        # Some profiles have no “Contact Info” button; catch that too
        contact_btn = driver.find_element(By.ID, "top-card-text-details-contact-info")
        contact_btn.click()

        # give modal up to 12 s; if it never shows, just skip
        try:
            WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "section.artdeco-modal"))
            )

            # try to grab e-mail (may not exist)
            try:
                email_elem = driver.find_element(By.CSS_SELECTOR, "a[href^='mailto:']")
                data["email"] = email_elem.get_attribute("href").replace("mailto:", "")
            except NoSuchElementException:
                data["email"] = ""

            # close modal (safely)
            try:
                driver.find_element(By.CSS_SELECTOR, "button[aria-label='Dismiss']").click()
            except NoSuchElementException:
                pass

        except TimeoutException:
            logging.debug("Contact-info modal did not appear; continuing without e-mail")

    except NoSuchElementException:
        # profile simply doesn’t have a contact-info button
        pass

    return data


# ── main ──────────────────────────────────────────────────────────────
def main():
    # login creds
    email = os.getenv("LINKEDIN_EMAIL") or input("LinkedIn email: ")
    pwd   = os.getenv("LINKEDIN_PASSWORD") or input("LinkedIn password: ")

    src = pd.read_csv(SRC_CSV)
    src = src[src["linkedin_profile"].str.upper() != "NOT FOUND"].drop_duplicates()

    done_urls: set[str] = set()
    dest = Path(DEST_CSV)
    if dest.exists():
        prev = pd.read_csv(dest)
        done_urls = set(prev["linkedin_profile"])
        logging.info(f"Resuming – {len(done_urls)} profiles already scraped")

    dest.parent.mkdir(exist_ok=True)
    csv_file = dest.open("a", newline="", encoding="utf-8")
    writer = csv.DictWriter(
        csv_file,
        fieldnames=[
            "firstname", "lastname", "program", "linkedin_profile",
            "current_title", "current_company", "location",
            "connections", "headline", "profile_pic", "email",
        ],
    )
    if dest.stat().st_size == 0:
        writer.writeheader()

    driver = init_driver()
    linkedin_login(driver, email, pwd)

    for row in src.itertuples():
        url = row.linkedin_profile
        if url in done_urls:
            continue

        driver.get(url)
        time.sleep(PAGE_DELAY)

        pdata = grab_profile_data(driver)
        writer.writerow(
            {
                "firstname": row.firstname,
                "lastname": row.lastname,
                "program": row.program,
                "linkedin_profile": url,
                **pdata,
            }
        )
        csv_file.flush()
        logging.info(f"{row.firstname} {row.lastname} → scraped")
        time.sleep(1)

    driver.quit()
    csv_file.close()
    logging.info(f"Complete. Details in {DEST_CSV}")


if __name__ == "__main__":
    main()
