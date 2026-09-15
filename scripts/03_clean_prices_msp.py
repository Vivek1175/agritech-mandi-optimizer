"""
03_clean_prices_msp.py
-------------------------
Issues fixed:
  - min/max/modal price and msp all arrive as a mix of '₹7,570.17',
    'Rs. 7,299', 'INR 2,183', plain floats, and plain numeric strings
    (see common.parse_money)
  - mandi_id: same 6-shape problem as arrivals (see common.py)
  - district: sometimes null on the price record itself -> we don't need
    to guess it, because dim_mandi already has the correct district for
    every mandi_id; we just don't carry the (possibly wrong) district
    from this file forward at all, and join to dim_mandi later instead.
  - msp: occasionally blank on an individual record even though the same
    crop's MSP is a government-fixed constant that shows up on thousands
    of OTHER records. We verified this empirically (std=0 within crop) so
    imputing the missing msp from that crop's own most common value is
    not a guess, it's recovering a value that IS in the data, just not
    on this particular row.
"""

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent))
from common import canonical_crop, canonical_mandi_id, parse_messy_date, parse_money

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IN_PATH = PROJECT_ROOT / "data" / "raw" / "track3_price_and_msp.json"
OUT_PATH = PROJECT_ROOT / "data" / "processed" / "fact_prices.csv"


def run() -> pd.DataFrame:
    with open(IN_PATH, encoding="utf-8") as f:
        records = json.load(f)
    df = pd.DataFrame(records)
    raw_rows = len(df)

    df["mandi_id"] = df["mandi_id"].map(canonical_mandi_id)
    df["crop"] = df["crop_name"].map(canonical_crop)
    df["price_date"] = parse_messy_date(df["date"])

    for col in ["min_price", "max_price", "modal_price", "msp"]:
        df[col] = df[col].map(parse_money)

    # Impute missing MSP from the same crop's own (constant) value elsewhere
    # in the file — see docstring for why this is safe here specifically.
    msp_per_crop = df.groupby("crop")["msp"].agg(lambda s: s.mode().iloc[0] if not s.mode().empty else pd.NA)
    missing_msp_before = df["msp"].isna().sum()
    df["msp"] = df["msp"].fillna(df["crop"].map(msp_per_crop))
    missing_msp_after = df["msp"].isna().sum()

    # If modal price is missing but min & max exist, estimate the midpoint
    can_estimate = df["modal_price"].isna() & df["min_price"].notna() & df["max_price"].notna()
    df.loc[can_estimate, "modal_price"] = (df.loc[can_estimate, "min_price"] + df.loc[can_estimate, "max_price"]) / 2
    df["modal_price_was_imputed"] = can_estimate

    df["price_crash"] = df["modal_price"] < df["msp"]

    before_hard_drop = len(df)
    df = df.dropna(subset=["mandi_id", "price_date", "modal_price"])
    hard_dropped = before_hard_drop - len(df)

    keep_cols = ["record_id", "price_date", "mandi_id", "crop", "min_price",
                 "max_price", "modal_price", "modal_price_was_imputed", "msp", "price_crash"]
    clean_df = df[keep_cols].sort_values(["price_date", "mandi_id"])
    clean_df.to_csv(OUT_PATH, index=False)

    print("----- PRICE/MSP CLEANING SUMMARY -----")
    print(f"Raw rows                 : {raw_rows}")
    print(f"Clean rows                : {len(clean_df)}")
    print(f"Dropped (unrecoverable)   : {hard_dropped}")
    print(f"MSP missing before impute : {missing_msp_before}")
    print(f"MSP still missing after   : {missing_msp_after}")
    print(f"Modal prices imputed      : {int(can_estimate.sum())}")
    print(f"Price-crash rows (modal < MSP): {int(clean_df['price_crash'].sum())} "
          f"({clean_df['price_crash'].mean()*100:.1f}% of rows)")
    print(f"Wrote {OUT_PATH}")
    return clean_df


if __name__ == "__main__":
    run()
