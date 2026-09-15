"""
02_clean_arrivals.py
----------------------
Issues fixed here, in the order they're handled:

  1. mandi_id     -> 6 raw shapes collapsed to one (see common.py)
  2. crop_name    -> Hindi/Punjabi/English variants merged (see common.py)
  3. date         -> 6 raw formats, resolved deterministically (see common.py)
  4. quantity+unit -> THE hard one. Two different messiness patterns exist
     in the same column:
       (a) a clean number in `arrival_quantity` + a separate `unit` column
           ("332.54", unit="Qtl")
       (b) the unit stuck INSIDE the quantity string with `unit` blank
           ("415.88 qtl", unit=NaN)
     Both have to end up as the same thing: quintals.
  5. negative quantities -> physically impossible (a mandi can't receive
     -107 quintals of maize). We take the absolute value AND keep a flag
     column so anyone auditing the data can see exactly which rows were
     touched — silently flipping a sign without saying so would be hiding
     a data quality problem, not fixing it.
"""

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent))
from common import canonical_crop, canonical_mandi_id, parse_messy_date

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IN_PATH = PROJECT_ROOT / "data" / "raw" / "track3_mandi_arrivals.csv"
OUT_PATH = PROJECT_ROOT / "data" / "processed" / "fact_arrivals.csv"

# 1 Quintal = 100 KG, 1 Tonne = 10 Quintal (stated explicitly in the dataset notes)
UNIT_TO_QUINTAL = {
    "kg": 1 / 100, "kgs": 1 / 100, "kilo": 1 / 100,
    "q": 1, "qtl": 1, "quintal": 1, "quintals": 1,
    "t": 10, "mt": 10, "tonnes": 10, "tonne": 10,
}

_QTY_UNIT_PATTERN = re.compile(r"([\d.]+)\s*([a-zA-Z]+)")


def split_quantity_and_unit(raw_qty, raw_unit):
    """Handles BOTH messiness patterns described above in one function."""
    if pd.notna(raw_unit) and str(raw_unit).strip() != "":
        qty = pd.to_numeric(raw_qty, errors="coerce")
        unit = str(raw_unit).strip().lower()
        return qty, unit

    # unit column was blank -> it must be embedded in the quantity text
    match = _QTY_UNIT_PATTERN.search(str(raw_qty))
    if match:
        return float(match.group(1)), match.group(2).strip().lower()
    return pd.to_numeric(raw_qty, errors="coerce"), None


def run() -> pd.DataFrame:
    df = pd.read_csv(IN_PATH)
    raw_rows = len(df)

    df["mandi_id"] = df["mandi_id"].map(canonical_mandi_id)
    df["crop"] = df["crop_name"].map(canonical_crop)
    df["arrival_date"] = parse_messy_date(df["date"])

    qty_unit = df.apply(lambda r: split_quantity_and_unit(r["arrival_quantity"], r["unit"]), axis=1)
    df["qty_raw"] = qty_unit.map(lambda t: t[0])
    df["unit_raw"] = qty_unit.map(lambda t: t[1])
    df["unit_factor"] = df["unit_raw"].map(UNIT_TO_QUINTAL)

    unresolved_unit = df["unit_factor"].isna() & df["qty_raw"].notna()
    print(f"[fact_arrivals] rows with unresolved unit (defaulted to Quintal): {unresolved_unit.sum()}")
    df.loc[unresolved_unit, "unit_factor"] = 1.0  # safest default: assume already Quintal

    df["was_negative_qty"] = df["qty_raw"] < 0
    df["arrival_quintal"] = (df["qty_raw"].abs() * df["unit_factor"]).round(2)

    unrecognised_crop = df["crop"].str.startswith("UNRECOGNISED").sum()
    unparsed_date = df["arrival_date"].isna().sum()

    before_hard_drop = len(df)
    df = df.dropna(subset=["mandi_id", "arrival_date", "arrival_quintal"])
    hard_dropped = before_hard_drop - len(df)

    keep_cols = ["arrival_id", "arrival_date", "mandi_id", "crop", "variety",
                 "arrival_quintal", "was_negative_qty", "farmer_count"]
    clean_df = df[keep_cols].sort_values(["arrival_date", "mandi_id"])
    clean_df.to_csv(OUT_PATH, index=False)

    print("\n----- ARRIVALS CLEANING SUMMARY -----")
    print(f"Raw rows              : {raw_rows}")
    print(f"Clean rows            : {len(clean_df)}")
    print(f"Dropped (unrecoverable): {hard_dropped}")
    print(f"Unrecognised crop names: {unrecognised_crop}")
    print(f"Unparseable dates      : {unparsed_date}")
    print(f"Negative quantities fixed (abs taken, flagged): {int(clean_df['was_negative_qty'].sum())}")
    print(f"Wrote {OUT_PATH}")
    return clean_df


if __name__ == "__main__":
    run()
