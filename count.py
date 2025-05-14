import pandas as pd
from pathlib import Path

# ---- paths ---------------------------------------------------------
SRC_CSV   = "output/alumni_linkedin_urls.csv"        # source file
DEST_CSV  = "output/alumni_linkedin_urls_FOUND.csv"  # rows with real URLs

# ---- load & analyse -----------------------------------------------
df = pd.read_csv(SRC_CSV)

mask_found = df["linkedin_profile"].str.upper() != "NOT FOUND"
n_found    = mask_found.sum()
n_missing  = (~mask_found).sum()

print(f"Total rows   : {len(df):,}")
print(f"Found URLs   : {n_found:,}")
print(f"NOT FOUND    : {n_missing:,}")

# ---- save only rows that have a URL --------------------------------
Path(DEST_CSV).parent.mkdir(exist_ok=True)
df[mask_found].to_csv(DEST_CSV, index=False)
print(f"Saved {n_found:,} rows with LinkedIn URLs → {DEST_CSV}")
