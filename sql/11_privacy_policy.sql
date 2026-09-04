-- =====================================================================
-- GLASSPOCKET / 11_privacy_policy.sql
-- The privacy layer behind Tab 05. Build Spec Section 06.1, with the
-- Section 10 fallback taken.
--
-- BUILD THIS FIRST IN PRACTICE.
--   Section 09 puts this in the Friday night block, ahead of the entire
--   data layer, because it is the only component that can fail in a way
--   that cannot be fixed later. That is exactly what happened here, and
--   finding it first is why the rest of the build is intact.
--
-- ---------------------------------------------------------------------
-- WHAT WAS ATTEMPTED, AND WHAT THE ACCOUNT SAID
-- ---------------------------------------------------------------------
--   CREATE PRIVACY BUDGET ...
--     -> SQL compilation error: syntax error at position 26
--        unexpected 'BUDGET'.
--
--   ALTER VIEW ... SET PRIVACY POLICY ... ENTITY KEY (beneficiary_id)
--     -> SQL compilation error: syntax error at position 36
--        unexpected 'PRIVACY'.
--
-- The keywords do not parse. This is not a permissions problem, so no
-- grant fixes it, and it is not a credit problem, so waiting does not
-- either. The differential privacy feature set is absent from this
-- deployment. The account IS Enterprise Edition: it accepts aggregation
-- policies and ninety-day Time Travel, both of which are Enterprise
-- gated. See docs/platform_constraints.md for the full probe.
--
-- The intended DDL is preserved verbatim at the foot of this file so the
-- difference between what was wanted and what shipped is inspectable
-- rather than described.
--
-- ---------------------------------------------------------------------
-- WHAT SHIPS INSTEAD, AND WHAT IT HONESTLY GUARANTEES
-- ---------------------------------------------------------------------
-- Section 10, hour 5:
--
--   "Fallback: implement the Attacker tab against an aggregation policy
--    with a minimum group size instead, which enforces a real
--    k-anonymity floor and is still a genuine governance feature.
--    Relabel the tab honestly as a minimum-cohort guarantee rather than
--    a differential-privacy guarantee."
--
-- So Tab 05 is a MINIMUM-COHORT GUARANTEE. What that means precisely:
--
--   IT DOES     refuse to answer any aggregate whose underlying group is
--               smaller than fifty entities, and it is Snowflake that
--               refuses, not the application. Switching roles does not
--               get around it and neither does rephrasing the query.
--
--   IT DOES NOT add calibrated noise, and it has no budget. A patient
--               attacker issuing many overlapping large-cohort queries
--               can still narrow in on an individual by differencing
--               them. Differential privacy is what defends against that,
--               and this account cannot offer it.
--
-- Tab 05 states both halves on screen. The word "differential" is not
-- used about what this policy does.
-- =====================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE GP_WH;
USE DATABASE GLASSPOCKET;

-- The analyst persona the application connects as.
CREATE ROLE IF NOT EXISTS GP_ANALYST;

-- ---------------------------------------------------------------------
-- The minimum-cohort policy. Fifty entities is the floor.
--
-- ACCOUNTADMIN is exempt, which is what makes the counterfactual column
-- on Tab 05 possible: the tab shows the true answer beside the released
-- answer, and the true answer has to come from somewhere.
-- ---------------------------------------------------------------------
-- A policy that is attached to a view cannot be replaced, so a re-run
-- has to detach it first. Wrapped because on a first run there is
-- nothing attached and nothing to detach.
EXECUTE IMMEDIATE $$
BEGIN
  ALTER VIEW GLASSPOCKET.SERVING.V_BENEFICIARY_OUTCOMES
    UNSET AGGREGATION POLICY;
  RETURN 'detached the existing policy so it can be replaced';
EXCEPTION
  WHEN OTHER THEN
    RETURN 'nothing attached yet, first run';
END;
$$;

CREATE OR REPLACE AGGREGATION POLICY GLASSPOCKET.SERVING.beneficiary_policy
  AS () RETURNS AGGREGATION_CONSTRAINT ->
  CASE
    WHEN CURRENT_ROLE() = 'ACCOUNTADMIN' THEN NO_AGGREGATION_CONSTRAINT()
    ELSE AGGREGATION_CONSTRAINT(MIN_GROUP_SIZE => 50)
  END;

-- ---------------------------------------------------------------------
-- The protected serving view. Terminal. Nothing reads from it
-- downstream and no Dynamic Table may ever depend on it.
--
-- TRAP 05 still applies with an aggregation policy: a policy-protected
-- object breaks downstream Dynamic Table refresh just the same, which is
-- why this sits at the very end of the pipeline.
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
  SET AGGREGATION POLICY GLASSPOCKET.SERVING.beneficiary_policy
  ENTITY KEY (beneficiary_id);

-- A row-level projection is the thing an attacker actually wants, and
-- the entity key is what makes "fifty entities" mean fifty people rather
-- than fifty rows: one beneficiary contributing forty rows does not
-- satisfy the floor on their own.

GRANT SELECT ON VIEW GLASSPOCKET.SERVING.V_BENEFICIARY_OUTCOMES TO ROLE GP_ANALYST;

-- ---------------------------------------------------------------------
-- The paired unprotected view.
--
-- Tab 05 shows the true value beside the released one, so a second view
-- over the same facts is required. It is readable only by a privileged
-- role and is used exclusively to render the left-hand comparison
-- column. GP_ANALYST is deliberately NOT granted on it: if the analyst
-- persona could read this, Tab 05 would be theatre.
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
  'COUNTERFACTUAL ONLY. The answer that would be released if no policy existed. Rendered on Tab 05 beside the protected answer and labelled as such. Never granted to GP_ANALYST.';

-- ---------------------------------------------------------------------
-- Cohort telemetry for the Tab 05 hero.
--
-- With no privacy budget to report, the tab reports the thing that
-- actually governs the answer: how close the current question sits to
-- the floor. Readable by the analyst persona because knowing the floor
-- is not a leak; the floor is the published rule.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW GLASSPOCKET.SERVING.V_COHORT_FLOOR AS
SELECT
  50                                   AS min_group_size,
  'AGGREGATION_POLICY'                 AS mechanism,
  'minimum cohort guarantee'           AS guarantee_label,
  'Snowflake refuses any aggregate over fewer than fifty beneficiaries. '
  || 'This is k-anonymity, not differential privacy: it adds no noise and '
  || 'has no query budget.'            AS guarantee_note;

GRANT SELECT ON VIEW GLASSPOCKET.SERVING.V_COHORT_FLOOR TO ROLE GP_ANALYST;

-- =====================================================================
-- VERIFICATION STEP, DO NOT SKIP
--
-- Run all three as GP_ANALYST, immediately.
--
--   1. A row-level select MUST fail.
--   2. A broad aggregate MUST succeed and return the true value, because
--      a minimum-cohort policy does not perturb what it does release.
--   3. An aggregate filtered below fifty beneficiaries MUST be refused.
--
-- Note how 2 differs from the differential privacy behaviour the spec
-- describes. Under DP the broad aggregate comes back slightly noised.
-- Here it comes back exact. That difference is the cost of the fallback
-- and Tab 05 says so.
-- =====================================================================

USE ROLE GP_ANALYST;
USE WAREHOUSE GP_WH;
USE DATABASE GLASSPOCKET;

-- 1. MUST FAIL. A refusal here is the guarantee working, so the deploy
-- runner is told to expect it.
-- EXPECT_FAIL
SELECT beneficiary_id, amount_usd
FROM GLASSPOCKET.SERVING.V_BENEFICIARY_OUTCOMES
LIMIT 10;

-- 2. MUST SUCCEED, exactly.
SELECT COUNT(*) AS n, SUM(amount_usd) AS total
FROM GLASSPOCKET.SERVING.V_BENEFICIARY_OUTCOMES;

-- 3. MUST be refused, because the group falls below the floor.
SELECT COUNT(*) AS n, SUM(amount_usd) AS total
FROM GLASSPOCKET.SERVING.V_BENEFICIARY_OUTCOMES
WHERE district       = (SELECT MIN(district) FROM MARTS.DISTRICT_DIM)
  AND programme_code = 'AID-2026-DR-114'
  AND month_key      = '2026-08';

USE ROLE ACCOUNTADMIN;

INSERT INTO MARTS.BUILD_LOG (step, detail)
VALUES ('11_privacy_policy',
        'minimum-cohort aggregation policy attached to '
        || 'SERVING.V_BENEFICIARY_OUTCOMES, entity key beneficiary_id, '
        || 'MIN_GROUP_SIZE 50. Differential privacy DDL unavailable on '
        || 'this deployment; see docs/platform_constraints.md.');

-- =====================================================================
-- THE INTENDED DIFFERENTIAL PRIVACY IMPLEMENTATION
--
-- Preserved verbatim. Restore it on any account where the DDL parses,
-- and revert Tab 05's wording with it. Everything else in the build is
-- unaffected by the swap, because the policy attaches to a terminal
-- serving view and nothing reads from it downstream.
-- =====================================================================
--
-- CREATE PRIVACY BUDGET IF NOT EXISTS GLASSPOCKET.SERVING.public_analyst
--   TYPE           = per_query_epsilon
--   EPSILON        = 0.1
--   REFRESH_PERIOD = 24;
--
-- CREATE OR REPLACE PRIVACY POLICY GLASSPOCKET.SERVING.beneficiary_policy
--   AS () RETURNS privacy_budget ->
--   CASE
--     WHEN CURRENT_ROLE() = 'ACCOUNTADMIN' THEN no_privacy_policy()
--     WHEN CURRENT_ROLE() = 'GP_ANALYST'   THEN privacy_budget(name => 'public_analyst')
--     ELSE privacy_budget(name => 'default')
--   END;
--
-- ALTER VIEW GLASSPOCKET.SERVING.V_BENEFICIARY_OUTCOMES
--   SET PRIVACY POLICY GLASSPOCKET.SERVING.beneficiary_policy
--   ENTITY KEY (beneficiary_id);
--
-- ALTER VIEW GLASSPOCKET.SERVING.V_BENEFICIARY_OUTCOMES
--   MODIFY COLUMN amount_usd SET PRIVACY DOMAIN (0, 5000);
--
-- ALTER VIEW GLASSPOCKET.SERVING.V_BENEFICIARY_OUTCOMES
--   MODIFY COLUMN district SET PRIVACY DOMAIN (
--     SELECT DISTINCT district FROM MARTS.DISTRICT_DIM);
