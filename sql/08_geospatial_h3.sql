-- =====================================================================
-- GLASSPOCKET / 08_geospatial_h3.sql
-- H3 geospatial diversion detection. Build Spec Section 06.4.
--
-- Acceptance criteria, Snowflake surface:
--   "At least four distinct H3 or geospatial functions appear in
--    production queries."
--
-- Used here and in 02/03:
--   H3_LATLNG_TO_CELL_STRING   index a point at a resolution
--   H3_CELL_TO_PARENT          coarsen a delivery cell to footprint scale
--   H3_GRID_DISTANCE           grid steps between two cells
--   H3_GRID_DISK               the plausible operating footprint
--   H3_CELL_TO_POINT           cell centroid, for the drill-down
--   ST_POINT / ST_DISTANCE     straight-line metres between coordinates
-- =====================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE GP_WH;
USE DATABASE GLASSPOCKET;

CREATE OR REPLACE TABLE MARTS.DELIVERY_GEOMETRY AS
SELECT
  d.disbursement_id,
  d.org_id,
  d.district,
  d.amount_usd,
  d.pledged_usd,
  d.status,
  d.delivery_h3,
  d.lat,
  d.lon,
  d.dispatched_at,
  d.delivered_at,
  o.name                                                       AS org_name,
  o.is_synthetic,
  o.home_h3,
  H3_GRID_DISTANCE(o.home_h3, H3_CELL_TO_PARENT(d.delivery_h3, 5)) AS hops,
  o.max_hops,
  ST_DISTANCE(ST_POINT(o.lon, o.lat), ST_POINT(d.lon, d.lat)) / 1000 AS km_from_base,
  DATEDIFF('hour', d.dispatched_at, d.delivered_at)            AS transit_hours,
  CASE
    WHEN d.status = 'UNACCOUNTED' THEN 'NEVER_ARRIVED'
    WHEN H3_GRID_DISTANCE(o.home_h3, H3_CELL_TO_PARENT(d.delivery_h3, 5)) > o.max_hops
      THEN 'OUTSIDE_FOOTPRINT'
    WHEN DATEDIFF('hour', d.dispatched_at, d.delivered_at) < 1
     AND ST_DISTANCE(ST_POINT(o.lon, o.lat), ST_POINT(d.lon, d.lat)) > 400000
      THEN 'IMPOSSIBLE_TRANSIT'
    ELSE 'PLAUSIBLE'
  END                                                          AS geometry_verdict
FROM STAGING.DISBURSEMENTS d
JOIN STAGING.ORGS o USING (org_id);

-- ---------------------------------------------------------------------
-- The plausible operating footprint, as cells rather than as a radius.
-- H3_GRID_DISK is what makes "outside footprint" a statement about the
-- grid rather than about a circle drawn on a projection.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE MARTS.ORG_FOOTPRINT AS
SELECT
  o.org_id,
  o.home_h3,
  o.max_hops,
  ARRAY_SIZE(H3_GRID_DISK(o.home_h3, LEAST(o.max_hops, 12))) AS footprint_cells
FROM STAGING.ORGS o
WHERE o.home_h3 IS NOT NULL;

-- ---------------------------------------------------------------------
-- Hex aggregation that feeds the pydeck layer directly.
-- Section 06.4. Tab 03, C03-1.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW SERVING.V_HEX_RISK AS
SELECT
  delivery_h3                                                       AS h3,
  COUNT(*)                                                          AS n,
  SUM(amount_usd)                                                   AS usd,
  AVG(CASE WHEN geometry_verdict <> 'PLAUSIBLE' THEN 1 ELSE 0 END)  AS flag_rate,
  ANY_VALUE(district)                                               AS district,
  ST_Y(H3_CELL_TO_POINT(delivery_h3))                               AS centroid_lat,
  ST_X(H3_CELL_TO_POINT(delivery_h3))                               AS centroid_lon
FROM MARTS.DELIVERY_GEOMETRY
GROUP BY delivery_h3;

-- ---------------------------------------------------------------------
-- Verdict composition, Tab 03 section S5. Four segments, centre of the
-- donut carries value at risk.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW SERVING.V_VERDICT_COMPOSITION AS
SELECT
  geometry_verdict,
  COUNT(*)          AS events,
  SUM(amount_usd)   AS usd,
  DIV0(COUNT(*), (SELECT COUNT(*) FROM MARTS.DELIVERY_GEOMETRY)) AS share
FROM MARTS.DELIVERY_GEOMETRY
GROUP BY geometry_verdict;

-- ---------------------------------------------------------------------
-- Transit feasibility, Tab 04 C04-2. A truck cannot cover four hundred
-- kilometres in under an hour. The shaded region below the plausible
-- speed line is computed here rather than drawn by eye.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW SERVING.V_TRANSIT_FEASIBILITY AS
SELECT
  disbursement_id,
  org_id,
  district,
  km_from_base,
  transit_hours,
  amount_usd,
  geometry_verdict,
  DIV0(km_from_base, NULLIF(transit_hours, 0)) AS implied_kmh,
  DIV0(km_from_base, NULLIF(transit_hours, 0)) > 90 AS exceeds_plausible_speed
FROM MARTS.DELIVERY_GEOMETRY
WHERE transit_hours IS NOT NULL
  AND km_from_base  IS NOT NULL;

INSERT INTO MARTS.BUILD_LOG (step, detail)
SELECT '08_geospatial_h3',
       'geometry rows: ' || COUNT(*)::STRING
    || ', verdict classes: ' || COUNT(DISTINCT geometry_verdict)::STRING
FROM MARTS.DELIVERY_GEOMETRY;

-- Exit condition for the Saturday midday block: verdicts distributed
-- across all four categories, not piled into one.
SELECT geometry_verdict, COUNT(*) AS events, SUM(amount_usd) AS usd
FROM MARTS.DELIVERY_GEOMETRY
GROUP BY 1
ORDER BY events DESC;
