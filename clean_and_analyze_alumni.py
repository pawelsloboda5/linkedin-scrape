#!/usr/bin/env python3
"""
clean_and_analyze_alumni.py
───────────────────────────
Utility script for the School of Information (**NDU**) that:
1. Reads the raw `output/alumni_linkedin_details.csv` produced by the scraper.
2. Applies light cleaning so the Dean can open an immaculate sheet in Excel.
3. Exports the cleaned data to `output/alumni_linkedin_details_clean.csv`.
4. Creates a handful of informative charts (PNG format) in `output/plots/` to
   highlight cohort statistics and fun facts for 2014-2024 alumni.

Usage (inside project root):
    python clean_and_analyze_alumni.py

Dependencies: pandas, seaborn, matplotlib  (already standard in most DS stacks)
"""

from __future__ import annotations

import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

# Configure matplotlib to use a non-interactive backend (avoids Tk dependency)
import matplotlib
matplotlib.use("Agg")

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from dateutil.parser import parse as date_parse

# ─────────────────────── paths ──────────────────────────────────────────
RAW_CSV     = Path("output/alumni_linkedin_details.csv")
BASE_CSV    = Path("output/alumni_linkedin_details_clean.csv")
EXP_CSV     = Path("output/alumni_experience.csv")
EDU_CSV     = Path("output/alumni_education.csv")
LIC_CSV     = Path("output/alumni_licenses.csv")
VOL_CSV     = Path("output/alumni_volunteering.csv")

PLOT_DIR    = Path("output/plots")

# Ensure output directories exist
BASE_CSV.parent.mkdir(parents=True, exist_ok=True)
PLOT_DIR.mkdir(parents=True, exist_ok=True)

# ─────────────────────── cleaning helpers ───────────────────────────────

BASE64_PATTERN = re.compile(r"^data:image/[^;]+;base64,", re.I)
DIGITS_PATTERN = re.compile(r"(\d+)")


def _strip_base64(val: str) -> str:
    """Remove inline base-64 images (Excel chokes on very long cells)."""
    if isinstance(val, str) and BASE64_PATTERN.match(val):
        return ""
    return val


def _clean_connections(val: str | int | float) -> int | None:
    """Convert connection strings like "500+" or "1,234" to int."""
    if pd.isna(val):
        return None
    if isinstance(val, (int, float)):
        return int(val)
    m = DIGITS_PATTERN.search(str(val).replace(",", ""))
    return int(m.group(1)) if m else None


# ─────────────────────── main cleaning routine ──────────────────────────

def _safe_json_loads(raw: str) -> Any:
    """Attempt to json.loads even when single quotes used."""
    import json
    try:
        return json.loads(raw)
    except Exception:
        try:
            fixed = re.sub(r"'", '"', raw)
            return json.loads(fixed)
        except Exception:
            return None


def _parse_date(token: str) -> datetime | None:
    token = token.strip()
    if token.lower() in {"present", "current", "now"}:
        return None
    try:
        dt = date_parse(token, default=datetime(1900, 1, 1))
        return dt
    except Exception:
        return None


def _split_date_range(range_str: str) -> tuple[datetime | None, datetime | None]:
    parts = [p.strip() for p in re.split(r"[–-]", range_str, maxsplit=1)]
    if len(parts) == 2:
        return _parse_date(parts[0]), _parse_date(parts[1])
    return _parse_date(parts[0]), None


def _explode_series(name: str, series: pd.Series) -> pd.DataFrame:
    """Turn semicolon-separated strings into long form with seq index."""
    rows: List[Dict[str, Any]] = []
    for link, cell in series.items():
        if pd.isna(cell) or not str(cell).strip():
            continue
        items = [i.strip() for i in str(cell).split("; ") if i.strip()]
        for idx, itm in enumerate(items, start=1):
            rows.append({"linkedin_profile": link, "seq": idx, name: itm})
    return pd.DataFrame(rows)


def _parse_experience(df: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for link, cell in df["experience"].items():
        if pd.isna(cell) or not str(cell).strip():
            continue
        items = [i.strip() for i in str(cell).split("; ") if i.strip()]
        for seq, item in enumerate(items, start=1):
            m = re.match(r"(?P<title>.*?)\s*@\s*(?P<company>.*?)\s*[–-]\s*(?P<dates>.*)", item)
            if m:
                title   = m.group("title").strip()
                company = m.group("company").strip()
                date_rng= m.group("dates").strip()
                start_d, end_d = _split_date_range(date_rng)
            else:
                title = company = item
                start_d = end_d = None
            rows.append({
                "linkedin_profile": link,
                "seq": seq,
                "title": title,
                "company": company,
                "start_date": start_d,
                "end_date": end_d,
            })
    return pd.DataFrame(rows)


def load_and_clean() -> pd.DataFrame:
    if not RAW_CSV.exists():
        raise FileNotFoundError(f"Raw CSV not found at {RAW_CSV!s}")

    # Read everything as string to keep initial cleaning simple
    df = pd.read_csv(RAW_CSV, dtype=str, keep_default_na=False)

    # 1️⃣ Trim whitespace & newlines (applymap is deprecated from pandas 3.2)
    for col in df.columns:
        df[col] = (
            df[col]
            .astype(str)
            .str.replace("\n", " ", regex=False)
            .str.strip()
        )

    # 2️⃣ Drop duplicate LinkedIn profiles (should be unique key)
    df = df.drop_duplicates(subset="linkedin_profile", keep="first")

    # 3️⃣ Clean heavy / unnecessary fields
    df["profile_pic"] = df["profile_pic"].map(_strip_base64)

    # 4️⃣ Sanitize numeric-ish fields
    df["connections"] = df["connections"].map(_clean_connections)

    # 5️⃣ (optional) sort for nicer appearance
    df = df.sort_values(by=["lastname", "firstname"]).reset_index(drop=True)

    # 6️⃣ split location
    loc_split = df["location"].str.split(r",\s*", expand=True)
    if not loc_split.empty:
        df["city"]     = loc_split[0]
        df["state"]    = loc_split[1] if loc_split.shape[1] > 1 else pd.NA
        df["country"]  = loc_split[2] if loc_split.shape[1] > 2 else pd.NA

    # 7️⃣ replace blank strings with NA
    df.replace({"": pd.NA}, inplace=True)

    return df


# ─────────────────────── visualization helpers ─────────────────────────

def plot_bar(series: pd.Series, title: str, fname: str, top_n: int = 10):
    top = series.value_counts().head(top_n).sort_values(ascending=True)
    plt.figure(figsize=(8, max(3, 0.4 * len(top))))
    sns.barplot(x=top.values, y=top.index, palette="viridis")
    plt.title(title)
    plt.xlabel("Count")
    plt.tight_layout()
    plt.savefig(PLOT_DIR / fname)
    plt.close()


def plot_hist(series: pd.Series, title: str, fname: str, bins: int = 10):
    plt.figure(figsize=(7, 4))
    sns.histplot(series.dropna(), kde=False, bins=bins, color="#4C72B0")
    plt.title(title)
    plt.xlabel(series.name)
    plt.ylabel("Frequency")
    plt.tight_layout()
    plt.savefig(PLOT_DIR / fname)
    plt.close()


# ─────────────────────── orchestrator ──────────────────────────────────

def main() -> None:
    print("Loading & cleaning …")
    clean_df = load_and_clean()

    # Export to clean CSV (UTF-8 w/out BOM for Excel compatibility)
    clean_df.to_csv(BASE_CSV, index=False, encoding="utf-8")
    try:
        rel_path = BASE_CSV.resolve().relative_to(Path.cwd())
    except ValueError:
        rel_path = BASE_CSV.resolve()
    print(f"✔ Clean CSV written → {rel_path}")

    # ───────── child tables ─────────
    print("Normalizing experience/education/licensing/volunteering …")
    base_idx = clean_df.set_index("linkedin_profile")

    exp_df = _parse_experience(base_idx)
    edu_df = _explode_series("education", base_idx["education"])
    lic_df = _explode_series("licenses",  base_idx["licenses"])
    vol_df = _explode_series("volunteering", base_idx["volunteering"])

    exp_df.to_csv(EXP_CSV, index=False)
    edu_df.to_csv(EDU_CSV, index=False)
    lic_df.to_csv(LIC_CSV, index=False)
    vol_df.to_csv(VOL_CSV, index=False)

    print("✔ Child tables saved (experience, education, licenses, volunteering)")

    # ───────── generate fun stats ─────────
    print("Generating plots …")
    plot_bar(clean_df["program"], "Top Programs (count)", "program_counts.png")
    plot_bar(clean_df["current_company"], "Top Current Companies (top 10)", "company_counts.png")
    plot_bar(clean_df["location"], "Top Locations (top 10)", "location_counts.png")
    plot_hist(clean_df["connections"].astype(float), "Distribution of LinkedIn Connections", "connections_hist.png", bins=15)

    try:
        plots_rel = PLOT_DIR.resolve().relative_to(Path.cwd())
    except ValueError:
        plots_rel = PLOT_DIR.resolve()
    print(f"✔ Plots stored in {plots_rel} (PNG files)")

    # ───────── embed into Excel ─────────
    excel_file = BASE_CSV.with_suffix(".xlsx")
    print("Creating Excel workbook with embedded charts …")
    try:
        with pd.ExcelWriter(excel_file, engine="xlsxwriter") as writer:
            clean_df.to_excel(writer, sheet_name="Alumni", index=False)

            workbook  = writer.book
            chart_ws  = workbook.add_worksheet("Charts")

            row = 0
            for img in sorted(PLOT_DIR.glob("*.png")):
                chart_ws.write(row, 0, img.stem.replace("_", " ").title())
                chart_ws.insert_image(row + 1, 0, str(img), {"x_scale": 0.9, "y_scale": 0.9})
                row += 26  # adjust spacing between charts

        try:
            rel_excel = excel_file.resolve().relative_to(Path.cwd())
        except ValueError:
            rel_excel = excel_file.resolve()
        print(f"✔ Excel workbook created → {rel_excel}")
    except ImportError:
        print("⚠ xlsxwriter not available – skipped Excel embedding. `pip install xlsxwriter` to enable this feature.")


if __name__ == "__main__":
    main() 