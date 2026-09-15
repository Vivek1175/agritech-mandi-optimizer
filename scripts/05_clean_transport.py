"""
05_clean_transport.py
------------------------
Issues fixed:
  1. departure_time / arrival_time: 6 different formats (ISO with space,
     ISO with 'T', DD/MM/YYYY with or without time, DD-Mon-YYYY, and
     MM-DD-YYYY hh:mm AM/PM) - same multi-format problem as the other
     date columns, just with a time component too.
  2. transit_hours: sometimes has a literal ' hrs' suffix stuck on, and
     ~5% of rows are negative (physically impossible - a trip can't take
     negative time).
     FIX STRATEGY: where BOTH timestamps parsed successfully, we trust the
     timestamps and recompute transit_hours = arrival - departure. This is
     strictly better than trusting a free-text hours field, because two
     independently-entered numbers (departure, arrival) are less likely to
     both be wrong than one manually-typed duration field. We only fall
     back to the raw (absolute-valued) transit_hours field when a
     timestamp is missing.
  3. distance/distance_unit: miles converted to km (1 mile = 1.60934 km).
  4. vehicle_no: standardised to one format regardless of spacing/case
     (see common.canonical_vehicle_no).
  5. "delayed" trip definition: since no target SLA is given per route, we
     define a route's benchmark as the MEDIAN transit_hours for that
     mandi->warehouse pair, and flag a trip "delayed" if it took more than
     1.5x that benchmark. This is a documented assumption, not a given
     rule - change DELAY_THRESHOLD_MULTIPLIER if your evaluator specifies
     a different SLA.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent))
from common import canonical_mandi_id, canonical_vehicle_no

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IN_PATH = PROJECT_ROOT / "data" / "raw" / "track3_transport_logistics.csv"
OUT_PATH = PROJECT_ROOT / "data" / "processed" / "fact_transport.csv"

DELAY_THRESHOLD_MULTIPLIER = 1.5
TIMESTAMP_FORMATS = [
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M",
    "%d/%m/%Y", "%m-%d-%Y %I:%M %p", "%d-%b-%Y %H:%M:%S",
]
MILES_TO_KM = 1.60934


def parse_messy_timestamp(raw_value):
    if pd.isna(raw_value):
        return pd.NaT
    text = str(raw_value).strip()
    for fmt in TIMESTAMP_FORMATS:
        try:
            return pd.to_datetime(text, format=fmt)
        except ValueError:
            continue
    return pd.NaT


def run() -> pd.DataFrame:
    df = pd.read_csv(IN_PATH)
    raw_rows = len(df)

    df["mandi_id"] = df["mandi_id"].map(canonical_mandi_id)
    df["departure_dt"] = df["departure_time"].map(parse_messy_timestamp)
    df["arrival_dt"] = df["arrival_time"].map(parse_messy_timestamp)
    df["vehicle_no_clean"] = df["vehicle_no"].map(canonical_vehicle_no)

    distance_numeric = pd.to_numeric(df["distance"], errors="coerce")
    df["distance_km"] = np.where(
        df["distance_unit"].astype(str).str.strip().str.lower() == "miles",
        distance_numeric * MILES_TO_KM,
        distance_numeric,
    )
    df["distance_km"] = pd.Series(df["distance_km"]).round(2)

    raw_hours = df["transit_hours"].astype(str).str.replace("hrs", "", case=False).str.strip()
    raw_hours = pd.to_numeric(raw_hours, errors="coerce").abs()

    both_timestamps_ok = df["departure_dt"].notna() & df["arrival_dt"].notna()
    computed_hours = (df["arrival_dt"] - df["departure_dt"]).dt.total_seconds() / 3600

    df["transit_hours_clean"] = np.where(both_timestamps_ok, computed_hours, raw_hours)
    # A recomputed negative duration means arrival was logged BEFORE
    # departure - i.e. the two timestamps themselves are swapped/wrong,
    # not just the hours field. Same fix: take the absolute value and flag it.
    df["was_impossible_duration"] = df["transit_hours_clean"] < 0
    df["transit_hours_clean"] = df["transit_hours_clean"].abs().round(2)

    before_drop = len(df)
    df = df.dropna(subset=["mandi_id", "destination_warehouse", "transit_hours_clean"])
    dropped = before_drop - len(df)

    route_benchmark = df.groupby(["mandi_id", "destination_warehouse"])["transit_hours_clean"].transform("median")
    df["is_delayed"] = df["transit_hours_clean"] > (route_benchmark * DELAY_THRESHOLD_MULTIPLIER)

    keep_cols = ["trip_id", "mandi_id", "destination_warehouse", "departure_dt", "arrival_dt",
                 "transit_hours_clean", "was_impossible_duration", "distance_km",
                 "vehicle_no_clean", "driver_id", "is_delayed"]
    clean_df = df[keep_cols].rename(columns={
        "departure_dt": "departure_time", "arrival_dt": "arrival_time",
        "transit_hours_clean": "transit_hours",
    }).sort_values("departure_time")
    clean_df.to_csv(OUT_PATH, index=False)

    print("----- TRANSPORT CLEANING SUMMARY -----")
    print(f"Raw rows                     : {raw_rows}")
    print(f"Clean rows                    : {len(clean_df)}")
    print(f"Dropped (unrecoverable)       : {dropped}")
    print(f"Transit hours recomputed from timestamps (trusted over raw field): {int(both_timestamps_ok.sum())}")
    print(f"Impossible (negative) durations fixed: {int(clean_df['was_impossible_duration'].sum())}")
    print(f"Unrecognised vehicle plates    : {int(clean_df['vehicle_no_clean'].astype(str).str.startswith('UNRECOGNISED').sum())}")
    print(f"Trips flagged delayed (>{DELAY_THRESHOLD_MULTIPLIER}x route median): {int(clean_df['is_delayed'].sum())} "
          f"({clean_df['is_delayed'].mean()*100:.1f}%)")
    print(f"Wrote {OUT_PATH}")
    return clean_df


if __name__ == "__main__":
    run()
