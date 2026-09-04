-- =====================================================================
-- GLASSPOCKET / 06_embeddings.sql
-- On-warehouse embeddings. Build Spec Section 06.2.
--
-- RUN ONCE. NEVER INSIDE THE APP.
--
-- TRAP 09: embeddings are generated once, in a single batch, and never
-- regenerated on application load. If an embedding query is written
-- inside a Streamlit render path, that is a defect and the acceptance
-- checks in 99 will catch it.
--
-- The vector is computed over name, mission line and cause together
-- rather than over the name alone. An impersonator that changes the name
-- but keeps the mission is still caught, and one that keeps the name but
-- serves an unrelated cause is not falsely matched.
-- =====================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE GP_WH;
USE DATABASE GLASSPOCKET;

UPDATE STAGING.ORGS
   SET name_vec = AI_EMBED(
         'snowflake-arctic-embed-m',
         name || ' :: ' || COALESCE(blurb, '') || ' :: ' || COALESCE(cause, '')
       )
 WHERE name_vec IS NULL;

-- ---------------------------------------------------------------------
-- Verification. Every row that participates in clone detection must
-- carry a vector, or the similarity join silently drops it.
-- ---------------------------------------------------------------------
SELECT
  COUNT(*)                                  AS total_orgs,
  COUNT(name_vec)                           AS embedded,
  COUNT(*) - COUNT(name_vec)                AS missing,
  COUNT_IF(is_synthetic AND name_vec IS NULL) AS missing_on_suspect_side
FROM STAGING.ORGS;

-- ---------------------------------------------------------------------
-- Export for the offline PCA projection and the graph layout.
-- tools/make_synthetic.py --project reads this, runs scikit-learn PCA to
-- two components and a networkx spring layout, and writes the results
-- back to MARTS.ORG_PROJECTION and MARTS.GRAPH_NODES.
--
-- Do not attempt UMAP in the warehouse runtime. Section 07, C01-3.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW STAGING.V_ORG_VECTORS AS
SELECT
  org_id,
  name,
  cause,
  state,
  region_h3,
  is_synthetic,
  is_verified,
  synth_target_id,
  name_vec
FROM STAGING.ORGS
WHERE name_vec IS NOT NULL;

-- ---------------------------------------------------------------------
-- Landing tables for the offline geometry. Written by
-- tools/make_synthetic.py --project, read by Tabs 01 and 02.
--
-- These exist because neither computation belongs in a render path and
-- neither belongs in the warehouse: PCA and a spring layout are one-time
-- offline work whose output is three numbers per row.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS MARTS.ORG_PROJECTION (
  org_id STRING PRIMARY KEY,
  pc1    FLOAT,
  pc2    FLOAT
);

CREATE TABLE IF NOT EXISTS MARTS.GRAPH_NODES (
  org_id    STRING PRIMARY KEY,
  name      STRING,
  x         FLOAT,
  y         FLOAT,
  node_kind STRING,   -- 'verified' | 'imitation'
  degree    INT
);

CREATE TABLE IF NOT EXISTS MARTS.GRAPH_EDGES (
  source_id  STRING,
  target_id  STRING,
  similarity FLOAT
);

INSERT INTO MARTS.BUILD_LOG (step, detail)
SELECT '06_embeddings', 'vectors written: ' || COUNT(name_vec)::STRING
FROM STAGING.ORGS;
