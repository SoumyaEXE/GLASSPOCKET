"""Tab 09 / Where A Dollar Lands. Build Spec Section 07.

    The point was never to catch people. It was to help you give.

THE ONLY TAB IN THE APPLICATION WITH ZERO SYNTHETIC CONTENT.

Every organisation here is a real entry from the IRS Business Master File
in good standing. A hard filter excludes any row where is_synthetic is
true, and acceptance check INT-05 verifies that the filter holds. The
interface states the guarantee in S1 rather than leaving it implied.
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

import charts
import components as C
import data
from theme import CATEGORICAL, SNOWFLAKE_BLUE


def _small_multiples(df):
    """One mini chart per cause on shared axes, so causes are comparable."""
    causes = df["cause"].value_counts().head(6).index.tolist()
    if not causes:
        return None

    from plotly.subplots import make_subplots

    rows, cols = 2, 3
    fig = make_subplots(rows=rows, cols=cols, subplot_titles=causes,
                        shared_xaxes=True, shared_yaxes=True,
                        horizontal_spacing=0.06, vertical_spacing=0.16)

    for idx, cause in enumerate(causes):
        sub = df[df["cause"] == cause]
        fig.add_scatter(
            x=sub["delivery_rate"], y=sub["receipt_coverage"], mode="markers",
            marker=dict(size=6, color=CATEGORICAL[idx % len(CATEGORICAL)],
                        opacity=0.65),
            name=cause, showlegend=False,
            hovertemplate="delivery %{x:.0%} · receipts %{y:.0%}<extra></extra>",
            row=idx // cols + 1, col=idx % cols + 1,
        )

    fig.update_xaxes(range=[0, 1.05], tickformat=".0%", showgrid=False)
    fig.update_yaxes(range=[0, 1.05], tickformat=".0%")
    fig = charts.style_fig(fig, height=380)
    for annotation in fig.layout.annotations:
        annotation.font.update(family=charts.FONT, size=12, color="#6B7280")
    return fig


def render() -> None:
    C.tab_title(
        "Where A Dollar Lands",
        "The point was never to catch people. It was to help you give.",
    )

    cleared = data.scalar("Q_CONFIDENCE_COUNT", "cleared", default=0)

    # ---------------------------------------------------------------- S1
    C.hero(f"{int(cleared):,}", "organisations cleared every check in this dataset")
    st.markdown(
        C.chip("every organisation on this tab is real. "
               "no seeded entity appears here.", "verified"),
        unsafe_allow_html=True,
    )
    st.markdown(
        "Every organisation on this tab is real and cleared every check. "
        "This is what the machinery was for."
    )

    # ---------------------------------------------------------------- S2
    C.section("Filters")
    ranked_all = data.run("Q_CONFIDENCE_RANK", (None, None, None, None, 0.0))
    if ranked_all.empty:
        st.warning(
            "No organisations have both delivery and receipt statistics yet. "
            "Run the disbursement and mint stages first."
        )
        return

    f1, f2, f3 = st.columns([2, 2, 3], gap="small")
    with f1:
        causes = ["any"] + sorted(ranked_all["cause"].dropna().unique().tolist())
        cause = st.selectbox("cause", causes, key="gp_d_cause")
    with f2:
        states = ["any"] + sorted(ranked_all["state"].dropna().unique().tolist())
        state = st.selectbox("region", states, key="gp_d_state")
    with f3:
        min_coverage = st.slider("minimum receipt coverage", 0.0, 1.0, 0.0,
                                 0.05, format="%.0f%%", key="gp_d_coverage")

    ranked = ranked_all.copy()
    if cause != "any":
        ranked = ranked[ranked["cause"] == cause]
    if state != "any":
        ranked = ranked[ranked["state"] == state]
    ranked = ranked[ranked["receipt_coverage"] >= min_coverage]

    if ranked.empty:
        st.markdown('<div class="gp-source">No organisation matches those '
                    'filters. Widen them.</div>', unsafe_allow_html=True)
        return

    # ---------------------------------------------------------------- S3
    C.section("Confidence against delivery rate")
    st.plotly_chart(charts.confidence_scatter(ranked),
                    use_container_width=True, config=charts.bare_config())
    C.source_note(
        "Bubble area is value moved. The shaded upper right is where both "
        "signals agree: aid arrives, and a public receipt exists for it."
    )

    # ------------------------------------------------------------ S4, S5
    lcol, rcol = st.columns([3, 2], gap="medium")

    with lcol:
        C.section("Confidence leaderboard")
        top = ranked.nlargest(20, "confidence")[
            ["name", "cause", "state", "delivery_rate",
             "receipt_coverage", "confidence"]
        ].copy()
        top.columns = ["organisation", "cause", "region",
                       "delivery rate", "receipt coverage", "confidence"]
        st.dataframe(
            top, use_container_width=True, hide_index=True,
            column_config={
                "delivery rate": st.column_config.ProgressColumn(
                    "delivery rate", min_value=0, max_value=1, format="%.0f%%"),
                "receipt coverage": st.column_config.ProgressColumn(
                    "receipt coverage", min_value=0, max_value=1, format="%.0f%%"),
            },
        )

    with rcol:
        C.section("Organisation detail")
        pick = st.selectbox(
            "organisation", ranked.nlargest(40, "confidence")["org_id"].tolist(),
            format_func=lambda oid: ranked.loc[
                ranked["org_id"] == oid, "name"].iloc[0],
            key="gp_d_pick",
        )
        row = ranked[ranked["org_id"] == pick].iloc[0]
        st.markdown(
            f'<div class="gp-card">'
            f'<div class="gp-card-name">{row["name"]}</div>'
            f'<div class="gp-card-meta">{row["cause"]} &middot; '
            f'{row["city"]} &middot; {row["state"]}</div>'
            f'<div class="gp-card-blurb">{row["blurb"]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        C.identifier(str(row["ein"]), "EIN", copyable=False)
        C.stat_band([
            (f"{row['delivery_rate'] * 100:.0f}%", "delivery"),
            (f"{row['receipt_coverage'] * 100:.0f}%", "receipts"),
            (C.usd(row["value_moved_usd"]), "moved"),
        ])
        C.chips([("verified", "verified"),
                 ("in good standing", "neutral"),
                 ("receipts on chain", "chain")])

    # ---------------------------------------------------------------- S6
    C.section("By cause")
    multiples = _small_multiples(ranked)
    if multiples is not None:
        st.plotly_chart(multiples, use_container_width=True,
                        config=charts.bare_config())
        C.source_note(
            "Same axes on every panel, so causes are comparable at a glance "
            "rather than only within themselves."
        )

    # ---------------------------------------------------------------- S7
    C.section("Closing")
    st.markdown(
        "Every previous tab was built to be sceptical. This one is not. "
        "These are real organisations, from a public filing list, that "
        "delivered what they said they would and left a receipt anybody can "
        "check. None of the machinery behind this application exists to catch "
        "people. It exists so that a person who wants to give can find out "
        "where the money went, without having to take anybody's word for it, "
        "and then give anyway."
    )

    C.provenance_footer(
        "SERVING.V_CONFIDENCE_RANK, built exclusively from IRS Business Master "
        "File organisations in good standing, joined to their delivery and "
        "receipt statistics. A hard filter excludes any row where is_synthetic "
        "is true, and acceptance check INT-05 verifies that the filter holds."
    )
