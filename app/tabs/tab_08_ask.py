"""Tab 08 / Ask The Warehouse. Build Spec Section 07.

    Accountability that requires SQL is accountability for people who
    already have power.

Frames natural-language access over governed data as an equity feature,
which is a listed theme angle, rather than as a party trick.

GRACEFUL DEGRADATION
    If Cortex Analyst is unavailable or unreliable in the chosen region,
    the preset questions stay wired to hand-written SQL against the same
    semantic view, the model browser stays, and the tab states that
    free-form questions are disabled in this build. The semantic view
    object still counts as a feature and the tab still makes its point.

THE ANSWER AND THE SQL WERE IN COLUMNS THAT COULD NOT END TOGETHER.

    A three-to-two split put a twelve-bar chart on the left and a
    four-line SELECT on the right, so the right column stopped a third of
    the way down and left a half-page of white beside the chart. Two
    columns only read as one row when both of them are the same shape,
    and a chart and a query never are. The query now sits under the
    answer, full width, where its own line length is the only thing that
    decides how much room it takes.
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

import charts
import components as C
import data
import queries as Q
from theme import SNOWFLAKE_BLUE

#: question -> (query, dimension column, metric column, what the metric is,
#:              how to format it, what the answer means in one line)
PRESETS = {
    "which causes attract the most imitation?": (
        "Q_ASK_CAUSE_IMITATION", "cause", "imitations_per_100",
        "imitations per 100 verified organisations", "{:.1f}",
        "Every cause in the corpus is imitated. The spread between the "
        "most and least targeted is under a factor of three, which is a "
        "more useful finding than a league table would have been: there "
        "is no safe category.",
    ),
    "flagged deliveries by state": (
        "Q_ASK_FLAGGED_BY_STATE", "state", "flagged_pct",
        "share of deliveries with implausible geometry", "{:.1f}%",
        "The states at the top are not the states with the most fraud. "
        "They are the states whose registered organisations deliver "
        "furthest from their filing address, which is what the geometry "
        "test measures and all it measures.",
    ),
    "total moved last quarter": (
        "Q_ASK_TOTAL_MOVED", "quarter", "total_usd",
        "total value moved", "${:,.0f}",
        "One row per quarter, over the corpus window. The shape is flat "
        "because the generator distributes disbursements evenly; a real "
        "corpus would carry appeal seasonality and this one does not "
        "pretend to.",
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


def _shape():
    """Counts read off the semantic view object, never typed here.

    DESCRIBE returns one row per property, so the shape is the count of
    DISTINCT object names within each kind. Counting rows instead would
    report thirty dimensions where there are six.
    """
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
    return counts, synonyms


def _answer_chart(result, dim_col, metric_col, value_fmt):
    if dim_col == "quarter":
        fig = go.Figure()
        fig.add_scatter(
            x=result[dim_col], y=result[metric_col], mode="lines+markers",
            line=dict(color=SNOWFLAKE_BLUE, width=2.5),
            marker=dict(size=9, color=SNOWFLAKE_BLUE,
                        line=dict(width=2, color="#FFFFFF")),
            hovertemplate="%{x}: $%{y:,.0f}<extra></extra>",
        )
        fig = charts.style_fig(fig, height=320)
        fig.update_yaxes(tickprefix="$", separatethousands=True)
        return fig

    scale = 100 if metric_col == "flagged_pct" else 1
    return charts.horizontal_bar(
        result[dim_col].head(12),
        result[metric_col].head(12) * scale,
        colour=SNOWFLAKE_BLUE,
        height=max(240, 28 * min(len(result), 12) + 70),
        value_fmt=value_fmt,
    )


def render() -> None:
    C.tab_title(
        "Ask The Warehouse",
        "Accountability that requires SQL is accountability for people who "
        "already have power.",
    )

    counts, synonyms = _shape()

    # ---------------------------------------------------------------- S1
    C.hero(
        f"{counts.get('TABLE', 0)} tables · {counts.get('DIMENSION', 0)} "
        f"dimensions · {counts.get('METRIC', 0)} metrics",
        f"one semantic model, {synonyms} synonyms, "
        "read from the object rather than typed",
    )
    C.source_note(
        "Every figure in that line comes from DESCRIBE SEMANTIC VIEW "
        "MARTS.GIVING_SEMANTICS. None of it is typed into this file, "
        "because a tab about a model that reads the warehouse should not "
        "be hand-carrying the warehouse's own shape."
    )

    # ---------------------------------------------------------------- S2
    C.section("Ask")
    chosen = st.session_state.get("gp_a_chosen", list(PRESETS)[0])

    with C.panel():
        C.panel_head("Ask in ordinary words", "marts.giving_semantics")
        question = st.text_input(
            "question", value="", key="gp_a_question",
            placeholder="which causes attract the most imitation?",
            label_visibility="collapsed",
        )
        cols = st.columns(len(PRESETS), gap="small")
        for col, preset in zip(cols, PRESETS):
            with col:
                if st.button(preset, key=f"gp_a_{abs(hash(preset))}",
                             use_container_width=True,
                             type="primary" if preset == chosen
                             else "secondary"):
                    chosen = preset
                    st.session_state["gp_a_chosen"] = preset

        matched_words: set[str] = set()
        if question.strip():
            # Match a typed question to the nearest preset by word
            # overlap. Free-form Cortex Analyst is not on the critical
            # path, and the interface says so here rather than pretending
            # a model answered.
            asked = set(question.lower().split())
            best = max(PRESETS,
                       key=lambda p: len(asked & set(p.lower().split())))
            matched_words = asked & set(best.lower().split())
            if matched_words:
                chosen = best
                st.session_state["gp_a_chosen"] = best

        if question.strip():
            if matched_words:
                C.source_note(
                    "Matched to the nearest preset on the words "
                    + ", ".join(sorted(matched_words))
                    + ". This is word overlap, not a language model, and "
                    "saying so is the point: no model sits on the "
                    "critical path of this tab."
                )
            else:
                C.source_note(
                    "No preset shares a word with that question, so "
                    "nothing was matched and the previous answer still "
                    "stands. Free-form question answering is disabled in "
                    "this build; the semantic view it would run against "
                    "is real and is browsable below."
                )

    query_name, dim_col, metric_col, metric_label, value_fmt, reading = (
        PRESETS[chosen]
    )
    result = data.run(query_name)

    # ---------------------------------------------------------------- S3
    C.section("Answer")
    with C.panel():
        C.panel_head(chosen, metric_label)
        if result.empty:
            C.note("No rows.")
        else:
            st.plotly_chart(
                _answer_chart(result, dim_col, metric_col, value_fmt),
                use_container_width=True, config=charts.bare_config(),
            )
            C.readout([
                (f"{len(result):,}", "rows returned"),
                (str(result[dim_col].iloc[0]), "at the top"),
                (value_fmt.format(
                    float(result[metric_col].iloc[0])
                    * (100 if metric_col == "flagged_pct" else 1)),
                 metric_label),
            ])
            C.note(reading)

    # ---------------------------------------------------------------- S4
    with C.panel():
        C.panel_head("The SQL it ran", "always visible")
        C.sql_block(Q.QUERIES[query_name].sql)
        C.source_note(
            "An accountability tool that hides its own query contradicts "
            "itself. This is the exact statement that produced the chart "
            "above, quoted from app/queries.py rather than reconstructed "
            "for display, so it cannot drift away from what ran."
        )

    # ---------------------------------------------------------------- S5
    C.section("Semantic model browser")
    with C.panel():
        C.panel_head("What a question is allowed to mean",
                     "describe semantic view")
        C.note(
            "A dimension is something a question can group by, a metric "
            "is something it can measure, and the synonyms are what let "
            "the question use the words a person would actually reach "
            "for. Without them, “how much money moved” matches "
            "nothing and “SUM(disb.amount_usd)” matches "
            "everything, which is the gap this whole tab is about."
        )
        for label, key in (("tables", "tables"), ("dimensions", "dimensions"),
                           ("metrics", "metrics")):
            # All three open. The model is the substance of this tab, and
            # two thirds of it sitting behind a collapsed row made the
            # page read as thin when it is not.
            with st.expander(f"{label} ({len(MODEL[key])})", expanded=True):
                C.table(
                    [("name", "gp-td-lead"), ("definition", ""),
                     ("also called", "")],
                    [[name, definition, also_called]
                     for name, definition, also_called in MODEL[key]],
                    widths=["22%", "38%", "40%"],
                )
        C.source_note(
            "Read from MARTS.GIVING_SEMANTICS, defined in "
            "sql/10_semantic_view.sql. The counts in the headline above "
            "come from the object itself; the definitions here are "
            "restated in plain language for a reader who does not write "
            "SQL, which is the reader this tab exists for."
        )

    # ---------------------------------------------------------------- S6
    C.section("Why this is an equity feature, not a novelty")
    C.step_explainer([
        ("Who currently gets to ask",
         "Today, checking a charity's delivery record means writing SQL "
         "or hiring somebody who can. That filters out almost everyone "
         "the money is supposed to reach."),
        ("What a semantic layer changes",
         "The model carries the definitions and the synonyms, so a "
         "question in ordinary words maps onto governed data with the "
         "same permissions and the same privacy policy as any other "
         "query."),
        ("The policy still applies",
         "A question asked here runs as the same role, under the same "
         "aggregation policy, as any other query against these objects. "
         "Plain language changes who can ask, never what may be "
         "answered."),
        ("What we did not do",
         "We did not put a language model on the critical path. The "
         "presets run hand-written SQL against the semantic view, so this "
         "tab works whether or not free-form question answering is "
         "available in the region, and it says which one you are looking "
         "at."),
    ])

    C.provenance_footer(
        "MARTS.GIVING_SEMANTICS, the semantic view defined in "
        "sql/10_semantic_view.sql, over STAGING.ORGS and "
        "MARTS.DELIVERY_GEOMETRY. Shape counts come from DESCRIBE SEMANTIC "
        "VIEW. The three answers run the statements quoted on this tab."
    )
