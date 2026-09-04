"""Tab 02 / The Trust Graph. Build Spec Section 07.

    One imitation is an incident. Four hundred is a structure.

Moves the viewer from a single pair to the shape of the whole problem.
"""

from __future__ import annotations

import streamlit as st

import charts
import components as C
import data
from theme import FLAG_RED, SNOWFLAKE_BLUE


def render() -> None:
    C.tab_title(
        "The Trust Graph",
        "One imitation is an incident. Four hundred is a structure.",
    )

    summary = data.run("Q_GRAPH_SUMMARY")
    s = summary.iloc[0] if len(summary) else {}

    # ---------------------------------------------------------------- S1
    C.hero(
        f"{int(s.get('targets_affected', 0) or 0):,}",
        "verified organisations have at least one imitation inside the threshold",
    )

    # ---------------------------------------------------------------- S2
    C.stat_band([
        (f"{int(s.get('pairs_detected', 0) or 0):,}", "pairs detected"),
        (f"{float(s.get('mean_similarity', 0) or 0):.3f}", "mean similarity"),
        (f"{float(s.get('mean_evasion_gap', 0) or 0):.3f}", "mean evasion gap"),
        (f"{int(s.get('causes_affected', 0) or 0)}", "causes affected"),
    ])

    # ------------------------------------------------------------ S3, S4
    C.section("Impersonation network")
    nodes = data.run("Q_GRAPH_NODES")
    edges = data.run("Q_GRAPH_EDGES")

    gcol, icol = st.columns([3, 2], gap="medium")

    with gcol:
        if nodes.empty:
            st.markdown('<div class="gp-source">No graph stored.</div>',
                        unsafe_allow_html=True)
        else:
            event = st.plotly_chart(
                charts.impersonation_network(nodes, edges),
                use_container_width=True, config=charts.bare_config(),
                on_select="rerun", selection_mode="points",
                key="gp_g_network",
            )
            # Capture Plotly click events through the selection state.
            # Clicking writes focus_org_id and populates the inspector.
            try:
                points = event["selection"]["points"]
                if points:
                    custom = points[0].get("customdata")
                    if custom:
                        st.session_state["gp_focus_org_id"] = custom[0]
            except (KeyError, TypeError, IndexError):
                pass

            C.source_note(
                "Large blue nodes are verified organisations. Small red nodes "
                "are seeded imitations. Edge opacity scales with similarity. "
                "Positions come from an offline networkx spring layout, "
                "because third-party network components cannot load under the "
                "Content Security Policy."
            )

    with icol:
        C.section("Node inspector")
        focus = st.session_state.get("gp_focus_org_id")
        if not focus and len(nodes):
            focus = nodes.sort_values("degree", ascending=False).iloc[0]["org_id"]

        if not focus:
            st.markdown('<div class="gp-source">Click a node.</div>',
                        unsafe_allow_html=True)
        else:
            detail = data.run("Q_NODE_DETAIL", (focus,))
            if detail.empty:
                st.markdown('<div class="gp-source">No detail for that node.</div>',
                            unsafe_allow_html=True)
            else:
                d = detail.iloc[0]
                tone = "seeded" if bool(d["is_synthetic"]) else "verified"
                label = "seeded imitation" if bool(d["is_synthetic"]) else "verified"
                st.markdown(
                    f'<div class="gp-card">'
                    f'<div class="gp-card-name">{d["name"]}</div>'
                    f'<div class="gp-card-meta">{d["cause"]} &middot; '
                    f'{d["city"]} &middot; {d["state"]}</div>'
                    f'{C.chip(label, tone)}</div>',
                    unsafe_allow_html=True,
                )
                C.identifier(str(d["ein"]), "EIN", copyable=False)
                st.markdown(
                    f"**{int(d['imitations_pointing_at_it'])}** imitations "
                    "point at this organisation."
                )
                if st.button("trace its money", key="gp_g_trace"):
                    st.session_state["gp_focus_org_id"] = focus
                    st.info(
                        "Focus carried. Open Follow The Money to see where this "
                        "organisation's disbursements landed."
                    )

    # ------------------------------------------------------------ S5, S6
    ecol, tcol = st.columns(2, gap="medium")

    with ecol:
        C.section("Cause exposure")
        exposure = data.run("Q_CAUSE_EXPOSURE")
        if exposure.empty:
            st.markdown('<div class="gp-source">No exposure data.</div>',
                        unsafe_allow_html=True)
        else:
            st.plotly_chart(
                charts.horizontal_bar(
                    exposure["cause"], exposure["imitations_per_100"],
                    colour=FLAG_RED, height=max(220, 30 * len(exposure) + 60),
                    value_fmt="{:.1f}",
                    hover="%{y}: %{x:.1f} imitations per 100 verified<extra></extra>",
                ),
                use_container_width=True, config=charts.bare_config(),
            )
            C.source_note("Imitations per hundred verified organisations, by cause.")

    with tcol:
        C.section("Technique breakdown")
        technique = data.run("Q_TECHNIQUE_BREAKDOWN")
        if technique.empty:
            st.markdown('<div class="gp-source">No technique data.</div>',
                        unsafe_allow_html=True)
        else:
            st.plotly_chart(
                charts.horizontal_bar(
                    technique["technique"], technique["pairs_detected"],
                    colour=SNOWFLAKE_BLUE,
                    height=max(220, 30 * len(technique) + 60),
                    value_fmt="{:.0f}",
                    hover="%{y}: %{x} pairs<extra></extra>",
                ),
                use_container_width=True, config=charts.bare_config(),
            )
            C.source_note(
                "Which generation tactic produced each detected pair. This is "
                "honest to show because the tactics are known by construction, "
                "and it usefully shows which techniques the detector handles "
                "best."
            )

    # ---------------------------------------------------------------- S7
    C.section("Threshold sensitivity")
    curve = data.run("Q_THRESHOLD_CURVE")
    if curve.empty:
        st.markdown('<div class="gp-source">No threshold curve stored.</div>',
                    unsafe_allow_html=True)
    else:
        threshold = st.slider(
            "cosine similarity cut-off", min_value=0.70, max_value=0.99,
            value=0.86, step=0.01, key="gp_g_threshold",
        )
        st.plotly_chart(charts.threshold_curve(curve, threshold),
                        use_container_width=True, config=charts.bare_config())

        at = curve.iloc[(curve["threshold"] - threshold).abs().argmin()]
        C.stat_band([
            (f"{int(at['pairs_detected']):,}", f"pairs at {threshold:.2f}"),
            (f"{int(at['pairs_ai_confirmed']):,}", "also confirmed by the AI predicate"),
            ("0.86", "production value"),
        ])
        C.source_note(
            "The entire curve is precomputed into MARTS.THRESHOLD_CURVE, so "
            "the slider responds instantly with no query behind it. It shows "
            "the threshold was chosen rather than guessed."
        )

    C.provenance_footer(
        "CLONE_PAIRS and CLONE_CONFIRMED for edges. GRAPH_NODES and "
        "GRAPH_EDGES from an offline networkx layout, written once. "
        "THRESHOLD_CURVE precomputed by sweeping the cosine cut-off. Technique "
        "labels come from the generator, which records which transformation "
        "produced each row."
    )
