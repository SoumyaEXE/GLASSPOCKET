-- =====================================================================
-- GLASSPOCKET / 03_load_iati.sql
-- IATI activity and location data. The real geography behind Tabs 03 and 04.
-- Build Spec Section 05.
--
-- Acquisition, 45 minutes:
--   Take a BOUNDED slice, one sector or two countries. The full
--   datastore is far larger than this build needs and loading it will
--   waste an hour you do not have. See Section 04C.
--
--     PUT file://data/iati/activities.csv   @RAW.GP_STAGE/iati_activity/;
--     PUT file://data/iati/transactions.csv @RAW.GP_STAGE/iati_txn/;
--
-- IF THIS SOURCE WILL NOT LOAD
--   Do not spend more than ninety minutes fighting an upstream format.
--   Generate the disbursement layer entirely synthetically, calibrate it
--   against the published WFP figures, and disclose that on Tab 10.
--   Tabs 03 and 04 remain fully functional either way.
-- =====================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE GP_WH;
USE DATABASE GLASSPOCKET;

COPY INTO RAW.IATI_ACTIVITY (
  iati_identifier, reporting_org, title, description,
  sector_code, sector_name, recipient_country, location_name,
  latitude, longitude, budget_usd, start_date, end_date
)
FROM @RAW.GP_STAGE/iati_activity/
FILE_FORMAT = (FORMAT_NAME = RAW.FF_CSV_RAGGED)
ON_ERROR     = CONTINUE;

COPY INTO RAW.IATI_TRANSACTION (
  iati_identifier, transaction_type, transaction_date,
  value_usd, provider_org, receiver_org
)
FROM @RAW.GP_STAGE/iati_txn/
FILE_FORMAT = (FORMAT_NAME = RAW.FF_CSV_RAGGED)
ON_ERROR     = CONTINUE;

-- ---------------------------------------------------------------------
-- Activity locations, typed and H3-indexed.
--
-- Coordinates are jittered at roughly 1 km. IATI location points are
-- often a village centroid or a distribution site, and publishing them
-- unmodified alongside synthetic delivery events would imply a precision
-- this project does not have. Disclosed on Tab 10.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE STAGING.IATI_LOCATIONS AS
SELECT
  a.iati_identifier,
  TRIM(a.reporting_org)                       AS reporting_org,
  TRIM(a.title)                               AS title,
  TRIM(a.sector_name)                         AS sector_name,
  UPPER(TRIM(a.recipient_country))            AS country,
  INITCAP(TRIM(a.location_name))              AS district,
  TRY_TO_DOUBLE(a.latitude)
    + (UNIFORM(-90, 90, RANDOM()) / 10000.0)  AS lat,
  TRY_TO_DOUBLE(a.longitude)
    + (UNIFORM(-90, 90, RANDOM()) / 10000.0)  AS lon,
  TRY_TO_DOUBLE(a.budget_usd)                 AS budget_usd,
  TRY_TO_DATE(a.start_date)                   AS start_date,
  TRY_TO_DATE(a.end_date)                     AS end_date,
  'IATI_2026'                                 AS batch_id
FROM RAW.IATI_ACTIVITY a
WHERE TRY_TO_DOUBLE(a.latitude)  BETWEEN  -90 AND  90
  AND TRY_TO_DOUBLE(a.longitude) BETWEEN -180 AND 180
  AND a.location_name IS NOT NULL;

-- Index the locations. Resolution 7 for delivery granularity,
-- resolution 5 for the organisational footprint comparison.
ALTER TABLE STAGING.IATI_LOCATIONS ADD COLUMN location_h3 STRING;

UPDATE STAGING.IATI_LOCATIONS
SET location_h3 = H3_LATLNG_TO_CELL_STRING(lat, lon, 7)
WHERE location_h3 IS NULL;

-- ---------------------------------------------------------------------
-- District dimension. Feeds the privacy domain on the district column of
-- the protected serving view, which is what keeps range inference off
-- the table on Tab 05.
-- ---------------------------------------------------------------------
INSERT INTO MARTS.DISTRICT_DIM (district, country, region, centroid_lat, centroid_lon, district_h3)
SELECT
  district,
  ANY_VALUE(country)                                  AS country,
  ANY_VALUE(sector_name)                              AS region,
  AVG(lat)                                            AS centroid_lat,
  AVG(lon)                                            AS centroid_lon,
  H3_LATLNG_TO_CELL_STRING(AVG(lat), AVG(lon), 5)     AS district_h3
FROM STAGING.IATI_LOCATIONS
WHERE district IS NOT NULL
GROUP BY district;

-- ---------------------------------------------------------------------
-- Real transaction values, kept separate from the synthetic delivery
-- events so the two can never be confused in a query or on a screen.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE STAGING.IATI_TRANSACTIONS AS
SELECT
  t.iati_identifier,
  UPPER(TRIM(t.transaction_type))   AS transaction_type,
  TRY_TO_DATE(t.transaction_date)   AS transaction_date,
  TRY_TO_DOUBLE(t.value_usd)        AS value_usd,
  TRIM(t.provider_org)              AS provider_org,
  TRIM(t.receiver_org)              AS receiver_org,
  'IATI_2026'                       AS batch_id
FROM RAW.IATI_TRANSACTION t
WHERE TRY_TO_DOUBLE(t.value_usd) IS NOT NULL;

INSERT INTO MARTS.BUILD_LOG (step, detail)
SELECT '03_load_iati',
       'iati locations: ' || (SELECT COUNT(*)::STRING FROM STAGING.IATI_LOCATIONS)
    || ', districts: '    || (SELECT COUNT(*)::STRING FROM MARTS.DISTRICT_DIM);
