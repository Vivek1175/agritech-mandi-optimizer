"""
app.py - Executive Dashboard
------------------------------
Rebuilt against the real dataset (5 linked files). Covers every metric
listed in track3_dataset_notes.txt:
  - Total crop arrivals (Quintals), crop-wise distribution
  - Average wholesale modal price vs MSP, price crash instances
  - Average transit time by warehouse, transit delay rate
  - Weather impact on arrivals (rainfall correlation)
  - Top mandis by arrival volume

Run locally:    streamlit run dashboard/app.py
Deploy free:     push to GitHub -> share.streamlit.io -> New app -> this file
"""

import sys
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))
from agent.graph_agent import answer_query  # noqa: E402

DB_PATH = PROJECT_ROOT / "data" / "processed" / "agritech.db"
CORR_PATH = PROJECT_ROOT / "data" / "processed" / "weather_arrival_correlation.csv"

st.set_page_config(page_title="Mandi-to-Market Supply Chain Optimizer", layout="wide")


@st.cache_data(ttl=600)
def load_data():
    conn = sqlite3.connect(DB_PATH)
    data = {
        "arrivals": pd.read_sql(
            "SELECT f.*, m.mandi_name, m.district FROM fact_arrivals f JOIN dim_mandi m ON f.mandi_id = m.mandi_id",
            conn, parse_dates=["arrival_date"]),
        "prices": pd.read_sql("SELECT * FROM v_price_vs_msp", conn, parse_dates=["price_date"]),
        "crashes": pd.read_sql("SELECT * FROM v_price_crashes", conn),
        "transit_wh": pd.read_sql("SELECT * FROM v_transit_by_warehouse", conn),
        "delay": pd.read_sql("SELECT * FROM v_delay_rate", conn),
        "top_mandis": pd.read_sql("SELECT * FROM v_top_mandis", conn),
        "arrivals_by_crop": pd.read_sql("SELECT * FROM v_arrivals_by_crop", conn),
    }
    conn.close()
    data["correlation"] = pd.read_csv(CORR_PATH) if CORR_PATH.exists() else pd.DataFrame()
    return data


data = load_data()
arrivals = data["arrivals"]
prices = data["prices"]

# ---------------------------------------------------------------- SIDEBAR --
st.sidebar.title("🌾 Filters")
all_crops = sorted(arrivals["crop"].unique())
selected_crop = st.sidebar.selectbox("Commodity", all_crops, index=all_crops.index("Wheat") if "Wheat" in all_crops else 0)

all_districts = sorted(arrivals["district"].unique())
selected_districts = st.sidebar.multiselect("Districts", all_districts, default=all_districts[:4])

date_min, date_max = arrivals["arrival_date"].min(), arrivals["arrival_date"].max()
date_range = st.sidebar.date_input("Date range", value=(date_min, date_max), min_value=date_min, max_value=date_max)

filtered_arrivals = arrivals[
    (arrivals["crop"] == selected_crop)
    & (arrivals["district"].isin(selected_districts))
    & (arrivals["arrival_date"] >= pd.to_datetime(date_range[0]))
    & (arrivals["arrival_date"] <= pd.to_datetime(date_range[1]))
]
filtered_prices = prices[(prices["crop"] == selected_crop) & (prices["district"].isin(selected_districts))]

# ------------------------------------------------------------- HEADER/KPIs --
st.title("🌾 Mandi-to-Market Supply Chain Optimizer")
st.caption("State Agriculture Board view — arrivals, MSP compliance, transit performance, weather correlation")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Arrivals (Quintal)", f"{filtered_arrivals['arrival_quintal'].sum():,.0f}" if not filtered_arrivals.empty else "—")
col2.metric("Avg Modal Price", f"Rs. {filtered_prices['modal_price'].mean():,.0f}" if not filtered_prices.empty else "—")
if not filtered_prices.empty:
    avg_gap = filtered_prices["gap_pct"].mean()
    col3.metric("Avg Gap vs MSP", f"{avg_gap:+.1f}%")
else:
    col3.metric("Avg Gap vs MSP", "—")
crash_count = int(filtered_prices["price_crash"].sum()) if not filtered_prices.empty else 0
col4.metric("Price Crash Instances", f"{crash_count}", help="Records where modal price fell below MSP")

st.divider()

# --------------------------------------------------------------- CHARTS ----
left, right = st.columns([2, 1])

with left:
    st.subheader(f"Daily Arrival Trend — {selected_crop}")
    if not filtered_arrivals.empty:
        daily = filtered_arrivals.groupby(["arrival_date", "district"])["arrival_quintal"].sum().unstack(fill_value=0)
        st.line_chart(daily)
    else:
        st.info("No data for this filter combination.")

with right:
    st.subheader("Top Mandis (this crop)")
    top = data["top_mandis"][data["top_mandis"]["crop"] == selected_crop].head(8)
    st.dataframe(top[["mandi_name", "district", "total_arrivals_quintal"]], hide_index=True, use_container_width=True)

st.subheader("MSP Compliance — modal price vs MSP")
if not filtered_prices.empty:
    gap_daily = filtered_prices.groupby(["price_date", "district"])["gap_pct"].mean().unstack(fill_value=None)
    st.line_chart(gap_daily)
    st.caption("Negative % = farmers were paid below MSP that day. Zero line = exactly at MSP.")
else:
    st.info("No price data for this filter combination.")

col_a, col_b = st.columns(2)
with col_a:
    st.subheader("Crop-wise Arrival Distribution")
    st.bar_chart(data["arrivals_by_crop"].set_index("crop")["total_arrivals_quintal"])
with col_b:
    st.subheader("Avg Transit Time by Warehouse")
    st.bar_chart(data["transit_wh"].set_index("destination_warehouse")["avg_transit_hours"])

st.subheader("Transit Delay Rate — worst 10 mandi→warehouse routes")
st.dataframe(
    data["delay"].sort_values("delay_rate_pct", ascending=False).head(10),
    hide_index=True, use_container_width=True,
)

if not data["correlation"].empty:
    st.subheader("Weather Impact — rainfall vs arrivals correlation, by district")
    st.caption("Negative = heavier rainfall days tend to see fewer arrivals in that district (transport disruption); near zero = little relationship in this sample.")
    st.bar_chart(data["correlation"].set_index("district")["rainfall_arrivals_correlation"])

st.divider()

# ------------------------------------------------------- BONUS: AGENT ------
st.header("🤖 Ask the Agent (Bonus Layer)")
st.caption("Try any of the 6 example queries from the problem statement, e.g.:")
st.code('"Plot the daily arrival trend of Wheat in Amritsar mandi vs MSP for the last 30 days"', language=None)

user_question = st.text_input("Ask a question in plain English:")
if st.button("Ask") and user_question:
    result = answer_query(user_question)
    if "error" in result:
        st.error(result["error"])
    else:
        st.write(result["summary"])
        if result["chart_path"]:
            st.image(result["chart_path"])

st.divider()
st.caption("Data: real TransOrg AgentIQ Datathon Track 3 dataset (5 files: arrivals, prices/MSP, weather, transport, mandi master). See docs/DATA_DICTIONARY.md for cleaning details and assumptions.")
