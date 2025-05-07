import os, time, json, base64, logging
from io import BytesIO
from pathlib import Path
from PIL import Image

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys               # ← NEW
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

from config import (
    TARGET_INSTITUTIONS,
    OUTPUT_SETTINGS,
    SEARCH_SETTINGS,
    LINKEDIN_SELECTORS,
    OPENAI_SETTINGS,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logging.getLogger("selenium").setLevel(logging.WARNING)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY and OPENAI_SETTINGS.get("enabled", False):
    OPENAI_API_KEY = input("Enter OpenAI / Azure‑OpenAI key (leave blank to disable): ")
    if not OPENAI_API_KEY:
        OPENAI_SETTINGS["enabled"] = False


class AlumniScraper:
    def __init__(self, email: str, password: str):
        self.email, self.password, self.driver = email, password, None

    # ── driver ──────────────────────────────────────────────────────────────
    def initialize_driver(self) -> bool:
        try:
            opts = Options()
            opts.add_argument("--start-maximized")
            opts.add_argument("--disable-notifications")
            self.driver = webdriver.Chrome(options=opts)  # Selenium‑Manager
            logging.info("ChromeDriver initialized")
            return True
        except WebDriverException as e:
            logging.error(f"Driver init failed: {e}")
            return False

    # ── login ───────────────────────────────────────────────────────────────
    def login(self) -> bool:
        try:
            self.driver.get("https://www.linkedin.com/login")
            WebDriverWait(self.driver, 15).until(EC.presence_of_element_located((By.ID, "username")))
            self.driver.find_element(By.ID, "username").send_keys(self.email)
            self.driver.find_element(By.ID, "password").send_keys(self.password)
            self.driver.find_element(By.XPATH, '//button[@type="submit"]').click()
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.XPATH, '//input[contains(@placeholder,"Search")]'))
            )
            logging.info("Login successful")
            return True
        except Exception as e:
            logging.error(f"Login failed: {e}")
            return False

    # ── search box helper (ENTER instead of .submit()) ──────────────────────
    def search_for_institution(self, inst: str) -> bool:
        try:
            query = inst.replace(" ", "%20")  # URL‑encode spaces
            url = (
                "https://www.linkedin.com/search/results/people/"
                f"?keywords={query}&origin=SWITCH_SEARCH_VERTICAL"
            )
            self.driver.get(url)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "main"))
            )
            return True
        except Exception as e:
            logging.error(f"Search error for {inst}: {e}")
            return False


class ScreenshotAlumniScraper(AlumniScraper):
    # dirs --------------------------------------------------
    @staticmethod
    def _ensure_dir(p: str | Path):
        Path(p).mkdir(parents=True, exist_ok=True)

    # screenshot -------------------------------------------
    def snap(self, fname: str) -> str:
        self._ensure_dir("screenshots")
        path = Path("screenshots") / fname
        self.driver.save_screenshot(str(path))
        return str(path)

    # vision -----------------------------------------------
    def vision_extract(self, img_path: str) -> list[dict]:
        if not (OPENAI_SETTINGS.get("enabled") and OPENAI_API_KEY):
            return []
        from openai import OpenAI, AzureOpenAI
        if OPENAI_SETTINGS.get("use_azure"):
            client = AzureOpenAI(
                api_key=OPENAI_API_KEY,
                azure_endpoint=OPENAI_SETTINGS["azure_api_url"].split("/openai")[0],
                api_version=OPENAI_SETTINGS["azure_api_url"].split("api-version=")[1],
            )
            model = OPENAI_SETTINGS["azure_deployment_id"]
        else:
            client = OpenAI(api_key=OPENAI_API_KEY)
            model = OPENAI_SETTINGS.get("model", "gpt-4o-mini")

        with open(img_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()

        resp = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": 'Extract JSON array "profiles" with keys [name, job_title, company, location].'},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]},
            ],
            max_tokens=512,
            temperature=0,
        )
        try:
            txt = resp.choices[0].message.content
            data = json.loads(txt.split("```")[-2] if "```" in txt else txt)
            return data["profiles"] if isinstance(data, dict) else data
        except Exception as e:
            logging.error(f"Vision parse error: {e}")
            return []

    # pagination -------------------------------------------
    def click_next(self) -> bool:
        for sel in LINKEDIN_SELECTORS["next_page_button"]:
            try:
                btn = WebDriverWait(self.driver, 4).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, sel) if not sel.startswith("//") else (By.XPATH, sel))
                )
                btn.click()
                time.sleep(SEARCH_SETTINGS["page_load_delay"])
                return True
            except Exception:
                continue
        return False

    def page_profiles(self, inst: str, pno: int) -> list[dict]:
        shot = self.snap(f"{inst.replace(' ', '_')}_p{pno}.png")
        profs = self.vision_extract(shot)
        for pr in profs:
            pr["searched_institution"], pr["page_found"] = inst, pno
        return profs

    # crawl ------------------------------------------------
    def crawl_inst(self, inst: str) -> list[dict]:
        if not self.search_for_institution(inst):
            return []
        time.sleep(SEARCH_SETTINGS["page_load_delay"])
        collected = []
        for p in range(1, SEARCH_SETTINGS["max_pages_per_institution"] + 1):
            logging.info(f"{inst}: page {p}")
            collected.extend(self.page_profiles(inst, p))
            if not self.click_next():
                break
        return collected

    def run_with_screenshots(self):
        if not (self.initialize_driver() and self.login()):
            return
        all_p = []
        for inst in TARGET_INSTITUTIONS:
            all_p.extend(self.crawl_inst(inst))
            self.save(all_p)
            time.sleep(SEARCH_SETTINGS["delay_between_profiles"])
        if self.driver:
            self.driver.quit()

    # save -------------------------------------------------
    def save(self, data: list[dict]):
        if not data:
            return
        self._ensure_dir("output")
        out = Path("output") / OUTPUT_SETTINGS["json_filename"]
        out.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logging.info(f"Saved {len(data)} profiles → {out}")


# ── entry ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    EMAIL = os.getenv("LINKEDIN_EMAIL") or input("LinkedIn email: ")
    PASS = os.getenv("LINKEDIN_PASSWORD") or input("LinkedIn password: ")

    bot = ScreenshotAlumniScraper(EMAIL, PASS)
    logging.info("Starting LinkedIn Screenshot Alumni Scraper")
    bot.run_with_screenshots()
