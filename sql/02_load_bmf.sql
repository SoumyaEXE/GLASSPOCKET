-- =====================================================================
-- GLASSPOCKET / 02_load_bmf.sql
-- The organisation corpus into STAGING.ORGS.
-- Build Spec Section 05, source inventory.
--
-- THERE ARE TWO PATHS AND THEY PRODUCE THE SAME TABLE.
--
--   PATH A, FULL SCALE, at the foot of this file.
--     Stage the raw IRS regional extracts and let Snowflake do the
--     parsing, the deduplication, the ZIP join and the H3 indexing over
--     all 1.8 million rows. It is the honest full-corpus path and it is
--     kept because it is the one the write-up describes as possible.
--
--   PATH B, BOUNDED, immediately below, and the one the deployment runs.
--     Load the already-normalised corpus produced by
--     tools/export_for_snowflake.py.
--
-- WHY THE DEPLOYMENT TAKES PATH B
--   Two hard constraints, both from Section 02.
--
--   Trap 06. Vector similarity performs an exact scan. The similarity
--   join is pre-filtered on region_h3 and cause, but over nine hundred
--   thousand organisations even a pre-filtered self-join is a large
--   query, and it would run against a trial credit budget.
--
--   Trap 09. The AI functions that would populate the vector column are
--   blocked on this account, so the vectors are produced offline. Only
--   the organisations that can actually reach the pre-filtered join were
--   embedded. Loading rows with no vector would add cost and no
--   detection.
--
--   Everything DOWNSTREAM of this table is still computed in the
--   warehouse: clone detection, the evasion gap, the H3 geometry, the
--   risk UDF, the Dynamic Tables, the semantic view and the policy. This
--   file decides which rows Snowflake works over. It does not move the
--   work out of Snowflake.
--
--   Tab 10 reports the loaded count and the upstream count side by side,
--   so the bound is disclosed rather than implied.
-- =====================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE GP_WH;
USE DATABASE GLASSPOCKET;

CREATE OR REPLACE FILE FORMAT RAW.FF_PREPARED
  TYPE                         = CSV
  SKIP_HEADER                  = 1
  FIELD_OPTIONALLY_ENCLOSED_BY = '"'
  EMPTY_FIELD_AS_NULL          = TRUE
  NULL_IF                      = ('', 'NULL', 'None', 'nan')
  TRIM_SPACE                   = TRUE;

-- ---------------------------------------------------------------------
-- PATH B. The prepared corpus.
--   python tools/export_for_snowflake.py
--   PUT file://data/warehouse/orgs.csv @RAW.GP_STAGE/warehouse/;
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE RAW.ORGS_PREPARED (
  org_id STRING, ein STRING, name STRING, blurb STRING,
  city STRING, state STRING, ntee_code STRING, cause STRING,
  lat FLOAT, lon FLOAT, home_h3 STRING, region_h3 STRING, base_h3 STRING,
  max_hops INT, is_verified BOOLEAN, is_synthetic BOOLEAN, batch_id STRING,
  synth_technique STRING, synth_target_id STRING
);

COPY INTO RAW.ORGS_PREPARED
  FROM @RAW.GP_STAGE/warehouse/orgs.csv
  FILE_FORMAT = (FORMAT_NAME = RAW.FF_PREPARED)
  ON_ERROR = ABORT_STATEMENT;

-- The registered address and the declared operating base are different
-- things and the geometry test depends on the difference, so base_h3 is
-- carried through rather than recomputed. See tools/make_synthetic.py,
-- assign_operating_bases, for why a US-registered NGO delivering in
-- Kassala is not a finding.
ALTER TABLE STAGING.ORGS ADD COLUMN IF NOT EXISTS base_h3 STRING;

INSERT INTO STAGING.ORGS (
  org_id, ein, name, blurb, city, state, ntee_code, cause,
  lat, lon, home_h3, region_h3, base_h3, max_hops,
  is_verified, is_synthetic, batch_id, first_seen,
  synth_technique, synth_target_id
)
SELECT
  org_id, ein, name, blurb, city, state, ntee_code, cause,
  lat, lon, home_h3, region_h3, base_h3, max_hops,
  is_verified, is_synthetic, batch_id, CURRENT_TIMESTAMP(),
  synth_technique, synth_target_id
FROM RAW.ORGS_PREPARED;

-- ---------------------------------------------------------------------
-- Standing dimension.
--
-- Note the language. The Auto-Revocation List is overwhelmingly a record
-- of organisations that failed to file for three consecutive years, and
-- organisations later reinstated are excluded upstream. It is not a
-- fraud list, and calling it one would be exactly the sloppy inference
-- this project exists to criticise. Section 05.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE MARTS.ORG_STANDING (
  org_id         STRING,
  ein            STRING,
  name           STRING,
  revoked_on     DATE,
  reinstated_on  DATE,
  standing_label STRING,
  standing_note  STRING,
  batch_id       STRING
);

-- Populated from RAW.AUTO_REVOCATION under Path A. Under Path B the
-- standing decision has already been applied to STAGING.ORGS.is_verified
-- upstream, so this table stays empty and the enriched Dynamic Table
-- falls through to the is_verified flag.

INSERT INTO MARTS.BUILD_LOG (step, detail)
SELECT '02_load_bmf',
       'organisations loaded: ' || COUNT(*)::STRING
    || ' (' || COUNT_IF(NOT is_synthetic)::STRING || ' real, '
    || COUNT_IF(is_synthetic)::STRING || ' seeded)'
FROM STAGING.ORGS;

SELECT batch_id, COUNT(*) AS row_count, COUNT_IF(is_verified) AS verified
FROM STAGING.ORGS GROUP BY batch_id ORDER BY row_count DESC;

-- =====================================================================
-- PATH A. FULL SCALE, from the raw IRS extracts.
--
-- Acquisition, 20 minutes:
--   irs.gov > Charities and Non-Profits > EO BMF extract. Download every
--   regional file and the Auto-Revocation List.
--
--     PUT file://data/irs/eo*.csv        @RAW.GP_STAGE/bmf/        AUTO_COMPRESS=TRUE;
--     PUT file://data/irs/revocation.csv @RAW.GP_STAGE/revocation/ AUTO_COMPRESS=TRUE;
--     PUT file://data/geo/zips.csv       @RAW.GP_STAGE/zips/       AUTO_COMPRESS=TRUE;
--
-- Column names differ slightly between regions, so everything lands as
-- STRING and is normalised on the way out rather than trusting a single
-- header.
-- =====================================================================
--
-- COPY INTO RAW.BMF (
--   ein, name, ico, street, city, state, zip, "GROUP", subsection, affiliation,
--   classification, ruling, deductibility, foundation, activity, organization,
--   status, tax_period, asset_cd, income_cd, filing_req_cd, pf_filing_req,
--   acct_pd, asset_amt, income_amt, revenue_amt, ntee_cd, sort_name, source_file)
-- FROM (
--   SELECT $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,
--          $19,$20,$21,$22,$23,$24,$25,$26,$27,$28, METADATA$FILENAME
--   FROM @RAW.GP_STAGE/bmf/)
-- FILE_FORMAT = (FORMAT_NAME = RAW.FF_CSV_RAGGED)
-- ON_ERROR = CONTINUE;
--
-- CREATE OR REPLACE FUNCTION STAGING.F_NTEE_CAUSE(ntee STRING)
-- RETURNS STRING AS
-- $$
--   CASE UPPER(LEFT(COALESCE(ntee, 'Z'), 1))
--     WHEN 'A' THEN 'arts and culture'   WHEN 'B' THEN 'education'
--     WHEN 'C' THEN 'environment'        WHEN 'D' THEN 'animals'
--     WHEN 'E' THEN 'medical'            WHEN 'F' THEN 'mental health'
--     WHEN 'G' THEN 'disease research'   WHEN 'H' THEN 'medical research'
--     WHEN 'I' THEN 'public safety'      WHEN 'J' THEN 'employment'
--     WHEN 'K' THEN 'food and agriculture' WHEN 'L' THEN 'housing'
--     WHEN 'M' THEN 'disaster relief'    WHEN 'N' THEN 'recreation and sport'
--     WHEN 'O' THEN 'youth development'  WHEN 'P' THEN 'human services'
--     WHEN 'Q' THEN 'international development' WHEN 'R' THEN 'civil rights'
--     WHEN 'S' THEN 'community development' WHEN 'T' THEN 'philanthropy'
--     WHEN 'U' THEN 'science'            WHEN 'V' THEN 'social science'
--     WHEN 'W' THEN 'public benefit'     WHEN 'X' THEN 'religion'
--     WHEN 'Y' THEN 'mutual benefit'     ELSE 'unclassified'
--   END
-- $$;
--
-- INSERT INTO STAGING.ORGS (org_id, ein, name, blurb, city, state, ntee_code,
--   cause, lat, lon, home_h3, region_h3, max_hops, is_verified, is_synthetic,
--   batch_id, first_seen, synth_technique, synth_target_id)
-- WITH bmf AS (
--   SELECT REGEXP_REPLACE(b.ein, '[^0-9]', '')          AS ein_clean,
--          INITCAP(TRIM(b.name))                        AS name,
--          INITCAP(TRIM(b.city))                        AS city,
--          UPPER(TRIM(b.state))                         AS state,
--          LEFT(REGEXP_REPLACE(b.zip, '[^0-9]', ''), 5) AS zip5,
--          UPPER(TRIM(b.ntee_cd))                       AS ntee_cd,
--          TRY_TO_NUMBER(b.revenue_amt)                 AS revenue_amt,
--          TRIM(b.status)                               AS status,
--          ROW_NUMBER() OVER (PARTITION BY REGEXP_REPLACE(b.ein, '[^0-9]', '')
--                             ORDER BY TRY_TO_NUMBER(b.revenue_amt) DESC NULLS LAST) AS rn
--   FROM RAW.BMF b
--   WHERE LENGTH(REGEXP_REPLACE(b.ein, '[^0-9]', '')) = 9 AND b.name IS NOT NULL)
-- SELECT 'ORG_' || bmf.ein_clean, bmf.ein_clean, bmf.name,
--        STAGING.F_NTEE_CAUSE(bmf.ntee_cd) || ' organisation serving '
--          || COALESCE(bmf.city, 'its community') || ', ' || COALESCE(bmf.state, 'US'),
--        bmf.city, bmf.state, bmf.ntee_cd, STAGING.F_NTEE_CAUSE(bmf.ntee_cd),
--        z.lat, z.lon,
--        H3_LATLNG_TO_CELL_STRING(z.lat, z.lon, 5),
--        H3_LATLNG_TO_CELL_STRING(z.lat, z.lon, 3),
--        CASE WHEN bmf.revenue_amt >= 50000000 THEN 40
--             WHEN bmf.revenue_amt >= 5000000  THEN 24
--             WHEN bmf.revenue_amt >= 500000   THEN 14
--             WHEN bmf.revenue_amt >= 50000    THEN 8 ELSE 5 END,
--        (bmf.status = '01' AND rev.ein IS NULL), FALSE, 'IRS_BMF_2026',
--        CURRENT_TIMESTAMP(), NULL, NULL
-- FROM bmf
-- LEFT JOIN RAW.ZIP_CENTROIDS z ON z.zip = bmf.zip5
-- LEFT JOIN (SELECT DISTINCT REGEXP_REPLACE(ein, '[^0-9]', '') AS ein
--            FROM RAW.AUTO_REVOCATION
--            WHERE exemption_reinstatement_date IS NULL) rev
--        ON rev.ein = bmf.ein_clean
-- WHERE bmf.rn = 1 AND z.lat IS NOT NULL;
