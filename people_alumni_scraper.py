"""
alumni_details_scraper.py  ⟶  pulls rich profile data for every LinkedIn URL
──────────────────────────────────────────────────────────────────────────────
INPUT   : output/alumni_linkedin_urls.csv        (must already exist)
OUTPUT  : output/alumni_linkedin_details.csv     (appends / resumes)

New columns captured
───────────────────
    current_title      current_company
    second_title       second_company
    third_title        third_company
    location           connections
    headline           profile_pic
    email
    experience         (top-3 roles «title @ company – dates»  ;-separated)
    education          (schools other than NDU                  ;-separated)
    licenses           (top-3 items                             ;-separated)
    volunteering       (top-3 items                             ;-separated)

Technique
─────────
• Selenium logs in once.
• Loads each profile, *scrolls to the very bottom* (lazy sections load).
• Resizes window to full page height then screenshots once.
• Sends the screenshot to **OpenAI Vision** with an explicit JSON-only prompt
  requesting the fields above.
• Merges Vision JSON with DOM-fetched picture-URL & e-mail (from “Contact info”).
• Writes to CSV *after every profile* (safe resume).

Set env vars (or answer prompts):
    OPENAI_API_KEY   – GPT-4o-mini Vision used if provided, else Vision skipped
    LINKEDIN_EMAIL
    LINKEDIN_PASSWORD
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations
import os, csv, time, json, base64, logging
from pathlib import Path
from typing import Any, Dict

import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
)

# ── CONFIG ──────────────────────────────────────────────────────────────
IN_CSV   = Path("output/alumni_linkedin_urls_FOUND.csv")
OUT_CSV  = Path("output/alumni_linkedin_details.csv")
SHOTDIR  = Path("screenshots")
WAIT_HEAD   = 8         # seconds for top of profile
WAIT_MODAL  = 12        # contact-info modal
PAUSE_SCROLL= 0.3       # pause between scroll increments
PROMPT = (
    "From this LinkedIn profile page extract the following JSON object ONLY:\n"
    '{\n'
    ' "current_title": "", "current_company": "",\n'
    ' "second_title": "",  "second_company": "",\n'
    ' "third_title": "",   "third_company": "",\n'
    ' "location": "", "connections": "", "headline": "",\n'
    ' "experience": [],          # list of up to 3 strings "title @ company – dates"\n'
    ' "education":  [],          # list of schools EXCLUDING any National Defense University variants\n'
    ' "licenses":   [],          # list of up to 3 licenses / certs\n'
    ' "volunteering":[]          # list of up to 3 items\n'
    '}\n'
    "Return *pure JSON* – no markdown."
)

# ── LOGGING ──────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s – %(message)s")
logging.getLogger("selenium").setLevel(logging.WARNING)

# ── OPENAI VISION ────────────────────────────────────────────────────────
OPENAI_KEY = os.getenv("OPENAI_API_KEY") or input("OpenAI key (blank to skip): ").strip()
USE_VISION = bool(OPENAI_KEY)
if USE_VISION:
    from openai import OpenAI
    oaclient = OpenAI(api_key=OPENAI_KEY)

def call_vision(img: Path) -> Dict[str, Any]:
    if not USE_VISION:
        return {}
    try:
        b64 = base64.b64encode(img.read_bytes()).decode()
        rsp = oaclient.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                ],
            }],
            max_tokens=1024,
            temperature=0,
        )
        txt = rsp.choices[0].message.content
        if "```" in txt:                     # strip markdown fences
            txt = txt.split("```")[1] if txt.startswith("```") else txt.split("```")[0]
        return json.loads(txt)
    except Exception as e:                   # noqa: BLE001
        logging.error(f"Vision failed – {e}")
        return {}

# ── SELENIUM UTILITIES ──────────────────────────────────────────────────
def init_driver() -> webdriver.Chrome:
    opt = Options()
    opt.add_argument("--start-maximized")
    opt.add_argument("--disable-notifications")
    return webdriver.Chrome(options=opt)

def linkedin_login(driver: webdriver.Chrome, email: str, pwd: str) -> None:
    driver.get("https://www.linkedin.com/login")
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "username")))
    driver.find_element(By.ID, "username").send_keys(email)
    driver.find_element(By.ID, "password").send_keys(pwd)
    driver.find_element(By.XPATH, "//button[@type='submit']").click()
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.XPATH, "//input[contains(@placeholder,'Search')]"))
    )
    logging.info("Logged in.")

def scroll_full_page(driver: webdriver.Chrome) -> None:
    last_h = 0
    while True:
        driver.execute_script("window.scrollBy(0, 600);")
        time.sleep(PAUSE_SCROLL)
        new_h = driver.execute_script("return window.pageYOffset + window.innerHeight;")
        doc_h = driver.execute_script("return document.body.scrollHeight;")
        if new_h >= doc_h or new_h == last_h:
            break
        last_h = new_h
    # resize window to full height – allows single full-page screenshot
    full_h = driver.execute_script("return document.body.scrollHeight;")
    driver.set_window_size(1920, full_h)

def grab_dom_bits(driver: webdriver.Chrome) -> Dict[str, str]:
    out = {"profile_pic": "", "email": ""}
    # picture
    try:
        pic = driver.find_element(By.CSS_SELECTOR, "img.pv-top-card-profile-picture__image")
        out["profile_pic"] = pic.get_attribute("src")
    except NoSuchElementException:
        try:  # fallback
            pic = driver.find_element(By.CSS_SELECTOR, "img[id^='ember'][class*='profile']")
            out["profile_pic"] = pic.get_attribute("src")
        except NoSuchElementException:
            pass
    # email (contact modal)
    try:
        driver.find_element(By.ID, "top-card-text-details-contact-info").click()
        WebDriverWait(driver, WAIT_MODAL).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "section.artdeco-modal"))
        )
        try:
            mail = driver.find_element(By.CSS_SELECTOR, "a[href^='mailto:']")
            out["email"] = mail.get_attribute("href").replace("mailto:", "")
        except NoSuchElementException:
            pass
        # close
        try:
            driver.find_element(By.CSS_SELECTOR, "button[aria-label='Dismiss']").click()
        except NoSuchElementException:
            pass
    except NoSuchElementException:
        pass
    return out

# ── SCRAPER CORE ────────────────────────────────────────────────────────
def scrape_profile(driver: webdriver.Chrome) -> Dict[str, Any]:
    WebDriverWait(driver, WAIT_HEAD).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div.pv-text-details__left-panel"))
    )
    scroll_full_page(driver)

    SHOTDIR.mkdir(exist_ok=True)
    shot = SHOTDIR / f"{int(time.time()*1000)}.png"
    driver.save_screenshot(str(shot))

    dom = grab_dom_bits(driver)
    vis = call_vision(shot)
    # convert arrays to semicolon-strings for CSV
    for key in ("experience", "education", "licenses", "volunteering"):
        if key in vis and isinstance(vis[key], list):
            vis[key] = "; ".join(vis[key])
    return {**dom, **vis}

# ── MAIN RUN ────────────────────────────────────────────────────────────
def main() -> None:
    if not IN_CSV.exists():
        logging.error("Run the URL-scraper first – input file missing.")
        return

    email = os.getenv("LINKEDIN_EMAIL") or input("LinkedIn email: ").strip()
    pwd   = os.getenv("LINKEDIN_PASSWORD") or input("LinkedIn password: ").strip()

    base_df = pd.read_csv(IN_CSV)
    out_cols = list(base_df.columns) + [
        "current_title","current_company","second_title","second_company",
        "third_title","third_company","location","connections","headline",
        "profile_pic","email","experience","education","licenses","volunteering",
    ]

    done: set[str] = set()
    if OUT_CSV.exists():
        done = set(pd.read_csv(OUT_CSV)["linkedin_profile"].dropna())
        logging.info(f"Resuming – {len(done)} profiles done")

    OUT_CSV.parent.mkdir(exist_ok=True)
    fout = OUT_CSV.open("a", newline="", encoding="utf-8")
    writer = csv.DictWriter(fout, fieldnames=out_cols)
    if not OUT_CSV.exists() or OUT_CSV.stat().st_size == 0:
        writer.writeheader()

    drv = init_driver()
    try:
        linkedin_login(drv, email, pwd)
        time.sleep(2)

        for row in base_df.itertuples(index=False):
            url = str(row.linkedin_profile)
            if not url.startswith("http") or url in done:
                continue

            logging.info(f"→ {row.firstname} {row.lastname}")
            try:
                drv.get(url)
                pdata = scrape_profile(drv)
            except (TimeoutException, WebDriverException) as e:  # skip failures
                logging.error(f"{url} failed – {e}")
                pdata = {}

            record = {**row._asdict(), **pdata}
            writer.writerow(record)
            fout.flush()
            done.add(url)
            time.sleep(1.5)

    finally:
        drv.quit()
        fout.close()
        logging.info(f"Finished – {len(done)} profiles written to {OUT_CSV}")

if __name__ == "__main__":
    main()
