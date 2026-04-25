# Deployment Details: Singapore Rain Nowcasting MLOps

This document describes how the project pieces should be deployed to GCP and how local development maps to cloud services.

## Deployment Model

The project is deployed as several small units rather than one monolithic application.

| Project Unit | Local Location | GCP Target |
| :--- | :--- | :--- |
| Raw data archive | `data/` during local testing | GCS bucket |
| BigQuery schema | `sql/` | BigQuery dataset, table, and view |
| Shared schema/config code | `src/common/` | Packaged with functions/jobs |
| Real-time ingestion | `src/ingestion/` | Cloud Function |
| Model training | `src/training/` | Local script first, later Vertex AI or Cloud Run Job |
| Model artifact | `models/` during local testing | GCS model path |
| Prediction/inference | `src/inference/` | Cloud Function |
| Evaluation/monitoring | `src/evaluation/` | Scheduled job or Cloud Function |
| Deployment commands | `scripts/` | Run locally against GCP |
| Infrastructure definitions | `infra/` | Optional Terraform or IaC later |

## Core Data Contract

The key maintained dataset is the canonical BigQuery table:

```text
rain_silver
```

Both historical CSV data and real-time API data must be parsed into this same schema. Raw files in GCS are retained for audit, debugging, and replay, but training and inference should use `rain_silver` through the `rain_gold` feature view.

Recommended canonical fields:

| Field | Purpose |
| :--- | :--- |
| `observation_ts` | Timestamp of rainfall reading |
| `station_id` | Stable station identifier |
| `station_name` | Human-readable station name, if available |
| `latitude` | Station latitude |
| `longitude` | Station longitude |
| `rainfall_mm` | Rainfall value in millimeters |
| `source` | `historical_csv` or `realtime_api` |
| `ingested_at` | Timestamp when the row entered the pipeline |

## Deployment Sequence

### 1. Configure GCP

Create or select a GCP project, then enable the required services:

```bash
gcloud services enable cloudfunctions.googleapis.com
gcloud services enable cloudscheduler.googleapis.com
gcloud services enable bigquery.googleapis.com
gcloud services enable storage.googleapis.com
gcloud services enable firestore.googleapis.com
```

### 2. Create Storage

Create a GCS bucket for raw data and model artifacts:

```bash
gsutil mb -l asia-southeast1 gs://<bucket-name>
```

Recommended paths:

```text
gs://<bucket-name>/raw/historical/
gs://<bucket-name>/raw/realtime/
gs://<bucket-name>/models/
```

### 3. Create BigQuery Dataset, Table, and View

Use SQL files from `sql/` to create:

```text
rain_silver
rain_gold
```

`rain_silver` is the canonical cleaned observation table. `rain_gold` is the feature view used by training and inference.

### 4. Load Historical Data

During local development:

1. Download a small historical sample into `data/raw/`.
2. Parse it locally into the canonical schema.
3. Validate timestamps, station IDs, duplicates, missing values, and rainfall units.

For cloud loading:

1. Upload raw historical files to GCS.
2. Load parsed rows into BigQuery `rain_silver`.
3. Validate row counts and sample station timelines.

### 5. Train Initial Model

Initial training can run locally:

```bash
python3 -m src.training.train
```

The training job should:

1. Query or load features from `rain_gold`.
2. Train the model.
3. Evaluate it on a held-out time period.
4. Write a serialized artifact such as `model.joblib`.
5. Upload the approved artifact to GCS.

The model is not retrained for every new datapoint. Retraining is manual or scheduled, for example weekly or when drift is detected.

### 6. Deploy Real-Time Ingestion Function

Deploy `src/ingestion/` as a Cloud Function.

Responsibilities:

1. Call the real-time rainfall API.
2. Parse API JSON into the canonical `rain_silver` schema.
3. Optionally save raw API JSON to GCS.
4. Append cleaned rows to BigQuery `rain_silver`.

Trigger it with Cloud Scheduler every 5 minutes.

### 7. Deploy Prediction Function

Deploy `src/inference/` as a separate Cloud Function.

Responsibilities:

1. Query the latest feature rows from BigQuery `rain_gold`.
2. Download the existing model artifact from GCS.
3. Run inference.
4. Write the latest prediction to Firestore.

Trigger it with Cloud Scheduler every 15 minutes.

### 8. Deploy Evaluation Job

Deploy `src/evaluation/` as a scheduled job or function after inference is working.

Responsibilities:

1. Read historical predictions.
2. Join predictions against actual rainfall observations.
3. Calculate metrics such as recall, F1, Brier score, and calibration drift.
4. Store or publish the metrics for dashboarding.

### 9. Retraining Flow

As real-time data accumulates, it is appended to `rain_silver`. Over time, these rows become part of the training history.

Retraining should:

1. Query `rain_gold` over the desired training window.
2. Train a candidate model.
3. Compare it against the current production model.
4. Publish the new artifact to GCS only if it meets the promotion criteria.
5. Keep older model artifacts for rollback.

## Concrete Deployment Commands

Use these commands as the operational deployment path once the SQL files and Python entrypoints exist. Local values should come from `.env`; `.env.example` is the committed template.

Set local variables first if you are running raw `gcloud` commands. Python scripts and rendered SQL should read from `.env`.

```bash
export GCP_PROJECT="<project-id>"
export GCP_REGION="asia-southeast1"
export BQ_DATASET="<dataset-name>"
export RAW_MODEL_BUCKET="<bucket-name>"
```

### 1. Select Project and Enable Services

```bash
gcloud config set project "$GCP_PROJECT"

gcloud services enable cloudfunctions.googleapis.com
gcloud services enable cloudscheduler.googleapis.com
gcloud services enable bigquery.googleapis.com
gcloud services enable storage.googleapis.com
gcloud services enable firestore.googleapis.com
```

### 2. Create GCS Bucket

```bash
gcloud storage buckets create "gs://$RAW_MODEL_BUCKET" \
  --location="$GCP_REGION"
```

Recommended object prefixes:

```text
gs://<bucket-name>/raw/historical/
gs://<bucket-name>/raw/realtime/
gs://<bucket-name>/models/
```

### 3. Create BigQuery Dataset

```bash
bq --location="$GCP_REGION" mk "$BQ_DATASET"
```

Then apply SQL files:

```bash
python3 scripts/run_sql.py sql/create_raw_historical_external_table.sql
python3 scripts/run_sql.py sql/create_rain_silver.sql
python3 scripts/run_sql.py sql/create_rain_gold_view.sql
```

To inspect the rendered SQL without running it:

```bash
python3 scripts/run_sql.py sql/create_raw_historical_external_table.sql --dry-run
```

### 4. Upload Historical Raw Files

```bash
gcloud storage cp data/raw/*.csv "gs://$RAW_MODEL_BUCKET/raw/historical/"
```

Then load parsed canonical rows into BigQuery using the project loader script once implemented:

```bash
python3 -m src.ingestion.load_historical
```

If the CSV already matches the canonical `rain_silver` schema, a direct `bq load` can be used instead.

### 5. Train and Upload Initial Model

Run training locally:

```bash
python3 -m src.training.train
```

Upload the approved model artifact:

```bash
gcloud storage cp models/model.joblib "gs://$RAW_MODEL_BUCKET/models/model.joblib"
```

### 6. Deploy Ingestion Cloud Function

Deploy the real-time ingestion function:

```bash
gcloud functions deploy ingest-rainfall \
  --gen2 \
  --runtime=python312 \
  --region="$GCP_REGION" \
  --source=src/ingestion \
  --entry-point=main \
  --trigger-http \
  --set-env-vars="GCP_PROJECT=$GCP_PROJECT,BQ_DATASET=$BQ_DATASET,BQ_TABLE=rain_silver,RAW_BUCKET=$RAW_MODEL_BUCKET"
```

After deployment, capture the function URL:

```bash
gcloud functions describe ingest-rainfall \
  --gen2 \
  --region="$GCP_REGION" \
  --format="value(serviceConfig.uri)"
```

Create the 5-minute scheduler job:

```bash
gcloud scheduler jobs create http ingest-rainfall-every-5-min \
  --location="$GCP_REGION" \
  --schedule="*/5 * * * *" \
  --uri="<ingestion-function-url>" \
  --http-method=POST
```

### 7. Deploy Prediction Cloud Function

Deploy the inference function:

```bash
gcloud functions deploy predict-rainfall \
  --gen2 \
  --runtime=python312 \
  --region="$GCP_REGION" \
  --source=src/inference \
  --entry-point=main \
  --trigger-http \
  --set-env-vars="GCP_PROJECT=$GCP_PROJECT,BQ_DATASET=$BQ_DATASET,BQ_VIEW=rain_gold,MODEL_URI=gs://$RAW_MODEL_BUCKET/models/model.joblib"
```

After deployment, capture the function URL:

```bash
gcloud functions describe predict-rainfall \
  --gen2 \
  --region="$GCP_REGION" \
  --format="value(serviceConfig.uri)"
```

Create the 15-minute scheduler job:

```bash
gcloud scheduler jobs create http predict-rainfall-every-15-min \
  --location="$GCP_REGION" \
  --schedule="*/15 * * * *" \
  --uri="<prediction-function-url>" \
  --http-method=POST
```

### 8. Deploy Evaluation Later

Once predictions are being written, deploy `src/evaluation/` as either a daily Cloud Function or Cloud Run Job. It should join stored predictions with actual rainfall observations and publish metrics.

### Deployment Order Summary

```text
GCS bucket
-> BigQuery dataset/table/view
-> historical load
-> local training
-> upload model to GCS
-> deploy ingestion function
-> schedule ingestion
-> deploy prediction function
-> schedule prediction
-> deploy evaluation job
```

## Local Development Flow

Recommended order:

1. Build and test the historical parser.
2. Define the canonical `rain_silver` schema.
3. Prototype features locally with pandas.
4. Translate features into BigQuery SQL.
5. Train an initial model locally.
6. Test inference locally with one feature row.
7. Deploy ingestion.
8. Deploy inference.
9. Add evaluation and retraining.

For detailed local test commands, see `local_testing_guide.md`.

## Testing SQL Scripts

SQL files that contain `${VAR}` placeholders should be tested with `scripts/run_sql.py`, not sent directly to `bq`.

Preview rendered SQL:

```bash
python3 scripts/run_sql.py sql/create_raw_historical_external_table.sql --dry-run
```

Run the SQL against BigQuery:

```bash
python3 scripts/run_sql.py sql/create_raw_historical_external_table.sql
```

Validate the created object:

```bash
bq query --use_legacy_sql=false \
'SELECT COUNT(*) AS row_count
 FROM `singapore-weather-mlops.raw_layer.historical`'
```

## Repository Structure

```text
.
├── data/
├── infra/
├── models/
├── scripts/
├── sql/
├── src/
│   ├── common/
│   ├── evaluation/
│   ├── inference/
│   ├── ingestion/
│   └── training/
└── tests/
```
