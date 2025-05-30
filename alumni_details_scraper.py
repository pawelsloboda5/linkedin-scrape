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
    "div.ph5.pb5",                          # 2024‑2025 layout
    "section.pv-top-card",
)
WAIT_MODAL   = 12
PAUSE_SCROLL = 0.35

SECTION_REGEX = {
    "experience": re.compile(r"^experience", re.I),
    "education" : re.compile(r"^education",  re.I),
    "licenses"  : re.compile(r"^licenses? &", re.I),
    "volunteering": re.compile(r"^volunteer", re.I),
}

PROMPTS: Dict[str, str] = {
    # prompt texts kept minimal to save tokens
    "header": (
        "Return ONLY the following JSON (no markdown):\n"
        '{ "current_title":"", "current_company":"", "second_title":"", "second_company":"", '
        '  "third_title":"", "third_company":"", "location":"", "connections":"", "headline":"" }'
    ),
    "experience": (
        "Return ONLY JSON: { \"experience\": [] } where the list contains the top-3 items formatted as 'Title @ Company – Dates'."
    ),
    "education":  "Return ONLY JSON: { \"education\": [] } listing schools other than NDU (max 3)",
    "licenses":   "Return ONLY JSON: { \"licenses\": [] } listing up to 3 license names",
    "volunteering": "Return ONLY JSON: { \"volunteering\": [] } listing up to 3 items",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("selenium").setLevel(logging.WARNING)

# ─────────────────────── OpenAI Vision helper ────────────────────────────
OPENAI_KEY = os.getenv("OPENAI_API_KEY") or input("OpenAI key (blank to skip Vision): ").strip()
USE_VISION = bool(OPENAI_KEY)
if USE_VISION:
    from openai import OpenAI
    oaclient = OpenAI(api_key=OPENAI_KEY)

def call_vision(img: Path, prompt: str) -> Dict[str, Any]:
    """Send image screenshot + prompt to GPT‑4o‑mini Vision and return a dict."""
    if not USE_VISION:
        logging.debug("Vision disabled → returning empty dict.")
        return {}
    try:
        b64 = base64.b64encode(img.read_bytes()).decode()
        rsp = oaclient.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            }],
            max_tokens=900,
            temperature=0,
        )
        content = rsp.choices[0].message.content

        # ── attempt direct parse ──
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # ── strip common code-block fences ──
        cleaned = content.strip()
        if cleaned.startswith("```"):
            # remove leading and trailing ``` with optional "json"
            cleaned = re.sub(r"^```[a-zA-Z]*", "", cleaned)
            cleaned = re.sub(r"```$", "", cleaned).strip()

        # direct try again
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # ── fallback: grab first {...} blob ──
            m = re.search(r"{.*}", cleaned, flags=re.S)
            if m:
                try:
                    return json.loads(m.group(0))
                except json.JSONDecodeError:
                    pass

        raise ValueError("Unable to parse JSON from vision response")
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
    time.sleep(0.3)


def ensure_sections_loaded(drv: webdriver.Chrome) -> None:
    """Fast‑scroll page so that lazy‑loaded items for every desired section are rendered."""
    for h in drv.find_elements(By.CSS_SELECTOR, "section h2"):
        if any(pat.match(h.text.strip()) for pat in SECTION_REGEX.values()):
            _scroll_into(drv, h)

    last = 0
    while True:
        drv.execute_script("window.scrollBy(0, 600);")
        time.sleep(PAUSE_SCROLL)
        seen = drv.execute_script("return window.pageYOffset + window.innerHeight;")
        total = drv.execute_script("return document.body.scrollHeight;")
        if seen >= total or seen == last:
            break
        last = seen
    logging.debug("All sections loaded.")

# ───────────────────── DOM bits (pic & email) ───────────────────────────

def grab_dom_bits(drv: webdriver.Chrome, extract_contact_info: bool) -> Dict[str, str]:
    out = {"profile_pic": "", "email": ""}

    # ▸ profile picture
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

    # ▸ e‑mail via contact modal
    if extract_contact_info:
        try:
            drv.execute_script("window.scrollTo(0,0);")
            drv.execute_script("window.scrollBy(0,32);")
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
            logging.debug("Contact‑info link not present.")

    return out

# ───────────────────── utilities for screenshots ────────────────────────

def _slugify(text: str) -> str:
    """Return a filesystem-friendly slug."""
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()


def screenshot_element(drv: webdriver.Chrome, elem, label: str, person_slug: str = "") -> Path:
    """Capture a screenshot of a specific DOM element.

    If *person_slug* is supplied (e.g. "john_doe"), the filename becomes
    "john_doe_header_<ts>.png" for easier traceability.
    """
    SHOTDIR.mkdir(exist_ok=True)
    base = f"{person_slug + '_' if person_slug else ''}{label}_{int(time.time()*1000)}.png"
    path = SHOTDIR / base
    try:
        _scroll_into(drv, elem)
        elem.screenshot(str(path))
    except Exception:
        drv.save_screenshot(str(path))  # fallback to full-page
    return path

# ───────────────────── profile‑level scrape ─────────────────────────────

def scrape_profile(
    drv: webdriver.Chrome,
    extract_contact_info: bool,
    person_slug: str = "",
) -> Dict[str, Any]:
    # wait until header visible
    WebDriverWait(drv, WAIT_HEAD).until(
        lambda d: any(d.find_elements(By.CSS_SELECTOR, sel) for sel in HEAD_CSS)
    )
    ensure_sections_loaded(drv)

    data: Dict[str, Any] = {}

    # 1️⃣ header
    header_elem = None
    for sel in HEAD_CSS:
        if elems := drv.find_elements(By.CSS_SELECTOR, sel):
            header_elem = elems[0]
            break
    if header_elem is not None:
        shot = screenshot_element(drv, header_elem, "header", person_slug)
        data.update(call_vision(shot, PROMPTS["header"]))

    # 2️⃣ dynamic sections (exp/edu/lic/vol)
    for sec_name, regex in SECTION_REGEX.items():
        try:
            h2s = drv.find_elements(By.CSS_SELECTOR, "section h2")
            target_h = next((h for h in h2s if regex.match(h.text.strip())), None)
            if not target_h:
                continue
            section_elem = target_h.find_element(By.XPATH, "ancestor::section")
            shot = screenshot_element(drv, section_elem, sec_name, person_slug)
            payload = call_vision(shot, PROMPTS[sec_name])

            # ── special handling for experience: extract top-3 roles ──
            if sec_name == "experience" and isinstance(payload.get("experience"), list):
                exp_list = payload["experience"]
                # Fill title/company fields from first 3 entries
                for idx, item in enumerate(exp_list[:3]):
                    try:
                        # Expect format "Title @ Company – Dates"
                        title_part, rest = item.split("@", 1)
                        company_part = rest.split("–", 1)[0]
                        title_clean   = title_part.strip()
                        company_clean = company_part.strip()
                        if idx == 0:
                            data["current_title"]  = title_clean
                            data["current_company"] = company_clean
                        elif idx == 1:
                            data["second_title"]  = title_clean
                            data["second_company"] = company_clean
                        elif idx == 2:
                            data["third_title"]   = title_clean
                            data["third_company"]  = company_clean
                    except Exception as parse_err:
                        logging.debug(f"Experience parse failed ({item}) – {parse_err}")

                # store joined list for experience column
                payload["experience"] = "; ".join(exp_list)

            elif isinstance(payload.get(sec_name), list):
                # Coerce other list payloads to semicolon-separated string
                try:
                    payload[sec_name] = "; ".join(
                        str(item) if not isinstance(item, str) else item for item in payload[sec_name]
                    )
                except Exception as join_err:
                    logging.warning(f"{sec_name} join failed – {join_err}")

            data.update(payload)
        except Exception as e:
            logging.warning(f"{sec_name} capture failed – {e}")

    # 3️⃣ DOM‑extracted bits
    try:
        data.update(grab_dom_bits(drv, extract_contact_info))
    except Exception as e:
        logging.warning(f"DOM bits failed – {e}")

    logging.info(f"Collected keys → {list(data)}")
    return data

# ─────────────────────────────── main ────────────────────────────────────

def main() -> None:
    if not IN_CSV.exists():
        logging.error("Input URL list missing – run the URL scraper first.")
        return

    email = os.getenv("LINKEDIN_EMAIL") or input("LinkedIn e‑mail : ").strip()
    pwd   = os.getenv("LINKEDIN_PASSWORD") or input("LinkedIn password: ").strip()

    extract_contact_info_str = input("Try to extract contact info (email)? (y/n): ").strip().lower()
    extract_contact_info_bool = extract_contact_info_str == 'y'

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
                slug = _slugify(f"{r.firstname}_{r.lastname}")
                pdata = scrape_profile(drv, extract_contact_info_bool, person_slug=slug)
            except (TimeoutException, WebDriverException) as e:
                logging.error(f"⚠ Skipped – {e}")
                pdata = {}

            writer.writerow({**r._asdict(), **pdata})
            fout.flush()
            done.add(url)
            logging.debug("Row written & flushed.")
            time.sleep(1.3)

    finally:
        drv.quit()
        fout.close()
        logging.info(f"✓ Finished – total rows now {len(done)} in {OUT_CSV}")

if __name__ == "__main__":
    main()
