"""Every SQL statement the application executes, in one place.

Build Spec Section 04, CONVENTION:

    Every SQL statement the application executes lives as a named constant
    in app/queries.py. No inline SQL inside a tab module. This makes it
    possible to run the entire query surface headlessly during acceptance
    testing, and it makes the write-up easy because the SQL is quotable
    from one file.

Two rules hold for everything below.

  * Nothing heavier than a single indexed SELECT. Every embedding,
    similarity pair, geospatial join and blockchain asset identifier is
    already materialised by the numbered SQL files. No AI function, no
    embedding call and no unbounded scan appears here.

  * Every statement that can return many rows carries an explicit LIMIT.
    Streamlit in Snowflake caps a single backend-to-frontend transfer at
    32 MB (Trap 07), and an unbounded dataframe will hit it.

Each entry in QUERIES maps a key to the Snowflake SQL and to the table
that answers the same question in the local preview store, so a tab module
never needs to know which one it is talking to.
"""

from __future__ import annotations

from dataclasses import dataclass

DATABASE = "GLASSPOCKET"
ANALYST_ROLE = "GP_ANALYST"
SIMILARITY_THRESHOLD = 0.94
EXPLORER_BASE = "https://explorer.solana.com"
EXPLORER_CLUSTER = "devnet"


@dataclass(frozen=True)
class Query:
    """One question, answered two ways.

    ``sql`` is the statement that runs against Snowflake and is the one
    quoted in the write-up. ``local`` names the equivalent relation in the
    preview store; see app/data.py.
    """

    sql: str
    local: str
    note: str = ""


# ===========================================================================
# TAB 00 / The Brief
# ===========================================================================

Q_KPI = Query(
    sql="SELECT * FROM SERVING.V_KPI",
    local="""
        SELECT
          (SELECT COUNT(*) FROM staging_orgs)            AS orgs_indexed,
          (SELECT COUNT(*) FROM staging_disbursements)   AS disbursements_traced,
          (SELECT COUNT(*) FROM mint_log)                AS receipts_on_chain,
          (SELECT COUNT(*) FROM org_risk
            WHERE verdict = 'needs a second look')       AS needs_second_look,
          6                                              AS pipeline_objects_fresh
    """,
    note="Five live counts. The fifth quietly advertises the Dynamic Table layer.",
)

Q_PIPELINE_HEALTH = Query(
    sql="""
        SELECT object_name, short_name, state, refresh_end_time,
               seconds_since_refresh, target_lag_seconds, within_lag
        FROM SERVING.V_PIPELINE_HEALTH
        ORDER BY seconds_since_refresh DESC
        LIMIT 20
    """,
    local="""
        SELECT * FROM (VALUES
            ('STAGING.DT_ORG_ENRICHED',      'dt_org_enriched',      12, 60, TRUE),
            ('MARTS.DT_ORG_ACTIVITY',        'dt_org_activity',      41, 60, TRUE),
            ('MARTS.DT_ATTRITION_STAGES',    'dt_attrition_stages',   8, 60, TRUE),
            ('MARTS.DT_DISTRICT_ATTRITION',  'dt_district_attrition',27, 60, TRUE),
            ('MARTS.DT_CAUSE_EXPOSURE',      'dt_cause_exposure',    19, 60, TRUE),
            ('MARTS.BENEFICIARY_FACTS',      'beneficiary_facts',    34, 60, TRUE),
            ('MARTS.DT_RECEIPT_COVERAGE',    'dt_receipt_coverage',  52, 60, TRUE)
        ) AS t(object_name, short_name, seconds_since_refresh,
               target_lag_seconds, within_lag)
        ORDER BY seconds_since_refresh DESC
    """,
    note="Refresh age against TARGET_LAG, one bar per Dynamic Table.",
)

Q_EVIDENCE = Query(
    sql="""
        SELECT citation_id, claim, figure, magnitude, unit_type, region,
               issuing_body, published_on, url
        FROM MARTS.EVIDENCE_CITATIONS
        ORDER BY published_on
        LIMIT 20
    """,
    local="SELECT * FROM evidence_citations ORDER BY published_on LIMIT 20",
    note="Hand-entered in sql/04. Never computed, so it cannot drift.",
)


# ===========================================================================
# TAB 01 / Give With Confidence
# ===========================================================================

Q_CONFIDENCE_PAIRS = Query(
    sql="""
        SELECT suspect_id, suspect_name, suspect_blurb, suspect_city,
               suspect_state, suspect_cause,
               target_id, target_name, target_blurb, target_city,
               target_state, target_cause,
               semantic_sim, string_sim, evasion_gap, synth_technique
        FROM SERVING.V_CONFIDENCE_PAIRS
        ORDER BY evasion_gap DESC
        LIMIT 200
    """,
    local="""
        SELECT
          c.suspect_id, c.suspect_name,
          s.blurb AS suspect_blurb, s.city AS suspect_city,
          s.state AS suspect_state, s.cause AS suspect_cause,
          c.target_id, c.target_name,
          t.blurb AS target_blurb, t.city AS target_city,
          t.state AS target_state, t.cause AS target_cause,
          c.semantic_sim, c.string_sim, c.evasion_gap, c.synth_technique
        FROM clone_confirmed c
        JOIN staging_orgs s ON s.org_id = c.suspect_id
        JOIN staging_orgs t ON t.org_id = c.target_id
        WHERE s.is_synthetic AND NOT t.is_synthetic AND t.is_verified
        ORDER BY c.evasion_gap DESC
        LIMIT 200
    """,
    note="Suspect side is always seeded, target side always a real org in good standing.",
)

Q_ORG_RISK_ONE = Query(
    sql="""
        SELECT org_id, name, risk_score, verdict,
               comp_semantic, comp_evasion, comp_geometry,
               comp_unaccounted, comp_receipts,
               semantic_sim, evasion_gap, geom_flags,
               unaccounted_ratio, missing_receipts
        FROM MARTS.ORG_RISK
        WHERE org_id = ?
    """,
    local="""
        SELECT org_id, name, risk_score, verdict,
               comp_semantic, comp_evasion, comp_geometry,
               comp_unaccounted, comp_receipts,
               semantic_sim, evasion_gap, geom_flags,
               unaccounted_ratio, missing_receipts
        FROM org_risk WHERE org_id = ?
    """,
    note="The five components, so the waterfall reconstructs the total by eye.",
)

Q_PROJECTION = Query(
    sql="""
        SELECT org_id, name, cause, is_synthetic, is_verified, pc1, pc2
        FROM SERVING.V_ORG_PROJECTION
        WHERE cause = ?
        LIMIT 1500
    """,
    local="""
        SELECT p.org_id, o.name, o.cause, o.is_synthetic, o.is_verified,
               p.pc1, p.pc2
        FROM org_projection p
        JOIN staging_orgs o USING (org_id)
        WHERE o.cause = ?
        LIMIT 1500
    """,
    note="Offline PCA. Do not attempt UMAP in the warehouse runtime.",
)


# ===========================================================================
# TAB 02 / The Trust Graph
# ===========================================================================

Q_GRAPH_NODES = Query(
    sql="""
        SELECT org_id, name, x, y, node_kind, degree, cause, city, state, ein
        FROM SERVING.V_GRAPH
        LIMIT 1200
    """,
    local="""
        SELECT n.org_id, n.name, n.x, n.y, n.node_kind, n.degree,
               o.cause, o.city, o.state, o.ein
        FROM graph_nodes n
        JOIN staging_orgs o USING (org_id)
        LIMIT 1200
    """,
)

Q_GRAPH_EDGES = Query(
    sql="""
        SELECT source_id, target_id, similarity,
               source_x, source_y, target_x, target_y
        FROM SERVING.V_GRAPH_EDGES
        LIMIT 2000
    """,
    local="""
        SELECT e.source_id, e.target_id, e.similarity,
               ns.x AS source_x, ns.y AS source_y,
               nt.x AS target_x, nt.y AS target_y
        FROM graph_edges e
        JOIN graph_nodes ns ON ns.org_id = e.source_id
        JOIN graph_nodes nt ON nt.org_id = e.target_id
        LIMIT 2000
    """,
)

Q_GRAPH_SUMMARY = Query(
    sql="""
        SELECT COUNT(*)                              AS pairs_detected,
               COUNT(DISTINCT target_id)             AS targets_affected,
               AVG(semantic_sim)                     AS mean_similarity,
               AVG(evasion_gap)                      AS mean_evasion_gap,
               COUNT(DISTINCT cause)                 AS causes_affected
        FROM MARTS.CLONE_PAIRS
    """,
    local="""
        SELECT COUNT(*)                  AS pairs_detected,
               COUNT(DISTINCT target_id) AS targets_affected,
               AVG(semantic_sim)         AS mean_similarity,
               AVG(evasion_gap)          AS mean_evasion_gap,
               COUNT(DISTINCT cause)     AS causes_affected
        FROM clone_pairs
    """,
)

Q_CAUSE_EXPOSURE = Query(
    sql="""
        SELECT cause, verified_orgs, seeded_orgs, imitations_per_100
        FROM MARTS.DT_CAUSE_EXPOSURE
        WHERE seeded_orgs > 0
        ORDER BY imitations_per_100 DESC
        LIMIT 12
    """,
    local="""
        SELECT cause,
               COUNT(*) FILTER (WHERE is_verified AND NOT is_synthetic) AS verified_orgs,
               COUNT(*) FILTER (WHERE is_synthetic)                     AS seeded_orgs,
               100.0 * COUNT(*) FILTER (WHERE is_synthetic)
                 / NULLIF(COUNT(*) FILTER (WHERE is_verified AND NOT is_synthetic), 0)
                                                                        AS imitations_per_100
        FROM staging_orgs
        GROUP BY cause
        HAVING COUNT(*) FILTER (WHERE is_synthetic) > 0
        ORDER BY imitations_per_100 DESC
        LIMIT 12
    """,
)

Q_TECHNIQUE_BREAKDOWN = Query(
    sql="""
        SELECT technique, pairs_detected, mean_semantic_sim,
               mean_string_sim, mean_evasion_gap
        FROM MARTS.V_TECHNIQUE_BREAKDOWN
        LIMIT 10
    """,
    local="""
        SELECT COALESCE(synth_technique, 'unrecorded') AS technique,
               COUNT(*)             AS pairs_detected,
               AVG(semantic_sim)    AS mean_semantic_sim,
               AVG(string_sim)      AS mean_string_sim,
               AVG(evasion_gap)     AS mean_evasion_gap
        FROM clone_pairs
        GROUP BY 1
        ORDER BY pairs_detected DESC
    """,
    note="Honest, because the tactic is known by construction.",
)

Q_THRESHOLD_CURVE = Query(
    sql="""
        SELECT threshold, pairs_detected, pairs_ai_confirmed, is_production_value
        FROM MARTS.THRESHOLD_CURVE
        ORDER BY threshold
        LIMIT 40
    """,
    local="SELECT * FROM threshold_curve ORDER BY threshold LIMIT 40",
    note="Precomputed sweep, so the slider responds with no query behind it.",
)

Q_THRESHOLD_CALIBRATION = Query(
    sql="""
        SELECT threshold, pairs_detected, true_pairs,
               precision_at, recall_at, is_production_value
        FROM MARTS.THRESHOLD_CALIBRATION
        ORDER BY threshold
        LIMIT 40
    """,
    local="""
        SELECT threshold, pairs_detected,
               pairs_ai_confirmed AS true_pairs,
               NULL AS precision_at, NULL AS recall_at,
               is_production_value
        FROM threshold_curve ORDER BY threshold LIMIT 40
    """,
    note=(
        "Precision and recall against ground truth, because every seeded "
        "organisation records the real one it was built from. This is what "
        "justifies the cut-off rather than asserting it."
    ),
)

Q_NODE_DETAIL = Query(
    sql="""
        SELECT o.org_id, o.name, o.ein, o.city, o.state, o.cause,
               r.risk_score, r.verdict, r.is_synthetic,
               (SELECT COUNT(*) FROM MARTS.CLONE_PAIRS p
                 WHERE p.target_id = o.org_id) AS imitations_pointing_at_it
        FROM STAGING.ORGS o
        LEFT JOIN MARTS.ORG_RISK r USING (org_id)
        WHERE o.org_id = ?
    """,
    local="""
        SELECT o.org_id, o.name, o.ein, o.city, o.state, o.cause,
               r.risk_score, r.verdict, o.is_synthetic,
               (SELECT COUNT(*) FROM clone_pairs p
                 WHERE p.target_id = o.org_id) AS imitations_pointing_at_it
        FROM staging_orgs o
        LEFT JOIN org_risk r USING (org_id)
        WHERE o.org_id = ?
    """,
)


# ===========================================================================
# TAB 03 / Follow The Money
# ===========================================================================

Q_HEX_RISK = Query(
    sql="""
        SELECT h3, n, usd, flag_rate, district, centroid_lat, centroid_lon
        FROM SERVING.V_HEX_RISK
        ORDER BY usd DESC
        LIMIT 4000
    """,
    local="""
        SELECT delivery_h3 AS h3,
               COUNT(*)        AS n,
               SUM(amount_usd) AS usd,
               AVG(CASE WHEN geometry_verdict <> 'PLAUSIBLE' THEN 1 ELSE 0 END) AS flag_rate,
               ANY_VALUE(district) AS district,
               AVG(lat) AS centroid_lat,
               AVG(lon) AS centroid_lon
        FROM delivery_geometry
        GROUP BY delivery_h3
        ORDER BY usd DESC
        LIMIT 4000
    """,
    note="Feeds the pydeck H3HexagonLayer directly.",
)

Q_GEOMETRY_KPI = Query(
    sql="""
        SELECT COUNT(*)                                                AS events,
               COUNT(DISTINCT delivery_h3)                             AS cells,
               SUM(amount_usd)                                         AS usd_traced,
               COUNT_IF(geometry_verdict = 'OUTSIDE_FOOTPRINT')        AS outside_footprint,
               COUNT_IF(geometry_verdict = 'IMPOSSIBLE_TRANSIT')       AS impossible_transit,
               COUNT_IF(geometry_verdict <> 'PLAUSIBLE') / COUNT(*)    AS implausible_share
        FROM MARTS.DELIVERY_GEOMETRY
    """,
    local="""
        SELECT COUNT(*)                        AS events,
               COUNT(DISTINCT delivery_h3)     AS cells,
               SUM(amount_usd)                 AS usd_traced,
               COUNT(*) FILTER (WHERE geometry_verdict = 'OUTSIDE_FOOTPRINT')  AS outside_footprint,
               COUNT(*) FILTER (WHERE geometry_verdict = 'IMPOSSIBLE_TRANSIT') AS impossible_transit,
               CAST(COUNT(*) FILTER (WHERE geometry_verdict <> 'PLAUSIBLE') AS DOUBLE)
                 / COUNT(*)                    AS implausible_share
        FROM delivery_geometry
    """,
)

Q_VERDICT_COMPOSITION = Query(
    sql="""
        SELECT geometry_verdict, events, usd, share
        FROM SERVING.V_VERDICT_COMPOSITION
        ORDER BY events DESC
        LIMIT 10
    """,
    local="""
        SELECT geometry_verdict,
               COUNT(*)        AS events,
               SUM(amount_usd) AS usd,
               CAST(COUNT(*) AS DOUBLE)
                 / (SELECT COUNT(*) FROM delivery_geometry) AS share
        FROM delivery_geometry
        GROUP BY geometry_verdict
        ORDER BY events DESC
        LIMIT 10
    """,
)

Q_DISTANCE_HISTOGRAM = Query(
    sql="""
        SELECT km_from_base, geometry_verdict
        FROM MARTS.DELIVERY_GEOMETRY
        WHERE km_from_base IS NOT NULL
        LIMIT 12000
    """,
    local="""
        SELECT km_from_base, geometry_verdict
        FROM delivery_geometry
        WHERE km_from_base IS NOT NULL
        LIMIT 12000
    """,
)

Q_CELL_DRILLDOWN = Query(
    sql="""
        SELECT disbursement_id, org_name, district, amount_usd, status,
               ROUND(km_from_base, 1) AS km_from_base, hops, max_hops,
               transit_hours, geometry_verdict
        FROM MARTS.DELIVERY_GEOMETRY
        WHERE delivery_h3 = ?
        ORDER BY amount_usd DESC
        LIMIT 50
    """,
    local="""
        SELECT disbursement_id, org_name, district, amount_usd, status,
               ROUND(km_from_base, 1) AS km_from_base, hops, max_hops,
               transit_hours, geometry_verdict
        FROM delivery_geometry
        WHERE delivery_h3 = ?
        ORDER BY amount_usd DESC
        LIMIT 50
    """,
    note="Hard limit 50. Trap 07.",
)


# ===========================================================================
# TAB 04 / The Last Mile
# ===========================================================================

Q_ATTRITION_FLOW = Query(
    sql="""
        SELECT pledged_usd, dispatched_usd, delivered_usd, unaccounted_usd,
               never_dispatched_usd, events, delivery_rate
        FROM SERVING.V_ATTRITION_FLOW
    """,
    local="""
        WITH s AS (
          SELECT
            SUM(pledged_usd) AS pledged_usd,
            SUM(CASE WHEN status IN ('DISPATCHED','DELIVERED','UNACCOUNTED')
                     THEN amount_usd ELSE 0 END) AS dispatched_usd,
            SUM(CASE WHEN status = 'DELIVERED'   THEN amount_usd ELSE 0 END) AS delivered_usd,
            SUM(CASE WHEN status = 'UNACCOUNTED' THEN amount_usd ELSE 0 END) AS unaccounted_usd,
            COUNT(*) AS events
          FROM staging_disbursements
        )
        SELECT pledged_usd, dispatched_usd, delivered_usd, unaccounted_usd,
               GREATEST(0, pledged_usd - dispatched_usd) AS never_dispatched_usd,
               events,
               delivered_usd / NULLIF(dispatched_usd, 0) AS delivery_rate
        FROM s
    """,
)

Q_TRANSIT_FEASIBILITY = Query(
    sql="""
        SELECT disbursement_id, district, km_from_base, transit_hours,
               amount_usd, geometry_verdict, implied_kmh, exceeds_plausible_speed
        FROM SERVING.V_TRANSIT_FEASIBILITY
        LIMIT 8000
    """,
    local="""
        SELECT disbursement_id, district, km_from_base, transit_hours,
               amount_usd, geometry_verdict,
               km_from_base / NULLIF(transit_hours, 0) AS implied_kmh,
               (km_from_base / NULLIF(transit_hours, 0)) > 90 AS exceeds_plausible_speed
        FROM delivery_geometry
        WHERE transit_hours IS NOT NULL AND km_from_base IS NOT NULL
        LIMIT 8000
    """,
)

Q_DISTRICT_ATTRITION = Query(
    sql="""
        SELECT district, events, moved_usd, delivered_usd,
               attrition_rate, mean_transit_hours
        FROM SERVING.V_DISTRICT_ATTRITION
        ORDER BY attrition_rate DESC
        LIMIT 30
    """,
    local="""
        SELECT district,
               COUNT(*)        AS events,
               SUM(amount_usd) AS moved_usd,
               SUM(CASE WHEN status = 'DELIVERED' THEN amount_usd ELSE 0 END) AS delivered_usd,
               SUM(CASE WHEN status <> 'DELIVERED' THEN amount_usd ELSE 0 END)
                 / NULLIF(SUM(amount_usd), 0) AS attrition_rate,
               AVG(DATE_DIFF('hour', dispatched_at, delivered_at)) AS mean_transit_hours
        FROM staging_disbursements
        WHERE district IS NOT NULL
        GROUP BY district
        ORDER BY attrition_rate DESC
        LIMIT 30
    """,
    note="Clicking a bar carries the district into Tab 05.",
)


# ===========================================================================
# TAB 05 / The Wall
# ===========================================================================
#
# The two statements below are the whole point of the tab. They are
# identical except for the object they read, and that is the entire
# difference between an answer that protects a person and one that does
# not. The protected side runs as GP_ANALYST so the policy applies.

Q_BENEFICIARY_PRIVATE = Query(
    sql="""
        SELECT COUNT(*) AS cohort, SUM(amount_usd) AS total_usd,
               AVG(delivered_flag) AS delivery_rate
        FROM SERVING.V_BENEFICIARY_OUTCOMES
        WHERE (? IS NULL OR district       = ?)
          AND (? IS NULL OR programme_code = ?)
          AND (? IS NULL OR month_key      = ?)
          AND (? IS NULL OR amount_usd BETWEEN ? AND ?)
    """,
    local="beneficiary_facts",
    note="Runs as GP_ANALYST. Differential privacy noise is applied by the policy.",
)

Q_BENEFICIARY_TRUE = Query(
    sql="""
        SELECT COUNT(*) AS cohort, SUM(amount_usd) AS total_usd,
               AVG(delivered_flag) AS delivery_rate
        FROM PRIVILEGED.V_BENEFICIARY_OUTCOMES_TRUE
        WHERE (? IS NULL OR district       = ?)
          AND (? IS NULL OR programme_code = ?)
          AND (? IS NULL OR month_key      = ?)
          AND (? IS NULL OR amount_usd BETWEEN ? AND ?)
    """,
    local="beneficiary_facts",
    note="COUNTERFACTUAL ONLY. Privileged role. Never granted to GP_ANALYST.",
)

Q_COHORT_FLOOR = Query(
    sql="""
        SELECT min_group_size, mechanism, guarantee_label, guarantee_note
        FROM SERVING.V_COHORT_FLOOR
        LIMIT 1
    """,
    local="""
        SELECT 50 AS min_group_size,
               'AGGREGATION_POLICY' AS mechanism,
               'minimum cohort guarantee' AS guarantee_label,
               'Snowflake refuses any aggregate over fewer than fifty '
               || 'beneficiaries. This is k-anonymity, not differential '
               || 'privacy: it adds no noise and has no query budget.'
                 AS guarantee_note
    """,
    note=(
        "The differential privacy DDL does not parse on this deployment, so "
        "Tab 05 ships against an aggregation policy with a minimum group "
        "size. Section 10's documented fallback. See "
        "docs/platform_constraints.md."
    ),
)

Q_FILTER_OPTIONS = Query(
    sql="""
        SELECT DISTINCT district, programme_code, month_key
        FROM MARTS.BENEFICIARY_FACTS
        LIMIT 500
    """,
    local="SELECT DISTINCT district, programme_code, month_key FROM beneficiary_facts",
)


# ===========================================================================
# TAB 06 / The Receipt
# ===========================================================================

Q_RECEIPT_KPI = Query(
    sql="""
        SELECT (SELECT COUNT(*) FROM ORACLE.MINT_LOG)             AS receipts_on_chain,
               (SELECT MAX(cum_gap) FROM SERVING.V_RECEIPT_GAP)   AS receipts_missing
    """,
    local="""
        SELECT (SELECT COUNT(*) FROM mint_log) AS receipts_on_chain,
               (SELECT SUM(receipts_missing) FROM receipt_coverage) AS receipts_missing
    """,
)

Q_TREE_STATE = Query(
    sql="""
        SELECT tree_address, leaves_used, capacity, capacity_remaining,
               cluster, last_mint_at
        FROM SERVING.V_TREE_STATE
    """,
    local="""
        SELECT ANY_VALUE(tree_address) AS tree_address,
               COUNT(*)                AS leaves_used,
               16384                   AS capacity,
               16384 - COUNT(*)        AS capacity_remaining,
               'devnet'                AS cluster,
               MAX(minted_at)          AS last_mint_at
        FROM mint_log
    """,
    note="maxDepth 14 gives 16,384 leaves. Tree parameters are immutable.",
)

Q_RECEIPT_LOOKUP = Query(
    sql="""
        SELECT asset_id, signature, tree_address, leaf_index, minted_at,
               explorer_url, programme_code, amount_band, window_key, org_hash
        FROM SERVING.V_RECEIPT_LOOKUP
        WHERE asset_id = ?
        LIMIT 1
    """,
    local="""
        SELECT m.asset_id, m.signature, m.tree_address, m.leaf_index,
               m.minted_at, m.explorer_url,
               q.programme_code, q.amount_band, q.window_key, q.org_hash
        FROM mint_log m
        JOIN mint_queue q USING (disbursement_id)
        WHERE m.asset_id = ?
        LIMIT 1
    """,
    note="Reads the local mirror. Never calls an RPC from a render path.",
)

Q_RECEIPT_GAP = Query(
    sql="""
        SELECT day, expected_receipts, actual_receipts,
               cum_expected, cum_actual, cum_gap
        FROM SERVING.V_RECEIPT_GAP
        ORDER BY day
        LIMIT 400
    """,
    local="""
        WITH expected AS (
          SELECT CAST(DATE_TRUNC('day', COALESCE(delivered_at, dispatched_at)) AS DATE) AS day,
                 COUNT(*) AS expected_receipts
          FROM staging_disbursements
          WHERE status IN ('DELIVERED', 'UNACCOUNTED')
          GROUP BY 1
        ),
        actual AS (
          SELECT CAST(DATE_TRUNC('day', minted_at) AS DATE) AS day,
                 COUNT(*) AS actual_receipts
          FROM mint_log GROUP BY 1
        ),
        days AS (
          SELECT day FROM expected UNION SELECT day FROM actual
        )
        SELECT d.day,
               COALESCE(e.expected_receipts, 0) AS expected_receipts,
               COALESCE(a.actual_receipts, 0)   AS actual_receipts,
               SUM(COALESCE(e.expected_receipts, 0)) OVER (ORDER BY d.day) AS cum_expected,
               SUM(COALESCE(a.actual_receipts, 0))   OVER (ORDER BY d.day) AS cum_actual,
               SUM(COALESCE(e.expected_receipts, 0)) OVER (ORDER BY d.day)
                 - SUM(COALESCE(a.actual_receipts, 0)) OVER (ORDER BY d.day) AS cum_gap
        FROM days d
        LEFT JOIN expected e ON e.day = d.day
        LEFT JOIN actual   a ON a.day = d.day
        ORDER BY d.day
        LIMIT 400
    """,
)

Q_MINT_ACTIVITY = Query(
    sql="""
        SELECT m.asset_id, m.minted_at, q.amount_band
        FROM ORACLE.MINT_LOG m
        JOIN ORACLE.MINT_QUEUE q USING (disbursement_id)
        ORDER BY m.minted_at
        LIMIT 3000
    """,
    local="""
        SELECT asset_id, minted_at, amount_band
        FROM mint_log
        ORDER BY minted_at
        LIMIT 3000
    """,
)

Q_SAMPLE_ASSET = Query(
    sql="SELECT asset_id FROM ORACLE.MINT_LOG ORDER BY minted_at DESC LIMIT 1",
    local="SELECT asset_id FROM mint_log ORDER BY minted_at DESC LIMIT 1",
)


# ===========================================================================
# TAB 07 / The Historian
# ===========================================================================
#
# Time Travel as tamper evidence. The mechanic is to update a row, then
# query the same row as it existed before the update, and show both.

Q_RETENTION = Query(
    sql="""
        SELECT RETENTION_TIME AS retention_days
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = 'MARTS' AND TABLE_NAME = 'ORG_RISK'
    """,
    local="SELECT 90 AS retention_days",
)

Q_TIME_TRAVEL = Query(
    sql="""
        SELECT 'current' AS version, org_id, name, risk_score, verdict
        FROM MARTS.ORG_RISK WHERE org_id = ?
        UNION ALL
        SELECT 'before', org_id, name, risk_score, verdict
        FROM MARTS.ORG_RISK AT(OFFSET => -300) WHERE org_id = ?
    """,
    local="__time_travel__",
    note="AT(OFFSET) needs no additional storage. Snowflake internal retention.",
)

Q_APPLY_CHANGE = Query(
    sql="UPDATE MARTS.ORG_RISK SET risk_score = ?, verdict = ? WHERE org_id = ?",
    local="__apply_change__",
    note="Demo mode only. A production deployment would not expose this.",
)


# ===========================================================================
# TAB 08 / Ask The Warehouse
# ===========================================================================

Q_SEMANTIC_SHAPE = Query(
    sql="""
        SELECT COUNT(DISTINCT table_name) AS tables,
               COUNT(DISTINCT CASE WHEN kind = 'DIMENSION' THEN name END) AS dimensions,
               COUNT(DISTINCT CASE WHEN kind = 'METRIC'    THEN name END) AS metrics,
               SUM(ARRAY_SIZE(COALESCE(synonyms, ARRAY_CONSTRUCT()))) AS synonyms
        FROM MARTS.V_SEMANTIC_SHAPE
    """,
    local="""
        SELECT 2 AS tables, 6 AS dimensions, 4 AS metrics, 19 AS synonyms
    """,
    note="Counted from the object, never typed into the interface.",
)

Q_ASK_CAUSE_IMITATION = Query(
    sql="""
        SELECT cause, verified_orgs, seeded_orgs, imitations_per_100
        FROM SERVING.V_ASK_CAUSE_IMITATION
        LIMIT 12
    """,
    local=Q_CAUSE_EXPOSURE.local,
)

Q_ASK_FLAGGED_BY_STATE = Query(
    sql="""
        SELECT state, flagged_pct, event_count
        FROM SERVING.V_ASK_FLAGGED_BY_STATE
        LIMIT 25
    """,
    local="""
        SELECT o.state,
               AVG(CASE WHEN g.geometry_verdict <> 'PLAUSIBLE' THEN 1.0 ELSE 0.0 END)
                 AS flagged_pct,
               COUNT(*) AS event_count
        FROM delivery_geometry g
        JOIN staging_orgs o USING (org_id)
        GROUP BY o.state
        HAVING COUNT(*) > 20
        ORDER BY flagged_pct DESC
        LIMIT 25
    """,
)

Q_ASK_TOTAL_MOVED = Query(
    sql="""
        SELECT quarter, total_usd, events
        FROM SERVING.V_ASK_TOTAL_MOVED
        LIMIT 24
    """,
    local="""
        SELECT STRFTIME(DATE_TRUNC('quarter', dispatched_at), '%Y-Q') ||
               CAST(QUARTER(dispatched_at) AS VARCHAR) AS quarter,
               SUM(amount_usd) AS total_usd,
               COUNT(*)        AS events
        FROM delivery_geometry
        WHERE dispatched_at IS NOT NULL
        GROUP BY 1
        ORDER BY 1
        LIMIT 24
    """,
)


# ===========================================================================
# TAB 09 / Where A Dollar Lands
# ===========================================================================
#
# THE ONLY TAB WITH ZERO SYNTHETIC CONTENT.

Q_CONFIDENCE_RANK = Query(
    sql="""
        SELECT org_id, ein, name, city, state, cause, blurb,
               delivery_rate, receipt_coverage, value_moved_usd,
               disbursements, confidence
        FROM SERVING.V_CONFIDENCE_RANK
        WHERE (? IS NULL OR cause = ?)
          AND (? IS NULL OR state = ?)
          AND receipt_coverage >= ?
        ORDER BY confidence DESC
        LIMIT 400
    """,
    # Mirrors SERVING.V_CONFIDENCE_RANK exactly, including which table
    # each column comes from: the activity figures live on the Dynamic
    # Table, not on ORG_RISK, and the preview has to agree or the two
    # backends would disagree about what confidence means.
    local="""
        SELECT o.org_id, o.ein, o.name, o.city, o.state, o.cause, o.blurb,
               COALESCE(a.delivery_rate, 0)    AS delivery_rate,
               COALESCE(r.receipt_coverage, 0) AS receipt_coverage,
               COALESCE(a.moved_usd, 0)        AS value_moved_usd,
               COALESCE(a.disbursements, 0)    AS disbursements,
               ROUND(60 * COALESCE(a.delivery_rate, 0)
                   + 40 * COALESCE(r.receipt_coverage, 0)
                   - COALESCE(rk.risk_score, 0) * 0.5, 1) AS confidence
        FROM staging_orgs o
        JOIN org_activity a USING (org_id)
        LEFT JOIN receipt_coverage r USING (org_id)
        LEFT JOIN org_risk rk USING (org_id)
        WHERE NOT o.is_synthetic
          AND o.is_verified
          AND o.batch_id = 'IRS_BMF_2026'
          AND a.disbursements > 0
          AND (CAST(? AS VARCHAR) IS NULL OR o.cause = CAST(? AS VARCHAR))
          AND (CAST(? AS VARCHAR) IS NULL OR o.state = CAST(? AS VARCHAR))
          AND COALESCE(r.receipt_coverage, 0) >= CAST(? AS DOUBLE)
        ORDER BY confidence DESC
        LIMIT 400
    """,
    note="Hard filter on is_synthetic, verified by acceptance check INT-05.",
)

Q_CONFIDENCE_COUNT = Query(
    sql="SELECT COUNT(*) AS cleared FROM SERVING.V_CONFIDENCE_RANK",
    local="""
        SELECT COUNT(*) AS cleared
        FROM staging_orgs o
        JOIN org_activity a USING (org_id)
        WHERE NOT o.is_synthetic AND o.is_verified AND a.disbursements > 0
    """,
)


# ===========================================================================
# TAB 10 / Method And Honesty
# ===========================================================================

Q_PROVENANCE = Query(
    sql="""
        SELECT table_name, batch_id, row_count
        FROM SERVING.V_PROVENANCE
        ORDER BY row_count DESC
        LIMIT 40
    """,
    local="""
        SELECT 'STAGING.ORGS' AS table_name, batch_id, COUNT(*) AS row_count
          FROM staging_orgs GROUP BY batch_id
        UNION ALL
        SELECT 'STAGING.DISBURSEMENTS', batch_id, COUNT(*)
          FROM staging_disbursements GROUP BY batch_id
        UNION ALL
        SELECT 'STAGING.BENEFICIARIES', batch_id, COUNT(*)
          FROM staging_beneficiaries GROUP BY batch_id
        UNION ALL
        SELECT 'ORACLE.MINT_LOG', 'SOLANA_DEVNET', COUNT(*) FROM mint_log
        ORDER BY row_count DESC
    """,
    note="Counted live so the honesty table cannot drift from reality.",
)

Q_HONESTY_TOTALS = Query(
    sql="SELECT real_rows, seeded_rows FROM SERVING.V_HONESTY_TOTALS LIMIT 1",
    # Counted from the rows that are actually loaded, not from the size of
    # the upstream corpus. A tab that claims 1.8 million rows while holding
    # a sample would be the exact failure this tab exists to prevent.
    local="""
        SELECT
          (SELECT COUNT(*) FROM staging_orgs WHERE NOT is_synthetic) AS real_rows,
          (SELECT COUNT(*) FROM staging_orgs WHERE is_synthetic)
            + (SELECT COUNT(*) FROM staging_disbursements)
            + (SELECT COUNT(*) FROM staging_beneficiaries) AS seeded_rows
    """,
)

Q_CORPUS_NOTE = Query(
    sql="""
        SELECT COUNT(*) AS row_count_loaded, COUNT(*) AS row_count_available
        FROM STAGING.ORGS WHERE batch_id = 'IRS_BMF_2026'
    """,
    local="""
        SELECT (SELECT COUNT(*) FROM staging_orgs WHERE NOT is_synthetic) AS rows_loaded,
               (SELECT bmf_rows_available FROM build_meta)               AS rows_available
    """,
    note="Lets Tab 10 disclose sampling instead of hiding it.",
)

Q_ACCEPTANCE = Query(
    sql="""
        SELECT check_id, area, statement, result
        FROM SERVING.V_ACCEPTANCE_CHECKS
        ORDER BY CASE result WHEN 'FAIL' THEN 0 WHEN 'REVIEW' THEN 1 ELSE 2 END,
                 check_id
        LIMIT 60
    """,
    local="__acceptance__",
)


#: Registry. Used by the headless query-surface test in tools/, and by
#: app/data.py to resolve a key to the right statement for the backend.
QUERIES: dict[str, Query] = {
    name: value
    for name, value in list(globals().items())
    if name.startswith("Q_") and isinstance(value, Query)
}
