"""
01_clean_mandi_master.py
-------------------------
The master table is the *dimension* every fact table joins to, so it gets
cleaned first and gets zero tolerance for duplicate IDs — a duplicate here
would silently double-count every arrival/price/trip joined to it.

Issues fixed here specifically:
  - district casing ("ludhiana", "LUDHIANA", "Ludhiana" -> "Ludhiana")
  - mandi_type casing ("PRIVATE", "apmc" -> "Private", "APMC")
  - exact duplicate rows (same mandi_id repeated)
  - missing district/state -> kept as "Unknown", NOT dropped (a mandi with
    a missing district still has real arrivals we don't want to lose)
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent))
from common import canonical_mandi_id

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IN_PATH = PROJECT_ROOT / "data" / "raw" / "track3_mandi_master.csv"
OUT_PATH = PROJECT_ROOT / "data" / "processed" / "dim_mandi.csv"


def run() -> pd.DataFrame:
    df = pd.read_csv(IN_PATH)
    raw_rows = len(df)

    df["mandi_id"] = df["mandi_id"].map(canonical_mandi_id)
    df["district"] = df["district"].str.strip().str.title().fillna("Unknown")
    df["state"] = df["state"].str.strip().str.title().fillna("Unknown")
    df["mandi_type"] = df["mandi_type"].str.strip().str.title().fillna("Unknown")
    df["total_area_acres"] = pd.to_numeric(df["total_area_acres"], errors="coerce")

    before_dedup = len(df)
    df = df.drop_duplicates(subset=["mandi_id"], keep="first")
    dupes_removed = before_dedup - len(df)

    df.to_csv(OUT_PATH, index=False)

    print(f"[dim_mandi] raw rows: {raw_rows} | clean rows: {len(df)} | exact duplicates removed: {dupes_removed}")
    print(f"[dim_mandi] districts still 'Unknown': {(df['district'] == 'Unknown').sum()}")
    print(f"[dim_mandi] wrote {OUT_PATH}")
    return df


if __name__ == "__main__":
    run()
