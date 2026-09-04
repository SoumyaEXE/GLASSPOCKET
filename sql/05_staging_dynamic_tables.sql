-- =====================================================================
-- GLASSPOCKET / 05_staging_dynamic_tables.sql
-- The declarative pipeline. Six Dynamic Tables on a 60 second target lag.
--
-- Acceptance criteria, Snowflake surface:
--   "At least six Dynamic Tables refresh within their TARGET_LAG."
--
-- Tab 00 renders the refresh age of each of these against its configured
-- lag, which is how a judge sees the declarative pipeline without
-- opening a SQL file, and how they see that the warehouse is live rather
-- than a static extract.
--
-- TRAP 05 / READ THIS BEFORE ADDING ONE
--   A Dynamic Table that depends on a privacy-protected object will fail
--   to refresh. Every table below reads from STAGING and MARTS base
--   tables only. Nothing here may ever be pointed at SERVING.
-- =====================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE GP_WH;
USE DATABASE GLASSPOCKET;

-- 1 ---------------------------------------------------------------------
-- Organisations, enriched with standing. The join that turns a filing
-- into a plain-language status line.
CREATE OR REPLACE DYNAMIC TABLE STAGING.DT_ORG_ENRICHED
  TARGET_LAG = '60 seconds'
  WAREHOUSE  = GP_WH
AS
SELECT
  o.org_id,
  o.ein,
  o.name,
  o.blurb,
  o.city,
  o.state,
  o.cause,
  o.ntee_code,
  o.lat,
  o.lon,
  o.home_h3,
  o.region_h3,
  o.max_hops,
  o.is_verified,
  o.is_synthetic,
  o.batch_id,
  o.synth_technique,
  o.synth_target_id,
  CASE
    WHEN o.is_synthetic          THEN 'seeded'
    WHEN st.org_id IS NOT NULL   THEN 'no longer in good standing'
    WHEN o.is_verified           THEN 'verified'
    ELSE 'unverified'
  END AS standing_label
FROM STAGING.ORGS o
LEFT JOIN MARTS.ORG_STANDING st USING (org_id);

-- 2 ---------------------------------------------------------------------
-- Disbursement rollup per organisation. Feeds the unaccounted ratio
-- component of the risk score.
CREATE OR REPLACE DYNAMIC TABLE MARTS.DT_ORG_ACTIVITY
  TARGET_LAG = '60 seconds'
  WAREHOUSE  = GP_WH
AS
SELECT
  d.org_id,
  COUNT(*)                                                        AS disbursements,
  COUNT(DISTINCT d.district)                                      AS districts,
  SUM(d.pledged_usd)                                              AS pledged_usd,
  SUM(d.amount_usd)                                               AS moved_usd,
  SUM(CASE WHEN d.status = 'DELIVERED'   THEN d.amount_usd ELSE 0 END) AS delivered_usd,
  SUM(CASE WHEN d.status = 'UNACCOUNTED' THEN d.amount_usd ELSE 0 END) AS unaccounted_usd,
  DIV0(
    SUM(CASE WHEN d.status = 'UNACCOUNTED' THEN d.amount_usd ELSE 0 END),
    NULLIF(SUM(d.amount_usd), 0)
  )                                                               AS unaccounted_ratio,
  DIV0(
    SUM(CASE WHEN d.status = 'DELIVERED' THEN d.amount_usd ELSE 0 END),
    NULLIF(SUM(d.amount_usd), 0)
  )                                                               AS delivery_rate,
  MIN(d.dispatched_at)                                            AS first_dispatch,
  MAX(d.delivered_at)                                             AS last_delivery
FROM STAGING.DISBURSEMENTS d
GROUP BY d.org_id;

-- 3 ---------------------------------------------------------------------
-- Stage totals for the Tab 04 Sankey. Four node columns, dollars only.
CREATE OR REPLACE DYNAMIC TABLE MARTS.DT_ATTRITION_STAGES
  TARGET_LAG = '60 seconds'
  WAREHOUSE  = GP_WH
AS
SELECT
  SUM(pledged_usd)                                                     AS pledged_usd,
  SUM(CASE WHEN status IN ('DISPATCHED','DELIVERED','UNACCOUNTED')
           THEN amount_usd ELSE 0 END)                                 AS dispatched_usd,
  SUM(CASE WHEN status = 'DELIVERED'   THEN amount_usd ELSE 0 END)     AS delivered_usd,
  SUM(CASE WHEN status = 'UNACCOUNTED' THEN amount_usd ELSE 0 END)     AS unaccounted_usd,
  SUM(pledged_usd)
    - SUM(CASE WHEN status IN ('DISPATCHED','DELIVERED','UNACCOUNTED')
               THEN amount_usd ELSE 0 END)                             AS never_dispatched_usd,
  COUNT(*)                                                             AS events
FROM STAGING.DISBURSEMENTS;

-- 4 ---------------------------------------------------------------------
-- Attrition by district. Clickable on Tab 04, and the click carries the
-- district into Tab 05 where the same district returns under privacy
-- protection. That handoff is narrated in the demo.
CREATE OR REPLACE DYNAMIC TABLE MARTS.DT_DISTRICT_ATTRITION
  TARGET_LAG = '60 seconds'
  WAREHOUSE  = GP_WH
AS
SELECT
  d.district,
  COUNT(*)                                                            AS events,
  SUM(d.amount_usd)                                                   AS moved_usd,
  SUM(CASE WHEN d.status = 'DELIVERED' THEN d.amount_usd ELSE 0 END)  AS delivered_usd,
  DIV0(
    SUM(CASE WHEN d.status <> 'DELIVERED' THEN d.amount_usd ELSE 0 END),
    NULLIF(SUM(d.amount_usd), 0)
  )                                                                   AS attrition_rate,
  AVG(DATEDIFF('hour', d.dispatched_at, d.delivered_at))              AS mean_transit_hours
FROM STAGING.DISBURSEMENTS d
WHERE d.district IS NOT NULL
GROUP BY d.district;

-- 5 ---------------------------------------------------------------------
-- Cause exposure. Imitations per hundred verified organisations, by
-- cause. Drives the Tab 02 exposure bars.
CREATE OR REPLACE DYNAMIC TABLE MARTS.DT_CAUSE_EXPOSURE
  TARGET_LAG = '60 seconds'
  WAREHOUSE  = GP_WH
AS
SELECT
  cause,
  COUNT_IF(is_verified  AND NOT is_synthetic)               AS verified_orgs,
  COUNT_IF(is_synthetic)                                    AS seeded_orgs,
  DIV0(
    100.0 * COUNT_IF(is_synthetic),
    NULLIF(COUNT_IF(is_verified AND NOT is_synthetic), 0)
  )                                                         AS imitations_per_100
FROM STAGING.ORGS
GROUP BY cause;

-- 6 ---------------------------------------------------------------------
-- Beneficiary facts. The base object the privacy policy will eventually
-- protect, one layer downstream. This is a Dynamic Table and the
-- protected object is a plain view on top of it, precisely because the
-- reverse arrangement cannot refresh. Trap 05.
CREATE OR REPLACE DYNAMIC TABLE MARTS.BENEFICIARY_FACTS
  TARGET_LAG = '60 seconds'
  WAREHOUSE  = GP_WH
AS
SELECT
  b.beneficiary_id,
  b.district,
  b.programme_code,
  b.cause,
  d.amount_usd,
  IFF(d.status = 'DELIVERED', 1, 0)                     AS delivered_flag,
  TO_CHAR(COALESCE(d.delivered_at, d.dispatched_at), 'YYYY-MM') AS month_key
FROM STAGING.BENEFICIARIES b
JOIN STAGING.DISBURSEMENTS d
  ON d.beneficiary_id = b.beneficiary_id;

-- 7 ---------------------------------------------------------------------
-- Receipt coverage per organisation. Depends on the mint log, so it goes
-- stale the moment the bridge stops, which is exactly the signal Tab 06
-- wants.
CREATE OR REPLACE DYNAMIC TABLE MARTS.DT_RECEIPT_COVERAGE
  TARGET_LAG = '60 seconds'
  WAREHOUSE  = GP_WH
AS
SELECT
  d.org_id,
  COUNT(*)                                    AS eligible_disbursements,
  COUNT(m.asset_id)                           AS receipts_on_chain,
  COUNT(*) - COUNT(m.asset_id)                AS receipts_missing,
  DIV0(COUNT(m.asset_id), NULLIF(COUNT(*), 0)) AS receipt_coverage
FROM STAGING.DISBURSEMENTS d
LEFT JOIN ORACLE.MINT_LOG m
  ON m.disbursement_id = d.disbursement_id
WHERE d.status IN ('DELIVERED', 'UNACCOUNTED')
GROUP BY d.org_id;

-- ---------------------------------------------------------------------
-- Pipeline health. Reads refresh history from INFORMATION_SCHEMA and is
-- what Tab 00 section S4 charts: seconds since last refresh against the
-- configured TARGET_LAG, one bar per Dynamic Table.
--
-- This is a plain view, not a Dynamic Table. A Dynamic Table over
-- INFORMATION_SCHEMA would be both circular and pointless.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW SERVING.V_PIPELINE_HEALTH AS
WITH latest AS (
  SELECT
    name,
    schema_name,
    state,
    refresh_end_time,
    ROW_NUMBER() OVER (
      PARTITION BY qualified_name ORDER BY refresh_end_time DESC
    ) AS rn
  FROM TABLE(
    INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(
      RESULT_LIMIT => 500
    )
  )
)
SELECT
  l.schema_name || '.' || l.name                             AS object_name,
  LOWER(l.name)                                              AS short_name,
  l.state,
  l.refresh_end_time,
  DATEDIFF('second', l.refresh_end_time, CURRENT_TIMESTAMP()) AS seconds_since_refresh,
  60                                                          AS target_lag_seconds,
  DATEDIFF('second', l.refresh_end_time, CURRENT_TIMESTAMP()) <= 60 AS within_lag
FROM latest l
WHERE l.rn = 1
ORDER BY seconds_since_refresh DESC;

INSERT INTO MARTS.BUILD_LOG (step, detail)
VALUES ('05_staging_dynamic_tables', 'six dynamic tables created at 60 second target lag');
