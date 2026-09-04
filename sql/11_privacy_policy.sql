-- =====================================================================
-- GLASSPOCKET / 11_privacy_policy.sql
-- Differential privacy. The centrepiece. Build Spec Section 06.1.
--
-- RUN THIS FIRST IN PRACTICE.
--   Section 09 puts this in the Friday night block, hours 3 to 5, ahead
--   of the entire data layer. It is numbered 11 because that is where it
--   sits in the dependency graph, but it is built first because it is
--   the only component that can fail in a way that cannot be fixed
--   later. Build it against a minimal fabricated fact table, verify the
--   three behaviours at the foot of this file, and only then continue.
--
-- TRAP 05 / WHY THE POLICY IS AT THE END OF THE PIPELINE
--   A privacy policy cannot coexist with an aggregation policy or a
--   masking policy on the same object. A privacy-protected table blocks
--   row-level SELECT entirely. A Dynamic Table that depends on a
--   privacy-protected object will fail to refresh. Consequence: the
--   policy attaches only to a terminal serving view at the very end of
--   the pipeline, never to a table in the middle of the DAG.
-- =====================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE GP_WH;
USE DATABASE GLASSPOCKET;

-- The analyst persona the application connects as.
CREATE ROLE IF NOT EXISTS GP_ANALYST;

-- ---------------------------------------------------------------------
-- Privacy budgets. The named budget is what Tab 05 draws down and what
-- its hero figure reports. Epsilon is tuned for demonstration legibility
-- rather than for production, and Tab 10 says so.
-- ---------------------------------------------------------------------
CREATE PRIVACY BUDGET IF NOT EXISTS GLASSPOCKET.SERVING.public_analyst
  TYPE           = per_query_epsilon
  EPSILON        = 0.1
  REFRESH_PERIOD = 24
  COMMENT        = 'Public analyst budget. Drawn down by Tab 05.';

CREATE OR REPLACE PRIVACY POLICY GLASSPOCKET.SERVING.beneficiary_policy
  AS () RETURNS privacy_budget ->
  CASE
    WHEN CURRENT_ROLE() = 'ACCOUNTADMIN' THEN no_privacy_policy()
    WHEN CURRENT_ROLE() = 'GP_ANALYST'   THEN privacy_budget(name => 'public_analyst')
    ELSE privacy_budget(name => 'default')
  END;

-- ---------------------------------------------------------------------
-- The protected serving view. Terminal. Nothing reads from it downstream
-- and no Dynamic Table may ever depend on it.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW GLASSPOCKET.SERVING.V_BENEFICIARY_OUTCOMES AS
  SELECT
    beneficiary_id,
    district,
    programme_code,
    cause,
    amount_usd,
    delivered_flag,
    month_key
  FROM GLASSPOCKET.MARTS.BENEFICIARY_FACTS;

ALTER VIEW GLASSPOCKET.SERVING.V_BENEFICIARY_OUTCOMES
  SET PRIVACY POLICY GLASSPOCKET.SERVING.beneficiary_policy
  ENTITY KEY (beneficiary_id);

-- ---------------------------------------------------------------------
-- Privacy domains keep the noise calibrated and prevent range inference.
-- Without the amount domain, an attacker learns the bounds of the column
-- from the noise itself.
-- ---------------------------------------------------------------------
ALTER VIEW GLASSPOCKET.SERVING.V_BENEFICIARY_OUTCOMES
  MODIFY COLUMN amount_usd SET PRIVACY DOMAIN (0, 5000);

ALTER VIEW GLASSPOCKET.SERVING.V_BENEFICIARY_OUTCOMES
  MODIFY COLUMN district SET PRIVACY DOMAIN (
    SELECT DISTINCT district FROM MARTS.DISTRICT_DIM
  );

GRANT SELECT ON VIEW GLASSPOCKET.SERVING.V_BENEFICIARY_OUTCOMES TO ROLE GP_ANALYST;

-- ---------------------------------------------------------------------
-- The paired unprotected view.
--
-- Tab 05 shows true values beside private values, so a second view over
-- the same facts is required. It is readable only by a privileged role
-- and is used exclusively to render the left-hand comparison column. The
-- interface labels it unmistakably as the counterfactual that would
-- exist without the policy.
--
-- GP_ANALYST is deliberately NOT granted on this object. If the analyst
-- persona could read it, Tab 05 would be theatre.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW GLASSPOCKET.SERVING.V_BENEFICIARY_OUTCOMES_TRUE AS
  SELECT
    beneficiary_id,
    district,
    programme_code,
    cause,
    amount_usd,
    delivered_flag,
    month_key
  FROM GLASSPOCKET.MARTS.BENEFICIARY_FACTS;

COMMENT ON VIEW GLASSPOCKET.SERVING.V_BENEFICIARY_OUTCOMES_TRUE IS
  'COUNTERFACTUAL ONLY. The answer that would be released if no privacy '
  'policy existed. Rendered on Tab 05 beside the protected answer and '
  'labelled as such. Never granted to GP_ANALYST.';

-- ---------------------------------------------------------------------
-- Budget telemetry for the Tab 05 hero and burn-down chart.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW GLASSPOCKET.SERVING.V_PRIVACY_BUDGET AS
SELECT
  budget_name,
  epsilon_consumed,
  epsilon_allocated,
  GREATEST(0, epsilon_allocated - epsilon_consumed)         AS epsilon_remaining,
  DIV0(GREATEST(0, epsilon_allocated - epsilon_consumed),
       NULLIF(epsilon_allocated, 0))                        AS share_remaining,
  refresh_period_start,
  refresh_period_end
FROM TABLE(GLASSPOCKET.INFORMATION_SCHEMA.PRIVACY_BUDGETS());

GRANT SELECT ON VIEW GLASSPOCKET.SERVING.V_PRIVACY_BUDGET TO ROLE GP_ANALYST;

-- =====================================================================
-- VERIFICATION STEP, DO NOT SKIP
--
-- Section 06.1. Run all three as GP_ANALYST, immediately, before writing
-- another line of anything.
--
--   1. A row-level select MUST fail.
--   2. A broad aggregate MUST succeed with slight noise.
--   3. An aggregate filtered to a single beneficiary MUST return large
--      noise or be refused.
--
-- If all three behave as described, the centrepiece works and the rest
-- of the build is downhill. If not, apply the Section 10 fallback within
-- thirty minutes and move on: an aggregation policy with a minimum group
-- size, relabelled honestly as a minimum-cohort guarantee rather than a
-- differential-privacy guarantee, with the attempt documented in the
-- post.
-- =====================================================================

USE ROLE GP_ANALYST;
USE WAREHOUSE GP_WH;
USE DATABASE GLASSPOCKET;

-- 1. MUST FAIL. A privacy-protected object blocks row-level SELECT.
SELECT beneficiary_id, amount_usd
FROM GLASSPOCKET.SERVING.V_BENEFICIARY_OUTCOMES
LIMIT 10;

-- 2. MUST SUCCEED, with slight noise.
SELECT COUNT(*) AS n, SUM(amount_usd) AS total
FROM GLASSPOCKET.SERVING.V_BENEFICIARY_OUTCOMES;

-- 3. MUST return large noise, or be refused.
SELECT COUNT(*) AS n, SUM(amount_usd) AS total
FROM GLASSPOCKET.SERVING.V_BENEFICIARY_OUTCOMES
WHERE district       = (SELECT MIN(district) FROM MARTS.DISTRICT_DIM)
  AND programme_code = 'AID-2026-DR-114'
  AND month_key      = '2026-08';

USE ROLE ACCOUNTADMIN;

INSERT INTO MARTS.BUILD_LOG (step, detail)
VALUES ('11_privacy_policy',
        'beneficiary_policy attached to SERVING.V_BENEFICIARY_OUTCOMES, entity key beneficiary_id');
