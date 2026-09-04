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

-- ---------------------------------------------------------------------
-- NO IATI SLICE WAS LOADED FOR THIS BUILD.
--
-- Section 04C permits this explicitly: "If IATI proves awkward inside the
-- time budget, generate the disbursement layer entirely synthetically,
-- calibrate it against the published WFP figures, and disclose that on
-- Tab 10." That is what happened, the calibration is the 371-from-590
-- WFP ratio, and Tab 10 discloses it.
--
-- So the district dimension is derived from the delivery geography
-- instead of from IATI activity locations. It still has to exist,
-- because the governance policy and the semantic view both reference it.
--
--   PUT file://data/warehouse/district_dim.csv @RAW.GP_STAGE/warehouse/;
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE RAW.DISTRICT_PREPARED (
  district STRING, country STRING, region STRING,
  centroid_lat FLOAT, centroid_lon FLOAT, district_h3 STRING
);

COPY INTO RAW.DISTRICT_PREPARED
  FROM @RAW.GP_STAGE/warehouse/district_dim.csv
  FILE_FORMAT = (FORMAT_NAME = RAW.FF_PREPARED)
  ON_ERROR = ABORT_STATEMENT;

DELETE FROM MARTS.DISTRICT_DIM;

INSERT INTO MARTS.DISTRICT_DIM
  (district, country, region, centroid_lat, centroid_lon, district_h3)
SELECT district, country, region, centroid_lat, centroid_lon, district_h3
FROM RAW.DISTRICT_PREPARED;

-- Kept so the object exists for the full-scale path and for the semantic
-- layer, empty under this build.
CREATE TABLE IF NOT EXISTS STAGING.IATI_LOCATIONS (
  iati_identifier STRING, reporting_org STRING, title STRING,
  sector_name STRING, country STRING, district STRING,
  lat FLOAT, lon FLOAT, budget_usd FLOAT,
  start_date DATE, end_date DATE, batch_id STRING, location_h3 STRING
);

CREATE TABLE IF NOT EXISTS STAGING.IATI_TRANSACTIONS (
  iati_identifier STRING, transaction_type STRING, transaction_date DATE,
  value_usd FLOAT, provider_org STRING, receiver_org STRING, batch_id STRING
);

INSERT INTO MARTS.BUILD_LOG (step, detail)
SELECT '03_load_iati',
       'districts: ' || COUNT(*)::STRING
    || ' (derived from delivery geography; no IATI slice loaded, '
    || 'disclosed on Tab 10)'
FROM MARTS.DISTRICT_DIM;
