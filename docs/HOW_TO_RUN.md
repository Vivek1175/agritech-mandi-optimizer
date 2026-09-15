# How to Run This on Your Computer

## 1. One-time setup

```bash
# Install Python 3.10+ and Git if you don't have them already.

# Unzip the project you downloaded from Claude, cd into it:
cd agritech-mandi-optimizer

python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Run the pipeline (order matters — later steps depend on earlier ones)

```bash
python3 scripts/01_clean_mandi_master.py
python3 scripts/02_clean_arrivals.py
python3 scripts/03_clean_prices_msp.py
python3 scripts/04_clean_weather.py
python3 scripts/05_clean_transport.py
python3 scripts/06_build_analytics_db.py
```

Each script prints a before/after row-count summary — **screenshot these
for your README/report**, this is exactly what Gate 2 (Data Rescue) checks
for.

## 3. Explore the cleaned data (optional but recommended before the dashboard)

Open `data/processed/agritech.db` in [DB Browser for SQLite](https://sqlitebrowser.org/)
(free) and look at the views: `v_arrivals_by_crop`, `v_price_vs_msp`,
`v_price_crashes`, `v_transit_by_warehouse`, `v_delay_rate`, `v_top_mandis`.
If any number looks physically impossible, that's a sign to go back to the
relevant `0X_clean_*.py` script and tighten the cleaning rule — don't patch
it with a SQL `WHERE` clause, fix it at the source.

## 4. Launch the dashboard

```bash
streamlit run dashboard/app.py
```

This opens in your browser automatically. Try the filters, then scroll
down to "Ask the Agent" and try:
> Plot the daily arrival trend of Wheat in Amritsar mandi vs MSP for the last 30 days

## 5. Deploy for a public/live link (required for submission)

1. Push this whole folder to a **public** GitHub repo.
2. Go to <https://share.streamlit.io>, sign in with GitHub.
3. "New app" → pick your repo → set the main file to `dashboard/app.py`.
4. You'll get a public `https://...streamlit.app` URL — this is your
   "live deployed link."

**Important:** `data/processed/agritech.db` must exist in the repo (or the
app must run the 6 pipeline scripts on startup) for the deployed app to
have data. Easiest: commit the `data/processed/` folder as-is after
running the pipeline locally once.

## 6. Record your demo video (3–5 minutes)

1. Show `data/raw/` — the messy files, briefly open one in Excel/a text
   editor so the evaluator sees what you started with.
2. Run the 6 pipeline scripts live, pointing at the printed row-count
   summaries.
3. Walk through the dashboard filters and the MSP-compliance chart.
4. Ask the agent 2–3 of the example queries from
   `data/raw/track3_dataset_notes.txt` live and show the returned chart.

## If something breaks

- **"no such table" in Streamlit** → you skipped step 6
  (`06_build_analytics_db.py`) or ran it before the other cleaning scripts
  finished. Re-run steps 2 in order.
- **Weather script fails with a file-not-found on `dim_mandi.csv`** → run
  `01_clean_mandi_master.py` first; the weather cleaner needs it for the
  sensor→district mapping.
- **A number looks impossible** (e.g. average price of ₹0) → check
  `docs/ASSUMPTIONS.md` first — it might be a documented judgment call,
  not a bug. If it's genuinely wrong, the fix almost always belongs in the
  relevant `0X_clean_*.py` script, not in the dashboard code.
