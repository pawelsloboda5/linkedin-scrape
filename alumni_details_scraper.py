"""
alumni_details_scraper.py  –  enrich LinkedIn profile URLs with rich data
────────────────────────────────────────────────────────────────────────────
INPUT  : output/alumni_linkedin_urls_FOUND.csv   (URLs scraped previously)
OUTPUT : output/alumni_linkedin_details.csv      (appends / resumes safely)

New columns captured
────────────────────
current_title/current_company · second/third titles + companies · location
connections · headline · profile_pic · email
experience / education / licenses / volunteering   (lists ⇒ “; ”-joined)

Technique
─────────
• Logs in once with Selenium.
• For each profile
    – scrolls to Experience/Education/Licenses/Volunteering & bottom (lazy load)
    – jumps back to the very top, screenshots full page
    – sends screenshot to GPT-4o-mini Vision (JSON-only prompt)
    – pulls picture + e-mail via DOM (click-intercept safe)
    – writes CSV row immediately (resume-proof)
"""

from __future__ import annotations
import os, csv, time, json, base64, logging, re
from pathlib import Path
from typing import Any, Dict, List

import dotenv, pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, WebDriverException
)

dotenv.load_dotenv()

# ───────────────────────────── config ────────────────────────────────────
IN_CSV   = Path("output/alumni_linkedin_urls_FOUND.csv")
OUT_CSV  = Path("output/alumni_linkedin_details.csv")
SHOTDIR  = Path("screenshots")

WAIT_HEAD    = 20
HEAD_CSS     = (
    "div.pv-text-details__left-panel",      # classic layout
    "div.ph5.pb5",                          # 2024-2025 layout
    "section.pv-top-card",
)
WAIT_MODAL   = 12
PAUSE_SCROLL = 0.50

SECTIONS = tuple(re.compile(p, re.I) for p in (
    r"^experience", r"^education", r"^licenses? &", r"^volunteer"
))

PROMPT = (
    "Return ONLY the following JSON object extracted from this LinkedIn profile "
    "page (omit markdown):\n"
    '{ "current_title":"","current_company":"",'
    '  "second_title":"","second_company":"",'
    '  "third_title":"","third_company":"",'
    '  "location":"","connections":"","headline":"",'
    '  "experience":[], "education":[], "licenses":[], "volunteering":[] }'
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S"
)
logging.getLogger("selenium").setLevel(logging.WARNING)

# ─────────────────────── OpenAI Vision helper ────────────────────────────
OPENAI_KEY = os.getenv("OPENAI_API_KEY") or input("OpenAI key (blank to skip): ").strip()
USE_VISION = bool(OPENAI_KEY)
if USE_VISION:
    from openai import OpenAI
    oaclient = OpenAI(api_key=OPENAI_KEY)

def call_vision(img: Path) -> Dict[str, Any]:
    """Send screenshot to GPT-4o-mini Vision and return dict (may be {})."""
    if not USE_VISION:
        logging.debug("Vision disabled.")
        return {}
    try:
        b64 = base64.b64encode(img.read_bytes()).decode()
        rsp = oaclient.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text",  "text": PROMPT},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{b64}"}}]}],
            max_tokens=900, temperature=0,
        )
        raw = rsp.choices[0].message.content.strip().strip("```").strip()
        data = json.loads(raw)
        logging.debug(f"Vision JSON keys → {list(data)}")
        return data
    except Exception as e:
        logging.error(f"Vision parse error – {e}")
        return {}

# ───────────────────────── Selenium helpers ─────────────────────────────
def init_driver() -> webdriver.Chrome:
    opts = Options()
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-notifications")
    return webdriver.Chrome(options=opts)

def linkedin_login(drv: webdriver.Chrome, email: str, pwd: str) -> None:
    drv.get("https://www.linkedin.com/login")
    WebDriverWait(drv, 20).until(EC.presence_of_element_located((By.ID, "username")))
    drv.find_element(By.ID, "username").send_keys(email)
    drv.find_element(By.ID, "password").send_keys(pwd)
    drv.find_element(By.XPATH, "//button[@type='submit']").click()
    WebDriverWait(drv, 20).until(
        EC.presence_of_element_located((By.XPATH, "//input[contains(@placeholder,'Search')]"))
    )
    logging.info("✔ Logged in.")

# ─────────────── scrolling & loading helpers ────────────────────────────
def _scroll_into(drv: webdriver.Chrome, elem) -> None:
    drv.execute_script("arguments[0].scrollIntoView({block:'center'})", elem)
    time.sleep(0.4)

def ensure_sections_loaded(drv: webdriver.Chrome) -> None:
    """Scroll to each desired section header then to page bottom."""
    for h in drv.find_elements(By.CSS_SELECTOR, "section h2"):
        if any(pat.match(h.text.strip().lower()) for pat in SECTIONS):
            _scroll_into(drv, h)

    last = 0
    while True:
        drv.execute_script("window.scrollBy(0, 700);")
        time.sleep(PAUSE_SCROLL)
        seen = drv.execute_script("return window.pageYOffset + window.innerHeight;")
        total = drv.execute_script("return document.body.scrollHeight;")
        if seen >= total or seen == last:
            break
        last = seen
    drv.set_window_size(1920, drv.execute_script("return document.body.scrollHeight"))
    logging.debug("Sections loaded & full height set.")

# ───────────────────── DOM-extracted bits ───────────────────────────────
def grab_dom_bits(drv: webdriver.Chrome) -> Dict[str, str]:
    out = {"profile_pic": "", "email": ""}

    # ▸ profile picture ---------------------------------------------------
    for sel in (
        "img.pv-top-card-profile-picture__image",
        "img.profile-photo-edit__preview",
        "img[id^='ember'][class*='profile']",
    ):
        try:
            out["profile_pic"] = drv.find_element(By.CSS_SELECTOR, sel).get_attribute("src")
            break
        except NoSuchElementException:
            continue

    # ▸ contact-info modal (robust click + 32-px nudge) -------------------
    try:
        drv.execute_script("window.scrollTo(0,0);")
        drv.execute_script("window.scrollBy(0,32);")          # avoid sticky nav overlap
        link = drv.find_element(By.ID, "top-card-text-details-contact-info")
        try:
            link.click()
        except WebDriverException:
            drv.execute_script("arguments[0].click();", link)

        WebDriverWait(drv, WAIT_MODAL).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "section.artdeco-modal"))
        )
        try:
            mail = drv.find_element(By.CSS_SELECTOR, "a[href^='mailto:']")
            out["email"] = mail.get_attribute("href").replace("mailto:", "")
        except NoSuchElementException:
            pass
        drv.find_element(By.CSS_SELECTOR, "button[aria-label='Dismiss']").click()
    except NoSuchElementException:
        logging.debug("Contact-info link not present.")

    return out

# ───────────────────── profile-level scrape ──────────────────────────────
def scrape_profile(drv: webdriver.Chrome) -> Dict[str, Any]:
    WebDriverWait(drv, WAIT_HEAD).until(
        lambda d: any(d.find_elements(By.CSS_SELECTOR, sel) for sel in HEAD_CSS)
    )
    ensure_sections_loaded(drv)
    drv.execute_script("window.scrollTo(0,0);")
    time.sleep(0.6)

    SHOTDIR.mkdir(exist_ok=True)
    shot = SHOTDIR / f"{int(time.time()*1000)}.png"
    drv.save_screenshot(str(shot))
    logging.debug(f"Screenshot saved → {shot.name}")

    dom, vis = {}, {}
    try:
        dom = grab_dom_bits(drv)
    except Exception as e:
        logging.warning(f"DOM bits failed – {e}")

    try:
        vis = call_vision(shot)
    except Exception as e:
        logging.warning(f"Vision call failed – {e}")

    for k in ("experience", "education", "licenses", "volunteering"):
        if isinstance(vis.get(k), list):
            vis[k] = "; ".join(vis[k])

    logging.info(f"Collected keys → {list({**dom, **vis})}")
    return {**dom, **vis}

# ─────────────────────────────── main ────────────────────────────────────
def main() -> None:
    if not IN_CSV.exists():
        logging.error("Input URL list missing – run the URL scraper first.")
        return

    email = os.getenv("LINKEDIN_EMAIL")     or input("LinkedIn e-mail : ").strip()
    pwd   = os.getenv("LINKEDIN_PASSWORD")  or input("LinkedIn password: ").strip()

    base = pd.read_csv(IN_CSV)
    out_cols = list(base.columns) + [
        "current_title","current_company","second_title","second_company",
        "third_title","third_company","location","connections","headline",
        "profile_pic","email","experience","education","licenses","volunteering",
    ]

    done: set[str] = set()
    if OUT_CSV.exists():
        done = set(pd.read_csv(OUT_CSV)["linkedin_profile"].dropna())
        logging.info(f"Resuming – {len(done)} already done.")

    OUT_CSV.parent.mkdir(exist_ok=True)
    new_file = not OUT_CSV.exists() or OUT_CSV.stat().st_size == 0
    fout   = OUT_CSV.open("a", newline="", encoding="utf-8")
    writer = csv.DictWriter(fout, fieldnames=out_cols)
    if new_file:
        writer.writeheader()

    drv = init_driver()
    try:
        linkedin_login(drv, email, pwd)
        time.sleep(2)

        for r in base.itertuples(index=False):
            url = str(r.linkedin_profile)
            if not url.startswith("http") or url in done:
                continue

            logging.info(f"⇒ {r.firstname} {r.lastname} | {url.split('/')[-1]}")
            try:
                drv.get(url)
                pdata = scrape_profile(drv)
            except (TimeoutException, WebDriverException) as e:
                logging.error(f"⚠ Skipped – {e}")
                pdata = {}

            writer.writerow({**r._asdict(), **pdata})
            fout.flush()
            done.add(url)
            logging.debug("Row written & flushed.")
            time.sleep(1.5)

    finally:
        drv.quit()
        fout.close()
        logging.info(f"✓ Finished – total rows now {len(done)} in {OUT_CSV}")

if __name__ == "__main__":
    main()
