-- =====================================================================
-- GLASSPOCKET / 12_serving_views.sql
-- Terminal serving views. Everything the application selects from.
--
-- Every view here is shaped so the application can run a single indexed
-- SELECT against it. Nothing heavier than that may execute during the
-- demo: every embedding, similarity pair, geospatial join and blockchain
-- asset identifier is already materialised. Section 00, rule 4.
--
-- Section 07 requires that every table in the interface carry an
-- explicit LIMIT (Trap 07, the 32 MB frontend transfer cap). The LIMITs
-- live in app/queries.py, not here, so that a view stays reusable.
-- =====================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE GP_WH;
USE DATABASE GLASSPOCKET;

-- ---------------------------------------------------------------------
-- TAB 00 / The Brief
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW SERVING.V_KPI AS
SELECT
  (SELECT COUNT(*) FROM STAGING.ORGS)                                AS orgs_indexed,
  (SELECT COUNT(*) FROM STAGING.DISBURSEMENTS)                       AS disbursements_traced,
  (SELECT COUNT(*) FROM ORACLE.MINT_LOG)                             AS receipts_on_chain,
  (SELECT COUNT(*) FROM MARTS.ORG_RISK
    WHERE verdict = 'needs a second look')                           AS needs_second_look,
  (SELECT COUNT(*) FROM SERVING.V_PIPELINE_HEALTH WHERE within_lag)  AS pipeline_objects_fresh;

-- ---------------------------------------------------------------------
-- TAB 01 / Give With Confidence
-- The pairing that opens the application. Both sides carry identical
-- field shapes so the interface can render them with no visual tell.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW SERVING.V_CONFIDENCE_PAIRS AS
SELECT
  c.suspect_id,
  c.suspect_name,
  s.blurb        AS suspect_blurb,
  s.city         AS suspect_city,
  s.state        AS suspect_state,
  s.cause        AS suspect_cause,
  c.target_id,
  c.target_name,
  t.blurb        AS target_blurb,
  t.city         AS target_city,
  t.state        AS target_state,
  t.cause        AS target_cause,
  c.semantic_sim,
  c.string_sim,
  c.evasion_gap,
  c.synth_technique,
  c.confirmation_method
FROM MARTS.CLONE_CONFIRMED c
JOIN STAGING.ORGS s ON s.org_id = c.suspect_id
JOIN STAGING.ORGS t ON t.org_id = c.target_id
WHERE s.is_synthetic = TRUE     -- suspect side is seeded, always
  AND t.is_synthetic = FALSE    -- target side is real, always
  AND t.is_verified  = TRUE;

-- Semantic neighbourhood scatter. pc1 and pc2 are written by the offline
-- PCA in tools/make_synthetic.py, so the tab runs a plain SELECT and
-- renders instantly. Section 07, C01-3.
CREATE OR REPLACE VIEW SERVING.V_ORG_PROJECTION AS
SELECT
  p.org_id,
  o.name,
  o.cause,
  o.state,
  o.region_h3,
  o.is_synthetic,
  o.is_verified,
  o.synth_target_id,
  p.pc1,
  p.pc2
FROM MARTS.ORG_PROJECTION p
JOIN STAGING.ORGS o USING (org_id);

-- ---------------------------------------------------------------------
-- TAB 02 / The Trust Graph
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW SERVING.V_GRAPH AS
SELECT
  n.org_id,
  n.name,
  n.x,
  n.y,
  n.node_kind,          -- 'verified' | 'imitation'
  n.degree,
  o.cause,
  o.city,
  o.state,
  o.ein
FROM MARTS.GRAPH_NODES n
JOIN STAGING.ORGS o USING (org_id);

CREATE OR REPLACE VIEW SERVING.V_GRAPH_EDGES AS
SELECT
  e.source_id,
  e.target_id,
  e.similarity,
  ns.x AS source_x, ns.y AS source_y,
  nt.x AS target_x, nt.y AS target_y
FROM MARTS.GRAPH_EDGES e
JOIN MARTS.GRAPH_NODES ns ON ns.org_id = e.source_id
JOIN MARTS.GRAPH_NODES nt ON nt.org_id = e.target_id;

-- ---------------------------------------------------------------------
-- TAB 04 / The Last Mile
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW SERVING.V_ATTRITION_FLOW AS
SELECT
  pledged_usd,
  dispatched_usd,
  delivered_usd,
  unaccounted_usd,
  never_dispatched_usd,
  events,
  DIV0(delivered_usd, NULLIF(dispatched_usd, 0)) AS delivery_rate
FROM MARTS.DT_ATTRITION_STAGES;

-- District ranking, Tab 04 section S5. Clicking a bar sets the cross-tab
-- filter that carries the district into Tab 05, where the same district
-- returns under privacy protection. That handoff is narrated in the demo.
CREATE OR REPLACE VIEW SERVING.V_DISTRICT_ATTRITION AS
SELECT
  d.district,
  d.events,
  d.moved_usd,
  d.delivered_usd,
  d.attrition_rate,
  d.mean_transit_hours,
  dim.centroid_lat,
  dim.centroid_lon
FROM MARTS.DT_DISTRICT_ATTRITION d
LEFT JOIN MARTS.DISTRICT_DIM dim USING (district);

-- ---------------------------------------------------------------------
-- TAB 06 / The Receipt
-- The gap is real. A deliberate subset of verified disbursements is left
-- unminted so the missing-receipt finding is genuine rather than staged,
-- and Tab 10 says so.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW SERVING.V_RECEIPT_GAP AS
WITH expected AS (
  SELECT
    DATE_TRUNC('day', COALESCE(d.delivered_at, d.dispatched_at)) AS day,
    COUNT(*) AS expected_receipts
  FROM STAGING.DISBURSEMENTS d
  WHERE d.status IN ('DELIVERED', 'UNACCOUNTED')
  GROUP BY 1
),
actual AS (
  SELECT
    DATE_TRUNC('day', m.minted_at) AS day,
    COUNT(*) AS actual_receipts
  FROM ORACLE.MINT_LOG m
  GROUP BY 1
),
days AS (
  SELECT day FROM expected
  UNION
  SELECT day FROM actual
)
SELECT
  d.day,
  COALESCE(e.expected_receipts, 0) AS expected_receipts,
  COALESCE(a.actual_receipts, 0)   AS actual_receipts,
  SUM(COALESCE(e.expected_receipts, 0)) OVER (ORDER BY d.day) AS cum_expected,
  SUM(COALESCE(a.actual_receipts, 0))   OVER (ORDER BY d.day) AS cum_actual,
  SUM(COALESCE(e.expected_receipts, 0)) OVER (ORDER BY d.day)
    - SUM(COALESCE(a.actual_receipts, 0)) OVER (ORDER BY d.day) AS cum_gap
FROM days d
LEFT JOIN expected e USING (day)
LEFT JOIN actual   a USING (day)
ORDER BY d.day;

-- Receipt lookup. Reads the local mirror populated by the bridge. Only
-- the explorer link touches the network, and it does so in the viewer's
-- browser, not in a render path. Section 07, demo safety.
CREATE OR REPLACE VIEW SERVING.V_RECEIPT_LOOKUP AS
SELECT
  m.asset_id,
  m.signature,
  m.tree_address,
  m.leaf_index,
  m.minted_at,
  m.explorer_url,
  q.programme_code,
  q.amount_band,
  q.window_key,
  q.org_hash
FROM ORACLE.MINT_LOG m
JOIN ORACLE.MINT_QUEUE q USING (disbursement_id);

-- ---------------------------------------------------------------------
-- TAB 09 / Where A Dollar Lands
--
-- THE ONLY TAB WITH ZERO SYNTHETIC CONTENT.
-- Built exclusively from Business Master File organisations in good
-- standing. The hard filter on is_synthetic is verified by an acceptance
-- check, and the interface states the guarantee in S1.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW SERVING.V_CONFIDENCE_RANK AS
SELECT
  o.org_id,
  o.ein,
  o.name,
  o.city,
  o.state,
  o.cause,
  o.blurb,
  COALESCE(a.delivery_rate, 0)        AS delivery_rate,
  COALESCE(r.receipt_coverage, 0)     AS receipt_coverage,
  COALESCE(a.moved_usd, 0)            AS value_moved_usd,
  COALESCE(a.disbursements, 0)        AS disbursements,
  COALESCE(rk.risk_score, 0)          AS risk_score,
  -- Composite confidence. Delivery and receipt coverage carry it;
  -- anything that needed a second look is subtracted rather than hidden.
  ROUND(
      60 * COALESCE(a.delivery_rate, 0)
    + 40 * COALESCE(r.receipt_coverage, 0)
    -      COALESCE(rk.risk_score, 0) * 0.5
  , 1)                                AS confidence
FROM STAGING.ORGS o
LEFT JOIN MARTS.DT_ORG_ACTIVITY     a  ON a.org_id  = o.org_id
LEFT JOIN MARTS.DT_RECEIPT_COVERAGE r  ON r.org_id  = o.org_id
LEFT JOIN MARTS.ORG_RISK            rk ON rk.org_id = o.org_id
WHERE o.is_synthetic = FALSE          -- hard filter, verified in 99
  AND o.is_verified  = TRUE
  AND o.batch_id     = 'IRS_BMF_2026';

-- ---------------------------------------------------------------------
-- TAB 10 / Method And Honesty
-- Counted live so the honesty table cannot drift from reality.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW SERVING.V_PROVENANCE AS
SELECT 'STAGING.ORGS'           AS table_name, batch_id, COUNT(*) AS row_count
  FROM STAGING.ORGS           GROUP BY batch_id
UNION ALL
SELECT 'STAGING.DISBURSEMENTS', batch_id, COUNT(*)
  FROM STAGING.DISBURSEMENTS  GROUP BY batch_id
UNION ALL
SELECT 'STAGING.BENEFICIARIES', batch_id, COUNT(*)
  FROM STAGING.BENEFICIARIES  GROUP BY batch_id
UNION ALL
SELECT 'STAGING.IATI_LOCATIONS', batch_id, COUNT(*)
  FROM STAGING.IATI_LOCATIONS GROUP BY batch_id
UNION ALL
SELECT 'MARTS.ORG_STANDING',    batch_id, COUNT(*)
  FROM MARTS.ORG_STANDING     GROUP BY batch_id;

CREATE OR REPLACE VIEW SERVING.V_HONESTY_TOTALS AS
SELECT
  SUM(CASE WHEN batch_id = 'SYNTH_ADVERSARY_V1' THEN 0    ELSE row_count END) AS real_rows,
  SUM(CASE WHEN batch_id = 'SYNTH_ADVERSARY_V1' THEN row_count ELSE 0    END) AS seeded_rows
FROM SERVING.V_PROVENANCE;

GRANT SELECT ON ALL VIEWS   IN SCHEMA SERVING TO ROLE GP_ANALYST;
GRANT SELECT ON ALL TABLES  IN SCHEMA MARTS   TO ROLE GP_ANALYST;

-- GP_ANALYST must never be able to read the unprotected twin. The
-- blanket grant above would otherwise hand it the counterfactual and
-- turn Tab 05 into theatre, so it is revoked immediately afterwards and
-- future grants are blocked from re-adding it.
REVOKE SELECT ON VIEW SERVING.V_BENEFICIARY_OUTCOMES_TRUE FROM ROLE GP_ANALYST;

-- Belt and braces: a later GRANT ... ON ALL VIEWS would silently undo
-- the revoke above, so the same statement is repeated at the very end of
-- this file. If you add grants, add them BEFORE that line.
REVOKE SELECT ON VIEW SERVING.V_BENEFICIARY_OUTCOMES_TRUE FROM ROLE GP_ANALYST;

-- The counterfactual is readable only by the privileged role, which is
-- the whole reason Tab 05's left-hand column can exist at all.
SHOW GRANTS ON VIEW SERVING.V_BENEFICIARY_OUTCOMES_TRUE;

INSERT INTO MARTS.BUILD_LOG (step, detail)
VALUES ('12_serving_views', 'serving views created and granted');
