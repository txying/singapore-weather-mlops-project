# Repository Structure Guide

This file explains what each directory is for and where new project files should go.

## Top-Level Markdown Files

| Path | Use |
| :--- | :--- |
| `singapore_weather_mlops_plan.md` | Main project plan, architecture diagram, phases, and success metrics |
| `deployment_details.md` | GCP deployment process, commands, and service mapping |
| `repository_structure.md` | Guide for where code, SQL, scripts, models, and data should live |
| `local_testing_guide.md` | Local test workflow for SQL, parsers, training, inference, and deployment dry-runs |

## `data/`

Use this for local development data only.

Recommended structure:

```text
data/
├── raw/
│   └── historical/
├── interim/
└── processed/
```

Examples:

| Path | Use |
| :--- | :--- |
| `data/raw/historical/` | Locally downloaded historical CSV files from Data.gov.sg |
| `data/raw/realtime/` | Optional local samples of real-time API JSON |
| `data/interim/` | Temporary parsed files while developing locally |
| `data/processed/` | Local cleaned samples matching the `rain_silver` schema |

Do not commit real data files unless they are tiny test fixtures. The `data/.gitignore` file is set up to ignore local data by default.

## `sql/`

Use this for BigQuery SQL definitions.

Expected files:

```text
sql/
├── create_raw_historical_external_table.sql
├── create_rain_silver.sql
├── load_historical_to_silver.sql
├── create_rain_gold_view.sql
└── validation_queries.sql
```

Examples:

| File | Use |
| :--- | :--- |
| `create_raw_historical_external_table.sql` | Creates the raw-layer external table over historical CSV files in GCS |
| `create_rain_silver.sql` | Creates the canonical cleaned rainfall table |
| `load_historical_to_silver.sql` | Transforms raw historical rows into the canonical `rain_silver` table |
| `create_rain_gold_view.sql` | Creates the feature view used by training and inference |
| `validation_queries.sql` | Row count checks, duplicate checks, timestamp gap checks |

SQL files can contain `${VAR}` placeholders. Run them through `scripts/run_sql.py` so values are rendered from `.env` before BigQuery receives the query:

```bash
python3 scripts/run_sql.py sql/create_raw_historical_external_table.sql --dry-run
python3 scripts/run_sql.py sql/create_raw_historical_external_table.sql
```

## `src/common/`

Use this for shared Python code used by multiple components.

Examples:

```text
src/common/
├── config.py
├── schema.py
└── time_utils.py
```

Typical contents:

| File | Use |
| :--- | :--- |
| `config.py` | Loads `.env` and reads values like project ID, dataset, bucket, model URI |
| `schema.py` | Defines canonical field names and expected types for `rain_silver` |
| `time_utils.py` | Shared timestamp parsing and timezone helpers |

Keep this folder small. Only put code here if more than one part of the project needs it.

## `src/ingestion/`

Use this for code that gets data into the canonical `rain_silver` table.

This is where the historical CSV parser should go.

Recommended files:

```text
src/ingestion/
├── main.py
├── parse_historical_csv.py
├── parse_realtime_api.py
├── load_historical.py
└── requirements.txt
```

Examples:

| File | Use |
| :--- | :--- |
| `main.py` | Cloud Function entrypoint for real-time API ingestion |
| `parse_historical_csv.py` | Converts downloaded historical CSV rows into the canonical `rain_silver` schema |
| `parse_realtime_api.py` | Converts real-time API JSON into the canonical `rain_silver` schema |
| `load_historical.py` | One-time or repeatable script that loads parsed historical rows into BigQuery |
| `requirements.txt` | Dependencies needed by the ingestion Cloud Function |

Rule of thumb:

```text
If the code reads external rainfall data and turns it into rain_silver rows, put it in src/ingestion/.
```

## `src/training/`

Use this for model training code.

Recommended files:

```text
src/training/
├── train.py
├── features_local.py
├── evaluate_model.py
└── requirements.txt
```

Examples:

| File | Use |
| :--- | :--- |
| `train.py` | Queries training data, trains the model, writes `model.joblib` |
| `features_local.py` | Optional pandas prototype of feature logic before translating to BigQuery SQL |
| `evaluate_model.py` | Offline evaluation on validation/test splits |
| `requirements.txt` | Dependencies for local or cloud training |

Training should read from `rain_gold` or a local export of `rain_gold`, not from raw CSVs directly.

## `src/inference/`

Use this for prediction-time code.

Recommended files:

```text
src/inference/
├── main.py
├── predict.py
└── requirements.txt
```

Examples:

| File | Use |
| :--- | :--- |
| `main.py` | Cloud Function entrypoint for scheduled prediction |
| `predict.py` | Loads the model, accepts feature rows, returns prediction probabilities |
| `requirements.txt` | Dependencies needed by the inference Cloud Function |

Inference should query the latest features from `rain_gold`, load the existing model from GCS, and write predictions to Firestore.

## `src/evaluation/`

Use this for monitoring and evaluation jobs.

Recommended files:

```text
src/evaluation/
├── evaluate_predictions.py
├── drift_checks.py
└── requirements.txt
```

Examples:

| File | Use |
| :--- | :--- |
| `evaluate_predictions.py` | Joins predictions with actual rainfall observations and calculates metrics |
| `drift_checks.py` | Checks feature drift, calibration drift, or data freshness issues |
| `requirements.txt` | Dependencies for scheduled evaluation |

## `scripts/`

Use this for command-line helper scripts that operate the project.

Recommended files:

```text
scripts/
├── run_sql.py
├── deploy_bigquery.sh
├── deploy_ingestion.sh
├── deploy_inference.sh
├── upload_model.sh
└── run_local_checks.sh
```

Examples:

| File | Use |
| :--- | :--- |
| `run_sql.py` | Renders SQL files with `.env` values and runs them with `bq` |
| `deploy_bigquery.sh` | Runs SQL files to create/update BigQuery resources |
| `deploy_ingestion.sh` | Deploys the ingestion Cloud Function |
| `deploy_inference.sh` | Deploys the prediction Cloud Function |
| `upload_model.sh` | Uploads `models/model.joblib` to GCS |
| `run_local_checks.sh` | Runs formatting, tests, and validation queries |

Use `scripts/` for operational commands, not reusable Python logic.

## `models/`

Use this for local model artifacts during development.

Examples:

```text
models/
├── model.joblib
├── model_metrics.json
└── feature_columns.json
```

The production model should be uploaded to GCS:

```text
gs://<bucket-name>/models/model.joblib
```

Avoid committing large model files unless they are intentionally small examples.

## `infra/`

Use this for infrastructure-as-code later.

Examples:

```text
infra/
├── main.tf
├── variables.tf
└── outputs.tf
```

This can stay empty while deployment is handled by `gcloud` and shell scripts.

## `tests/`

Use this for automated tests.

Recommended files:

```text
tests/
├── test_parse_historical_csv.py
├── test_parse_realtime_api.py
├── test_features_local.py
└── fixtures/
```

Examples:

| File | Use |
| :--- | :--- |
| `test_parse_historical_csv.py` | Verifies historical CSV rows are parsed into the canonical schema |
| `test_parse_realtime_api.py` | Verifies API JSON rows are parsed into the canonical schema |
| `test_features_local.py` | Verifies lag, rolling, and target logic on small samples |
| `tests/fixtures/` | Tiny fake CSV/API samples that are safe to commit |

## Quick Placement Guide

| Task | Put It Here |
| :--- | :--- |
| Parse historical CSV files | `src/ingestion/parse_historical_csv.py` |
| Parse real-time API JSON | `src/ingestion/parse_realtime_api.py` |
| Load parsed historical rows to BigQuery | `src/ingestion/load_historical.py` |
| Define BigQuery table schema | `sql/create_rain_silver.sql` |
| Define BigQuery feature view | `sql/create_rain_gold_view.sql` |
| Prototype features in pandas | `src/training/features_local.py` |
| Train XGBoost model | `src/training/train.py` |
| Run scheduled prediction | `src/inference/main.py` |
| Evaluate predictions | `src/evaluation/evaluate_predictions.py` |
| Deploy Cloud Functions | `scripts/deploy_ingestion.sh`, `scripts/deploy_inference.sh` |
