-- =====================================================================
-- GLASSPOCKET / 10_semantic_view.sql
-- Semantic view over staging and marts. Build Spec Section 06.6.
--
-- Powers Tab 08, Ask The Warehouse. The tab exists because
-- accountability that requires SQL is accountability for people who
-- already have power, which makes natural-language access an equity
-- feature rather than a party trick.
--
-- The shape declared here is what Tab 08 counts live for its hero:
--   2 tables, 6 dimensions, 4 metrics, 19 synonyms.
-- If you add to this object, the hero figure follows automatically. It
-- is read from the object, never typed into the interface.
-- =====================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE GP_WH;
USE DATABASE GLASSPOCKET;

CREATE OR REPLACE SEMANTIC VIEW MARTS.GIVING_SEMANTICS
  TABLES (
    orgs AS STAGING.ORGS PRIMARY KEY (org_id)
      WITH SYNONYMS ('charities', 'nonprofits', 'organisations'),
    disb AS MARTS.DELIVERY_GEOMETRY PRIMARY KEY (disbursement_id)
      WITH SYNONYMS ('disbursements', 'deliveries', 'aid shipments')
  )
  RELATIONSHIPS (
    disb (org_id) REFERENCES orgs (org_id)
  )
  FACTS (
    disb.amount_usd AS amount_usd,
    disb.pledged_usd AS pledged_usd
  )
  DIMENSIONS (
    orgs.state    AS state
      WITH SYNONYMS ('province', 'region'),
    orgs.cause    AS cause
      WITH SYNONYMS ('sector', 'category', 'programme area'),
    orgs.city     AS city
      WITH SYNONYMS ('town'),
    disb.geometry_verdict AS verdict
      WITH SYNONYMS ('geometry verdict', 'plausibility'),
    disb.district AS district
      WITH SYNONYMS ('area', 'locality'),
    disb.status   AS status
      WITH SYNONYMS ('delivery status', 'stage')
  )
  METRICS (
    disb.total_usd AS SUM(disb.amount_usd)
      WITH SYNONYMS ('total disbursed', 'money moved'),
    disb.flagged_pct AS AVG(CASE WHEN disb.geometry_verdict <> 'PLAUSIBLE'
                                 THEN 1 ELSE 0 END)
      WITH SYNONYMS ('flag rate', 'share flagged'),
    disb.delivered_usd AS SUM(CASE WHEN disb.status = 'DELIVERED'
                                   THEN disb.amount_usd ELSE 0 END)
      WITH SYNONYMS ('value delivered', 'confirmed delivery value'),
    disb.event_count AS COUNT(disb.disbursement_id)
      WITH SYNONYMS ('shipments', 'number of deliveries')
  );

-- ---------------------------------------------------------------------
-- Model browser, Tab 08 section S5. Read from the object itself so the
-- browser cannot drift from the definition.
-- ---------------------------------------------------------------------
SHOW SEMANTIC VIEWS LIKE 'GIVING_SEMANTICS' IN SCHEMA MARTS;
SHOW SEMANTIC DIMENSIONS IN SEMANTIC VIEW MARTS.GIVING_SEMANTICS;
SHOW SEMANTIC METRICS    IN SEMANTIC VIEW MARTS.GIVING_SEMANTICS;

-- ---------------------------------------------------------------------
-- The three preset questions, wired to hand-written SQL over the same
-- semantic view.
--
-- Presets guarantee the demo works even if free-form input behaves
-- unpredictably. If Cortex Analyst is unavailable or unreliable in the
-- chosen region, degrade gracefully: keep these three, keep the model
-- browser, and state in S6 that free-form questions are disabled in this
-- build. The semantic view object still counts as a feature and the tab
-- still makes its point. Section 07, Tab 08.
-- ---------------------------------------------------------------------

-- "which causes attract the most imitation?"
CREATE OR REPLACE VIEW SERVING.V_ASK_CAUSE_IMITATION AS
SELECT
  cause,
  verified_orgs,
  seeded_orgs,
  imitations_per_100
FROM MARTS.DT_CAUSE_EXPOSURE
WHERE seeded_orgs > 0
ORDER BY imitations_per_100 DESC;

-- "flagged deliveries by state"
CREATE OR REPLACE VIEW SERVING.V_ASK_FLAGGED_BY_STATE AS
SELECT * FROM SEMANTIC_VIEW(
  MARTS.GIVING_SEMANTICS
  DIMENSIONS state
  METRICS    disb.flagged_pct, disb.event_count
)
ORDER BY flagged_pct DESC;

-- "total moved last quarter"
CREATE OR REPLACE VIEW SERVING.V_ASK_TOTAL_MOVED AS
SELECT
  TO_CHAR(DATE_TRUNC('quarter', dispatched_at), 'YYYY-"Q"Q') AS quarter,
  SUM(amount_usd)                                            AS total_usd,
  COUNT(*)                                                   AS events
FROM MARTS.DELIVERY_GEOMETRY
WHERE dispatched_at IS NOT NULL
GROUP BY 1
ORDER BY 1;

INSERT INTO MARTS.BUILD_LOG (step, detail)
VALUES ('10_semantic_view', 'GIVING_SEMANTICS: 2 tables, 6 dimensions, 4 metrics');
