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

Q_OBJECT_INVENTORY = Query(
    sql="""
        SELECT table_schema                              AS schema_name,
               COUNT(*)                                  AS objects,
               SUM(IFF(is_dynamic = 'YES', 1, 0))        AS dynamic_tables,
               SUM(IFF(table_type = 'VIEW', 1, 0))       AS views,
               COALESCE(SUM(row_count), 0)               AS total_rows
        FROM GLASSPOCKET.INFORMATION_SCHEMA.TABLES
        WHERE table_schema IN ('RAW','STAGING','MARTS','SERVING','ORACLE')
        GROUP BY table_schema
        LIMIT 10
    """,
    local="""
        SELECT * FROM (VALUES
            ('RAW',    10, 0,  0,  80103),
            ('STAGING', 6, 1,  0, 106620),
            ('MARTS',  21, 6,  1, 112317),
            ('SERVING',23, 0, 23,      0),
            ('ORACLE',  4, 0,  1,   4647)
        ) AS t(schema_name, objects, dynamic_tables, views, total_rows)
    """,
    note=(
        "The stage inventory behind the system map. Read live from "
        "INFORMATION_SCHEMA so the diagram cannot claim an object the "
        "warehouse does not actually have."
    ),
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
               semantic_sim, string_sim, evasion_gap, synth_technique,
               confirmation_method
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
          c.semantic_sim, c.string_sim, c.evasion_gap, c.synth_technique,
          c.confirmation_method
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
        SELECT org_id, name, ein, city, state, cause,
               is_synthetic, is_verified, synth_technique,
               risk_score, verdict,
               comp_semantic, comp_evasion, comp_geometry,
               comp_unaccounted, comp_receipts,
               semantic_sim, evasion_gap, geom_flags,
               unaccounted_ratio, missing_receipts, scored_at
        FROM MARTS.ORG_RISK
        WHERE org_id = ?
    """,
    local="""
        SELECT org_id, name, ein, city, state, cause,
               is_synthetic, is_verified, synth_technique,
               risk_score, verdict,
               comp_semantic, comp_evasion, comp_geometry,
               comp_unaccounted, comp_receipts,
               semantic_sim, evasion_gap, geom_flags,
               unaccounted_ratio, missing_receipts, scored_at
        FROM org_risk WHERE org_id = ?
    """,
    note=(
        "The five components, so the waterfall reconstructs the total by "
        "eye, plus the filing fields Tab 01 lays side by side. The record "
        "diff is the payoff of that tab and it needs the EIN, which is "
        "the one field an impersonator cannot copy."
    ),
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
        SELECT threshold, pairs_detected, true_pairs,
               precision_at, recall_at, is_production_value
        FROM threshold_calibration ORDER BY threshold LIMIT 40
    """,
    note=(
        "Precision and recall against ground truth, because every seeded "
        "organisation records the real one it was built from. This is what "
        "justifies the cut-off rather than asserting it."
    ),
)

Q_NODE_DETAIL = Query(
    sql="""
        SELECT o.org_id, o.name, o.ein, o.city, o.state, o.cause, o.blurb,
               o.is_synthetic, o.is_verified, o.synth_technique,
               r.risk_score, r.verdict, r.semantic_sim, r.evasion_gap,
               r.nearest_target_id, r.nearest_target_name,
               (SELECT COUNT(*) FROM MARTS.CLONE_PAIRS p
                 WHERE p.target_id = o.org_id) AS imitations_pointing_at_it
        FROM STAGING.ORGS o
        LEFT JOIN MARTS.ORG_RISK r USING (org_id)
        WHERE o.org_id = ?
    """,
    local="""
        SELECT o.org_id, o.name, o.ein, o.city, o.state, o.cause, o.blurb,
               o.is_synthetic, o.is_verified, o.synth_technique,
               r.risk_score, r.verdict, r.semantic_sim, r.evasion_gap,
               r.nearest_target_id, r.nearest_target_name,
               (SELECT COUNT(*) FROM clone_pairs p
                 WHERE p.target_id = o.org_id) AS imitations_pointing_at_it
        FROM staging_orgs o
        LEFT JOIN org_risk r USING (org_id)
        WHERE o.org_id = ?
    """,
    note=(
        "A seeded node has no imitations pointing at it, it points at "
        "something. Carrying the technique and the nearest target means the "
        "inspector can say which of the two it is looking at rather than "
        "reporting a zero and leaving the reader to guess."
    ),
)

# ---------------------------------------------------------------------------
# Trust lookup. Any organisation in the corpus, scored.
#
# THE SCORE IS NOT A NEW SCORE. Trust is 100 minus MARTS.F_RISK, the same
# UDF Tab 01 decomposes into a waterfall. Introducing a second scoring
# system to answer "how trusted is this one" would mean the application
# carries two numbers that can disagree about the same organisation, and
# the tab that exists to argue for legible scoring would be running an
# illegible one.
# ---------------------------------------------------------------------------

Q_ORG_SEARCH = Query(
    sql="""
        SELECT org_id, name, ein, city, state, cause,
               is_synthetic, is_verified, risk_score, verdict
        FROM MARTS.ORG_RISK
        WHERE UPPER(name) LIKE UPPER(?) OR ein LIKE ?
        ORDER BY risk_score DESC, name
        LIMIT 40
    """,
    local="""
        SELECT org_id, name, ein, city, state, cause,
               is_synthetic, is_verified, risk_score, verdict
        FROM org_risk
        WHERE UPPER(name) LIKE UPPER(?) OR ein LIKE ?
        ORDER BY risk_score DESC, name
        LIMIT 40
    """,
    note=(
        "Ordered by score rather than alphabetically. A search over 45,400 "
        "filings that returns forty alphabetical rows buries the one row "
        "worth looking at."
    ),
)

Q_ORG_TRUST_CONTEXT = Query(
    sql="""
        SELECT a.disbursements, a.districts, a.pledged_usd, a.moved_usd,
               a.delivered_usd, a.unaccounted_usd, a.unaccounted_ratio,
               a.delivery_rate,
               c.eligible_disbursements, c.receipts_on_chain,
               c.receipts_missing, c.receipt_coverage
        FROM MARTS.ORG_RISK r
        LEFT JOIN MARTS.DT_ORG_ACTIVITY      a ON a.org_id = r.org_id
        LEFT JOIN MARTS.DT_RECEIPT_COVERAGE  c ON c.org_id = r.org_id
        WHERE r.org_id = ?
        LIMIT 1
    """,
    local="""
        SELECT a.disbursements, a.districts, a.pledged_usd, a.moved_usd,
               a.delivered_usd, a.unaccounted_usd, a.unaccounted_ratio,
               a.delivery_rate,
               c.eligible_disbursements, c.receipts_on_chain,
               c.receipts_missing, c.receipt_coverage
        FROM org_risk r
        LEFT JOIN org_activity     a ON a.org_id = r.org_id
        LEFT JOIN receipt_coverage c ON c.org_id = r.org_id
        WHERE r.org_id = ?
        LIMIT 1
    """,
    note=(
        "What the score was computed from. A score with no evidence behind "
        "it is the thing this project is against, so the lookup shows the "
        "money and the receipts alongside the number. LIMIT 1 because "
        "MARTS.ORG_RISK is one row per organisation and the filter is on "
        "its key: the limit is a guard on that invariant rather than a "
        "truncation, and the acceptance check (CRF-09) is right to insist "
        "on it whether or not the invariant happens to hold today."
    ),
)

Q_ORG_TRUST_RANK = Query(
    sql="""
        SELECT COUNT(*)                                  AS population,
               COUNT_IF(risk_score < ?)                  AS more_trusted,
               COUNT_IF(risk_score = ?)                  AS same_score,
               COUNT_IF(cause = ?)                       AS cause_population,
               COUNT_IF(cause = ? AND risk_score < ?)    AS cause_more_trusted,
               COUNT_IF(state = ?)                       AS state_population,
               COUNT_IF(state = ? AND risk_score < ?)    AS state_more_trusted
        FROM MARTS.ORG_RISK
    """,
    local="""
        SELECT COUNT(*)                                          AS population,
               COUNT(*) FILTER (WHERE risk_score < ?)            AS more_trusted,
               COUNT(*) FILTER (WHERE risk_score = ?)            AS same_score,
               COUNT(*) FILTER (WHERE cause = ?)                 AS cause_population,
               COUNT(*) FILTER (WHERE cause = ? AND risk_score < ?)
                                                                 AS cause_more_trusted,
               COUNT(*) FILTER (WHERE state = ?)                 AS state_population,
               COUNT(*) FILTER (WHERE state = ? AND risk_score < ?)
                                                                 AS state_more_trusted
        FROM org_risk
    """,
    note=(
        "One pass over the mart returning seven counters, rather than three "
        "PERCENT_RANK window functions over 45,400 rows to place a single "
        "organisation. Params: (risk, risk, cause, cause, risk, state, "
        "state, risk).\n\n"
        "THE TIE COUNTER IS NOT OPTIONAL. 44,644 filings in this corpus "
        "carry a clean zero because they have moved no money and have no "
        "near neighbour, so a percentile would report a spotless "
        "organisation as sitting above 1.6 per cent of the corpus. The "
        "interface renders three counts instead: how many score higher, "
        "how many score the same, how many score lower."
    ),
)

Q_TRUST_BANDS = Query(
    sql="""
        SELECT FLOOR(risk_score / 5) * 5    AS risk_floor,
               COUNT_IF(NOT is_synthetic)   AS real_filings,
               COUNT_IF(is_synthetic)       AS seeded_rows
        FROM MARTS.ORG_RISK
        GROUP BY 1
        ORDER BY 1
        LIMIT 40
    """,
    local="""
        SELECT FLOOR(risk_score / 5) * 5                    AS risk_floor,
               COUNT(*) FILTER (WHERE NOT is_synthetic)     AS real_filings,
               COUNT(*) FILTER (WHERE is_synthetic)         AS seeded_rows
        FROM org_risk
        GROUP BY 1
        ORDER BY 1
        LIMIT 40
    """,
    note=(
        "Banded in SQL rather than shipped as 45,400 scores and binned in "
        "pandas. Twenty rows cross the wire instead of a column that has to "
        "be counted against the 32 MB transfer cap."
    ),
)

Q_TRUST_INVARIANT = Query(
    sql="""
        SELECT COUNT(*)                                        AS orgs_scored,
               COUNT_IF(NOT is_synthetic)                      AS real_filings,
               COUNT_IF(is_synthetic)                          AS seeded_rows,
               MAX(CASE WHEN NOT is_synthetic THEN risk_score END)
                                                               AS highest_real_risk,
               COUNT_IF(NOT is_synthetic
                        AND verdict = 'needs a second look')    AS real_second_look,
               COUNT_IF(is_synthetic
                        AND verdict = 'needs a second look')    AS seeded_second_look
        FROM MARTS.ORG_RISK
    """,
    local="""
        SELECT COUNT(*)                                                AS orgs_scored,
               COUNT(*) FILTER (WHERE NOT is_synthetic)                AS real_filings,
               COUNT(*) FILTER (WHERE is_synthetic)                    AS seeded_rows,
               MAX(CASE WHEN NOT is_synthetic THEN risk_score END)     AS highest_real_risk,
               COUNT(*) FILTER (WHERE NOT is_synthetic
                                AND verdict = 'needs a second look')   AS real_second_look,
               COUNT(*) FILTER (WHERE is_synthetic
                                AND verdict = 'needs a second look')   AS seeded_second_look
        FROM org_risk
    """,
    note=(
        "The safety property, asserted from the data rather than promised "
        "in prose: real_second_look must be zero. If a real filing ever "
        "crosses the second-look line, this application is publishing an "
        "accusation about a named organisation and the tab says so."
    ),
)

Q_TRUST_BY_COUNTRY = Query(
    sql="""
        SELECT dim.country                                              AS country,
               COUNT(DISTINCT g.org_id)                                 AS orgs,
               COUNT(*)                                                 AS disbursements,
               SUM(g.amount_usd)                                        AS usd,
               AVG(CASE WHEN g.geometry_verdict = 'PLAUSIBLE'
                        THEN 1 ELSE 0 END)                              AS plausible_share,
               DIV0(SUM(CASE WHEN g.status = 'UNACCOUNTED'
                             THEN g.amount_usd ELSE 0 END),
                    NULLIF(SUM(g.amount_usd), 0))                       AS unaccounted_share,
               AVG(CASE WHEN m.asset_id IS NOT NULL
                        THEN 1 ELSE 0 END)                              AS receipted_share,
               100 - DIV0(SUM(g.amount_usd * r.risk_score),
                          NULLIF(SUM(g.amount_usd), 0))                 AS trust_score,
               COUNT(DISTINCT CASE WHEN r.verdict = 'needs a second look'
                                   THEN g.org_id END)                   AS second_look_orgs
        FROM MARTS.DELIVERY_GEOMETRY g
        JOIN MARTS.DISTRICT_DIM dim ON dim.district = g.district
        JOIN MARTS.ORG_RISK     r   ON r.org_id     = g.org_id
        LEFT JOIN ORACLE.MINT_LOG m ON m.disbursement_id = g.disbursement_id
        GROUP BY dim.country
        ORDER BY usd DESC
        LIMIT 20
    """,
    local="""
        SELECT d.country                                                AS country,
               COUNT(DISTINCT g.org_id)                                 AS orgs,
               COUNT(*)                                                 AS disbursements,
               SUM(g.amount_usd)                                        AS usd,
               AVG(CASE WHEN g.geometry_verdict = 'PLAUSIBLE'
                        THEN 1.0 ELSE 0 END)                            AS plausible_share,
               SUM(CASE WHEN g.status = 'UNACCOUNTED'
                        THEN g.amount_usd ELSE 0 END)
                 / NULLIF(SUM(g.amount_usd), 0)                         AS unaccounted_share,
               AVG(CASE WHEN m.asset_id IS NOT NULL
                        THEN 1.0 ELSE 0 END)                            AS receipted_share,
               100 - SUM(g.amount_usd * r.risk_score)
                       / NULLIF(SUM(g.amount_usd), 0)                   AS trust_score,
               COUNT(DISTINCT CASE WHEN r.verdict = 'needs a second look'
                                   THEN g.org_id END)                   AS second_look_orgs
        FROM delivery_geometry g
        JOIN staging_disbursements d USING (disbursement_id)
        JOIN org_risk r ON r.org_id = g.org_id
        LEFT JOIN mint_log m ON m.disbursement_id = g.disbursement_id
        GROUP BY d.country
        ORDER BY usd DESC
        LIMIT 20
    """,
    note=(
        "The corridor view. The country is where the money LANDED, taken "
        "from MARTS.DISTRICT_DIM, not where the organisation is registered: "
        "every filing in this corpus is American and grouping them by "
        "registration country would return one row. Trust is weighted by "
        "dollars moved, so a corridor is judged by the money that went "
        "through it rather than by a headcount of the bodies that touched it."
    ),
)

Q_TRUST_BY_STATE = Query(
    sql="""
        SELECT state,
               COUNT(*)                                          AS orgs,
               COUNT_IF(is_synthetic)                            AS seeded,
               COUNT_IF(NOT is_synthetic AND is_verified)        AS verified,
               100.0 * COUNT_IF(is_synthetic)
                 / NULLIF(COUNT_IF(NOT is_synthetic AND is_verified), 0)
                                                                 AS imitations_per_100,
               100 - AVG(risk_score)                             AS trust_score,
               MIN(100 - risk_score)                             AS lowest_trust,
               COUNT_IF(verdict = 'needs a second look')         AS second_look_orgs
        FROM MARTS.ORG_RISK
        WHERE state IS NOT NULL AND state <> ''
        GROUP BY state
        HAVING COUNT(*) >= 250
        ORDER BY imitations_per_100 DESC
        LIMIT 60
    """,
    local="""
        SELECT state,
               COUNT(*)                                          AS orgs,
               COUNT(*) FILTER (WHERE is_synthetic)              AS seeded,
               COUNT(*) FILTER (WHERE NOT is_synthetic AND is_verified)
                                                                 AS verified,
               100.0 * COUNT(*) FILTER (WHERE is_synthetic)
                 / NULLIF(COUNT(*) FILTER (WHERE NOT is_synthetic AND is_verified), 0)
                                                                 AS imitations_per_100,
               100 - AVG(risk_score)                             AS trust_score,
               MIN(100 - risk_score)                             AS lowest_trust,
               COUNT(*) FILTER (WHERE verdict = 'needs a second look')
                                                                 AS second_look_orgs
        FROM org_risk
        WHERE state IS NOT NULL AND state <> ''
        GROUP BY state
        HAVING COUNT(*) >= 250
        ORDER BY imitations_per_100 DESC
        LIMIT 60
    """,
    note=(
        "The registration view, and the HAVING clause is the point of it. A "
        "state with nine filings and one imitation reads as eleven per "
        "hundred and tops any ranking that lets it in. The floor is 250 "
        "filings, which is a denominator large enough for the rate to mean "
        "something."
    ),
)

Q_TRUST_LEADERBOARD = Query(
    sql="""
        SELECT r.org_id, r.name, r.city, r.state, r.cause,
               100 - r.risk_score  AS trust_score,
               a.disbursements, a.districts, a.moved_usd,
               a.delivery_rate, a.unaccounted_ratio
        FROM MARTS.ORG_RISK r
        JOIN MARTS.DT_ORG_ACTIVITY a ON a.org_id = r.org_id
        WHERE r.is_synthetic = FALSE
          AND r.is_verified  = TRUE
          AND a.disbursements >= 8
        ORDER BY r.risk_score ASC, a.moved_usd DESC
        LIMIT 10
    """,
    local="""
        SELECT r.org_id, r.name, r.city, r.state, r.cause,
               100 - r.risk_score  AS trust_score,
               a.disbursements, a.districts, a.moved_usd,
               a.delivery_rate, a.unaccounted_ratio
        FROM org_risk r
        JOIN org_activity a ON a.org_id = r.org_id
        WHERE r.is_synthetic = FALSE
          AND r.is_verified  = TRUE
          AND a.disbursements >= 8
        ORDER BY r.risk_score ASC, a.moved_usd DESC
        LIMIT 10
    """,
    note=(
        "A high score with no activity behind it is not trust, it is "
        "absence of evidence, and 44,580 filings in this corpus have moved "
        "no money at all and therefore score a clean zero. The eight "
        "disbursement floor is what separates earned confidence from an "
        "empty record."
    ),
)

Q_TRUST_SECOND_LOOK = Query(
    sql="""
        SELECT r.org_id, r.name, r.city, r.state, r.cause,
               r.is_synthetic, r.synth_technique,
               r.risk_score, 100 - r.risk_score AS trust_score,
               r.semantic_sim, r.evasion_gap, r.nearest_target_name
        FROM MARTS.ORG_RISK r
        WHERE r.verdict = 'needs a second look'
        ORDER BY r.risk_score DESC
        LIMIT 10
    """,
    local="""
        SELECT r.org_id, r.name, r.city, r.state, r.cause,
               r.is_synthetic, r.synth_technique,
               r.risk_score, 100 - r.risk_score AS trust_score,
               r.semantic_sim, r.evasion_gap, r.nearest_target_name
        FROM org_risk r
        WHERE r.verdict = 'needs a second look'
        ORDER BY r.risk_score DESC
        LIMIT 10
    """,
    note=(
        "Every row this returns is seeded by construction. That is asserted "
        "by Q_TRUST_INVARIANT rather than assumed, and the tab renders the "
        "assertion beside the table."
    ),
)

Q_MOST_IMPERSONATED = Query(
    sql="""
        SELECT target_id, target_name, cause, state,
               COUNT(*)           AS imitations,
               AVG(semantic_sim)  AS mean_similarity,
               MAX(evasion_gap)   AS max_evasion_gap
        FROM MARTS.CLONE_PAIRS
        GROUP BY target_id, target_name, cause, state
        ORDER BY imitations DESC, mean_similarity DESC
        LIMIT 8
    """,
    local="""
        SELECT target_id, target_name, cause, state,
               COUNT(*)           AS imitations,
               AVG(semantic_sim)  AS mean_similarity,
               MAX(evasion_gap)   AS max_evasion_gap
        FROM clone_pairs
        GROUP BY target_id, target_name, cause, state
        ORDER BY imitations DESC, mean_similarity DESC
        LIMIT 8
    """,
    note=(
        "Naming these organisations is safe and it is the humane framing: "
        "they are the targets, not the suspects. It also gives the network "
        "graph a keyboard route to its hubs, which clicking a seven pixel "
        "marker does not."
    ),
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
               COUNT(DISTINCT district)                                AS districts,
               COUNT(DISTINCT org_id)                                  AS orgs,
               SUM(amount_usd)                                         AS usd_traced,
               COUNT_IF(geometry_verdict = 'OUTSIDE_FOOTPRINT')        AS outside_footprint,
               COUNT_IF(geometry_verdict = 'IMPOSSIBLE_TRANSIT')       AS impossible_transit,
               COUNT_IF(geometry_verdict <> 'PLAUSIBLE') / COUNT(*)    AS implausible_share
        FROM MARTS.DELIVERY_GEOMETRY
    """,
    local="""
        SELECT COUNT(*)                        AS events,
               COUNT(DISTINCT delivery_h3)     AS cells,
               COUNT(DISTINCT district)        AS districts,
               COUNT(DISTINCT org_id)          AS orgs,
               SUM(amount_usd)                 AS usd_traced,
               COUNT(*) FILTER (WHERE geometry_verdict = 'OUTSIDE_FOOTPRINT')  AS outside_footprint,
               COUNT(*) FILTER (WHERE geometry_verdict = 'IMPOSSIBLE_TRANSIT') AS impossible_transit,
               CAST(COUNT(*) FILTER (WHERE geometry_verdict <> 'PLAUSIBLE') AS DOUBLE)
                 / COUNT(*)                    AS implausible_share
        FROM delivery_geometry
    """,
)

Q_DELIVERY_FLOWS = Query(
    sql="""
        SELECT g.disbursement_id, g.org_id, g.org_name, g.district,
               g.amount_usd, g.status, g.geometry_verdict,
               g.km_from_base,
               o.city  AS origin_city,
               o.state AS origin_state,
               o.lat   AS origin_lat,
               o.lon   AS origin_lon,
               g.lat   AS dest_lat,
               g.lon   AS dest_lon
        FROM MARTS.DELIVERY_GEOMETRY g
        JOIN STAGING.ORGS o ON o.org_id = g.org_id
        WHERE o.lat IS NOT NULL AND o.lon IS NOT NULL
          AND g.lat IS NOT NULL AND g.lon IS NOT NULL
        LIMIT 9000
    """,
    local="""
        SELECT g.disbursement_id, g.org_id, g.org_name, g.district,
               g.amount_usd, g.status, g.geometry_verdict,
               g.km_from_base,
               o.city  AS origin_city,
               o.state AS origin_state,
               o.lat   AS origin_lat,
               o.lon   AS origin_lon,
               g.lat   AS dest_lat,
               g.lon   AS dest_lon
        FROM delivery_geometry g
        JOIN staging_orgs o ON o.org_id = g.org_id
        WHERE o.lat IS NOT NULL AND o.lon IS NOT NULL
          AND g.lat IS NOT NULL AND g.lon IS NOT NULL
        LIMIT 9000
    """,
    note=(
        "One query, two map layers. The arc layer draws the origin and "
        "destination columns, the scatter layer draws the destination "
        "columns only, and running one statement for both means the two "
        "views cannot show different totals.\n\n"
        "The origin is the REGISTERED ADDRESS, not the operating base. "
        "That is the point of the picture: money leaves an American filing "
        "address and lands in Rafah or Kassala, which is what an "
        "international NGO does and is not on its own a finding. The "
        "footprint test, which is what a finding comes from, is a grid "
        "distance from the DECLARED BASE and is computed in "
        "sql/08_geospatial_h3.sql, not here.\n\n"
        "8,545 rows by fourteen columns is roughly a megabyte, comfortably "
        "inside the 32 MB transfer cap (Trap 07). The LIMIT is the guard "
        "that keeps it that way if the corpus grows."
    ),
)

Q_DISTRICT_TOTALS = Query(
    sql="""
        SELECT g.district,
               dim.country,
               COUNT(*)                     AS deliveries,
               COUNT(DISTINCT g.org_id)     AS orgs,
               SUM(g.amount_usd)            AS usd,
               AVG(CASE WHEN g.geometry_verdict <> 'PLAUSIBLE'
                        THEN 1 ELSE 0 END)  AS flag_rate,
               SUM(CASE WHEN g.status = 'DELIVERED'
                        THEN g.amount_usd ELSE 0 END)   AS delivered_usd,
               SUM(CASE WHEN g.status = 'UNACCOUNTED'
                        THEN g.amount_usd ELSE 0 END)   AS unaccounted_usd,
               COUNT(m.asset_id)            AS receipts_on_chain,
               AVG(g.lat)                   AS centroid_lat,
               AVG(g.lon)                   AS centroid_lon
        FROM MARTS.DELIVERY_GEOMETRY g
        JOIN MARTS.DISTRICT_DIM dim ON dim.district = g.district
        LEFT JOIN ORACLE.MINT_LOG m ON m.disbursement_id = g.disbursement_id
        GROUP BY g.district, dim.country
        ORDER BY usd DESC
        LIMIT 40
    """,
    local="""
        SELECT g.district,
               ANY_VALUE(d.country)         AS country,
               COUNT(*)                     AS deliveries,
               COUNT(DISTINCT g.org_id)     AS orgs,
               SUM(g.amount_usd)            AS usd,
               AVG(CASE WHEN g.geometry_verdict <> 'PLAUSIBLE'
                        THEN 1.0 ELSE 0 END) AS flag_rate,
               SUM(CASE WHEN g.status = 'DELIVERED'
                        THEN g.amount_usd ELSE 0 END)   AS delivered_usd,
               SUM(CASE WHEN g.status = 'UNACCOUNTED'
                        THEN g.amount_usd ELSE 0 END)   AS unaccounted_usd,
               COUNT(m.asset_id)            AS receipts_on_chain,
               AVG(g.lat)                   AS centroid_lat,
               AVG(g.lon)                   AS centroid_lon
        FROM delivery_geometry g
        JOIN staging_disbursements d USING (disbursement_id)
        LEFT JOIN mint_log m ON m.disbursement_id = g.disbursement_id
        GROUP BY g.district
        ORDER BY usd DESC
        LIMIT 40
    """,
    note="Where the money actually landed, one row per district.",
)

Q_MONEY_OVER_TIME = Query(
    sql="""
        SELECT DATE_TRUNC('week', dispatched_at)                       AS week,
               COUNT(*)                                                AS events,
               SUM(amount_usd)                                         AS dispatched_usd,
               SUM(CASE WHEN status = 'DELIVERED'
                        THEN amount_usd ELSE 0 END)                    AS delivered_usd,
               SUM(CASE WHEN status = 'UNACCOUNTED'
                        THEN amount_usd ELSE 0 END)                    AS unaccounted_usd,
               SUM(CASE WHEN geometry_verdict <> 'PLAUSIBLE'
                        THEN amount_usd ELSE 0 END)                    AS flagged_usd
        FROM MARTS.DELIVERY_GEOMETRY
        WHERE dispatched_at IS NOT NULL
        GROUP BY 1
        ORDER BY 1
        LIMIT 200
    """,
    local="""
        SELECT DATE_TRUNC('week', dispatched_at)                       AS week,
               COUNT(*)                                                AS events,
               SUM(amount_usd)                                         AS dispatched_usd,
               SUM(CASE WHEN status = 'DELIVERED'
                        THEN amount_usd ELSE 0 END)                    AS delivered_usd,
               SUM(CASE WHEN status = 'UNACCOUNTED'
                        THEN amount_usd ELSE 0 END)                    AS unaccounted_usd,
               SUM(CASE WHEN geometry_verdict <> 'PLAUSIBLE'
                        THEN amount_usd ELSE 0 END)                    AS flagged_usd
        FROM delivery_geometry
        WHERE dispatched_at IS NOT NULL
        GROUP BY 1
        ORDER BY 1
        LIMIT 200
    """,
    note=(
        "Weekly, not daily. Eighteen weeks of dispatches read as a shape; "
        "a hundred and twenty days of them read as noise, and the tab is "
        "making a point about accumulation rather than about any one day."
    ),
)

Q_PROGRAMME_FLOW = Query(
    sql="""
        SELECT programme_code,
               COUNT(*)                                                  AS events,
               COUNT(DISTINCT district)                                  AS districts,
               COUNT(DISTINCT org_id)                                    AS orgs,
               SUM(amount_usd)                                           AS usd,
               SUM(CASE WHEN status = 'DELIVERED'
                        THEN amount_usd ELSE 0 END)                      AS delivered_usd,
               SUM(CASE WHEN status = 'DISPATCHED'
                        THEN amount_usd ELSE 0 END)                      AS in_flight_usd,
               SUM(CASE WHEN status = 'UNACCOUNTED'
                        THEN amount_usd ELSE 0 END)                      AS unaccounted_usd,
               SUM(CASE WHEN status = 'PLEDGED'
                        THEN pledged_usd ELSE 0 END)                     AS pledged_only_usd
        FROM STAGING.DISBURSEMENTS
        GROUP BY programme_code
        ORDER BY usd DESC
        LIMIT 20
    """,
    local="""
        SELECT programme_code,
               COUNT(*)                                                  AS events,
               COUNT(DISTINCT district)                                  AS districts,
               COUNT(DISTINCT org_id)                                    AS orgs,
               SUM(amount_usd)                                           AS usd,
               SUM(CASE WHEN status = 'DELIVERED'
                        THEN amount_usd ELSE 0 END)                      AS delivered_usd,
               SUM(CASE WHEN status = 'DISPATCHED'
                        THEN amount_usd ELSE 0 END)                      AS in_flight_usd,
               SUM(CASE WHEN status = 'UNACCOUNTED'
                        THEN amount_usd ELSE 0 END)                      AS unaccounted_usd,
               SUM(CASE WHEN status = 'PLEDGED'
                        THEN pledged_usd ELSE 0 END)                     AS pledged_only_usd
        FROM staging_disbursements
        GROUP BY programme_code
        ORDER BY usd DESC
        LIMIT 20
    """,
    note=(
        "Programme codes are the appeal a donation was given to. Four "
        "statuses, and the difference between DISPATCHED and UNACCOUNTED "
        "is the difference between money in transit and money nobody can "
        "account for. Collapsing them would flatter the numbers."
    ),
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
               amount_usd, geometry_verdict, implied_kmh
        FROM SERVING.V_TRANSIT_FEASIBILITY
        WHERE transit_hours > 0
        LIMIT 8000
    """,
    local="""
        SELECT disbursement_id, district, km_from_base, transit_hours,
               amount_usd, geometry_verdict,
               km_from_base / NULLIF(transit_hours, 0) AS implied_kmh
        FROM delivery_geometry
        WHERE transit_hours > 0 AND km_from_base IS NOT NULL
        LIMIT 8000
    """,
    note=(
        "transit_hours > 0, not >= 0. A delivery recorded as arriving in "
        "the same hour it was dispatched has no implied speed at all, only "
        "a division by zero, and the view's own DIV0 hands back a silent "
        "zero for it. Those rows are the finding, so they are counted "
        "separately by Q_TRANSIT_RULE_AUDIT rather than smuggled into a "
        "distribution as the slowest deliveries in the corpus."
    ),
)

Q_TRANSIT_RULE_AUDIT = Query(
    sql="""
        SELECT COUNT(*)                                           AS events,
               COUNT_IF(transit_hours IS NULL)                    AS no_transit_time,
               COUNT_IF(transit_hours = 0 AND km_from_base > 400) AS rule_matches,
               COUNT_IF(transit_hours = 0 AND km_from_base > 400
                        AND geometry_verdict = 'IMPOSSIBLE_TRANSIT')  AS labelled,
               COUNT_IF(transit_hours = 0 AND km_from_base > 400
                        AND geometry_verdict <> 'IMPOSSIBLE_TRANSIT') AS masked,
               SUM(CASE WHEN transit_hours = 0 AND km_from_base > 400
                        THEN amount_usd ELSE 0 END)               AS rule_usd,
               COUNT_IF(transit_hours > 0
                        AND km_from_base / NULLIF(transit_hours, 0) > 900) AS above_jet,
               COUNT_IF(transit_hours > 0
                        AND km_from_base / NULLIF(transit_hours, 0) > 90)  AS above_truck,
               COUNT_IF(transit_hours > 0)                        AS with_speed,
               MEDIAN(CASE WHEN transit_hours > 0
                           THEN km_from_base / transit_hours END) AS median_kmh
        FROM MARTS.DELIVERY_GEOMETRY
    """,
    local="""
        SELECT COUNT(*)                                              AS events,
               COUNT(*) FILTER (WHERE transit_hours IS NULL)         AS no_transit_time,
               COUNT(*) FILTER (WHERE transit_hours = 0 AND km_from_base > 400)
                                                                    AS rule_matches,
               COUNT(*) FILTER (WHERE transit_hours = 0 AND km_from_base > 400
                        AND geometry_verdict = 'IMPOSSIBLE_TRANSIT')  AS labelled,
               COUNT(*) FILTER (WHERE transit_hours = 0 AND km_from_base > 400
                        AND geometry_verdict <> 'IMPOSSIBLE_TRANSIT') AS masked,
               SUM(CASE WHEN transit_hours = 0 AND km_from_base > 400
                        THEN amount_usd ELSE 0 END)                  AS rule_usd,
               COUNT(*) FILTER (WHERE transit_hours > 0
                        AND km_from_base / NULLIF(transit_hours, 0) > 900) AS above_jet,
               COUNT(*) FILTER (WHERE transit_hours > 0
                        AND km_from_base / NULLIF(transit_hours, 0) > 90)  AS above_truck,
               COUNT(*) FILTER (WHERE transit_hours > 0)             AS with_speed,
               MEDIAN(CASE WHEN transit_hours > 0
                           THEN km_from_base / transit_hours END)    AS median_kmh
        FROM delivery_geometry
    """,
    note=(
        "The audit behind the transit section, and the reason that section "
        "was rewritten. It reports what the shipped rule actually matches "
        "(transit_hours = 0 on a journey over 400 km), how many of those "
        "rows carry the IMPOSSIBLE_TRANSIT label, and how many are masked "
        "by an earlier branch of the same CASE. It also reports how many "
        "deliveries exceed a road speed of 90 km/h, which is nearly all of "
        "them and is not a finding: the origin is a United States filing "
        "address and the destination is another continent."
    ),
)

Q_DISTRICT_ATTRITION = Query(
    sql="""
        SELECT g.district,
               dim.country,
               COUNT(*)                                              AS events,
               SUM(g.pledged_usd)                                    AS pledged_usd,
               SUM(CASE WHEN g.status IN ('DISPATCHED','DELIVERED','UNACCOUNTED')
                        THEN g.amount_usd ELSE 0 END)                AS moved_usd,
               SUM(CASE WHEN g.status = 'DELIVERED'
                        THEN g.amount_usd ELSE 0 END)                AS delivered_usd,
               SUM(CASE WHEN g.status = 'DISPATCHED'
                        THEN g.amount_usd ELSE 0 END)                AS in_flight_usd,
               SUM(CASE WHEN g.status = 'UNACCOUNTED'
                        THEN g.amount_usd ELSE 0 END)                AS unaccounted_usd,
               DIV0(SUM(CASE WHEN g.status = 'DELIVERED'
                             THEN g.amount_usd ELSE 0 END),
                    NULLIF(SUM(CASE WHEN g.status IN ('DISPATCHED','DELIVERED','UNACCOUNTED')
                                    THEN g.amount_usd ELSE 0 END), 0))
                                                                     AS delivery_rate,
               DIV0(SUM(CASE WHEN g.status = 'UNACCOUNTED'
                             THEN g.amount_usd ELSE 0 END),
                    NULLIF(SUM(CASE WHEN g.status IN ('DISPATCHED','DELIVERED','UNACCOUNTED')
                                    THEN g.amount_usd ELSE 0 END), 0))
                                                                     AS unaccounted_rate,
               AVG(g.transit_hours)                                  AS mean_transit_hours,
               COUNT_IF(g.geometry_verdict <> 'PLAUSIBLE')           AS flagged_events
        FROM MARTS.DELIVERY_GEOMETRY g
        LEFT JOIN MARTS.DISTRICT_DIM dim ON dim.district = g.district
        WHERE g.district IS NOT NULL
        GROUP BY g.district, dim.country
        ORDER BY unaccounted_rate DESC
        LIMIT 40
    """,
    local="""
        SELECT g.district,
               ANY_VALUE(d.country)                                  AS country,
               COUNT(*)                                              AS events,
               SUM(g.pledged_usd)                                    AS pledged_usd,
               SUM(CASE WHEN g.status IN ('DISPATCHED','DELIVERED','UNACCOUNTED')
                        THEN g.amount_usd ELSE 0 END)                AS moved_usd,
               SUM(CASE WHEN g.status = 'DELIVERED'
                        THEN g.amount_usd ELSE 0 END)                AS delivered_usd,
               SUM(CASE WHEN g.status = 'DISPATCHED'
                        THEN g.amount_usd ELSE 0 END)                AS in_flight_usd,
               SUM(CASE WHEN g.status = 'UNACCOUNTED'
                        THEN g.amount_usd ELSE 0 END)                AS unaccounted_usd,
               SUM(CASE WHEN g.status = 'DELIVERED'
                        THEN g.amount_usd ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN g.status IN ('DISPATCHED','DELIVERED','UNACCOUNTED')
                                   THEN g.amount_usd ELSE 0 END), 0) AS delivery_rate,
               SUM(CASE WHEN g.status = 'UNACCOUNTED'
                        THEN g.amount_usd ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN g.status IN ('DISPATCHED','DELIVERED','UNACCOUNTED')
                                   THEN g.amount_usd ELSE 0 END), 0) AS unaccounted_rate,
               AVG(g.transit_hours)                                  AS mean_transit_hours,
               COUNT(*) FILTER (WHERE g.geometry_verdict <> 'PLAUSIBLE')
                                                                     AS flagged_events
        FROM delivery_geometry g
        JOIN staging_disbursements d USING (disbursement_id)
        WHERE g.district IS NOT NULL
        GROUP BY g.district
        ORDER BY unaccounted_rate DESC
        LIMIT 40
    """,
    note=(
        "REWRITTEN. The shipped version divided everything that was not "
        "DELIVERED by everything moved and called the result attrition, "
        "which put money still sitting in a warehouse in the same bucket as "
        "money nobody can account for. It read 34 to 42 percent per "
        "district against a real unaccounted share near 12, and it is the "
        "exact conflation the rest of this application argues against. The "
        "three statuses come back separately here so the chart can stack "
        "them and name each one."
    ),
)

Q_CORRIDOR_ATTRITION = Query(
    sql="""
        SELECT dim.country,
               COUNT(*)                                              AS events,
               COUNT(DISTINCT g.district)                            AS districts,
               COUNT(DISTINCT g.org_id)                              AS orgs,
               SUM(CASE WHEN g.status IN ('DISPATCHED','DELIVERED','UNACCOUNTED')
                        THEN g.amount_usd ELSE 0 END)                AS moved_usd,
               SUM(CASE WHEN g.status = 'DELIVERED'
                        THEN g.amount_usd ELSE 0 END)                AS delivered_usd,
               SUM(CASE WHEN g.status = 'DISPATCHED'
                        THEN g.amount_usd ELSE 0 END)                AS in_flight_usd,
               SUM(CASE WHEN g.status = 'UNACCOUNTED'
                        THEN g.amount_usd ELSE 0 END)                AS unaccounted_usd,
               DIV0(SUM(CASE WHEN g.status = 'DELIVERED'
                             THEN g.amount_usd ELSE 0 END),
                    NULLIF(SUM(CASE WHEN g.status IN ('DISPATCHED','DELIVERED','UNACCOUNTED')
                                    THEN g.amount_usd ELSE 0 END), 0))
                                                                     AS delivery_rate,
               DIV0(SUM(CASE WHEN g.status = 'UNACCOUNTED'
                             THEN g.amount_usd ELSE 0 END),
                    NULLIF(SUM(CASE WHEN g.status IN ('DISPATCHED','DELIVERED','UNACCOUNTED')
                                    THEN g.amount_usd ELSE 0 END), 0))
                                                                     AS unaccounted_rate,
               AVG(g.transit_hours)                                  AS mean_transit_hours
        FROM MARTS.DELIVERY_GEOMETRY g
        JOIN MARTS.DISTRICT_DIM dim ON dim.district = g.district
        GROUP BY dim.country
        ORDER BY unaccounted_rate DESC
        LIMIT 20
    """,
    local="""
        SELECT d.country,
               COUNT(*)                                              AS events,
               COUNT(DISTINCT g.district)                            AS districts,
               COUNT(DISTINCT g.org_id)                              AS orgs,
               SUM(CASE WHEN g.status IN ('DISPATCHED','DELIVERED','UNACCOUNTED')
                        THEN g.amount_usd ELSE 0 END)                AS moved_usd,
               SUM(CASE WHEN g.status = 'DELIVERED'
                        THEN g.amount_usd ELSE 0 END)                AS delivered_usd,
               SUM(CASE WHEN g.status = 'DISPATCHED'
                        THEN g.amount_usd ELSE 0 END)                AS in_flight_usd,
               SUM(CASE WHEN g.status = 'UNACCOUNTED'
                        THEN g.amount_usd ELSE 0 END)                AS unaccounted_usd,
               SUM(CASE WHEN g.status = 'DELIVERED'
                        THEN g.amount_usd ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN g.status IN ('DISPATCHED','DELIVERED','UNACCOUNTED')
                                   THEN g.amount_usd ELSE 0 END), 0) AS delivery_rate,
               SUM(CASE WHEN g.status = 'UNACCOUNTED'
                        THEN g.amount_usd ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN g.status IN ('DISPATCHED','DELIVERED','UNACCOUNTED')
                                   THEN g.amount_usd ELSE 0 END), 0) AS unaccounted_rate,
               AVG(g.transit_hours)                                  AS mean_transit_hours
        FROM delivery_geometry g
        JOIN staging_disbursements d USING (disbursement_id)
        GROUP BY d.country
        ORDER BY unaccounted_rate DESC
        LIMIT 20
    """,
    note=(
        "The same split one level up. Five corridors rather than sixteen "
        "districts, which is the resolution at which the difference between "
        "them is a claim rather than noise."
    ),
)

Q_DELIVERY_RATE_WEEKLY = Query(
    sql="""
        SELECT DATE_TRUNC('week', dispatched_at)                     AS week,
               COUNT(*)                                              AS events,
               SUM(CASE WHEN status IN ('DISPATCHED','DELIVERED','UNACCOUNTED')
                        THEN amount_usd ELSE 0 END)                  AS moved_usd,
               SUM(CASE WHEN status = 'DELIVERED'
                        THEN amount_usd ELSE 0 END)                  AS delivered_usd,
               SUM(CASE WHEN status = 'UNACCOUNTED'
                        THEN amount_usd ELSE 0 END)                  AS unaccounted_usd,
               DIV0(SUM(CASE WHEN status = 'DELIVERED'
                             THEN amount_usd ELSE 0 END),
                    NULLIF(SUM(CASE WHEN status IN ('DISPATCHED','DELIVERED','UNACCOUNTED')
                                    THEN amount_usd ELSE 0 END), 0)) AS delivery_rate
        FROM MARTS.DELIVERY_GEOMETRY
        WHERE dispatched_at IS NOT NULL
        GROUP BY 1
        ORDER BY 1
        LIMIT 200
    """,
    local="""
        SELECT DATE_TRUNC('week', dispatched_at)                     AS week,
               COUNT(*)                                              AS events,
               SUM(CASE WHEN status IN ('DISPATCHED','DELIVERED','UNACCOUNTED')
                        THEN amount_usd ELSE 0 END)                  AS moved_usd,
               SUM(CASE WHEN status = 'DELIVERED'
                        THEN amount_usd ELSE 0 END)                  AS delivered_usd,
               SUM(CASE WHEN status = 'UNACCOUNTED'
                        THEN amount_usd ELSE 0 END)                  AS unaccounted_usd,
               SUM(CASE WHEN status = 'DELIVERED'
                        THEN amount_usd ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN status IN ('DISPATCHED','DELIVERED','UNACCOUNTED')
                                   THEN amount_usd ELSE 0 END), 0)   AS delivery_rate
        FROM delivery_geometry
        WHERE dispatched_at IS NOT NULL
        GROUP BY 1
        ORDER BY 1
        LIMIT 200
    """,
    note=(
        "The calibration made visible. Each week's delivery rate against "
        "the published World Food Programme ratio of 371 collected from 590 "
        "moved. The aggregate is tuned to that figure; the weekly series "
        "shows the spread the tuning leaves behind, which is the honest way "
        "to display a calibrated number."
    ),
)

Q_DISTRICT_LADDER = Query(
    sql="""
        SELECT COUNT(*)                                              AS events,
               COUNT(DISTINCT org_id)                                AS orgs,
               SUM(pledged_usd)                                      AS pledged_usd,
               SUM(CASE WHEN status IN ('DISPATCHED','DELIVERED','UNACCOUNTED')
                        THEN amount_usd ELSE 0 END)                  AS moved_usd,
               SUM(CASE WHEN status = 'DELIVERED'
                        THEN amount_usd ELSE 0 END)                  AS delivered_usd,
               SUM(CASE WHEN status = 'DISPATCHED'
                        THEN amount_usd ELSE 0 END)                  AS in_flight_usd,
               SUM(CASE WHEN status = 'UNACCOUNTED'
                        THEN amount_usd ELSE 0 END)                  AS unaccounted_usd,
               COUNT_IF(geometry_verdict = 'OUTSIDE_FOOTPRINT')      AS outside_footprint,
               COUNT_IF(geometry_verdict = 'IMPOSSIBLE_TRANSIT')     AS impossible_transit,
               COUNT_IF(geometry_verdict = 'NEVER_ARRIVED')          AS never_arrived,
               AVG(transit_hours)                                    AS mean_transit_hours
        FROM MARTS.DELIVERY_GEOMETRY
        WHERE district = ?
    """,
    local="""
        SELECT COUNT(*)                                              AS events,
               COUNT(DISTINCT org_id)                                AS orgs,
               SUM(pledged_usd)                                      AS pledged_usd,
               SUM(CASE WHEN status IN ('DISPATCHED','DELIVERED','UNACCOUNTED')
                        THEN amount_usd ELSE 0 END)                  AS moved_usd,
               SUM(CASE WHEN status = 'DELIVERED'
                        THEN amount_usd ELSE 0 END)                  AS delivered_usd,
               SUM(CASE WHEN status = 'DISPATCHED'
                        THEN amount_usd ELSE 0 END)                  AS in_flight_usd,
               SUM(CASE WHEN status = 'UNACCOUNTED'
                        THEN amount_usd ELSE 0 END)                  AS unaccounted_usd,
               COUNT(*) FILTER (WHERE geometry_verdict = 'OUTSIDE_FOOTPRINT')
                                                                     AS outside_footprint,
               COUNT(*) FILTER (WHERE geometry_verdict = 'IMPOSSIBLE_TRANSIT')
                                                                     AS impossible_transit,
               COUNT(*) FILTER (WHERE geometry_verdict = 'NEVER_ARRIVED')
                                                                     AS never_arrived,
               AVG(transit_hours)                                    AS mean_transit_hours
        FROM delivery_geometry
        WHERE district = ?
    """,
    note=(
        "One district's whole ladder, for the handoff panel. Aggregate "
        "only: no beneficiary column is selected here, because the point of "
        "the handoff is that the next tab is the one allowed to answer "
        "questions about people, and only under a policy."
    ),
)


#
# The two statements below are the whole point of the tab. They are
# identical except for the object they read, and that is the entire
# difference between an answer that protects a person and one that does
# not. The protected side runs as GP_ANALYST so the policy applies.


# ===========================================================================
# TAB 06 / The Receipt
# ===========================================================================

Q_RECEIPT_KPI = Query(
    sql="""
        SELECT (SELECT COUNT(*) FROM ORACLE.MINT_LOG)                  AS receipts_on_chain,
               (SELECT COUNT(DISTINCT disbursement_id) FROM ORACLE.MINT_LOG)
                                                                       AS disbursements_covered,
               (SELECT COUNT(*) FROM ORACLE.MINT_QUEUE)                AS queued,
               (SELECT COUNT(*) FROM ORACLE.MINT_QUEUE) -
               (SELECT COUNT(DISTINCT disbursement_id) FROM ORACLE.MINT_LOG)
                                                                       AS awaiting,
               (SELECT MIN(minted_at) FROM ORACLE.MINT_LOG)            AS first_mint,
               (SELECT MAX(minted_at) FROM ORACLE.MINT_LOG)            AS last_mint
    """,
    local="""
        SELECT (SELECT COUNT(*) FROM mint_log)                         AS receipts_on_chain,
               (SELECT COUNT(DISTINCT disbursement_id) FROM mint_log)  AS disbursements_covered,
               (SELECT COUNT(*) FROM mint_queue)                       AS queued,
               (SELECT COUNT(*) FROM mint_queue) -
               (SELECT COUNT(DISTINCT disbursement_id) FROM mint_log)  AS awaiting,
               (SELECT MIN(minted_at) FROM mint_log)                   AS first_mint,
               (SELECT MAX(minted_at) FROM mint_log)                   AS last_mint
    """,
    note=(
        "REWRITTEN, because the two backends were answering different "
        "questions. The warehouse read MAX(cum_gap) off the daily gap view "
        "and the preview summed receipts_missing off the coverage table, "
        "and the two came back 206 apart on the same corpus. Both figures "
        "are now counted straight off the queue and the log, which is the "
        "only pair of objects that cannot disagree with itself.\n\n"
        "receipts_on_chain and disbursements_covered are deliberately "
        "separate. A mint is an append and it is not idempotent: a retried "
        "disbursement writes a second leaf, and an append-only ledger has "
        "no way to take the first one back. Reporting 285 receipts as 285 "
        "disbursements would be the sort of quiet overstatement this whole "
        "application exists to argue against."
    ),
)

Q_MINT_PROGRESS = Query(
    sql="""
        SELECT q.amount_band,
               -- COUNT(DISTINCT q.queue_id), not COUNT(*). The join to
               -- the log fans out on any disbursement minted more than
               -- once, so a plain row count reported 4,412 queued
               -- against a queue holding 4,333: inflated by exactly the
               -- 79 duplicate leaves this query exists to expose.
               COUNT(DISTINCT q.queue_id)                     AS queued,
               COUNT(DISTINCT m.disbursement_id)              AS covered,
               COUNT(m.asset_id)                              AS leaves_written
        FROM ORACLE.MINT_QUEUE q
        LEFT JOIN ORACLE.MINT_LOG m ON m.disbursement_id = q.disbursement_id
        GROUP BY q.amount_band
        ORDER BY queued DESC
        LIMIT 20
    """,
    local="""
        SELECT q.amount_band,
               -- COUNT(DISTINCT q.queue_id), not COUNT(*). The join to
               -- the log fans out on any disbursement minted more than
               -- once, so a plain row count reported 4,412 queued
               -- against a queue holding 4,333: inflated by exactly the
               -- 79 duplicate leaves this query exists to expose.
               COUNT(DISTINCT q.queue_id)                     AS queued,
               COUNT(DISTINCT m.disbursement_id)              AS covered,
               COUNT(m.asset_id)                              AS leaves_written
        FROM mint_queue q
        LEFT JOIN mint_log m ON m.disbursement_id = q.disbursement_id
        GROUP BY q.amount_band
        ORDER BY queued DESC
        LIMIT 20
    """,
    note=(
        "Migration progress by the only field the queue publishes about "
        "value. The band, never the amount: the band is what goes on chain, "
        "so it is also what this tab is allowed to group by."
    ),
)

Q_MINT_PROGRAMME = Query(
    sql="""
        SELECT q.programme_code,
               -- COUNT(DISTINCT q.queue_id), not COUNT(*). The join to
               -- the log fans out on any disbursement minted more than
               -- once, so a plain row count reported 4,412 queued
               -- against a queue holding 4,333: inflated by exactly the
               -- 79 duplicate leaves this query exists to expose.
               COUNT(DISTINCT q.queue_id)                     AS queued,
               COUNT(DISTINCT m.disbursement_id)              AS covered,
               COUNT(m.asset_id)                              AS leaves_written
        FROM ORACLE.MINT_QUEUE q
        LEFT JOIN ORACLE.MINT_LOG m ON m.disbursement_id = q.disbursement_id
        GROUP BY q.programme_code
        ORDER BY queued DESC
        LIMIT 20
    """,
    local="""
        SELECT q.programme_code,
               -- COUNT(DISTINCT q.queue_id), not COUNT(*). The join to
               -- the log fans out on any disbursement minted more than
               -- once, so a plain row count reported 4,412 queued
               -- against a queue holding 4,333: inflated by exactly the
               -- 79 duplicate leaves this query exists to expose.
               COUNT(DISTINCT q.queue_id)                     AS queued,
               COUNT(DISTINCT m.disbursement_id)              AS covered,
               COUNT(m.asset_id)                              AS leaves_written
        FROM mint_queue q
        LEFT JOIN mint_log m ON m.disbursement_id = q.disbursement_id
        GROUP BY q.programme_code
        ORDER BY queued DESC
        LIMIT 20
    """,
    note="The same progress by appeal, so no programme can be quietly ahead.",
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
        SELECT m.asset_id, m.minted_at, q.amount_band
        FROM mint_log m
        JOIN mint_queue q USING (disbursement_id)
        ORDER BY m.minted_at
        LIMIT 3000
    """,
    note=(
        "The band comes from the queue, not from the log. ORACLE.MINT_LOG "
        "records what the chain returned and nothing about the payload; the "
        "preview used to carry an amount_band column on the log because the "
        "preview was a mock-up rather than a mirror, and reading it broke "
        "the moment the real table was synced in."
    ),
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
    # DESCRIBE is what actually reads the object. There is no
    # INFORMATION_SCHEMA table listing a semantic view's dimensions and
    # metrics, so the alternative would be typing the shape into the
    # interface, which is exactly what this tab claims not to do.
    sql="DESCRIBE SEMANTIC VIEW MARTS.GIVING_SEMANTICS",
    local="""
        SELECT * FROM (VALUES
            ('TABLE','orgs'), ('TABLE','disb'),
            ('DIMENSION','state'), ('DIMENSION','cause'), ('DIMENSION','city'),
            ('DIMENSION','geometry_verdict'), ('DIMENSION','district'),
            ('DIMENSION','status'),
            ('METRIC','total_usd'), ('METRIC','flagged_pct'),
            ('METRIC','delivered_usd'), ('METRIC','event_count'),
            ('FACT','amount_usd'), ('FACT','pledged_usd')
        ) AS t(object_kind, object_name)
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
        WHERE disbursements > 0
          AND (? IS NULL OR cause = ?)
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
    note=(
        "Hard filter on is_synthetic, verified by acceptance check INT-05.\n\n"
        "disbursements > 0 is the second filter and it was missing from the "
        "warehouse statement. SERVING.V_CONFIDENCE_RANK LEFT JOINs activity "
        "onto every verified organisation in the filing list, so without it "
        "the warehouse returned 44,101 rows against the preview's 820: "
        "43,000 of them organisations that have moved no money at all, "
        "scored zero on both axes, and sat in a heap on the origin of the "
        "chart. The preview had the filter implicitly, through an inner "
        "join, which is how the two backends came to disagree by a factor "
        "of fifty about how many organisations this tab is about. An "
        "organisation with no disbursements has not cleared every check; it "
        "has not taken any."
    ),
)

Q_CONFIDENCE_COUNT = Query(
    sql=("SELECT COUNT(*) AS cleared FROM SERVING.V_CONFIDENCE_RANK "
         "WHERE disbursements > 0"),
    local="""
        SELECT COUNT(*) AS cleared
        FROM staging_orgs o
        JOIN org_activity a USING (org_id)
        WHERE NOT o.is_synthetic AND o.is_verified AND a.disbursements > 0
    """,
)


#: Registry. Used by the headless query-surface test in tools/, and by
#: app/data.py to resolve a key to the right statement for the backend.
QUERIES: dict[str, Query] = {
    name: value
    for name, value in list(globals().items())
    if name.startswith("Q_") and isinstance(value, Query)
}
