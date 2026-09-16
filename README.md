# 🌾 Mandi-to-Market Supply Chain Optimizer

TransOrg AgentIQ Datathon — Track 3 (AgriTech), built and tested against the
**real released dataset** (`track3_agritech_dataset_files.zip`): 5 linked
files covering arrivals, prices/MSP, weather sensors, transport logistics,
and mandi master data.

## Architecture

```
data/raw/                  <- the 5 files exactly as released
data/processed/            <- cleaned CSVs + agritech.db (SQLite) + agent chart PNGs
scripts/common.py           <- shared cleaning rules (crop names, mandi IDs, money, dates)
scripts/01_clean_mandi_master.py
scripts/02_clean_arrivals.py
scripts/03_clean_prices_msp.py
scripts/04_clean_weather.py
scripts/05_clean_transport.py
scripts/06_build_analytics_db.py  <- builds SQLite + 7 business-metric views
agent/graph_agent.py         <- Bonus Layer: rule-based text-to-chart agent
dashboard/app.py             <- Streamlit executive dashboard
docs/                        <- data dictionary, assumptions log, this guide
```

## Quickstart (run in this exact order — later scripts depend on earlier ones)

```bash
pip install -r requirements.txt

python3 scripts/01_clean_mandi_master.py     # builds dim_mandi.csv
python3 scripts/02_clean_arrivals.py
python3 scripts/03_clean_prices_msp.py
python3 scripts/04_clean_weather.py          # needs dim_mandi.csv for district mapping
python3 scripts/05_clean_transport.py
python3 scripts/06_build_analytics_db.py     # builds agritech.db + all views

streamlit run dashboard/app.py
```

Try the agent (standalone or inside the dashboard's chat box) with the
exact example queries from the dataset notes:
```bash
python3 agent/graph_agent.py
```

## Data Rescue — results on the real dataset

| Table | Raw rows | Clean rows | What was fixed |
|---|---|---|---|
| `dim_mandi` | 60 | 57 | 3 exact duplicates removed; missing district/state/type kept as "Unknown", not dropped |
| `fact_arrivals` | 25,750 | 25,750 (0 lost) | 6 mandi_id formats unified; Hindi/Punjabi/English crop names merged; Quintal/KG/Tonne units reconciled (incl. units embedded inside the quantity string); 1,261 negative quantities abs()'d and flagged; 6 date formats parsed |
| `fact_prices` | 12,000 | 10,709 | Currency strings (₹/Rs./INR/commas) parsed; 2,377 missing MSPs imputed from each crop's own constant government value; 546 modal prices imputed from (min+max)/2; 1,291 dropped, almost all because mandi_id was unrecoverable |
| `fact_weather` | 15,000 readings | 4,249 daily district-rows | UTC→IST conversion; °F→°C (incl. embedded in the string); inch→mm; 1,518 negative rainfall glitches clipped to 0; 50 sensors mapped to 18 districts (documented assumption, see `docs/ASSUMPTIONS.md`) |
| `fact_transport` | 10,400 | 10,346 | Transit hours **recomputed from timestamps** (trusted over the free-text hours field) for 9,347 trips; 340 impossible negative durations fixed; distance miles→km; vehicle plates standardised to one format |

## Business metrics implemented (all from `data/raw/track3_dataset_notes.txt`)

| Metric | View / function |
|---|---|
| Total crop arrivals (Quintals), crop-wise distribution | `v_arrivals_by_crop` |
| Average wholesale modal price vs MSP | `v_price_vs_msp` |
| Price crash instances (modal < MSP) | `v_price_crashes` |
| Average transit time by warehouse | `v_transit_by_warehouse` |
| Transit delay rate | `v_delay_rate` (delayed = >1.5× that route's own median — see `docs/ASSUMPTIONS.md`) |
| Weather impact on arrivals (rainfall correlation) | `weather_arrival_correlation.csv`, computed in `06_build_analytics_db.py` |
| Top mandis by arrival volume | `v_top_mandis` |

Real numbers from this run: **Wheat has the highest total arrivals**
(991,324 quintals across 4,431 reports), followed by Mustard (982,393 q)
and Sugarcane (966,862 q).

## Why these engineering choices 

| Decision | Reason |
|---|---|
| One shared `common.py` for crop/ID/date/money rules | 3 of the 5 raw files repeat the same messiness (crop names, mandi IDs); a shared module means the rule can't drift between files |
| SQLite, not just pandas | The dataset notes ask for a governed, query-ready model; a DB with named VIEWS is queryable by anyone with a SQLite browser, a DataFrame in your notebook isn't |
| Transit hours recomputed from timestamps, not trusted from the raw field | Two independently-logged timestamps are less likely to both be wrong than one manually-typed duration column |
| MSP imputed from the crop's own data, not an external table | Verified empirically that MSP has zero variance within a crop in this file — so this is recovering a real value, not guessing one |
| Streamlit for the dashboard | Free public deploy (`share.streamlit.io`), and the bonus agent lives inside the same app |
| Rule-based agent, not an LLM API | Dataset FAQ says don't spend money on cloud tiers; a regex slot-filler is free, offline, and fully explainable |

## Known assumptions — read `docs/ASSUMPTIONS.md`

Two judgment calls were necessary because the raw data doesn't fully
specify them: the weather-sensor-to-district mapping, and the definition
of a "delayed" trip. Both are documented there with the reasoning, so you
can defend them in your viva or adjust them if the organisers clarify.

## Files

- `docs/DATA_DICTIONARY.md` — every raw and cleaned column, explained
- `docs/ASSUMPTIONS.md` — the judgment calls made and why
- `docs/HOW_TO_RUN.md` — exact commands for your machine + how to deploy the dashboard
- `Project_Report.docx` — 4-page report with real charts and rubric self-score
