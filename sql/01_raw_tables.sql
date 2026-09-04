-- =====================================================================
-- GLASSPOCKET / 01_raw_tables.sql
-- Landing tables and the core staging schema.
-- Build Spec Section 05.
-- =====================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE GP_WH;
USE DATABASE GLASSPOCKET;

-- ---------------------------------------------------------------------
-- RAW. Shaped to tolerate what the IRS actually publishes rather than
-- what its documentation claims. Column names differ slightly between
-- regional files, so everything lands as STRING and is normalised on the
-- way into STAGING.
-- ---------------------------------------------------------------------

CREATE OR REPLACE FILE FORMAT RAW.FF_CSV_RAGGED
  TYPE                         = CSV
  FIELD_DELIMITER              = ','
  SKIP_HEADER                  = 1
  FIELD_OPTIONALLY_ENCLOSED_BY = '"'
  TRIM_SPACE                   = TRUE
  ERROR_ON_COLUMN_COUNT_MISMATCH = FALSE   -- regional files are ragged
  REPLACE_INVALID_CHARACTERS   = TRUE
  EMPTY_FIELD_AS_NULL          = TRUE
  NULL_IF                      = ('', 'NULL', 'null', 'N/A');

CREATE STAGE IF NOT EXISTS RAW.GP_STAGE
  FILE_FORMAT = RAW.FF_CSV_RAGGED
  COMMENT     = 'Upload BMF, revocation and IATI extracts here through Snowsight.';

-- IRS Exempt Organizations Business Master File.
-- Roughly 1.8 million rows across the regional files. The primary corpus.
CREATE OR REPLACE TABLE RAW.BMF (
  ein            STRING,
  name           STRING,
  ico            STRING,
  street         STRING,
  city           STRING,
  state          STRING,
  zip            STRING,
  "GROUP"        STRING,
  subsection     STRING,
  affiliation    STRING,
  classification STRING,
  ruling         STRING,
  deductibility  STRING,
  foundation     STRING,
  activity       STRING,
  organization   STRING,
  status         STRING,
  tax_period     STRING,
  asset_cd       STRING,
  income_cd      STRING,
  filing_req_cd  STRING,
  pf_filing_req  STRING,
  acct_pd        STRING,
  asset_amt      STRING,
  income_amt     STRING,
  revenue_amt    STRING,
  ntee_cd        STRING,
  sort_name      STRING,
  source_file    STRING,
  loaded_at      TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- IRS Auto-Revocation List.
-- BE PRECISE: this records failure to file for three consecutive years.
-- It is not a fraud list. Every surface that touches it must say
-- "no longer in good standing" and never "fraudulent". See Section 05.
CREATE OR REPLACE TABLE RAW.AUTO_REVOCATION (
  ein               STRING,
  name              STRING,
  city              STRING,
  state             STRING,
  country           STRING,
  exemption_type    STRING,
  revocation_date   STRING,
  revocation_posting_date STRING,
  exemption_reinstatement_date STRING,
  loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- IATI Datastore slice. A bounded slice only, one sector or two
-- countries. The full corpus is far larger than this build needs.
CREATE OR REPLACE TABLE RAW.IATI_ACTIVITY (
  iati_identifier   STRING,
  reporting_org     STRING,
  title             STRING,
  description       STRING,
  sector_code       STRING,
  sector_name       STRING,
  recipient_country STRING,
  location_name     STRING,
  latitude          STRING,
  longitude         STRING,
  budget_usd        STRING,
  start_date        STRING,
  end_date          STRING,
  loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE OR REPLACE TABLE RAW.IATI_TRANSACTION (
  iati_identifier   STRING,
  transaction_type  STRING,
  transaction_date  STRING,
  value_usd         STRING,
  provider_org      STRING,
  receiver_org      STRING,
  loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- ProPublica Nonprofit Explorer detail, fetched during preparation.
-- Never called at render time. See Section 05.
CREATE OR REPLACE TABLE RAW.PROPUBLICA_FILINGS (
  ein             STRING,
  tax_prd_yr      STRING,
  totrevenue      STRING,
  totfuncexpns    STRING,
  totassetsend    STRING,
  pct_compnsatncurrofcr STRING,
  loaded_at       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- =====================================================================
-- STAGING. The columns the application actually uses.
-- Section 05, core schema.
-- =====================================================================

CREATE OR REPLACE TABLE STAGING.ORGS (
  org_id       STRING PRIMARY KEY,
  ein          STRING,
  name         STRING,
  blurb        STRING,
  city         STRING,
  state        STRING,
  ntee_code    STRING,
  cause        STRING,
  lat          FLOAT,
  lon          FLOAT,
  home_h3      STRING,           -- resolution 5 cell of registered address
  region_h3    STRING,           -- resolution 3 cell, the similarity pre-filter
  max_hops     INT,              -- plausible operating radius in grid steps
  is_verified  BOOLEAN,          -- present in BMF and in good standing
  is_synthetic BOOLEAN,
  batch_id     STRING,
  first_seen   TIMESTAMP_NTZ,
  name_vec     VECTOR(FLOAT, 768),

  -- Generator provenance. Populated for seeded rows only, so Tab 02 can
  -- report which technique produced each detected pair. Honest, because
  -- the tactic is known by construction.
  synth_technique STRING,
  synth_target_id STRING
);

CREATE OR REPLACE TABLE STAGING.DISBURSEMENTS (
  disbursement_id STRING PRIMARY KEY,
  org_id          STRING,
  programme_code  STRING,
  beneficiary_id  STRING,        -- entity key for differential privacy
  amount_usd      NUMBER(12,2),
  pledged_usd     NUMBER(12,2),
  district        STRING,
  lat             FLOAT,
  lon             FLOAT,
  delivery_h3     STRING,        -- resolution 7
  dispatched_at   TIMESTAMP_NTZ,
  delivered_at    TIMESTAMP_NTZ,
  status          STRING,        -- PLEDGED, DISPATCHED, DELIVERED, UNACCOUNTED
  is_synthetic    BOOLEAN,
  batch_id        STRING
);

-- Beneficiary records. Entirely synthetic. No real personal data enters
-- this project at any point, which is itself the correct engineering
-- decision and is stated in the interface. Section 07, Tab 05.
CREATE OR REPLACE TABLE STAGING.BENEFICIARIES (
  beneficiary_id STRING PRIMARY KEY,
  district       STRING,
  programme_code STRING,
  cause          STRING,
  cohort_band    STRING,
  is_synthetic   BOOLEAN,
  batch_id       STRING
);

-- District dimension. Also the source of the privacy domain on the
-- district column of the protected view, which prevents range inference.
CREATE OR REPLACE TABLE MARTS.DISTRICT_DIM (
  district    STRING PRIMARY KEY,
  country     STRING,
  region      STRING,
  centroid_lat FLOAT,
  centroid_lon FLOAT,
  district_h3 STRING
);

-- The seven cited figures from Section 01, hand-entered on purpose.
-- They must never drift, so they are not computed and not templated.
CREATE OR REPLACE TABLE MARTS.EVIDENCE_CITATIONS (
  citation_id  STRING PRIMARY KEY,
  claim        STRING,
  figure       STRING,
  magnitude    FLOAT,          -- normalised within unit_type for the timeline
  unit_type    STRING,         -- USD, DOMAINS, TRUCKS, TONNES, INR_CRORE, INR_LAKH
  region       STRING,
  issuing_body STRING,
  published_on DATE,
  url          STRING
);

CREATE OR REPLACE TABLE MARTS.BUILD_LOG (
  step        STRING,
  detail      STRING,
  logged_at   TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
