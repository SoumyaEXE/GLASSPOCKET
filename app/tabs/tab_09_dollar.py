"""Tab 09 / Where A Dollar Lands. Build Spec Section 07.

    The point was never to catch people. It was to help you give.

THE ONLY TAB IN THE APPLICATION WITH ZERO SYNTHETIC CONTENT.

Every organisation here is a real entry from the IRS Business Master File
in good standing. A hard filter excludes any row where is_synthetic is
true, and acceptance check INT-05 verifies that the filter holds. The
interface states the guarantee in S1 rather than leaving it implied.

FOUR THINGS WERE WRONG, AND THREE OF THEM WERE ARITHMETIC.

    1. THE TWO BACKENDS DISAGREED BY A FACTOR OF FIFTY.

       SERVING.V_CONFIDENCE_RANK LEFT JOINs activity onto every verified
       organisation in the filing list, and the warehouse statement had
       no filter on it, so the warehouse returned 44,101 rows where the
       preview returned 820. Forty-three thousand of those had moved no
       money at all, scored zero on both axes, and sat in a heap on the
       origin of the chart. The preview had the filter implicitly through
       an inner join. Q_CONFIDENCE_RANK now carries disbursements > 0
       explicitly on both sides: an organisation with no disbursements
       has not cleared every check, it has not taken any.

    2. THE LEADERBOARD REPORTED A HUNDRED PERCENT AS ONE PERCENT.

       st.column_config.ProgressColumn applies its format string to the
       raw value, so a delivery rate of 1.0 with format "%.0f%%" printed
       "1%". Every organisation in the table read 1% delivery and 0
       receipts. The table is now C.table, which is what every other
       ranked table in this build uses, and the percentages are formatted
       once, in Python, where they can be read.

    3. RECEIPT COVERAGE WAS ZERO FOR EVERY ROW.

       The preview's receipt_coverage mirror had been synced while
       ORACLE.MINT_LOG was still empty, so the y axis of the signature
       chart was a solid line of dots along the bottom and the "give here
       with confidence" box in the upper right was empty by construction.
       The mirror is refreshed; coverage now runs to 57 percent.

    4. THE CHART COLOURED BY CAUSE, AND THERE ARE TWENTY-FIVE CAUSES.

       Five rows of legend pushed the plot below the fold to encode a
       fact that belongs in a hover. It is now coloured by whether the
       ledger has heard of the organisation at all, which is two colours
       and the split that actually matters while minting is in progress.

WHAT THIS TAB IS HONEST ABOUT.

    Minting is a live migration. Most organisations here have no receipt
    yet, and that is a statement about the migration rather than about
    them. The tab says so where the chart could otherwise be read as an
    accusation.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import charts
import components as C
import data

#: How many organisations the cause comparison ranks. Beyond this the dot
#: plot is a wall of labels, and the causes past it carry single figures
#: of organisations, where a median is not a claim.
TOP_CAUSES = 12

#: The floor under a cause before its median is drawn at all.
MIN_ORGS_PER_CAUSE = 5


def _f(value, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _i(value, default: int = 0) -> int:
    return int(_f(value, default))


def _pct(value: float, digits: int = 0) -> str:
    return f"{value * 100:.{digits}f}%"


# ---------------------------------------------------------------------------
# S3 / the two signals
# ---------------------------------------------------------------------------


def _signals(ranked) -> None:
    C.section("The two signals, side by side")
    with_receipts = int((ranked["receipt_coverage"] > 0).sum())
    top_coverage = _f(ranked["receipt_coverage"].max())

    with C.panel():
        C.panel_head("Delivery against receipts", "serving.v_confidence_rank")
        C.note(
            "Across is the share of dispatched value that reached a "
            "confirmed delivery. Up is the share of those deliveries with "
            "a receipt on a public ledger. Bubble area is value moved, "
            "and every dot is a real organisation from the filing list."
        )
        st.plotly_chart(charts.confidence_scatter(ranked, height=420),
                        use_container_width=True, config=charts.bare_config())
        C.readout([
            (f"{len(ranked):,}", "organisations"),
            (_pct(_f(ranked["delivery_rate"].median())), "median delivery"),
            (f"{with_receipts:,}", "with a receipt on chain"),
            (_pct(top_coverage), "best receipt coverage"),
        ])
        C.note(
            f"<b>{len(ranked) - with_receipts:,}</b> of these sit on the "
            "bottom line, and that is a fact about the ledger rather than "
            "about them. Minting is a migration in progress: it began on "
            "one day, ran until the devnet wallet ran down, and has "
            "covered a small share of the queue so far. An organisation "
            "with no receipt yet has not failed anything. It is waiting."
        )
        C.source_note(
            "The quadrant this chart used to shade, at seventy percent on "
            "both axes, is gone. The highest receipt coverage in the "
            f"corpus is {_pct(top_coverage)}, so that box was empty by "
            "construction, and a recommendation region that cannot "
            "contain anything is worse than none at all."
        )


# ---------------------------------------------------------------------------
# S4 / the leaderboard and the detail
# ---------------------------------------------------------------------------


def _leaderboard(ranked) -> None:
    C.section("Who comes out best, and what that is made of")
    left, right = st.columns([3, 2], gap="medium")

    with left:
        with C.panel():
            C.panel_head("Confidence leaderboard", "60 delivery · 40 receipts · − risk")
            top = ranked.nlargest(14, "confidence")
            C.table(
                [
                    ("organisation", "gp-td-lead"),
                    ("cause", ""),
                    ("region", ""),
                    ("delivery", "gp-td-num"),
                    ("receipts", "gp-td-num"),
                    ("moved", "gp-td-num"),
                    ("confidence", "gp-td-num"),
                ],
                [
                    [
                        str(row.name),
                        str(row.cause),
                        str(row.state),
                        _pct(_f(row.delivery_rate)),
                        _pct(_f(row.receipt_coverage)),
                        C.usd(_f(row.value_moved_usd)),
                        f"{_f(row.confidence):.1f}",
                    ]
                    for row in top.itertuples()
                ],
                widths=["30%", "15%", "8%", "11%", "11%", "12%", "13%"],
            )
            C.source_note(
                "Confidence is sixty parts delivery rate, forty parts "
                "receipt coverage, minus half the risk score. It is a "
                "composite and it is stated here rather than left as a "
                "number to be trusted. While receipt coverage is thin, "
                "delivery carries almost all of it, which is why the "
                "delivery column and the confidence column move together."
            )

    with right:
        with C.panel():
            C.panel_head("Organisation detail", "staging.orgs")
            pick = st.selectbox(
                "organisation",
                ranked.nlargest(40, "confidence")["org_id"].tolist(),
                format_func=lambda oid: ranked.loc[
                    ranked["org_id"] == oid, "name"].iloc[0],
                key="gp_d_pick", label_visibility="collapsed",
            )
            row = ranked[ranked["org_id"] == pick].iloc[0]
            st.markdown(
                f'<div class="gp-card">'
                f'<div class="gp-card-name">{row["name"]}</div>'
                f'<div class="gp-card-meta">{row["cause"]} &middot; '
                f'{row["city"]} &middot; {row["state"]}</div>'
                f'<div class="gp-card-blurb">{row["blurb"]}</div>'
                f"</div>",
                unsafe_allow_html=True,
            )
            C.kv_rows([
                ("EIN", str(row["ein"])),
                ("disbursements", f"{_i(row['disbursements']):,}"),
                ("value moved", C.usd(_f(row["value_moved_usd"]))),
                ("delivery rate", _pct(_f(row["delivery_rate"]), 1)),
                ("receipt coverage", _pct(_f(row["receipt_coverage"]), 1)),
                ("confidence", f"{_f(row['confidence']):.1f}"),
            ])
            C.chips([
                ("verified", "verified"),
                ("in good standing", "neutral"),
                ("receipts on chain", "chain")
                if _f(row["receipt_coverage"]) > 0
                else ("awaiting a receipt", "neutral"),
            ])
            C.source_note(
                "The last chip is read from the data, not decoration. An "
                "organisation with no receipt yet says so, because a row "
                "of badges that are always green is a row of badges "
                "nobody should believe."
            )


# ---------------------------------------------------------------------------
# S5 / by cause
# ---------------------------------------------------------------------------


def _by_cause(ranked) -> None:
    C.section("By cause")
    grouped = (
        ranked.groupby("cause")
        .agg(orgs=("org_id", "count"),
             delivery_rate=("delivery_rate", "median"),
             receipt_coverage=("receipt_coverage", "median"))
        .reset_index()
    )
    grouped = grouped[grouped["orgs"] >= MIN_ORGS_PER_CAUSE]
    grouped = grouped.nlargest(TOP_CAUSES, "orgs").sort_values(
        "delivery_rate", ascending=False)

    if grouped.empty:
        C.note(
            f"No cause has {MIN_ORGS_PER_CAUSE} organisations under the "
            "current filters, so no median is drawn. A median over three "
            "organisations is not a claim about a cause."
        )
        return

    with C.panel():
        C.panel_head("Median delivery and median receipts, per cause",
                     f"causes with at least {MIN_ORGS_PER_CAUSE} organisations")
        st.plotly_chart(
            charts.cause_signals(grouped,
                                 height=max(260, 26 * len(grouped) + 110)),
            use_container_width=True, config=charts.bare_config(),
        )
        best = grouped.nlargest(1, "delivery_rate").iloc[0]
        worst = grouped.nsmallest(1, "delivery_rate").iloc[0]
        C.readout([
            (f"{len(grouped)}", "causes compared"),
            (_pct(_f(best["delivery_rate"])), f"best, {best['cause']}"),
            (_pct(_f(worst["delivery_rate"])), f"lowest, {worst['cause']}"),
            (_pct(_f(grouped["receipt_coverage"].median())),
             "median receipts across causes"),
        ])
        C.source_note(
            "Medians, not means, because a single large organisation "
            "inside a small cause would otherwise carry the whole "
            "category. The gap between the two dots on each line is the "
            "distance between what was delivered and what can be checked "
            "without trusting this application, and closing it is what "
            "the mint queue is for."
        )


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------


def render() -> None:
    C.tab_title(
        "Where A Dollar Lands",
        "The point was never to catch people. It was to help you give.",
    )

    cleared = data.scalar("Q_CONFIDENCE_COUNT", "cleared", default=0)

    # ---------------------------------------------------------------- S1
    C.hero(f"{int(cleared):,}",
           "organisations cleared every check in this dataset")
    st.markdown(
        C.chip("every organisation on this tab is real. "
               "no seeded entity appears here.", "verified"),
        unsafe_allow_html=True,
    )
    C.note(
        "Every previous tab was built to be sceptical. This one is not. "
        "These are real entries from the IRS Business Master File, in "
        "good standing, that moved money and delivered what they said "
        "they would. A hard filter excludes any row where is_synthetic is "
        "true, and acceptance check INT-05 verifies that the filter holds."
    )

    ranked_all = data.run("Q_CONFIDENCE_RANK", (None, None, None, None, 0.0))
    if ranked_all.empty:
        st.warning(
            "No organisations have both delivery and receipt statistics "
            "yet. Run the disbursement and mint stages first."
        )
        return

    # ---------------------------------------------------------------- S2
    C.section("Narrow it down")
    with C.panel():
        C.panel_head("Filters", "applied to every section below")
        f1, f2, f3 = st.columns([2, 2, 3], gap="small")
        with f1:
            causes = ["any"] + sorted(
                ranked_all["cause"].dropna().unique().tolist())
            cause = st.selectbox("cause", causes, key="gp_d_cause")
        with f2:
            states = ["any"] + sorted(
                ranked_all["state"].dropna().unique().tolist())
            state = st.selectbox("region", states, key="gp_d_state")
        with f3:
            min_coverage = st.slider(
                "minimum receipt coverage", 0.0, 1.0, 0.0, 0.05,
                format="%.0f%%", key="gp_d_coverage",
            )

        ranked = ranked_all.copy()
        if cause != "any":
            ranked = ranked[ranked["cause"] == cause]
        if state != "any":
            ranked = ranked[ranked["state"] == state]
        ranked = ranked[ranked["receipt_coverage"] >= min_coverage]

        C.readout([
            (f"{len(ranked):,}", "organisations shown"),
            (f"{len(ranked_all):,}", "before filtering"),
            (C.usd(float(ranked["value_moved_usd"].sum())), "value moved"),
            (f"{int(ranked['disbursements'].sum()):,}", "disbursements"),
        ])
        if min_coverage > 0:
            C.source_note(
                "The coverage floor is the one filter that can mislead "
                "here. Raising it above zero hides every organisation the "
                "mint queue has not reached yet, which is most of them, "
                "so what comes back is the front of a migration rather "
                "than the best of the corpus."
            )

    if ranked.empty:
        C.note(
            "No organisation matches those filters. Widen them, or lower "
            "the receipt coverage floor: most of the corpus is still "
            "waiting on the mint queue."
        )
        return

    # ------------------------------------------------------------ S3 - S5
    _signals(ranked)
    _leaderboard(ranked)
    _by_cause(ranked)

    # ---------------------------------------------------------------- S6
    C.section("Closing")
    C.note(
        "None of the machinery behind this application exists to catch "
        "people. It exists so that a person who wants to give can find "
        "out where the money went, without having to take anybody's word "
        "for it, and then give anyway. The organisations on this tab "
        "delivered what they said they would. Some of them already have a "
        "public receipt to prove it, and the rest are in a queue we are "
        "still working through, which is a thing worth saying out loud "
        "rather than a thing worth rounding up."
    )

    C.step_explainer([
        ("Only real organisations",
         "A hard filter on is_synthetic keeps every seeded entity off "
         "this tab. It is the one tab in the build with no invented "
         "content, and the acceptance suite fails if that stops being "
         "true."),
        ("Only organisations that moved money",
         "An organisation with no disbursements has not cleared every "
         "check; it has not taken any. Both backends now apply that "
         "filter explicitly rather than one of them applying it by "
         "accident."),
        ("Two signals, kept apart",
         "Delivery is what the warehouse can confirm. Receipts are what "
         "anybody can confirm without us. They are drawn on two axes "
         "because they are two different guarantees."),
        ("Nothing rounded up",
         "Where receipt coverage is zero, the tab says the ledger has not "
         "got there yet rather than leaving a blank that reads as a "
         "failing grade."),
    ])

    C.provenance_footer(
        "SERVING.V_CONFIDENCE_RANK, built exclusively from IRS Business "
        "Master File organisations in good standing, joined to their "
        "delivery and receipt statistics from MARTS.DT_ORG_ACTIVITY and "
        "MARTS.DT_RECEIPT_COVERAGE. A hard filter excludes any row where "
        "is_synthetic is true, and acceptance check INT-05 verifies that "
        "the filter holds."
    )
