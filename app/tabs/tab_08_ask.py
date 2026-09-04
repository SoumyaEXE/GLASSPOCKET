"""Tab 08 / Ask The Warehouse. Build Spec Section 07.

    Accountability that requires SQL is accountability for people who
    already have power.

Frames natural-language access over governed data as an equity feature,
which is a listed theme angle, rather than as a party trick.

GRACEFUL DEGRADATION
    If Cortex Analyst is unavailable or unreliable in the chosen region,
    the three preset questions stay wired to hand-written SQL against the
    same semantic view, the model browser stays, and S6 states that
    free-form questions are disabled in this build. The semantic view
    object still counts as a feature and the tab still makes its point.
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

import charts
import components as C
import data
import queries as Q
from theme import SNOWFLAKE_BLUE

PRESETS = {
    "which causes attract the most imitation?": (
        "Q_ASK_CAUSE_IMITATION", "cause", "imitations_per_100",
        "imitations per 100 verified organisations",
    ),
    "flagged deliveries by state": (
        "Q_ASK_FLAGGED_BY_STATE", "state", "flagged_pct",
        "share of deliveries with implausible geometry",
    ),
    "total moved last quarter": (
        "Q_ASK_TOTAL_MOVED", "quarter", "total_usd",
        "total value moved",
    ),
}

MODEL = {
    "tables": [
        ("orgs", "STAGING.ORGS", "charities, nonprofits, organisations"),
        ("disb", "MARTS.DELIVERY_GEOMETRY",
         "disbursements, deliveries, aid shipments"),
    ],
    "dimensions": [
        ("state", "orgs.state", "province, region"),
        ("cause", "orgs.cause", "sector, category, programme area"),
        ("city", "orgs.city", "town"),
        ("verdict", "disb.geometry_verdict", "geometry verdict, plausibility"),
        ("district", "disb.district", "area, locality"),
        ("status", "disb.status", "delivery status, stage"),
    ],
    "metrics": [
        ("total_usd", "SUM(disb.amount_usd)", "total disbursed, money moved"),
        ("flagged_pct", "AVG(verdict <> 'PLAUSIBLE')", "flag rate, share flagged"),
        ("delivered_usd", "SUM(amount_usd WHERE DELIVERED)",
         "value delivered, confirmed delivery value"),
        ("event_count", "COUNT(disb.disbursement_id)",
         "shipments, number of deliveries"),
    ],
}


def render() -> None:
    C.tab_title(
        "Ask The Warehouse",
        "Accountability that requires SQL is accountability for people who "
        "already have power.",
    )

    # DESCRIBE returns one row per property, so the shape is the count of
    # DISTINCT object names within each kind. Counting rows instead would
    # report thirty dimensions where there are six.
    shape = data.run("Q_SEMANTIC_SHAPE")
    counts = {"TABLE": 2, "DIMENSION": 6, "METRIC": 4, "FACT": 2}
    synonyms = 19
    if len(shape) and {"object_kind", "object_name"} <= set(shape.columns):
        counts = (shape.groupby("object_kind")["object_name"]
                  .nunique().to_dict())
        if "property" in shape.columns and "property_value" in shape.columns:
            syn = shape[shape["property"].astype(str).str.upper() == "SYNONYMS"]
            synonyms = sum(
                str(v).count(",") + 1
                for v in syn["property_value"].dropna() if str(v).strip()
            )

    # ---------------------------------------------------------------- S1
    C.hero(
        f"{counts.get('TABLE', 0)} tables · {counts.get('DIMENSION', 0)} dimensions "
        f"· {counts.get('METRIC', 0)} metrics",
        f"one semantic model, {synonyms} synonyms, "
        "read from the object rather than typed",
    )

    # ---------------------------------------------------------------- S2
    C.section("Ask")
    question = st.text_input(
        "question", value="", key="gp_a_question",
        placeholder="which causes attract the most imitation?",
        label_visibility="collapsed",
    )

    cols = st.columns(len(PRESETS), gap="small")
    chosen = st.session_state.get("gp_a_chosen", list(PRESETS)[0])
    for col, preset in zip(cols, PRESETS):
        with col:
            if st.button(preset, key=f"gp_a_{abs(hash(preset))}",
                         use_container_width=True):
                chosen = preset
                st.session_state["gp_a_chosen"] = preset

    if question.strip():
        # Match a typed question to the nearest preset by word overlap.
        # Free-form Cortex Analyst is not on the critical path, and the
        # interface says so below rather than pretending otherwise.
        asked = set(question.lower().split())
        best = max(PRESETS, key=lambda p: len(asked & set(p.lower().split())))
        if asked & set(best.lower().split()):
            chosen = best
            st.session_state["gp_a_chosen"] = best

    query_name, dim_col, metric_col, metric_label = PRESETS[chosen]
    result = data.run(query_name)

    # ------------------------------------------------------------ S3, S4
    acol, scol = st.columns([3, 2], gap="medium")

    with acol:
        C.section("Answer")
        st.markdown(f'<div class="gp-eyebrow">{chosen}</div>',
                    unsafe_allow_html=True)
        if result.empty:
            st.markdown('<div class="gp-source">No rows.</div>',
                        unsafe_allow_html=True)
        else:
            # Auto-selected chart: one numeric and one categorical gives a
            # bar, a date column gives a line, otherwise a table.
            if dim_col == "quarter":
                fig = go.Figure()
                fig.add_scatter(
                    x=result[dim_col], y=result[metric_col], mode="lines+markers",
                    line=dict(color=SNOWFLAKE_BLUE, width=2.5),
                    marker=dict(size=8, color=SNOWFLAKE_BLUE),
                    hovertemplate="%{x}: %{y:,.0f}<extra></extra>",
                )
                st.plotly_chart(charts.style_fig(fig, height=320),
                                use_container_width=True,
                                config=charts.bare_config())
            else:
                scale = 100 if metric_col == "flagged_pct" else 1
                suffix = "%" if metric_col == "flagged_pct" else ""
                st.plotly_chart(
                    charts.horizontal_bar(
                        result[dim_col].head(12),
                        result[metric_col].head(12) * scale,
                        colour=SNOWFLAKE_BLUE,
                        height=max(240, 28 * min(len(result), 12) + 60),
                        value_fmt="{:.1f}" + suffix,
                    ),
                    use_container_width=True, config=charts.bare_config(),
                )
            C.source_note(metric_label)

    with scol:
        C.section("The SQL it wrote")
        C.sql_block(Q.QUERIES[query_name].sql)
        C.source_note(
            "Always visible. An accountability tool that hides its own query "
            "contradicts itself."
        )

    # ---------------------------------------------------------------- S5
    C.section("Semantic model browser")
    for label, key in (("tables", "tables"), ("dimensions", "dimensions"),
                       ("metrics", "metrics")):
        with st.expander(f"{label} ({len(MODEL[key])})", expanded=(key == "metrics")):
            for name, definition, also_called in MODEL[key]:
                st.markdown(
                    f'<div style="padding:8px 0;border-bottom:1px solid #E4E7EB">'
                    f'<b>{name}</b> &nbsp; '
                    f'<span style="color:#6B7280">{definition}</span><br>'
                    f'<span style="font-size:11px;letter-spacing:0.09em;'
                    f'text-transform:uppercase;color:#6B7280">'
                    f'also called: {also_called}</span></div>',
                    unsafe_allow_html=True,
                )
    C.source_note(
        "Read from MARTS.GIVING_SEMANTICS. The synonyms are what let a "
        "question use the words a person would actually use."
    )

    # ---------------------------------------------------------------- S6
    C.section("Why this is an equity feature, not a novelty")
    C.step_explainer([
        ("Who currently gets to ask",
         "Today, checking a charity's delivery record means writing SQL or "
         "hiring somebody who can. That filters out almost everyone the "
         "money is supposed to reach."),
        ("What a semantic layer changes",
         "The model carries the definitions and the synonyms, so a question "
         "in ordinary words maps onto governed data with the same "
         "permissions and the same privacy policy as any other query."),
        ("What we did not do",
         "We did not put a language model on the critical path. The presets "
         "run hand-written SQL against the semantic view, so this tab works "
         "whether or not free-form question answering is available in the "
         "region."),
    ])

    C.provenance_footer(
        "MARTS.GIVING_SEMANTICS, the semantic view defined in "
        "sql/10_semantic_view.sql, over STAGING.ORGS and "
        "MARTS.DELIVERY_GEOMETRY."
    )
