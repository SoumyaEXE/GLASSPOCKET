-- =====================================================================
-- GLASSPOCKET / 06_embeddings.sql
-- Vectors into a VECTOR(FLOAT, 768) column. Build Spec Section 06.2.
--
-- RUN ONCE. NEVER INSIDE THE APP.
--
-- TRAP 09: embeddings are generated once, in a single batch, and never
-- regenerated on application load. If an embedding query is written
-- inside a Streamlit render path, that is a defect.
--
-- ---------------------------------------------------------------------
-- WHY THE AI_EMBED CALL IS COMMENTED OUT ON THIS ACCOUNT
-- ---------------------------------------------------------------------
-- The intended statement is preserved verbatim below. It fails here:
--
--   AI function _AI_EMBED_WITH_PROMPT_768 is not available for
--   trial accounts.
--
-- That is an account-class restriction, not credit exhaustion, so no
-- grant and no waiting fixes it. Every SNOWFLAKE.CORTEX.* function is
-- blocked the same way. See docs/platform_constraints.md.
--
-- The fallback keeps the model and moves the machine: the same
-- snowflake-arctic-embed-m vectors are computed offline by
-- tools/embed_offline.py and loaded here. What matters for the thesis is
-- unaffected, because the SIMILARITY SEARCH still runs in the warehouse
-- in SQL, over a real VECTOR column, with the mandatory pre-filter. Only
-- the vector generation moved.
--
-- Restore the AI_EMBED path on any account where it is available. It is
-- the better story and it is one uncommented statement away.
-- =====================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE GP_WH;
USE DATABASE GLASSPOCKET;

-- ---------------------------------------------------------------------
-- THE INTENDED STATEMENT, unavailable on a trial account.
-- ---------------------------------------------------------------------
-- UPDATE STAGING.ORGS
--    SET name_vec = AI_EMBED(
--          'snowflake-arctic-embed-m',
--          name || ' :: ' || COALESCE(blurb, '') || ' :: ' || COALESCE(cause, '')
--        )
--  WHERE name_vec IS NULL;

-- ---------------------------------------------------------------------
-- THE FALLBACK. Offline vectors, staged as JSON arrays, cast into the
-- VECTOR column. The cast is the part that matters: from here on the
-- column is a genuine VECTOR(FLOAT, 768) and every downstream query is
-- doing real vector work in the warehouse.
--
--   python tools/embed_offline.py           writes data/vectors/org_vectors.csv
--   PUT file://data/vectors/org_vectors.csv @RAW.GP_STAGE/vectors/;
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE RAW.ORG_VECTORS (
  org_id STRING,
  vec    STRING            -- JSON array of 768 floats
);

COPY INTO RAW.ORG_VECTORS
  FROM @RAW.GP_STAGE/vectors/org_vectors.csv
  FILE_FORMAT = (FORMAT_NAME = RAW.FF_PREPARED)
  ON_ERROR = ABORT_STATEMENT;

UPDATE STAGING.ORGS o
   SET name_vec = v.vec::ARRAY::VECTOR(FLOAT, 768)
  FROM RAW.ORG_VECTORS v
 WHERE v.org_id = o.org_id
   AND o.name_vec IS NULL;

-- ---------------------------------------------------------------------
-- Verification. Every row that participates in clone detection must
-- carry a vector, or the similarity join silently drops it.
-- ---------------------------------------------------------------------
SELECT
  COUNT(*)                                    AS total_orgs,
  COUNT(name_vec)                             AS embedded,
  COUNT(*) - COUNT(name_vec)                  AS missing,
  COUNT_IF(is_synthetic AND name_vec IS NULL) AS missing_on_suspect_side
FROM STAGING.ORGS;

-- Prove the column is a real vector and cosine similarity works on it.
SELECT VECTOR_COSINE_SIMILARITY(a.name_vec, b.name_vec) AS sanity_check
FROM STAGING.ORGS a, STAGING.ORGS b
WHERE a.name_vec IS NOT NULL AND b.name_vec IS NOT NULL
  AND a.org_id <> b.org_id
LIMIT 1;

-- ---------------------------------------------------------------------
-- Landing tables for the offline geometry, written by
-- tools/make_synthetic.py and read by Tabs 01 and 02. Neither a PCA nor
-- a spring layout belongs in a render path.
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

-- Load them.
--   PUT file://data/warehouse/projection.csv      @RAW.GP_STAGE/warehouse/;
--   PUT file://data/warehouse/graph_nodes.csv     @RAW.GP_STAGE/warehouse/;
--   PUT file://data/warehouse/graph_edges.csv     @RAW.GP_STAGE/warehouse/;
--   PUT file://data/warehouse/threshold_curve.csv @RAW.GP_STAGE/warehouse/;

TRUNCATE TABLE IF EXISTS MARTS.ORG_PROJECTION;
COPY INTO MARTS.ORG_PROJECTION (org_id, pc1, pc2)
  FROM @RAW.GP_STAGE/warehouse/projection.csv
  FILE_FORMAT = (FORMAT_NAME = RAW.FF_PREPARED)
  ON_ERROR = ABORT_STATEMENT;

TRUNCATE TABLE IF EXISTS MARTS.GRAPH_NODES;
COPY INTO MARTS.GRAPH_NODES (org_id, name, x, y, node_kind, degree)
  FROM @RAW.GP_STAGE/warehouse/graph_nodes.csv
  FILE_FORMAT = (FORMAT_NAME = RAW.FF_PREPARED)
  ON_ERROR = ABORT_STATEMENT;

TRUNCATE TABLE IF EXISTS MARTS.GRAPH_EDGES;
COPY INTO MARTS.GRAPH_EDGES (source_id, target_id, similarity)
  FROM @RAW.GP_STAGE/warehouse/graph_edges.csv
  FILE_FORMAT = (FORMAT_NAME = RAW.FF_PREPARED)
  ON_ERROR = ABORT_STATEMENT;

-- The threshold sweep. Precomputed so the Tab 02 slider responds with no
-- query behind it, and recomputed in SQL by 07 when the corpus changes.
CREATE TABLE IF NOT EXISTS MARTS.THRESHOLD_CURVE (
  threshold FLOAT, pairs_detected INT,
  pairs_ai_confirmed INT, is_production_value BOOLEAN
);

INSERT INTO MARTS.BUILD_LOG (step, detail)
SELECT '06_embeddings',
       'vectors loaded: ' || COUNT(name_vec)::STRING
    || ' (offline arctic-embed-m; AI_EMBED blocked on trial accounts)'
FROM STAGING.ORGS;
