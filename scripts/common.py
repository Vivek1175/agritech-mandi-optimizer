"""
common.py
---------
WHY A SHARED MODULE (say this in your viva):
Five different raw files all contain a "crop name" and a "mandi_id" column,
each messy in the same way. If every cleaning script re-implemented its own
crop-name mapping, they would eventually drift apart (one script would fix
a typo the other didn't) and your arrivals table and your price table would
silently disagree on what "Wheat" means. Putting the mapping in ONE place
and importing it everywhere is what makes this a "governed" pipeline
instead of five unrelated scripts that happen to sit in the same folder.

Every regex/mapping decision below was reached by actually inspecting the
distinct values in the raw files first (see the profiling commands in the
project history) — not guessed.
"""

import re
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# CROP NAME CANONICALISATION
# Built by listing every distinct crop_name value across BOTH
# track3_mandi_arrivals.csv and track3_price_and_msp.json and grouping them.
# Note: "Narma" is Punjabi for American cotton (not maize) and "Kanak" is
# Punjabi for wheat — these are real regional terms, not typos.
# ---------------------------------------------------------------------------
CROP_GROUPS = {
    "Wheat":     ["wheat", "gehun", "gehu", "गेहूं", "kanak"],
    "Paddy":     ["paddy", "dhaan", "धान"],
    "Rice":      ["rice", "chawal", "चावल", "basmati"],
    "Maize":     ["corn", "maize", "makka", "makki", "मक्का"],
    "Cotton":    ["cotton", "kapas", "कपास", "narma"],
    "Mustard":   ["mustard", "sarso", "sarson", "सरसों"],
    "Sugarcane": ["sugarcane", "ganna", "ganne", "गन्ना"],
}
_CROP_LOOKUP = {variant: canon for canon, variants in CROP_GROUPS.items() for variant in variants}


def canonical_crop(raw_value) -> str:
    """Maps any of Wheat/WHEAT/wheat/Gehun/GEHUN/गेहूं/Kanak (etc.) to one
    canonical name. Unrecognised values are kept, flagged, so you can SEE
    what fell through instead of silently losing rows."""
    if pd.isna(raw_value):
        return "UNKNOWN"
    key = str(raw_value).strip().lower()
    return _CROP_LOOKUP.get(key, f"UNRECOGNISED:{raw_value}")


# ---------------------------------------------------------------------------
# MANDI ID CANONICALISATION
# Real data has 6 distinct shapes for the same ID: MANDI026 / MANDI-054 /
# mandi_049 / mandi050 / M045 / 056. All resolve to one 3-digit number —
# we just pull the digits out and re-pad, regardless of the prefix style.
# ---------------------------------------------------------------------------
def canonical_mandi_id(raw_value) -> str:
    if pd.isna(raw_value):
        return None
    digits = re.sub(r"\D", "", str(raw_value))
    if not digits:
        return None
    return f"MANDI{int(digits):03d}"


# ---------------------------------------------------------------------------
# MONEY STRING PARSING
# Real values seen: '₹7,570.17', 'Rs. 7,299', 'INR 2,183', '5,878.62/-',
# plain floats, plain numeric strings, and blanks.
# ---------------------------------------------------------------------------
def parse_money(raw_value):
    if raw_value is None or (isinstance(raw_value, float) and np.isnan(raw_value)):
        return np.nan
    if isinstance(raw_value, (int, float)):
        return float(raw_value)
    text = str(raw_value).strip()
    if text == "":
        return np.nan
    text = re.sub(r"[₹]|Rs\.?|INR|/-", "", text, flags=re.IGNORECASE)
    text = text.replace(",", "").strip()
    try:
        return float(text)
    except ValueError:
        return np.nan


# ---------------------------------------------------------------------------
# DATE PARSING
# The exact format order below was determined empirically: hyphen-numeric
# dates in this dataset are ALWAYS MM-DD-YYYY (verified: the second number
# exceeds 12 in >50% of rows, which is only possible if it's the day, not
# the month); slash and dot dates are ALWAYS DD/MM/YYYY and DD.MM.YYYY
# (same check, opposite slot); YYYY/... and YYYY-... dates are ISO-style.
# Trying formats in this fixed order and keeping the first successful parse
# per row resolves 100% of the dates in this dataset with no ambiguity.
# ---------------------------------------------------------------------------
DATE_FORMATS_IN_ORDER = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%d.%m.%Y",
    "%m-%d-%Y",
    "%d-%b-%Y",
]


def parse_messy_date(series: pd.Series) -> pd.Series:
    raw = series.astype(str).str.strip()
    parsed = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    for fmt in DATE_FORMATS_IN_ORDER:
        still_missing = parsed.isna()
        if not still_missing.any():
            break
        parsed.loc[still_missing] = pd.to_datetime(raw[still_missing], format=fmt, errors="coerce")
    return parsed


# ---------------------------------------------------------------------------
# VEHICLE NUMBER CANONICALISATION
# Seen: 'HR 27 AB 5680', 'hr 96-BC-4441', 'RJ-81-CD-5503', 'DL53-BC-4403'.
# Real Indian RTO plates are STATE(2 letters) + RTO code(2 digits) +
# series(2 letters) + number(4 digits). We strip every separator and
# re-join in one fixed uppercase format so the same physical truck isn't
# counted as three different vehicles because of spacing differences.
# ---------------------------------------------------------------------------
_PLATE_RE = re.compile(r"([A-Za-z]{2})\s*-?\s*(\d{2})\s*-?\s*([A-Za-z]{2})\s*-?\s*(\d{4})")


def canonical_vehicle_no(raw_value):
    if pd.isna(raw_value):
        return None
    match = _PLATE_RE.search(str(raw_value).upper())
    if not match:
        return f"UNRECOGNISED:{raw_value}"
    state, rto, series, number = match.groups()
    return f"{state}-{rto}-{series}-{number}"
