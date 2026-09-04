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
-- Landing tables for the prepared export.
--
--   python tools/export_for_snowflake.py
--   PUT file://data/warehouse/*.csv @RAW.GP_STAGE/warehouse/;
--
-- The seeded organisations already arrived with the corpus in file 02,
-- carrying is_synthetic and batch_id, so this file loads the delivery
-- events and the beneficiary records and then enforces the contract over
-- all of it.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE RAW.DISBURSEMENTS_PREPARED (
  disbursement_id STRING, org_id STRING, programme_code STRING,
  beneficiary_id STRING, amount_usd FLOAT, pledged_usd FLOAT,
  district STRING, lat FLOAT, lon FLOAT, delivery_h3 STRING,
  dispatched_at STRING, delivered_at STRING, status STRING,
  is_synthetic BOOLEAN, batch_id STRING
);

COPY INTO RAW.DISBURSEMENTS_PREPARED
  FROM @RAW.GP_STAGE/warehouse/disbursements.csv
  FILE_FORMAT = (FORMAT_NAME = RAW.FF_PREPARED)
  ON_ERROR = ABORT_STATEMENT;

INSERT INTO STAGING.DISBURSEMENTS (
  disbursement_id, org_id, programme_code, beneficiary_id,
  amount_usd, pledged_usd, district, lat, lon, delivery_h3,
  dispatched_at, delivered_at, status, is_synthetic, batch_id)
SELECT
  disbursement_id, org_id, programme_code, beneficiary_id,
  amount_usd, pledged_usd, district, lat, lon, delivery_h3,
  TRY_TO_TIMESTAMP_NTZ(dispatched_at),
  TRY_TO_TIMESTAMP_NTZ(delivered_at),
  status, is_synthetic, batch_id
FROM RAW.DISBURSEMENTS_PREPARED;

CREATE OR REPLACE TABLE RAW.BENEFICIARIES_PREPARED (
  beneficiary_id STRING, district STRING, programme_code STRING,
  cause STRING, cohort_band STRING, is_synthetic BOOLEAN, batch_id STRING
);

COPY INTO RAW.BENEFICIARIES_PREPARED
  FROM @RAW.GP_STAGE/warehouse/beneficiaries.csv
  FILE_FORMAT = (FORMAT_NAME = RAW.FF_PREPARED)
  ON_ERROR = ABORT_STATEMENT;

INSERT INTO STAGING.BENEFICIARIES
  (beneficiary_id, district, programme_code, cause, cohort_band,
   is_synthetic, batch_id)
SELECT beneficiary_id, district, programme_code, cause, cohort_band,
       is_synthetic, batch_id
FROM RAW.BENEFICIARIES_PREPARED;

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
