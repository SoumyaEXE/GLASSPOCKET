-- =====================================================================
-- GLASSPOCKET / 09_risk_score_udf.sql
-- The risk score, decomposable by design. Build Spec Section 06.5.
--
-- An opaque score is unusable in an accountability tool. The score must
-- be reconstructable by hand from its components, and the interface must
-- show the components. It is a SQL UDF so that it is inspectable, and
-- Tab 01 renders it as a waterfall so the arithmetic can be checked by
-- eye. Acceptance criteria: "The risk score is a SQL UDF whose
-- components are displayed in the interface."
-- =====================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE GP_WH;
USE DATABASE GLASSPOCKET;

CREATE OR REPLACE FUNCTION MARTS.F_RISK(
    semantic_sim      FLOAT,
    evasion_gap       FLOAT,
    geom_flags        INT,
    unaccounted_ratio FLOAT,
    missing_receipts  INT)
RETURNS FLOAT
AS
$$
  LEAST(100,
      35 * GREATEST(0, (semantic_sim - 0.86) / 0.14)
    + 25 * LEAST(1, evasion_gap / 0.45)
    + 20 * LEAST(1, geom_flags / 5.0)
    + 12 * LEAST(1, unaccounted_ratio)
    +  8 * LEAST(1, missing_receipts / 10.0))
$$;

-- ---------------------------------------------------------------------
-- The five components, materialised alongside the total so the waterfall
-- on Tab 01 reads them rather than recomputing them in Python. The
-- component columns and the total come from the same UDF weights, so
-- they cannot drift apart.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE MARTS.ORG_RISK AS
WITH clone AS (
  SELECT
    suspect_id            AS org_id,
    MAX(semantic_sim)     AS semantic_sim,
    MAX(evasion_gap)      AS evasion_gap,
    COUNT(*)              AS pair_count,
    ANY_VALUE(target_id)  AS nearest_target_id,
    ANY_VALUE(target_name) AS nearest_target_name
  FROM MARTS.CLONE_PAIRS
  GROUP BY suspect_id
),
geom AS (
  SELECT
    org_id,
    COUNT_IF(geometry_verdict <> 'PLAUSIBLE') AS geom_flags,
    COUNT(*)                                  AS geom_events
  FROM MARTS.DELIVERY_GEOMETRY
  GROUP BY org_id
)
SELECT
  o.org_id,
  o.name,
  o.ein,
  o.city,
  o.state,
  o.cause,
  o.is_synthetic,
  o.is_verified,
  o.batch_id,
  o.synth_technique,

  COALESCE(c.semantic_sim, 0)                        AS semantic_sim,
  COALESCE(c.evasion_gap, 0)                         AS evasion_gap,
  COALESCE(g.geom_flags, 0)                          AS geom_flags,
  COALESCE(a.unaccounted_ratio, 0)                   AS unaccounted_ratio,
  COALESCE(r.receipts_missing, 0)                    AS missing_receipts,
  c.nearest_target_id,
  c.nearest_target_name,

  -- the five components, each exactly as weighted inside F_RISK
  35 * GREATEST(0, (COALESCE(c.semantic_sim, 0) - 0.86) / 0.14) AS comp_semantic,
  25 * LEAST(1, COALESCE(c.evasion_gap, 0) / 0.45)              AS comp_evasion,
  20 * LEAST(1, COALESCE(g.geom_flags, 0) / 5.0)                AS comp_geometry,
  12 * LEAST(1, COALESCE(a.unaccounted_ratio, 0))               AS comp_unaccounted,
   8 * LEAST(1, COALESCE(r.receipts_missing, 0) / 10.0)         AS comp_receipts,

  MARTS.F_RISK(
    COALESCE(c.semantic_sim, 0),
    COALESCE(c.evasion_gap, 0),
    COALESCE(g.geom_flags, 0),
    COALESCE(a.unaccounted_ratio, 0),
    COALESCE(r.receipts_missing, 0)
  )                                                  AS risk_score,

  -- Interface language, Section 07 framing rule. Never fraud, criminal,
  -- scam or guilty. The product is a confidence layer, not an
  -- accusation engine.
  CASE
    WHEN MARTS.F_RISK(
           COALESCE(c.semantic_sim, 0), COALESCE(c.evasion_gap, 0),
           COALESCE(g.geom_flags, 0), COALESCE(a.unaccounted_ratio, 0),
           COALESCE(r.receipts_missing, 0)) >= 55 THEN 'needs a second look'
    WHEN o.is_verified THEN 'verified'
    ELSE 'unverified'
  END                                                AS verdict,
  CURRENT_TIMESTAMP()                                AS scored_at
FROM STAGING.ORGS o
LEFT JOIN clone c                  ON c.org_id = o.org_id
LEFT JOIN geom  g                  ON g.org_id = o.org_id
LEFT JOIN MARTS.DT_ORG_ACTIVITY a  ON a.org_id = o.org_id
LEFT JOIN MARTS.DT_RECEIPT_COVERAGE r ON r.org_id = o.org_id;

-- ---------------------------------------------------------------------
-- Reconstructability check. The five components must sum to the total,
-- allowing for the LEAST(100, ...) ceiling. If this fails, the waterfall
-- on Tab 01 would be lying, which is worse than having no waterfall.
-- ---------------------------------------------------------------------
SELECT
  COUNT(*)                                                          AS rows_checked,
  COUNT_IF(ABS(
    LEAST(100, comp_semantic + comp_evasion + comp_geometry
             + comp_unaccounted + comp_receipts)
    - risk_score) > 0.001)                                          AS mismatches
FROM MARTS.ORG_RISK;

INSERT INTO MARTS.BUILD_LOG (step, detail)
SELECT '09_risk_score_udf',
       'scored orgs: ' || COUNT(*)::STRING
    || ', needs a second look: ' || COUNT_IF(verdict = 'needs a second look')::STRING
FROM MARTS.ORG_RISK;
