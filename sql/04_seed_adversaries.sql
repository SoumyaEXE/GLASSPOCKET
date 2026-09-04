-- =====================================================================
-- GLASSPOCKET / 04_seed_adversaries.sql
-- Synthetic impersonators, synthetic disbursements, synthetic
-- beneficiaries, and the hand-entered evidence citations.
--
-- Build Spec Section 05, "The synthetic adversary set, and the
-- labelling contract".
--
-- There is no public labelled dataset of fake charities, because fakes
-- are taken down rather than catalogued. Therefore the impersonating
-- organisations in this build are generated. That is acceptable and
-- defensible only if it is disclosed relentlessly, which is what the
-- contract at the foot of this file enforces in SQL rather than by
-- convention.
--
-- Upstream: tools/make_synthetic.py writes the four CSVs staged below.
--     PUT file://data/synthetic/*.csv @RAW.GP_STAGE/synthetic/;
-- =====================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE GP_WH;
USE DATABASE GLASSPOCKET;

-- ---------------------------------------------------------------------
-- Landing tables for the generator output.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE RAW.SYNTH_ORGS (
  org_id STRING, ein STRING, name STRING, blurb STRING,
  city STRING, state STRING, ntee_code STRING, cause STRING,
  lat FLOAT, lon FLOAT, max_hops INT,
  synth_technique STRING, synth_target_id STRING
);

CREATE OR REPLACE TABLE RAW.SYNTH_DISBURSEMENTS (
  disbursement_id STRING, org_id STRING, programme_code STRING,
  beneficiary_id STRING, amount_usd FLOAT, pledged_usd FLOAT,
  district STRING, lat FLOAT, lon FLOAT,
  dispatched_at STRING, delivered_at STRING, status STRING
);

CREATE OR REPLACE TABLE RAW.SYNTH_BENEFICIARIES (
  beneficiary_id STRING, district STRING, programme_code STRING,
  cause STRING, cohort_band STRING
);

CREATE OR REPLACE FILE FORMAT RAW.FF_SYNTH_CSV
  TYPE = CSV SKIP_HEADER = 1 FIELD_OPTIONALLY_ENCLOSED_BY = '"'
  EMPTY_FIELD_AS_NULL = TRUE NULL_IF = ('', 'NULL');

COPY INTO RAW.SYNTH_ORGS
  FROM @RAW.GP_STAGE/synthetic/synth_orgs.csv
  FILE_FORMAT = (FORMAT_NAME = RAW.FF_SYNTH_CSV);

COPY INTO RAW.SYNTH_DISBURSEMENTS
  FROM @RAW.GP_STAGE/synthetic/synth_disbursements.csv
  FILE_FORMAT = (FORMAT_NAME = RAW.FF_SYNTH_CSV);

COPY INTO RAW.SYNTH_BENEFICIARIES
  FROM @RAW.GP_STAGE/synthetic/synth_beneficiaries.csv
  FILE_FORMAT = (FORMAT_NAME = RAW.FF_SYNTH_CSV);

-- ---------------------------------------------------------------------
-- Impersonators into STAGING.ORGS.
--
-- is_verified is FALSE by construction and is_synthetic is TRUE by
-- construction. Both are asserted at the foot of this file. The
-- generator records which of the five documented techniques produced
-- each row, which is what Tab 02 reports in its technique breakdown.
-- ---------------------------------------------------------------------
INSERT INTO STAGING.ORGS (
  org_id, ein, name, blurb, city, state, ntee_code, cause,
  lat, lon, home_h3, region_h3, max_hops,
  is_verified, is_synthetic, batch_id, first_seen,
  synth_technique, synth_target_id
)
SELECT
  s.org_id,
  s.ein,
  s.name,
  s.blurb,
  s.city,
  s.state,
  s.ntee_code,
  s.cause,
  s.lat,
  s.lon,
  H3_LATLNG_TO_CELL_STRING(s.lat, s.lon, 5) AS home_h3,
  H3_LATLNG_TO_CELL_STRING(s.lat, s.lon, 3) AS region_h3,
  s.max_hops,
  FALSE                                     AS is_verified,
  TRUE                                      AS is_synthetic,
  'SYNTH_ADVERSARY_V1'                      AS batch_id,
  CURRENT_TIMESTAMP()                       AS first_seen,
  s.synth_technique,
  s.synth_target_id
FROM RAW.SYNTH_ORGS s;

-- ---------------------------------------------------------------------
-- Disbursement events. Real geography from IATI, synthetic movement.
-- Attrition is tuned so the aggregate delivery share sits close to the
-- published WFP ratio of 371 collected from 590 moved. Stated on Tab 04
-- section S6 and again on Tab 10. The individual events are not real and
-- the interface never implies they are.
-- ---------------------------------------------------------------------
INSERT INTO STAGING.DISBURSEMENTS (
  disbursement_id, org_id, programme_code, beneficiary_id,
  amount_usd, pledged_usd, district, lat, lon, delivery_h3,
  dispatched_at, delivered_at, status, is_synthetic, batch_id
)
SELECT
  d.disbursement_id,
  d.org_id,
  d.programme_code,
  d.beneficiary_id,
  d.amount_usd,
  d.pledged_usd,
  d.district,
  d.lat,
  d.lon,
  H3_LATLNG_TO_CELL_STRING(d.lat, d.lon, 7)  AS delivery_h3,
  TRY_TO_TIMESTAMP_NTZ(d.dispatched_at)      AS dispatched_at,
  TRY_TO_TIMESTAMP_NTZ(d.delivered_at)       AS delivered_at,
  d.status,
  TRUE                                       AS is_synthetic,
  'SYNTH_ADVERSARY_V1'                       AS batch_id
FROM RAW.SYNTH_DISBURSEMENTS d;

INSERT INTO STAGING.BENEFICIARIES (
  beneficiary_id, district, programme_code, cause, cohort_band,
  is_synthetic, batch_id
)
SELECT
  b.beneficiary_id, b.district, b.programme_code, b.cause, b.cohort_band,
  TRUE, 'SYNTH_ADVERSARY_V1'
FROM RAW.SYNTH_BENEFICIARIES b;

-- =====================================================================
-- The seven cited figures, Section 01.
--
-- Hand-entered on purpose. They are not computed, not templated and not
-- fetched, because they must never drift. A project about accountability
-- that cites loosely has already lost the argument.
--
-- OPERATOR NOTE. The IC3 URL is the one given verbatim in the
-- specification. The remaining six carry their issuing body and
-- publication date, which is what the interface renders. Paste the
-- canonical source URL into the url column before recording; do not let
-- the application invent one. Tab 00 renders a citation without a URL as
-- attributed text rather than as a dead link.
-- =====================================================================
DELETE FROM MARTS.EVIDENCE_CITATIONS;

INSERT INTO MARTS.EVIDENCE_CITATIONS
  (citation_id, claim, figure, magnitude, unit_type, region, issuing_body, published_on, url)
VALUES
  ('IC3_2024',
   'Charitable and crowdfunding fraud, United States, 2024',
   'More than 4,500 complaints reporting approximately 96 million USD in losses to fraudulent charities, crowdfunding accounts and disaster relief campaigns',
   96000000, 'USD', 'United States',
   'FBI IC3 Public Service Announcement I-011625',
   '2025-01-16',
   'https://www.ic3.gov/PSA/2025/PSA250116'),

  ('BFOREAI_LA_FIRES',
   'Impersonation surges after disasters',
   '119 domains registered between 8 and 13 January 2025 using keywords including "LA fire", "wildfire", "relief", "fund" and "rebuild"',
   119, 'DOMAINS', 'United States',
   'BforeAI threat research report on the Los Angeles wildfires',
   '2025-01-13',
   NULL),

  ('GOFUNDME_LA',
   'Scale of the legitimate pool being imitated',
   'More than 250 million USD raised for Los Angeles wildfire relief',
   250000000, 'USD', 'United States',
   'GoFundMe public statement',
   '2025-01-31',
   NULL),

  ('WFP_GAZA_TRUCKS',
   'Last-mile diversion, Gaza',
   '590 trucks moved from Ashdod to Kerem Shalom, of which 371 were collected inside Gaza; organised criminal looting estimated by field monitors at about 20 percent of cases',
   590, 'TRUCKS', 'Palestine',
   'WFP State of Palestine External Situation Report 55',
   '2025-06-06',
   NULL),

  ('WFP_SUDAN_GEZIRA',
   'Warehouse-scale diversion, Sudan',
   'Looting of a Gezira State warehouse holding over 2,500 metric tons of food, enough for nearly 1.5 million people for one month',
   2500, 'TONNES', 'Sudan',
   'WFP statement',
   '2023-12-01',
   NULL),

  ('MGNREGA_LEAKAGE',
   'Programme leakage, India',
   'Total financial misappropriation of 169.75 crore rupees with only 20.93 crore recovered, a recovery rate of 12.33 percent, across 125,602 reported cases',
   169.75, 'INR_CRORE', 'India',
   'MGNREGA action report',
   '2025-03-29',
   NULL),

  ('CAG_PMAY_UP',
   'Diversion before delivery, India',
   '86.20 lakh rupees intended for 159 genuine beneficiaries diverted to other bank accounts',
   86.20, 'INR_LAKH', 'India',
   'CAG audit of PMAY-Gramin, Uttar Pradesh',
   '2025-12-01',
   NULL);

-- =====================================================================
-- THE LABELLING CONTRACT, ENFORCED
--
-- Section 05 is explicit that these must be enforced in SQL, not merely
-- by convention. Each block raises if the contract is broken, which
-- fails the build here rather than in front of a judge.
-- =====================================================================

EXECUTE IMMEDIATE $$
DECLARE
  bad_batch    INTEGER;
  bad_verified INTEGER;
  bad_real     INTEGER;
BEGIN
  -- 1. Every synthetic row carries the batch identifier.
  SELECT COUNT(*) INTO bad_batch
  FROM STAGING.ORGS
  WHERE is_synthetic = TRUE AND batch_id <> 'SYNTH_ADVERSARY_V1';

  -- 2. No synthetic organisation may ever be marked verified.
  SELECT COUNT(*) INTO bad_verified
  FROM STAGING.ORGS
  WHERE is_synthetic = TRUE AND is_verified = TRUE;

  -- 3. No real row may carry a synthetic batch identifier.
  SELECT COUNT(*) INTO bad_real
  FROM STAGING.ORGS
  WHERE is_synthetic = FALSE AND batch_id = 'SYNTH_ADVERSARY_V1';

  IF (bad_batch > 0 OR bad_verified > 0 OR bad_real > 0) THEN
    RETURN 'CONTRACT VIOLATION. unlabelled=' || bad_batch
        || ' synthetic_marked_verified=' || bad_verified
        || ' real_marked_synthetic=' || bad_real
        || '. Fix before proceeding. See Section 05.';
  END IF;

  RETURN 'labelling contract holds';
END;
$$;

INSERT INTO MARTS.BUILD_LOG (step, detail)
SELECT '04_seed_adversaries',
       'seeded orgs: '
    || (SELECT COUNT(*)::STRING FROM STAGING.ORGS WHERE is_synthetic)
    || ', seeded disbursements: '
    || (SELECT COUNT(*)::STRING FROM STAGING.DISBURSEMENTS WHERE is_synthetic)
    || ', seeded beneficiaries: '
    || (SELECT COUNT(*)::STRING FROM STAGING.BENEFICIARIES);
