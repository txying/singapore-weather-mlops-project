# Local Testing Guide

This guide explains how to test project components locally before deploying them to GCP.

## Prerequisites

Install and configure:

```bash
gcloud --version
bq version
python3 --version
```

Authenticate with GCP:

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project singapore-weather-mlops
```

Confirm `.env` exists:

```bash
test -f .env && echo ".env found"
```

If it does not exist:

```bash
cp .env.example .env
```

Then edit `.env` with your local project, dataset, table, and bucket values.

## 1. Test `.env` Loading

Python scripts should load values from `.env` through `src/common/config.py`.

Quick check:

```bash
python3 - <<'PY'
from src.common.config import load_env, get_required_env

load_env()
print(get_required_env("GCP_PROJECT_ID"))
print(get_required_env("GCS_HISTORICAL_URI"))
PY
```

Expected result: it prints your project ID and historical GCS URI.

## 2. Test SQL Rendering

BigQuery SQL files do not read `.env` directly. Use `scripts/run_sql.py` to render `${VAR}` placeholders from `.env`.

Dry-run render:

```bash
python3 scripts/run_sql.py sql/create_raw_historical_external_table.sql --dry-run
```

Expected result: the output should contain concrete values, for example:

```sql
CREATE OR REPLACE EXTERNAL TABLE `singapore-weather-mlops.raw_layer.historical`
...
uris = ['gs://historical-rainfall-data/HistoricalRainfallacrossSingapore*.csv']
```

If you still see `${GCP_PROJECT_ID}` or `${GCS_HISTORICAL_URI}`, `.env` is missing the required value.

## 3. Test SQL Against BigQuery

Make sure the raw dataset exists:

```bash
bq --location=asia-southeast1 mk raw_layer
```

If it already exists, BigQuery may return an "Already Exists" message. That is fine.

Run the SQL:

```bash
python3 scripts/run_sql.py sql/create_raw_historical_external_table.sql
```

Validate the external table:

```bash
bq query --use_legacy_sql=false \
'SELECT COUNT(*) AS row_count
 FROM `singapore-weather-mlops.raw_layer.historical`'
```

Preview rows:

```bash
bq query --use_legacy_sql=false \
'SELECT *
 FROM `singapore-weather-mlops.raw_layer.historical`
 LIMIT 10'
```

Common issues:

| Error | Likely Cause |
| :--- | :--- |
| Dataset not found | Create the dataset or fix `BQ_RAW_DATASET` |
| Access denied | Wrong project, missing IAM, or unauthenticated CLI |
| URI not found | Wrong `GCS_HISTORICAL_URI` or bucket path |
| CSV parse error | SQL schema does not match the CSV column order or timestamp format |

## 4. Test Historical CSV Parsing

Historical parsing code should live in:

```text
src/ingestion/parse_historical_csv.py
```

Expected local workflow once implemented:

```bash
python3 -m src.ingestion.parse_historical_csv \
  --input data/raw/historical/sample.csv \
  --output data/processed/historical_sample.parquet
```

The parser should verify:

1. Required columns exist.
2. Timestamps parse correctly.
3. Rainfall values are numeric.
4. Output rows match the canonical `rain_silver` schema.
5. Duplicate station/timestamp rows are handled deliberately.

Automated tests should live in:

```text
tests/test_parse_historical_csv.py
```

Run them with:

```bash
python3 -m pytest tests/test_parse_historical_csv.py
```

## 5. Test Real-Time API Parsing

Real-time parsing code should live in:

```text
src/ingestion/parse_realtime_api.py
```

Use a saved fixture before testing live API calls:

```text
tests/fixtures/realtime_rainfall_sample.json
```

Expected local workflow once implemented:

```bash
python3 -m src.ingestion.parse_realtime_api \
  --input tests/fixtures/realtime_rainfall_sample.json
```

Automated tests should live in:

```text
tests/test_parse_realtime_api.py
```

Run them with:

```bash
python3 -m pytest tests/test_parse_realtime_api.py
```

## 6. Test Historical Load to BigQuery

Historical loading code should live in:

```text
src/ingestion/load_historical.py
```

Expected workflow once implemented:

```bash
python3 -m src.ingestion.load_historical
```

Validation queries:

```bash
bq query --use_legacy_sql=false \
'SELECT COUNT(*) AS row_count
 FROM `singapore-weather-mlops.silver_layer.rain_silver`'
```

```bash
bq query --use_legacy_sql=false \
'SELECT station_id, COUNT(*) AS rows
 FROM `singapore-weather-mlops.silver_layer.rain_silver`
 GROUP BY station_id
 ORDER BY rows DESC
 LIMIT 10'
```

## 7. Test Feature SQL

Feature SQL should live in:

```text
sql/create_rain_gold_view.sql
```

Render first:

```bash
python3 scripts/run_sql.py sql/create_rain_gold_view.sql --dry-run
```

Run it:

```bash
python3 scripts/run_sql.py sql/create_rain_gold_view.sql
```

Validate feature rows:

```bash
bq query --use_legacy_sql=false \
'SELECT *
 FROM `singapore-weather-mlops.gold_layer.rain_gold`
 WHERE rainfall_lag_60m IS NOT NULL
 LIMIT 10'
```

Check that labels do not leak into inference. Training can use future-looking target columns such as `LEAD(...)`; prediction should only use features available at prediction time.

## 8. Test Training Locally

Training code should live in:

```text
src/training/train.py
```

Expected workflow once implemented:

```bash
python3 -m src.training.train
```

Expected outputs:

```text
models/model.joblib
models/model_metrics.json
models/feature_columns.json
```

The training script should:

1. Load `.env`.
2. Query training data from `rain_gold`.
3. Split data by time, not random row order.
4. Train the model.
5. Save model and metadata locally.

## 9. Test Inference Locally

Inference code should live in:

```text
src/inference/predict.py
```

Expected local workflow once implemented:

```bash
python3 -m src.inference.predict \
  --features data/processed/latest_feature_row.json \
  --model models/model.joblib
```

Expected result: it prints a probability such as:

```text
rain_probability=0.42
```

Before deploying the Cloud Function, verify that the inference code can:

1. Load the model artifact.
2. Accept one feature row.
3. Return a probability.
4. Fail clearly if required features are missing.

## 10. Test Cloud Function Entrypoints Locally

Function entrypoints should be thin wrappers around testable helper functions.

Expected files:

```text
src/ingestion/main.py
src/inference/main.py
```

Local test strategy:

1. Test parser and prediction helpers directly with unit tests.
2. Keep Cloud Function `main` functions small.
3. Use mocked BigQuery, GCS, and Firestore clients in tests.

Recommended test files:

```text
tests/test_ingestion_function.py
tests/test_inference_function.py
```

## 11. Test Deployment Commands Without Deploying

For SQL, use dry-run rendering:

```bash
python3 scripts/run_sql.py sql/create_raw_historical_external_table.sql --dry-run
```

For shell deployment scripts, prefer adding a `--dry-run` flag when they are implemented. Until then, manually inspect commands in:

```text
deployment_details.md
```

## 12. Local Test Checklist

Before deploying:

```text
[ ] .env contains correct project, dataset, table, and bucket values
[ ] SQL renders correctly with scripts/run_sql.py --dry-run
[ ] raw external table can be queried
[ ] historical parser outputs canonical rain_silver rows
[ ] real-time parser outputs canonical rain_silver rows
[ ] rain_silver table contains historical rows
[ ] rain_gold view returns lag/rolling features
[ ] training writes model.joblib and metrics
[ ] inference returns one probability from one feature row
[ ] unit tests pass
```

