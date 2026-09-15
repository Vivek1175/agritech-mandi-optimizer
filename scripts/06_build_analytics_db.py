"""
06_build_analytics_db.py
--------------------------
Loads the 5 cleaned tables (1 dimension + 4 facts) into SQLite and builds
the exact business metrics the dataset notes ask for:

  - Total crop arrivals (in Quintals)          -> v_arrivals_by_crop
  - Average wholesale modal price vs MSP        -> v_price_vs_msp
  - Price crash instances (Modal < MSP)         -> v_price_crashes
  - Average transit time by warehouse           -> v_transit_by_warehouse
  - Transit delay rate                          -> v_delay_rate
  - Top Mandis by arrival volume                -> v_top_mandis
  - Crop-wise arrival distribution               -> v_arrivals_by_crop (same view answers this too)

Weather-vs-arrivals correlation isn't a single number SQL can hand back
cleanly, so that one is computed separately in Python (see the
correlation() function below) and printed / used directly by the dashboard.
"""

import sqlite3
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED = PROJECT_ROOT / "data" / "processed"
DB_PATH = PROCESSED / "agritech.db"


def load_tables(conn: sqlite3.Connection) -> None:
    pd.read_csv(PROCESSED / "dim_mandi.csv").to_sql("dim_mandi", conn, if_exists="replace", index=False)
    pd.read_csv(PROCESSED / "fact_arrivals.csv", parse_dates=["arrival_date"]).to_sql(
        "fact_arrivals", conn, if_exists="replace", index=False)
    pd.read_csv(PROCESSED / "fact_prices.csv", parse_dates=["price_date"]).to_sql(
        "fact_prices", conn, if_exists="replace", index=False)
    pd.read_csv(PROCESSED / "fact_weather.csv", parse_dates=["reading_date"]).to_sql(
        "fact_weather", conn, if_exists="replace", index=False)
    pd.read_csv(PROCESSED / "fact_transport.csv", parse_dates=["departure_time", "arrival_time"]).to_sql(
        "fact_transport", conn, if_exists="replace", index=False)


def create_views(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    cur.execute("""
        CREATE VIEW IF NOT EXISTS v_arrivals_by_crop AS
        SELECT crop, COUNT(*) AS n_reports, SUM(arrival_quintal) AS total_arrivals_quintal
        FROM fact_arrivals GROUP BY crop ORDER BY total_arrivals_quintal DESC
    """)

    cur.execute("""
        CREATE VIEW IF NOT EXISTS v_top_mandis AS
        SELECT m.mandi_name, m.district, f.crop,
               SUM(f.arrival_quintal) AS total_arrivals_quintal
        FROM fact_arrivals f
        JOIN dim_mandi m ON f.mandi_id = m.mandi_id
        GROUP BY m.mandi_name, m.district, f.crop
        ORDER BY total_arrivals_quintal DESC
    """)

    cur.execute("""
        CREATE VIEW IF NOT EXISTS v_price_vs_msp AS
        SELECT p.price_date, m.mandi_name, m.district, p.crop,
               p.modal_price, p.msp,
               ROUND(p.modal_price - p.msp, 2) AS gap_rs,
               ROUND(100.0 * (p.modal_price - p.msp) / p.msp, 2) AS gap_pct,
               p.price_crash
        FROM fact_prices p
        JOIN dim_mandi m ON p.mandi_id = m.mandi_id
    """)

    cur.execute("""
        CREATE VIEW IF NOT EXISTS v_price_crashes AS
        SELECT m.mandi_name, m.district, p.crop,
               COUNT(*) AS crash_instances,
               ROUND(AVG(p.modal_price - p.msp), 2) AS avg_shortfall_rs
        FROM fact_prices p
        JOIN dim_mandi m ON p.mandi_id = m.mandi_id
        WHERE p.price_crash = 1
        GROUP BY m.mandi_name, m.district, p.crop
        ORDER BY crash_instances DESC
    """)

    cur.execute("""
        CREATE VIEW IF NOT EXISTS v_transit_by_warehouse AS
        SELECT destination_warehouse,
               COUNT(*) AS n_trips,
               ROUND(AVG(transit_hours), 2) AS avg_transit_hours,
               ROUND(AVG(distance_km), 1) AS avg_distance_km
        FROM fact_transport
        GROUP BY destination_warehouse
        ORDER BY avg_transit_hours DESC
    """)

    cur.execute("""
        CREATE VIEW IF NOT EXISTS v_delay_rate AS
        SELECT m.mandi_name, t.destination_warehouse,
               COUNT(*) AS n_trips,
               SUM(CASE WHEN t.is_delayed THEN 1 ELSE 0 END) AS n_delayed,
               ROUND(100.0 * SUM(CASE WHEN t.is_delayed THEN 1 ELSE 0 END) / COUNT(*), 1) AS delay_rate_pct
        FROM fact_transport t
        JOIN dim_mandi m ON t.mandi_id = m.mandi_id
        GROUP BY m.mandi_name, t.destination_warehouse
        ORDER BY delay_rate_pct DESC
    """)

    cur.execute("""
        CREATE VIEW IF NOT EXISTS v_arrivals_daily_district AS
        SELECT f.arrival_date, m.district, f.crop, SUM(f.arrival_quintal) AS total_arrivals_quintal
        FROM fact_arrivals f
        JOIN dim_mandi m ON f.mandi_id = m.mandi_id
        GROUP BY f.arrival_date, m.district, f.crop
    """)

    conn.commit()


def weather_arrival_correlation(conn: sqlite3.Connection) -> pd.DataFrame:
    """Correlation between daily rainfall and daily arrival volume, per
    district. Computed in pandas because SQLite has no CORR() function."""
    arrivals = pd.read_sql(
        "SELECT arrival_date, district, SUM(total_arrivals_quintal) AS arrivals "
        "FROM v_arrivals_daily_district GROUP BY arrival_date, district",
        conn, parse_dates=["arrival_date"],
    )
    weather = pd.read_sql("SELECT reading_date, district, rainfall_mm FROM fact_weather",
                           conn, parse_dates=["reading_date"])

    merged = arrivals.merge(
        weather, left_on=["arrival_date", "district"], right_on=["reading_date", "district"], how="inner"
    )
    corr = merged.groupby("district").apply(
        lambda g: g["arrivals"].corr(g["rainfall_mm"]) if len(g) > 5 else float("nan"),
        include_groups=False,
    ).reset_index(name="rainfall_arrivals_correlation")
    corr.to_csv(PROCESSED / "weather_arrival_correlation.csv", index=False)
    return corr


def sanity_check(conn: sqlite3.Connection) -> None:
    for view in ["v_arrivals_by_crop", "v_price_vs_msp", "v_price_crashes",
                 "v_transit_by_warehouse", "v_delay_rate", "v_top_mandis"]:
        df = pd.read_sql(f"SELECT * FROM {view} LIMIT 3", conn)
        print(f"\n--- {view} ---")
        print(df.to_string(index=False))


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    load_tables(conn)
    create_views(conn)
    sanity_check(conn)

    corr = weather_arrival_correlation(conn)
    print("\n--- Weather-Arrival correlation (rainfall vs arrivals, by district) ---")
    print(corr.to_string(index=False))

    conn.close()
    print(f"\nSQLite database ready at: {DB_PATH}")
