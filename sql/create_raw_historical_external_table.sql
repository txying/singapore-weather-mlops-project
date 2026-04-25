CREATE OR REPLACE EXTERNAL TABLE `${GCP_PROJECT_ID}.${BQ_RAW_DATASET}.${BQ_RAW_HISTORICAL_TABLE}`
(
  date DATE,
  timestamp TIMESTAMP,
  update_timestamp TIMESTAMP,
  station_id STRING,
  station_name STRING,
  station_device_id STRING,
  location_longitude FLOAT64,
  location_latitude FLOAT64,
  reading_update_timestamp TIMESTAMP,
  reading_value FLOAT64,
  reading_type STRING,
  reading_unit STRING
)
OPTIONS (
  format = 'CSV',
  uris = ['${GCS_HISTORICAL_URI}'],
  skip_leading_rows = 1
);