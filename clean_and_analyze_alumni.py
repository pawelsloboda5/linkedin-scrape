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

# Configure matplotlib to use a non-interactive backend (avoids Tk dependency)
import matplotlib
matplotlib.use("Agg")

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# ─────────────────────── paths ──────────────────────────────────────────
RAW_CSV   = Path("output/alumni_linkedin_details.csv")
CLEAN_CSV = Path("output/alumni_linkedin_details_clean.csv")
PLOT_DIR  = Path("output/plots")

# Ensure output directories exist
CLEAN_CSV.parent.mkdir(parents=True, exist_ok=True)
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
    clean_df.to_csv(CLEAN_CSV, index=False, encoding="utf-8")
    try:
        rel_path = CLEAN_CSV.resolve().relative_to(Path.cwd())
    except ValueError:
        rel_path = CLEAN_CSV.resolve()
    print(f"✔ Clean CSV written → {rel_path}")

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
    excel_file = CLEAN_CSV.with_suffix(".xlsx")
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