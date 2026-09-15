# Assumptions Log

Everything else in this pipeline is a direct, verifiable fix (a unit
conversion, a currency symbol stripped, a date format resolved). These two
are genuine judgment calls, made because the raw data doesn't fully specify
the answer. Both are isolated to one function so they're easy to change.

## 1. Weather sensor → district mapping

**The problem:** `track3_weather_sensors.xlsx` has 50 real sensor IDs (plus
an "UNKNOWN" one) and no column linking a sensor to a mandi or district.
`track3_dataset_notes.txt` says this mapping "is implied or can be assumed
1:1 with districts for simplicity."

**What we did:** `scripts/04_clean_weather.py::build_sensor_district_map()`
sorts the 18 real districts and the 50 real sensors, then assigns each
sensor to a district round-robin (sensor 1→district 1, sensor 2→district 2,
... sensor 19→district 1 again, and so on). Multiple sensors per district
are then averaged per day.

**Why round-robin instead of literal 1:1:** there are more sensors (50)
than districts (18), so a strict 1:1 would silently discard readings from
32 sensors. Round-robin keeps every real sensor reading and simply treats
multiple sensors in the same district as independent instruments measuring
the same weather — which is how a real IoT deployment would work anyway.

**How to replace it:** if the organisers release the real sensor→location
map, replace `build_sensor_district_map()` with a direct lookup from that
file. Nothing downstream (the SQL views, the dashboard, the agent) needs
to change, because they only consume the resulting `district` column.

## 2. Definition of a "delayed" transit trip

**The problem:** `fact_transport` has no target SLA or expected transit
time per route, so "delay rate" has no ready-made threshold.

**What we did:** `scripts/05_clean_transport.py` computes the MEDIAN
transit_hours for each `(mandi_id, destination_warehouse)` route as that
route's own benchmark, and flags a trip "delayed" if its transit_hours
exceeds `DELAY_THRESHOLD_MULTIPLIER × benchmark` (currently 1.5×).

**Why the route's own median, not a single global number:** WH-North and
Export-Terminal are not equidistant from every mandi, so a single
"anything over 12 hours is late" rule would flag every long-haul route as
permanently late and never flag a genuinely abnormal short-haul trip.
Using each route's own median adapts to that automatically.

**How to change it:** edit `DELAY_THRESHOLD_MULTIPLIER` at the top of
`05_clean_transport.py` if your evaluator specifies a different SLA rule
(e.g. "more than 24 hours is always late" instead of a relative one).

## 3. Matching "Amritsar mandi" to real mandi names

**The problem:** in the real data, `mandi_name` values are unrelated
place names ("Kochi Mandi", "Hyderabad Mandi", "Vijayawada Mandi") — the
generated data used mandi names independently of Punjab geography. So a
query like "Wheat in Amritsar mandi" (the example query from the notes)
matches no mandi literally named "Amritsar".

**What we did:** `agent/graph_agent.py::answer_arrival_trend_vs_msp()`
matches the location phrase against **either** `mandi_name` **or**
`district` (Amritsar is a real district in `dim_mandi`, just not a mandi
name). This keeps the agent's answer to the example bonus query correct
and honest about what it actually matched on.

## Everything else is not a judgment call

For the record, these were verified empirically before writing the fix
(not assumed) — see the project's data-profiling notes:
- Hyphen-numeric dates in this dataset are always MM-DD-YYYY (confirmed:
  in >50% of such dates, the second number exceeds 12, which is only
  possible if it's the day).
- Slash and dot dates are always DD/MM/YYYY and DD.MM.YYYY (same check,
  opposite slot).
- MSP is constant per crop everywhere it appears in `fact_prices` (std
  = 0), so imputing a missing MSP from that crop's own modal value
  elsewhere in the file recovers a real number, it doesn't invent one.
