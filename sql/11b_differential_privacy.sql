-- =====================================================================
-- GLASSPOCKET / 11b_differential_privacy.sql
--
-- THE FILE THAT SHOULD NOT EXIST, AND THE REASON IT DOES.
--
--   sql/11_privacy_policy.sql records that differential privacy is
--   absent from this deployment, on the evidence of two statements that
--   failed to parse:
--
--     CREATE PRIVACY BUDGET ...
--       -> syntax error at position 26 unexpected 'BUDGET'
--     ALTER VIEW ... SET PRIVACY POLICY ...
--       -> syntax error at position 36 unexpected 'PRIVACY'
--
--   Both statements were malformed. There is no CREATE PRIVACY BUDGET
--   statement in Snowflake at all: a budget comes into existence the
--   moment a policy body names one. And the attach clause is ADD
--   PRIVACY POLICY, not SET. A parser error says a statement is
--   malformed. It does not say a feature is missing, and for a weekend
--   this build treated those as the same fact.
--
--   Written in syntax that exists, on the same account and the same
--   warehouse, it works. This file is the proof, and The Wall renders
--   its output live.
--
-- ---------------------------------------------------------------------
-- WHAT THE PRIVACY ENGINE ACTUALLY DEMANDS
-- ---------------------------------------------------------------------
--   Attaching the policy is the easy half. Getting a query past it took
--   four more refusals, each of which is a real constraint worth
--   knowing:
--
--   1. 510242  "Supported aggregates: COUNT, COUNT_STAR."
--        A column cannot be aggregated or grouped on until it has a
--        PRIVACY DOMAIN. Without one its domain is infinite, and
--        calibrating noise against an infinite domain needs infinite
--        noise. Every column this view exposes therefore declares one.
--
--   2. The domain syntax is not what the intent comment in 11 guessed.
--        Range:      SET PRIVACY DOMAIN BETWEEN (0, 5000)
--        Enumerated: SET PRIVACY DOMAIN IN ('a', 'b', 'c')
--        A subquery is rejected in either position, so the categorical
--        domains are materialised as literals below.
--
--   3. 210007  "Private tables have an infinite multiplier."
--        A beneficiary holds up to five rows here, so one person can
--        move a row count by five. Snowflake refuses to reason about
--        that: the query itself must deduplicate on the entity key.
--        COUNT(DISTINCT beneficiary_id) does. COUNT(*) does not, and no
--        view definition fixes it, because the engine will not take a
--        GROUP BY inside a view as proof of one row per entity.
--        That is why the whole of The Wall counts people rather than
--        rows, which is what it should have counted anyway.
--
--   4. GROUP BY over an unbounded key is refused separately, with
--        "number of possible groups (infinity) must not exceed 10000".
--
--   The surface that survives all four is exactly one shape:
--
--        SELECT COUNT(DISTINCT beneficiary_id)
--        FROM SERVING.V_BENEFICIARY_DP
--        WHERE <filters over columns with declared domains>
--
--   which is, precisely, the question The Wall exists to ask.
--
-- ---------------------------------------------------------------------
-- WHY THE AGGREGATION POLICY STAYS
-- ---------------------------------------------------------------------
--   A privacy policy and an aggregation policy cannot both sit on one
--   object, so this is a SECOND view over the same facts rather than a
--   replacement. That is not a workaround, it is the exhibit: The Wall
--   asks one question of three objects and gets three different
--   answers.
--
--     PRIVILEGED.V_BENEFICIARY_OUTCOMES_TRUE   no policy, exact
--     SERVING.V_BENEFICIARY_OUTCOMES           MIN_GROUP_SIZE 50
--     SERVING.V_BENEFICIARY_DP                 epsilon budget, noised
--
--   The comparison is the argument. A cohort floor answers exactly or
--   refuses absolutely, and answering exactly is what leaves
--   differencing open. A privacy budget never refuses and never answers
--   exactly, and that is what closes it.
-- =====================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE GP_WH;
USE DATABASE GLASSPOCKET;

-- ---------------------------------------------------------------------
-- The policy. The budget is created by being named here; no separate
-- statement creates one, which is the fact the original probe missed.
--
--   BUDGET_LIMIT              total epsilon before the budget is spent
--   MAX_BUDGET_PER_AGGREGATE  per-query epsilon, so 3,000 queries at
--                             0.1 exhaust a limit of 300
-- ---------------------------------------------------------------------
-- A policy that is attached to an object cannot be replaced, so a re-run
-- has to detach it first. Wrapped because on a first run there is
-- nothing attached and nothing to detach.
EXECUTE IMMEDIATE $$
BEGIN
  ALTER VIEW GLASSPOCKET.SERVING.V_BENEFICIARY_DP
    DROP PRIVACY POLICY GLASSPOCKET.SERVING.beneficiary_dp_policy;
  RETURN 'detached the existing privacy policy so it can be replaced';
EXCEPTION
  WHEN OTHER THEN
    RETURN 'nothing attached yet, first run';
END;
$$;

CREATE OR REPLACE PRIVACY POLICY GLASSPOCKET.SERVING.beneficiary_dp_policy
  AS () RETURNS PRIVACY_BUDGET ->
  PRIVACY_BUDGET(BUDGET_NAME              => 'gp_analysts',
                 BUDGET_LIMIT             => 300,
                 MAX_BUDGET_PER_AGGREGATE => 0.1);

-- ---------------------------------------------------------------------
-- The protected view. Terminal, like its aggregation-policy twin, for
-- the same reason: a policy-protected object breaks downstream Dynamic
-- Table refresh.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW GLASSPOCKET.SERVING.V_BENEFICIARY_DP AS
  SELECT
    beneficiary_id,
    district,
    programme_code,
    cause,
    amount_usd,
    delivered_flag,
    month_key
  FROM GLASSPOCKET.MARTS.BENEFICIARY_FACTS;

ALTER VIEW GLASSPOCKET.SERVING.V_BENEFICIARY_DP
  ADD PRIVACY POLICY GLASSPOCKET.SERVING.beneficiary_dp_policy
  ENTITY KEY (beneficiary_id);

-- ---------------------------------------------------------------------
-- Privacy domains. Without these every query is refused with 510242,
-- because a column with no declared domain has an infinite one.
--
-- The categorical domains are built as literal lists from the data,
-- because SET PRIVACY DOMAIN IN (...) rejects a subquery. That is a
-- disclosure and not a detail: declaring a domain publishes the set of
-- values, so the forty district names are public by construction. They
-- are place names on a map, which is the right thing to be public. A
-- column whose values were themselves sensitive could not be given an
-- enumerated domain at all, and that is a genuine limit on where this
-- mechanism can be used.
--
-- The literals are built with CHR(39) rather than escaped quotes. This
-- string is already inside a $$ block inside dynamic SQL, and the third
-- layer of quote escaping is where the mistakes live.
-- ---------------------------------------------------------------------
EXECUTE IMMEDIATE $$
DECLARE
  cols ARRAY DEFAULT ARRAY_CONSTRUCT('district', 'programme_code',
                                     'month_key', 'cause');
  col  STRING;
  vals STRING;

BEGIN
  FOR i IN 0 TO ARRAY_SIZE(cols) - 1 DO
    col := GET(:cols, i)::STRING;
    EXECUTE IMMEDIATE
      'SELECT LISTAGG(DISTINCT CHR(39) || REPLACE(' || col
      || ', CHR(39), CHR(39) || CHR(39)) || CHR(39), '', '') '
      || 'FROM GLASSPOCKET.MARTS.BENEFICIARY_FACTS';
    SELECT * INTO :vals FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));
    EXECUTE IMMEDIATE
      'ALTER VIEW GLASSPOCKET.SERVING.V_BENEFICIARY_DP MODIFY COLUMN '
      || col || ' SET PRIVACY DOMAIN IN (' || :vals || ')';
  END FOR;
  RETURN 'categorical privacy domains declared';
END;
$$;

ALTER VIEW GLASSPOCKET.SERVING.V_BENEFICIARY_DP
  MODIFY COLUMN amount_usd SET PRIVACY DOMAIN BETWEEN (0, 5000);

ALTER VIEW GLASSPOCKET.SERVING.V_BENEFICIARY_DP
  MODIFY COLUMN delivered_flag SET PRIVACY DOMAIN BETWEEN (0, 1);

GRANT SELECT ON VIEW GLASSPOCKET.SERVING.V_BENEFICIARY_DP TO ROLE GP_ANALYST;

-- ---------------------------------------------------------------------
-- Telemetry the tab reads. The mechanism is nameable without a caveat
-- now, so the honest label changes with it.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW GLASSPOCKET.SERVING.V_PRIVACY_MECHANISMS AS
SELECT 'PRIVILEGED.V_BENEFICIARY_OUTCOMES_TRUE' AS object_name,
       'none'                                   AS mechanism,
       'the counterfactual'                     AS label,
       0                                        AS min_group_size,
       NULL                                     AS epsilon_per_query,
       NULL                                     AS budget_limit,
       'Exact. Readable only by a privileged role, rendered beside the '
       || 'protected answers so the cost of each guarantee is visible.'
                                                AS note
UNION ALL
SELECT 'SERVING.V_BENEFICIARY_OUTCOMES', 'AGGREGATION_POLICY',
       'minimum cohort guarantee', 50, NULL, NULL,
       'Refuses any aggregate over fewer than fifty beneficiaries and '
       || 'releases everything else exactly. k-anonymity: no noise, no '
       || 'budget, and therefore no defence against differencing.'
UNION ALL
SELECT 'SERVING.V_BENEFICIARY_DP', 'PRIVACY_POLICY',
       'differential privacy', 0, 0.1, 300,
       'Never refuses and never answers exactly. Laplace noise is '
       || 'calibrated per query from the declared privacy domains, and '
       || 'every query spends epsilon whether or not it was useful.';

GRANT SELECT ON VIEW GLASSPOCKET.SERVING.V_PRIVACY_MECHANISMS TO ROLE GP_ANALYST;

-- =====================================================================
-- VERIFICATION. Run as the analyst persona, with secondary roles off.
--
--   1. Row-level projection MUST fail.
--   2. COUNT(DISTINCT beneficiary_id) MUST succeed and MUST return a
--      DIFFERENT number on each run. That difference is the noise, and
--      it is the whole point.
--   3. COUNT(*) MUST fail with 210007: the query does not deduplicate
--      on the entity key, so the multiplier is unbounded.
-- =====================================================================

USE ROLE GP_ANALYST;
USE SECONDARY ROLES NONE;
USE WAREHOUSE GP_WH;
USE DATABASE GLASSPOCKET;

-- 1. MUST FAIL.
-- EXPECT_FAIL
SELECT beneficiary_id, amount_usd
FROM GLASSPOCKET.SERVING.V_BENEFICIARY_DP LIMIT 10;

-- 2. MUST SUCCEED, three times, with three different answers.
SELECT COUNT(DISTINCT beneficiary_id) AS people
FROM GLASSPOCKET.SERVING.V_BENEFICIARY_DP;
SELECT COUNT(DISTINCT beneficiary_id) AS people
FROM GLASSPOCKET.SERVING.V_BENEFICIARY_DP;
SELECT COUNT(DISTINCT beneficiary_id) AS people
FROM GLASSPOCKET.SERVING.V_BENEFICIARY_DP;

-- 3. MUST FAIL with the infinite multiplier.
-- EXPECT_FAIL
SELECT COUNT(*) AS n FROM GLASSPOCKET.SERVING.V_BENEFICIARY_DP;

USE ROLE ACCOUNTADMIN;
USE SECONDARY ROLES ALL;

INSERT INTO MARTS.BUILD_LOG (step, detail)
VALUES ('11b_differential_privacy',
        'privacy policy beneficiary_dp_policy attached to '
        || 'SERVING.V_BENEFICIARY_DP, entity key beneficiary_id, budget '
        || 'gp_analysts limit 300, 0.1 epsilon per aggregate. The '
        || 'earlier finding that this deployment lacks differential '
        || 'privacy was a syntax error in the probe, not a capability '
        || 'report. See docs/platform_constraints.md.');
