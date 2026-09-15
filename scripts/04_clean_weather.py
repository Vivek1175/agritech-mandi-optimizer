"""
04_clean_weather.py
----------------------
Issues fixed:
  1. Timestamp chaos: ISO with explicit "UTC"/"IST" suffix, ISO with no
     suffix, ISO with a "T" separator, date-only, and US-style
     "MM-DD-YYYY hh:mm AM/PM". A row tagged UTC is converted to IST by
     adding 5 hours 30 minutes — get this wrong and every weather reading
     lands on the wrong calendar day when you later join it to arrivals.
  2. Temperature: sometimes a plain number + a separate unit column
     ('f','°F','Celsius'...), sometimes the unit is baked into the value
     itself ('39.8°C') with the unit column blank. Both are converted to
     Celsius.
  3. Rainfall: numeric + a unit column with 6 different spellings for the
     same two units (mm/MM/millimeters vs in/inch/inches).
  4. Sensor -> district mapping: THE ONE GENUINE ASSUMPTION IN THIS WHOLE
     PIPELINE. The dataset notes say sensor-to-location mapping isn't
     given and "can be assumed 1:1 with districts for simplicity." There
     are 50 real sensors and 18 districts, so we deterministically spread
     the 50 sensors across the 18 districts (round-robin, sorted order)
     and average multiple sensors' readings per district-day. This is
     documented here and in the README — if the organisers release the
     real sensor-to-district map, replace SENSOR_DISTRICT_MAP with it and
     nothing else in the pipeline changes.
"""

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent))

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IN_PATH = PROJECT_ROOT / "data" / "raw" / "track3_weather_sensors.xlsx"
MANDI_MASTER_PATH = PROJECT_ROOT / "data" / "processed" / "dim_mandi.csv"
OUT_PATH = PROJECT_ROOT / "data" / "processed" / "fact_weather.csv"

TIMESTAMP_FORMATS = [
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M",
    "%d/%m/%Y", "%m-%d-%Y %I:%M %p", "%d-%b-%Y %H:%M:%S",
]


def parse_timestamp_to_ist(raw_value):
    if pd.isna(raw_value):
        return pd.NaT
    text = str(raw_value).strip()

    is_utc = text.endswith("UTC")
    is_ist = text.endswith("IST")
    text = text.replace("UTC", "").replace("IST", "").strip()

    parsed = pd.NaT
    for fmt in TIMESTAMP_FORMATS:
        try:
            parsed = pd.to_datetime(text, format=fmt)
            break
        except ValueError:
            continue
    if pd.isna(parsed):
        return pd.NaT

    if is_utc:
        parsed = parsed + pd.Timedelta(hours=5, minutes=30)  # UTC -> IST
    # if no marker at all, we assume the sensor already logs local IST time
    return parsed


def normalise_temperature(raw_value, raw_unit) -> float:
    """Handles both 'value + separate unit column' and 'unit baked into
    the value string' in one function, then converts everything to °C."""
    if isinstance(raw_value, str):
        match = re.match(r"([\d.]+)\s*°?\s*([CFcf])", raw_value)
        if match:
            value, unit = float(match.group(1)), match.group(2).upper()
        else:
            value, unit = pd.to_numeric(raw_value, errors="coerce"), None
    else:
        value, unit = raw_value, None

    if unit is None and pd.notna(raw_unit):
        unit_text = str(raw_unit).strip().lower()
        unit = "F" if unit_text in ("f", "fahrenheit", "°f") else "C"

    if pd.isna(value):
        return np.nan
    if unit == "F":
        return round((value - 32) * 5 / 9, 1)
    return round(float(value), 1)


def normalise_rainfall(raw_value, raw_unit) -> float:
    """Also clips negative readings to 0 - a sensor can misfire and log a
    negative number, but rainfall itself is never negative in reality.
    We clip rather than drop the row, since temperature/humidity on the
    same row are usually still valid."""
    value = pd.to_numeric(raw_value, errors="coerce")
    if pd.isna(value):
        return np.nan
    unit_text = str(raw_unit).strip().lower() if pd.notna(raw_unit) else "mm"
    value_mm = value * 25.4 if unit_text in ("in", "inch", "inches") else value
    return round(max(value_mm, 0.0), 2)


def build_sensor_district_map(sensor_ids: list, districts: list) -> dict:
    sensor_ids_sorted = sorted(s for s in sensor_ids if s != "UNKNOWN")
    districts_sorted = sorted(districts)
    return {sensor: districts_sorted[i % len(districts_sorted)] for i, sensor in enumerate(sensor_ids_sorted)}


def run() -> pd.DataFrame:
    df = pd.read_excel(IN_PATH)
    raw_rows = len(df)

    df["reading_time_ist"] = df["timestamp"].map(parse_timestamp_to_ist)
    df["temp_c"] = df.apply(lambda r: normalise_temperature(r["temperature"], r["temp_unit"]), axis=1)
    negative_rain_count = (pd.to_numeric(df["rainfall"], errors="coerce") < 0).sum()
    df["rainfall_mm"] = df.apply(lambda r: normalise_rainfall(r["rainfall"], r["rain_unit"]), axis=1)

    mandi_master = pd.read_csv(MANDI_MASTER_PATH)
    districts = [d for d in mandi_master["district"].dropna().unique().tolist() if d != "Unknown"]
    sensor_district_map = build_sensor_district_map(df["sensor_id"].unique().tolist(), districts)
    df["district"] = df["sensor_id"].map(sensor_district_map)

    unparsed_ts = df["reading_time_ist"].isna().sum()
    before_drop = len(df)
    df = df.dropna(subset=["reading_time_ist", "district"])
    dropped = before_drop - len(df)

    df["reading_date"] = df["reading_time_ist"].dt.date

    daily = (
        df.groupby(["reading_date", "district"])
        .agg(temp_c=("temp_c", "mean"), rainfall_mm=("rainfall_mm", "sum"), humidity_percent=("humidity_percent", "mean"))
        .round(2)
        .reset_index()
    )
    daily.to_csv(OUT_PATH, index=False)

    print("----- WEATHER CLEANING SUMMARY -----")
    print(f"Raw sensor readings        : {raw_rows}")
    print(f"Unparseable timestamps      : {unparsed_ts}")
    print(f"Negative rainfall readings clipped to 0: {int(negative_rain_count)}")
    print(f"Dropped (no timestamp/district): {dropped}")
    print(f"Sensors mapped to districts : {len(sensor_district_map)} sensors -> {len(set(sensor_district_map.values()))} districts (round-robin, see docstring)")
    print(f"Daily district-level rows produced: {len(daily)}")
    print(f"Wrote {OUT_PATH}")
    return daily


if __name__ == "__main__":
    run()
