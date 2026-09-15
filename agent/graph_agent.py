"""
graph_agent.py
--------------
BONUS LAYER: "Agentic Graph AI" - rebuilt against the real dataset's schema.

Same design as before (see the long comment in the project history if you
want the full reasoning): a rule-based slot-filling parser, not an LLM API,
because the FAQ says don't spend money on cloud tiers, and a regex-based
parser is 100% explainable in a viva.

This version specifically answers the 6 example agent queries listed in
track3_dataset_notes.txt:
  1. Plot the daily arrival trend of Wheat in Amritsar mandi vs MSP for the last 30 days.
  2. Show total arrivals by crop type.
  3. Which mandi has the highest average transit delay?
  4. Compare total rainfall by district over the last 3 months.
  5. Show the distribution of wholesale prices for Rice.
  6. Which warehouse receives the highest volume of crops?
"""

import re
import sqlite3
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "processed" / "agritech.db"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "agent_charts"
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

KNOWN_CROPS = ["Wheat", "Paddy", "Rice", "Maize", "Cotton", "Mustard", "Sugarcane"]


def _conn():
    return sqlite3.connect(DB_PATH)


def _find(text: str, options: list[str]) -> list[str]:
    low = text.lower()
    return [o for o in options if o.lower() in low]


def _days_window(text: str, default: int = 30) -> int:
    m = re.search(r"last\s+(\d+)\s+day", text.lower())
    if m:
        return int(m.group(1))
    m = re.search(r"last\s+(\d+)\s+month", text.lower())
    if m:
        return int(m.group(1)) * 30
    return default


def parse_query(text: str) -> dict:
    conn = _conn()
    mandis = pd.read_sql("SELECT DISTINCT mandi_name FROM dim_mandi", conn)["mandi_name"].tolist()
    districts = pd.read_sql("SELECT DISTINCT district FROM dim_mandi", conn)["district"].tolist()
    warehouses = pd.read_sql("SELECT DISTINCT destination_warehouse FROM fact_transport", conn)["destination_warehouse"].tolist()
    conn.close()

    crops = _find(text, KNOWN_CROPS)
    low = text.lower()
    return {
        "raw_text": text,
        "crop": crops[0] if crops else None,
        "mandi": next((m for m in mandis if m.lower() in low), None),
        "district": next((d for d in districts if d.lower() in low), None),
        "warehouse": next((w for w in warehouses if w.lower() in low), None),
        "days": _days_window(text),
        "wants_msp": "msp" in low,
        "wants_delay": "delay" in low,
        "wants_distribution": "distribution" in low,
        "wants_total_by": "total" in low and ("crop" in low or "type" in low),
        "wants_top_warehouse": "warehouse" in low and ("highest" in low or "most" in low or "top" in low),
        "wants_rainfall_compare": "rainfall" in low,
    }


def _save(fig, name):
    path = OUTPUT_DIR / f"{name}.png"
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return str(path)


# Query 1 --------------------------------------------------------------
def answer_arrival_trend_vs_msp(intent):
    conn = _conn()
    # "Amritsar mandi" in the real data means "the mandi(s) located in
    # Amritsar district" (mandi_name itself is an unrelated city name like
    # "Kochi Mandi") - so match on mandi_name OR district, whichever the
    # question actually gave us.
    location = intent["mandi"] or intent["district"]
    df = pd.read_sql("""
        SELECT f.arrival_date, SUM(f.arrival_quintal) AS arrivals
        FROM fact_arrivals f JOIN dim_mandi m ON f.mandi_id = m.mandi_id
        WHERE f.crop = ? AND (m.mandi_name LIKE ? OR m.district LIKE ?)
        GROUP BY f.arrival_date ORDER BY f.arrival_date DESC LIMIT ?
    """, conn, params=(intent["crop"], f"%{location}%", f"%{location}%", intent["days"]))
    msp_row = pd.read_sql("SELECT msp FROM fact_prices WHERE crop = ? LIMIT 1", conn, params=(intent["crop"],))
    conn.close()
    if df.empty:
        return None, f"No arrivals found for {intent['crop']} matching '{location}'."
    df = df.sort_values("arrival_date")
    df["label"] = pd.to_datetime(df["arrival_date"]).dt.strftime("%d-%b")
    msp = float(msp_row.iloc[0, 0]) if not msp_row.empty else None

    fig, ax1 = plt.subplots(figsize=(9, 5))
    ax1.bar(df["label"], df["arrivals"], color="#8bc34a", alpha=0.6, label="Arrivals (Quintal)")
    ax1.tick_params(axis="x", rotation=60)
    ax1.set_ylabel("Arrivals (Quintal)")
    if msp:
        ax2 = ax1.twinx()
        ax2.axhline(msp, color="#c62828", linestyle="--", label=f"MSP Rs.{msp:.0f}")
        ax2.set_ylabel("MSP reference (Rs./Quintal)")
    plt.title(f"{intent['crop']} arrivals near {location} (last {intent['days']} days) vs MSP")
    chart = _save(fig, f"trend_{intent['crop']}_{location}")
    summary = f"Total {intent['crop']} arrivals near {location} over the last {intent['days']} days: {df['arrivals'].sum():,.0f} quintals. MSP reference: Rs. {msp:.0f}/quintal." if msp else f"Total arrivals: {df['arrivals'].sum():,.0f} quintals."
    return chart, summary


# Query 2 ----------------------------------------------------------------
def answer_total_by_crop(intent):
    conn = _conn()
    df = pd.read_sql("SELECT * FROM v_arrivals_by_crop", conn)
    conn.close()
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(df["crop"], df["total_arrivals_quintal"], color="#558b2f")
    ax.set_ylabel("Total Arrivals (Quintal)")
    plt.xticks(rotation=30)
    plt.title("Total arrivals by crop type")
    chart = _save(fig, "total_by_crop")
    top = df.iloc[0]
    summary = f"{top['crop']} has the highest total arrivals at {top['total_arrivals_quintal']:,.0f} quintals across all mandis."
    return chart, summary


# Query 3 ------------------------------------------------------------------
def answer_highest_delay_mandi(intent):
    conn = _conn()
    df = pd.read_sql("""
        SELECT mandi_name, AVG(delay_rate_pct) AS avg_delay_rate
        FROM v_delay_rate GROUP BY mandi_name ORDER BY avg_delay_rate DESC LIMIT 10
    """, conn)
    conn.close()
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(df["mandi_name"][::-1], df["avg_delay_rate"][::-1], color="#e65100")
    ax.set_xlabel("Average Delay Rate (%)")
    plt.title("Top 10 mandis by transit delay rate")
    chart = _save(fig, "top_delay_mandis")
    top = df.iloc[0]
    summary = f"{top['mandi_name']} has the highest average transit delay rate, at {top['avg_delay_rate']:.1f}% of trips flagged delayed."
    return chart, summary


# Query 4 --------------------------------------------------------------------
def answer_rainfall_by_district(intent):
    conn = _conn()
    df = pd.read_sql("""
        SELECT district, SUM(rainfall_mm) AS total_rainfall_mm
        FROM fact_weather
        WHERE reading_date >= date((SELECT MAX(reading_date) FROM fact_weather), ?)
        GROUP BY district ORDER BY total_rainfall_mm DESC
    """, conn, params=(f"-{intent['days']} days",))
    conn.close()
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(df["district"], df["total_rainfall_mm"], color="#0277bd")
    plt.xticks(rotation=60)
    ax.set_ylabel("Total Rainfall (mm)")
    plt.title(f"Total rainfall by district (last {intent['days']} days)")
    chart = _save(fig, "rainfall_by_district")
    top = df.iloc[0]
    summary = f"{top['district']} received the most rainfall in this window, at {top['total_rainfall_mm']:.0f} mm total."
    return chart, summary


# Query 5 -----------------------------------------------------------------
def answer_price_distribution(intent):
    conn = _conn()
    df = pd.read_sql("SELECT modal_price FROM fact_prices WHERE crop = ?", conn, params=(intent["crop"],))
    conn.close()
    if df.empty:
        return None, f"No price records found for {intent['crop']}."
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(df["modal_price"], bins=25, color="#6a1b9a", alpha=0.8)
    ax.set_xlabel("Modal Price (Rs./Quintal)")
    ax.set_ylabel("Number of records")
    plt.title(f"Distribution of wholesale (modal) prices — {intent['crop']}")
    chart = _save(fig, f"price_distribution_{intent['crop']}")
    summary = f"{intent['crop']} modal prices range from Rs. {df['modal_price'].min():.0f} to Rs. {df['modal_price'].max():.0f}, averaging Rs. {df['modal_price'].mean():.0f}/quintal."
    return chart, summary


# Query 6 -----------------------------------------------------------------
def answer_top_warehouse(intent):
    conn = _conn()
    df = pd.read_sql("""
        SELECT destination_warehouse, COUNT(*) AS n_trips
        FROM fact_transport GROUP BY destination_warehouse ORDER BY n_trips DESC
    """, conn)
    conn.close()
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(df["destination_warehouse"], df["n_trips"], color="#1565c0")
    plt.xticks(rotation=30)
    ax.set_ylabel("Number of Trips (proxy for volume)")
    plt.title("Trips received by warehouse")
    chart = _save(fig, "top_warehouse")
    top = df.iloc[0]
    summary = f"{top['destination_warehouse']} receives the highest volume of crops, with {top['n_trips']:,} trips recorded."
    return chart, summary


def answer_query(text: str) -> dict:
    intent = parse_query(text)

    if intent["wants_top_warehouse"]:
        chart, summary = answer_top_warehouse(intent)
    elif intent["wants_delay"] and "which mandi" in text.lower():
        chart, summary = answer_highest_delay_mandi(intent)
    elif intent["wants_rainfall_compare"]:
        chart, summary = answer_rainfall_by_district(intent)
    elif intent["crop"] and (intent["mandi"] or intent["district"]) and ("trend" in text.lower() or "daily" in text.lower() or intent["wants_msp"]):
        chart, summary = answer_arrival_trend_vs_msp(intent)
    elif intent["wants_distribution"] and intent["crop"]:
        chart, summary = answer_price_distribution(intent)
    elif intent["wants_total_by"]:
        chart, summary = answer_total_by_crop(intent)
    elif intent["crop"] and (intent["mandi"] or intent["district"]):
        chart, summary = answer_arrival_trend_vs_msp(intent)
    elif intent["crop"]:
        chart, summary = answer_price_distribution(intent)
    else:
        return {"error": "Could not identify what you're asking about. Try naming a crop, mandi, district, or warehouse."}

    return {"intent": intent, "chart_path": chart, "summary": summary}


if __name__ == "__main__":
    demo_queries = [
        "Plot the daily arrival trend of Wheat in Amritsar mandi vs MSP for the last 30 days",
        "Show total arrivals by crop type",
        "Which mandi has the highest average transit delay?",
        "Compare total rainfall by district over the last 3 months",
        "Show the distribution of wholesale prices for Rice",
        "Which warehouse receives the highest volume of crops?",
    ]
    for q in demo_queries:
        result = answer_query(q)
        print("\nQ:", q)
        if "error" in result:
            print("  ERROR:", result["error"])
        else:
            print("  Chart  :", result["chart_path"])
            print("  Summary:", result["summary"])
