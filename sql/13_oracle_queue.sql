-- =====================================================================
-- GLASSPOCKET / 13_oracle_queue.sql
-- The queue contract between the warehouse and the Solana bridge.
-- Build Spec Section 08.
--
-- TRAP 02 / DO NOT ATTEMPT TO INVERT THIS
--   Trial accounts have no external network access. Any attempt to
--   create an external access integration or call out from a UDF fails
--   with error 509009. This is why the bridge is an outbound-polling
--   Node process that reaches INTO Snowflake, rather than Snowflake
--   reaching out to an RPC. A signing key also has no business inside a
--   data warehouse regardless of what the platform permits.
--
-- WHAT GOES ON CHAIN, AND WHAT MUST NOT
--   The receipt metadata carries a claim, never a person. Programme
--   code, amount BAND rather than exact amount, delivery WINDOW rather
--   than exact timestamp, a salted hash of the organisation identifier,
--   and a schema version. No beneficiary identifier, no coordinates, no
--   name, no exact figure.
--
--   Publish the claim, not the data. A public ledger is permanent, and
--   permanence plus personal data is a harm that cannot be undone.
-- =====================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE GP_WH;
USE DATABASE GLASSPOCKET;

CREATE OR REPLACE TABLE ORACLE.MINT_QUEUE (
  queue_id        STRING DEFAULT UUID_STRING() PRIMARY KEY,
  disbursement_id STRING,
  programme_code  STRING,
  amount_band     STRING,   -- '0-500', '500-2K', '2K-10K'
  window_key      STRING,   -- '2026-08'
  org_hash        STRING,   -- SHA2(org_id || salt)
  claimed_at      TIMESTAMP_NTZ,
  status          STRING DEFAULT 'PENDING'  -- PENDING, CLAIMED, MINTED, FAILED
);

CREATE OR REPLACE TABLE ORACLE.MINT_LOG (
  disbursement_id STRING,
  asset_id        STRING,
  signature       STRING,
  tree_address    STRING,
  leaf_index      INT,
  minted_at       TIMESTAMP_NTZ,
  explorer_url    STRING
);

CREATE OR REPLACE TABLE ORACLE.MINT_FAILURES (
  queue_id    STRING,
  disbursement_id STRING,
  error_text  STRING,
  failed_at   TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- ---------------------------------------------------------------------
-- Amount banding. The exact figure never leaves the warehouse.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION ORACLE.F_AMOUNT_BAND(amount FLOAT)
RETURNS STRING
AS
$$
  CASE
    WHEN amount <   500 THEN '0-500'
    WHEN amount <  2000 THEN '500-2K'
    WHEN amount < 10000 THEN '2K-10K'
    ELSE '10K+'
  END
$$;

-- ---------------------------------------------------------------------
-- Populate the queue.
--
-- RECEIPT_SALT is generated locally and lives in the bridge environment,
-- never in this file and never in the repository. Set it as a session
-- variable for this one statement, then unset it.
--
--   SET receipt_salt = '<the value from bridge/.env>';
--
-- The hash is what makes the ledger carry a claim rather than a directly
-- reversible identifier.
--
-- DELIBERATE GAP. Roughly one in every thirty eligible disbursements is
-- withheld from the queue so that the missing-receipt finding on Tab 06
-- is genuine rather than staged. Tab 10 discloses this. Do not remove
-- it: an accountability tool that manufactures a clean result has
-- demonstrated the opposite of its thesis.
-- ---------------------------------------------------------------------
INSERT INTO ORACLE.MINT_QUEUE
  (disbursement_id, programme_code, amount_band, window_key, org_hash, status)
SELECT
  d.disbursement_id,
  d.programme_code,
  ORACLE.F_AMOUNT_BAND(d.amount_usd)                        AS amount_band,
  TO_CHAR(COALESCE(d.delivered_at, d.dispatched_at), 'YYYY-MM') AS window_key,
  SHA2(d.org_id || $receipt_salt, 256)                      AS org_hash,
  'PENDING'                                                 AS status
FROM STAGING.DISBURSEMENTS d
JOIN MARTS.DELIVERY_GEOMETRY g USING (disbursement_id)
WHERE d.status = 'DELIVERED'
  AND g.geometry_verdict = 'PLAUSIBLE'
  AND MOD(ABS(HASH(d.disbursement_id)), 30) <> 0;   -- the deliberate gap

-- ---------------------------------------------------------------------
-- Bridge-facing helpers. The bridge is the only writer to this schema
-- and connects with a role that has write privileges here and nowhere
-- else. Do not reuse GP_ANALYST for the bridge.
-- ---------------------------------------------------------------------

-- Claim a batch. Atomic, so two bridge processes cannot mint the same row.
CREATE OR REPLACE PROCEDURE ORACLE.SP_CLAIM_BATCH(batch_size INT)
RETURNS TABLE (
  queue_id STRING, disbursement_id STRING, programme_code STRING,
  amount_band STRING, window_key STRING, org_hash STRING
)
LANGUAGE SQL
AS
$$
DECLARE
  res RESULTSET;
BEGIN
  UPDATE ORACLE.MINT_QUEUE
     SET status = 'CLAIMED', claimed_at = CURRENT_TIMESTAMP()
   WHERE queue_id IN (
     SELECT queue_id FROM ORACLE.MINT_QUEUE
      WHERE status = 'PENDING'
      ORDER BY queue_id
      LIMIT :batch_size
   );

  res := (
    SELECT queue_id, disbursement_id, programme_code,
           amount_band, window_key, org_hash
    FROM ORACLE.MINT_QUEUE
    WHERE status = 'CLAIMED' AND claimed_at >= DATEADD('minute', -1, CURRENT_TIMESTAMP())
  );
  RETURN TABLE(res);
END;
$$;

CREATE OR REPLACE VIEW ORACLE.V_QUEUE_STATUS AS
SELECT
  status,
  COUNT(*)      AS row_count,
  MIN(claimed_at) AS oldest_claim,
  MAX(claimed_at) AS newest_claim
FROM ORACLE.MINT_QUEUE
GROUP BY status;

-- Tree state for the Tab 06 stat band. maxDepth 14 gives a capacity of
-- 16,384 leaves, which comfortably exceeds demo volume. Tree parameters
-- are immutable after creation, so the tree is deliberately oversized.
CREATE OR REPLACE VIEW SERVING.V_TREE_STATE AS
SELECT
  ANY_VALUE(tree_address)             AS tree_address,
  COUNT(*)                            AS leaves_used,
  16384                               AS capacity,
  16384 - COUNT(*)                    AS capacity_remaining,
  'devnet'                            AS cluster,
  MAX(minted_at)                      AS last_mint_at
FROM ORACLE.MINT_LOG;

INSERT INTO MARTS.BUILD_LOG (step, detail)
SELECT '13_oracle_queue', 'queued for mint: ' || COUNT(*)::STRING
FROM ORACLE.MINT_QUEUE WHERE status = 'PENDING';
