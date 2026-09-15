# Data Dictionary

## Raw files (as released)

### track3_mandi_master.csv
| Column | Meaning | Known issues |
|---|---|---|
| mandi_id | Mandi identifier | 6 formats: MANDI001 / MANDI-001 / mandi_001 / mandi001 / M001 / 001 |
| mandi_name | Mandi name | Clean |
| district | District | Case inconsistent (ludhiana/LUDHIANA/Ludhiana); 4 rows missing |
| state | State | 4 rows missing |
| mandi_type | Private/Direct/APMC | Case inconsistent; 11 rows missing |
| total_area_acres | Mandi area | 6 rows literal "NA" (parsed as null automatically by pandas) |

### track3_mandi_arrivals.csv
| Column | Meaning | Known issues |
|---|---|---|
| arrival_id | Record ID | Clean |
| date | Arrival date | 6 formats (see `common.py` docstring for the exact resolution order) |
| mandi_id | Mandi identifier | Same 6-format problem as master |
| crop_name | Crop | English/Hindi/Punjabi mixed, case inconsistent |
| variety | Crop variety | ~15% missing |
| arrival_quantity | Quantity | Sometimes a clean number, sometimes has the unit baked in ("415.88 qtl"); ~5% negative |
| unit | KG/Qtl/Tonnes etc. | 12 spelling variants; blank when the unit is embedded in `arrival_quantity` instead |
| farmer_count | Number of farmers that day | ~15% missing |

### track3_price_and_msp.json
| Column | Meaning | Known issues |
|---|---|---|
| record_id | Record ID | Clean |
| date | Price date | Same 6-format problem |
| mandi_id | Mandi identifier | Same 6-format problem; ~10% unrecoverable (no digits at all) |
| district | District | ~6% missing — **not used**; we join to `dim_mandi` for district instead |
| crop_name | Crop | Same crop messiness as arrivals |
| min_price / max_price / modal_price | Rs./quintal | Mix of ₹7,570.17 / Rs. 7,299 / INR 2,183 / plain floats / plain numeric strings |
| msp | Government MSP, Rs./quintal | Same money-string mess; ~20% blank |

### track3_weather_sensors.xlsx
| Column | Meaning | Known issues |
|---|---|---|
| sensor_id | Sensor identifier | 50 real sensors + "UNKNOWN" |
| timestamp | Reading time | 6 formats; some tagged UTC, some IST, some untagged (assumed already IST); ~10% missing |
| temperature | Temp reading | Sometimes plain number + `temp_unit`, sometimes unit baked into the string ("39.8°C") |
| temp_unit | F/Fahrenheit/°F/C/Celsius/°C, mixed case | Blank when unit is embedded in `temperature` |
| rainfall | Rainfall reading | ~10% negative (sensor glitch) |
| rain_unit | mm/MM/millimeters vs in/inch/inches | |
| humidity_percent | % humidity | Some missing |

### track3_transport_logistics.csv
| Column | Meaning | Known issues |
|---|---|---|
| trip_id | Trip ID | Clean |
| mandi_id | Origin mandi | Same 6-format problem |
| destination_warehouse | WH-North/South/East/West/Central/Export-Terminal | Clean |
| departure_time / arrival_time | Timestamps | 6 formats; ~10% of arrival_time missing |
| transit_hours | Reported duration | Sometimes has " hrs" suffix; ~5% negative |
| distance / distance_unit | Distance | km or miles |
| vehicle_no | Registration plate | Spacing/hyphen/case all inconsistent; ~15% missing |
| driver_id | Driver ID | Clean |

## Cleaned tables (`data/processed/`)

**dim_mandi.csv**: mandi_id, mandi_name, district, state, mandi_type, total_area_acres — one row per unique mandi.

**fact_arrivals.csv**: arrival_id, arrival_date, mandi_id, crop, variety, arrival_quintal, was_negative_qty, farmer_count.

**fact_prices.csv**: record_id, price_date, mandi_id, crop, min_price, max_price, modal_price, modal_price_was_imputed, msp, price_crash.

**fact_weather.csv**: reading_date, district, temp_c, rainfall_mm, humidity_percent — aggregated to one row per district per day (mean of all sensors mapped to that district).

**fact_transport.csv**: trip_id, mandi_id, destination_warehouse, departure_time, arrival_time, transit_hours, was_impossible_duration, distance_km, vehicle_no_clean, driver_id, is_delayed.

**agritech.db**: SQLite database containing all 5 tables above plus the views listed in the main README.
