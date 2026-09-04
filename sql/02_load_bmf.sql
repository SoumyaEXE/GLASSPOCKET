-- =====================================================================
-- GLASSPOCKET / 02_load_bmf.sql
-- IRS Business Master File and the Auto-Revocation List.
-- Build Spec Section 05, source inventory.
--
-- Acquisition, 20 minutes:
--   irs.gov > Charities and Non-Profits > Exempt Organizations
--   Business Master File Extract. Download every regional file
--   (eo1.csv .. eo4.csv plus eo_xx.csv) and the Auto-Revocation List.
--   Upload through Snowsight into RAW.GP_STAGE.
--
--     PUT file://data/irs/eo*.csv        @RAW.GP_STAGE/bmf/        AUTO_COMPRESS=TRUE;
--     PUT file://data/irs/revocation.csv @RAW.GP_STAGE/revocation/ AUTO_COMPRESS=TRUE;
--
-- Column names differ slightly between regions. Everything lands as
-- STRING and is normalised here rather than trusting a single header.
-- =====================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE GP_WH;
USE DATABASE GLASSPOCKET;

COPY INTO RAW.BMF (
  ein, name, ico, street, city, state, zip, "GROUP", subsection, affiliation,
  classification, ruling, deductibility, foundation, activity, organization,
  status, tax_period, asset_cd, income_cd, filing_req_cd, pf_filing_req,
  acct_pd, asset_amt, income_amt, revenue_amt, ntee_cd, sort_name, source_file
)
FROM (
  SELECT
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14,
    $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28,
    METADATA$FILENAME
  FROM @RAW.GP_STAGE/bmf/
)
FILE_FORMAT = (FORMAT_NAME = RAW.FF_CSV_RAGGED)
ON_ERROR     = CONTINUE;

COPY INTO RAW.AUTO_REVOCATION (
  ein, name, city, state, country, exemption_type,
  revocation_date, revocation_posting_date, exemption_reinstatement_date
)
FROM @RAW.GP_STAGE/revocation/
FILE_FORMAT = (FORMAT_NAME = RAW.FF_CSV_RAGGED)
ON_ERROR     = CONTINUE;

-- ---------------------------------------------------------------------
-- Geography. The BMF carries a postal address but no coordinates.
--
-- Preferred path: attach a free Snowflake Marketplace geography listing
-- and join on ZIP. Zero load time, and attaching a free listing is
-- itself a line item in Section 05.
--
-- Fallback path, used when no listing is attached: RAW.ZIP_CENTROIDS,
-- populated from a public ZIP centroid file by tools/make_synthetic.py.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS RAW.ZIP_CENTROIDS (
  zip    STRING PRIMARY KEY,
  lat    FLOAT,
  lon    FLOAT,
  city   STRING,
  state  STRING,
  source STRING
);

-- ---------------------------------------------------------------------
-- NTEE major group to a plain-language cause. The cause column is load
-- bearing twice over: it is half of the similarity pre-filter (Trap 06)
-- and it is a dimension on the semantic view.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION STAGING.F_NTEE_CAUSE(ntee STRING)
RETURNS STRING
AS
$$
  CASE UPPER(LEFT(COALESCE(ntee, 'Z'), 1))
    WHEN 'A' THEN 'arts and culture'
    WHEN 'B' THEN 'education'
    WHEN 'C' THEN 'environment'
    WHEN 'D' THEN 'animals'
    WHEN 'E' THEN 'medical'
    WHEN 'F' THEN 'mental health'
    WHEN 'G' THEN 'disease research'
    WHEN 'H' THEN 'medical research'
    WHEN 'I' THEN 'public safety'
    WHEN 'J' THEN 'employment'
    WHEN 'K' THEN 'food and agriculture'
    WHEN 'L' THEN 'housing'
    WHEN 'M' THEN 'disaster relief'
    WHEN 'N' THEN 'recreation and sport'
    WHEN 'O' THEN 'youth development'
    WHEN 'P' THEN 'human services'
    WHEN 'Q' THEN 'international development'
    WHEN 'R' THEN 'civil rights'
    WHEN 'S' THEN 'community development'
    WHEN 'T' THEN 'philanthropy'
    WHEN 'U' THEN 'science'
    WHEN 'V' THEN 'social science'
    WHEN 'W' THEN 'public benefit'
    WHEN 'X' THEN 'religion'
    WHEN 'Y' THEN 'mutual benefit'
    ELSE 'unclassified'
  END
$$;

-- ---------------------------------------------------------------------
-- Normalise into STAGING.ORGS.
--
-- is_verified means: present in the BMF, status 01 (unconditional
-- exemption), and absent from the Auto-Revocation List. Read it as
-- "in good standing", nothing stronger.
-- ---------------------------------------------------------------------
INSERT INTO STAGING.ORGS (
  org_id, ein, name, blurb, city, state, ntee_code, cause,
  lat, lon, home_h3, region_h3, max_hops,
  is_verified, is_synthetic, batch_id, first_seen,
  synth_technique, synth_target_id
)
WITH bmf AS (
  SELECT
    REGEXP_REPLACE(b.ein, '[^0-9]', '')            AS ein_clean,
    INITCAP(TRIM(b.name))                          AS name,
    INITCAP(TRIM(b.city))                          AS city,
    UPPER(TRIM(b.state))                           AS state,
    LEFT(REGEXP_REPLACE(b.zip, '[^0-9]', ''), 5)   AS zip5,
    UPPER(TRIM(b.ntee_cd))                         AS ntee_cd,
    TRY_TO_NUMBER(b.revenue_amt)                   AS revenue_amt,
    TRIM(b.status)                                 AS status,
    ROW_NUMBER() OVER (
      PARTITION BY REGEXP_REPLACE(b.ein, '[^0-9]', '')
      ORDER BY TRY_TO_NUMBER(b.revenue_amt) DESC NULLS LAST
    ) AS rn
  FROM RAW.BMF b
  WHERE b.ein IS NOT NULL
    AND LENGTH(REGEXP_REPLACE(b.ein, '[^0-9]', '')) = 9
    AND b.name IS NOT NULL
)
SELECT
  'ORG_' || bmf.ein_clean                          AS org_id,
  bmf.ein_clean                                    AS ein,
  bmf.name,
  -- A short mission line. The BMF carries no free-text mission, so the
  -- blurb is composed from the fields it does carry. It is descriptive,
  -- not invented: every token comes from the filing.
  STAGING.F_NTEE_CAUSE(bmf.ntee_cd) || ' organisation serving '
    || COALESCE(bmf.city, 'its community') || ', ' || COALESCE(bmf.state, 'US')
                                                   AS blurb,
  bmf.city,
  bmf.state,
  bmf.ntee_cd                                      AS ntee_code,
  STAGING.F_NTEE_CAUSE(bmf.ntee_cd)                AS cause,
  z.lat,
  z.lon,
  H3_LATLNG_TO_CELL_STRING(z.lat, z.lon, 5)        AS home_h3,
  H3_LATLNG_TO_CELL_STRING(z.lat, z.lon, 3)        AS region_h3,
  -- Plausible operating radius, in resolution 5 grid steps. Scaled by
  -- reported revenue: a larger organisation credibly operates further
  -- from its registered address than a small one does.
  CASE
    WHEN bmf.revenue_amt >= 50000000 THEN 40
    WHEN bmf.revenue_amt >= 5000000  THEN 24
    WHEN bmf.revenue_amt >= 500000   THEN 14
    WHEN bmf.revenue_amt >= 50000    THEN 8
    ELSE 5
  END                                              AS max_hops,
  (bmf.status = '01' AND rev.ein IS NULL)          AS is_verified,
  FALSE                                            AS is_synthetic,
  'IRS_BMF_2026'                                   AS batch_id,
  CURRENT_TIMESTAMP()                              AS first_seen,
  NULL                                             AS synth_technique,
  NULL                                             AS synth_target_id
FROM bmf
LEFT JOIN RAW.ZIP_CENTROIDS z
  ON z.zip = bmf.zip5
LEFT JOIN (
  SELECT DISTINCT REGEXP_REPLACE(ein, '[^0-9]', '') AS ein
  FROM RAW.AUTO_REVOCATION
) rev
  ON rev.ein = bmf.ein_clean
WHERE bmf.rn = 1
  AND z.lat IS NOT NULL;   -- an org with no coordinate cannot be geo-checked

-- ---------------------------------------------------------------------
-- Standing dimension.
--
-- Note the language. The Auto-Revocation List is overwhelmingly a record
-- of organisations that failed to file for three consecutive years. It
-- is not a fraud list, and calling it one would be exactly the sloppy
-- inference this project exists to criticise. Section 05.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE MARTS.ORG_STANDING AS
SELECT
  'ORG_' || REGEXP_REPLACE(r.ein, '[^0-9]', '')             AS org_id,
  REGEXP_REPLACE(r.ein, '[^0-9]', '')                       AS ein,
  INITCAP(TRIM(r.name))                                     AS name,
  TRY_TO_DATE(r.revocation_date, 'DD-MON-YYYY')             AS revoked_on,
  TRY_TO_DATE(r.exemption_reinstatement_date, 'DD-MON-YYYY') AS reinstated_on,
  'no longer in good standing'                              AS standing_label,
  'Failure to file a required return for three consecutive years. '
    || 'An administrative status, not a finding of wrongdoing.'
                                                            AS standing_note,
  'IRS_BMF_2026'                                            AS batch_id
FROM RAW.AUTO_REVOCATION r
WHERE LENGTH(REGEXP_REPLACE(r.ein, '[^0-9]', '')) = 9;

INSERT INTO MARTS.BUILD_LOG (step, detail)
SELECT '02_load_bmf', 'staging.orgs real rows: ' || COUNT(*)::STRING
FROM STAGING.ORGS
WHERE batch_id = 'IRS_BMF_2026';
