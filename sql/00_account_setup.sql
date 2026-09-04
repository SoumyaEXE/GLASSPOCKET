-- =====================================================================
-- GLASSPOCKET / 00_account_setup.sql
-- Warehouse, database, schemas, edition assert.
--
-- Run first, as ACCOUNTADMIN, before anything else.
-- Build Spec Section 02 (Traps 01 and 09) and the environment matrix.
-- =====================================================================

USE ROLE ACCOUNTADMIN;

-- ---------------------------------------------------------------------
-- TRAP 01 / UNRECOVERABLE
-- Differential privacy requires Enterprise Edition or higher. Edition is
-- chosen at signup and cannot be changed afterwards. If this assertion
-- fails, stop: create a second trial and select Enterprise. Do not
-- proceed on a Standard account, because the centrepiece of this build
-- is permanently unavailable there.
-- ---------------------------------------------------------------------
SELECT CURRENT_EDITION() AS edition;

EXECUTE IMMEDIATE $$
BEGIN
  LET edition STRING := (SELECT CURRENT_EDITION());
  IF (edition NOT IN ('ENTERPRISE', 'BUSINESS CRITICAL', 'VPS')) THEN
    RAISE STATEMENT_ERROR;
  END IF;
  RETURN 'edition ok: ' || edition;
EXCEPTION
  WHEN STATEMENT_ERROR THEN
    RETURN 'FATAL: edition is ' || edition ||
           '. Differential privacy requires Enterprise or higher. '
           'Create a new trial and select Enterprise. See Trap 01.';
END;
$$;

-- ---------------------------------------------------------------------
-- Warehouse. XSMALL for everything in this build, 60 second auto-suspend.
-- TRAP 09: the trial credit budget is finite.
-- ---------------------------------------------------------------------
CREATE WAREHOUSE IF NOT EXISTS GP_WH
  WAREHOUSE_SIZE       = 'XSMALL'
  AUTO_SUSPEND         = 60
  AUTO_RESUME          = TRUE
  INITIALLY_SUSPENDED  = TRUE
  COMMENT              = 'GLASSPOCKET. XSMALL only. Do not resize.';

ALTER WAREHOUSE GP_WH SET
  WAREHOUSE_SIZE = 'XSMALL',
  AUTO_SUSPEND   = 60,
  AUTO_RESUME    = TRUE;

USE WAREHOUSE GP_WH;

-- ---------------------------------------------------------------------
-- Database and the five schemas named in the environment matrix.
-- RAW      landing zone, exactly as downloaded, never edited
-- STAGING  normalised and typed, one row per real-world entity
-- MARTS    derived intelligence: clone pairs, geometry, risk, graph
-- SERVING  terminal views only. The privacy policy attaches here.
-- ORACLE   mint queue and mint log. The bridge is the only writer.
-- ---------------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS GLASSPOCKET
  COMMENT = 'GLASSPOCKET. Accountability engine for charitable giving.';

USE DATABASE GLASSPOCKET;

CREATE SCHEMA IF NOT EXISTS RAW      COMMENT = 'As downloaded. Never edited.';
CREATE SCHEMA IF NOT EXISTS STAGING  COMMENT = 'Normalised entities.';
CREATE SCHEMA IF NOT EXISTS MARTS    COMMENT = 'Derived intelligence.';
CREATE SCHEMA IF NOT EXISTS SERVING  COMMENT = 'Terminal views. Privacy policy attaches here only.';
CREATE SCHEMA IF NOT EXISTS ORACLE   COMMENT = 'Mint queue and mint log. Written by the bridge.';

DROP SCHEMA IF EXISTS GLASSPOCKET.PUBLIC;

-- ---------------------------------------------------------------------
-- Retention. Enterprise Edition allows up to 90 days of Time Travel.
-- Tab 07 reads its hero figure from this value rather than hard-coding it.
-- ---------------------------------------------------------------------
ALTER DATABASE GLASSPOCKET SET DATA_RETENTION_TIME_IN_DAYS = 90;

-- ---------------------------------------------------------------------
-- The analyst persona. The application connects as this role on Tab 05
-- so the privacy policy actually applies. It must never be granted the
-- privileges that would let it read the unprotected twin.
-- ---------------------------------------------------------------------
CREATE ROLE IF NOT EXISTS GP_ANALYST
  COMMENT = 'Public analyst persona. Reads only privacy-protected serving views.';

GRANT USAGE ON WAREHOUSE GP_WH        TO ROLE GP_ANALYST;
GRANT USAGE ON DATABASE GLASSPOCKET   TO ROLE GP_ANALYST;
GRANT USAGE ON SCHEMA GLASSPOCKET.SERVING TO ROLE GP_ANALYST;
GRANT USAGE ON SCHEMA GLASSPOCKET.MARTS   TO ROLE GP_ANALYST;

-- The application runs as the current user inside Snowflake; give that
-- user the ability to assume the analyst persona for the Tab 05 demo.
SET current_user_name = CURRENT_USER();
GRANT ROLE GP_ANALYST TO USER IDENTIFIER($current_user_name);

-- ---------------------------------------------------------------------
-- TRAP 04 / MANUAL STEP, DO IT NOW
-- st.map and st.pydeck_chart draw tiles from Carto, a third-party
-- offering. Accept External Offerings Terms in Snowsight
-- (Admin > Billing & Terms > Enable) within the first ten minutes of the
-- build. If you skip it, Tab 03 renders an empty canvas with no error.
-- ---------------------------------------------------------------------
SELECT 'Accept External Offerings Terms in Snowsight now. See Trap 04.' AS reminder;

SHOW PARAMETERS LIKE 'DATA_RETENTION_TIME_IN_DAYS' IN DATABASE GLASSPOCKET;
