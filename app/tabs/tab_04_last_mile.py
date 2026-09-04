"""Tab 04 / The Last Mile. Build Spec Section 07.

    Money does not vanish at the source. It vanishes between the warehouse
    and the person.

Selecting a district here carries the filter into Tab 05, where the same
district returns under privacy protection. Narrate that handoff in the
demo: it is the moment the two halves of the argument join.
"""

from __future__ import annotations

import streamlit as st

import charts
import components as C
import data
from theme import FLAG_RED


def render() -> None:
    C.tab_title(
        "The Last Mile",
        "Money does not vanish at the source. "
        "It vanishes between the warehouse and the person.",
    )

    flow = data.run("Q_ATTRITION_FLOW")
    if flow.empty:
        st.warning("No disbursement data.")
        return
    f = flow.iloc[0]

    # ---------------------------------------------------------------- S1
    C.hero(
        f"{float(f['delivery_rate'] or 0) * 100:.0f}%",
        "of dispatched value reaches a confirmed delivery",
    )

    # ---------------------------------------------------------------- S2
    C.stat_band([
        (C.usd(f["pledged_usd"]), "pledged"),
        (C.usd(f["dispatched_usd"]), "dispatched"),
        (C.usd(f["delivered_usd"]), "delivered"),
        (C.usd(f["unaccounted_usd"]), "unaccounted"),
    ])

    # ---------------------------------------------------------------- S3
    C.section("Attrition flow")
    st.plotly_chart(
        charts.attrition_sankey({
            "dispatched_usd": float(f["dispatched_usd"] or 0),
            "never_dispatched_usd": float(f["never_dispatched_usd"] or 0),
            "delivered_usd": float(f["delivered_usd"] or 0),
            "unaccounted_usd": float(f["unaccounted_usd"] or 0),
        }),
        use_container_width=True, config=charts.bare_config(),
    )
    C.source_note(
        "Link width is dollars. The link into unaccounted is red and is "
        "deliberately the heaviest element on this tab, because it is the "
        "one the sector's annual reports tend to render as a footnote."
    )

    # ------------------------------------------------------------ S4, S5
    tcol, dcol = st.columns(2, gap="medium")

    with tcol:
        C.section("Transit time against distance")
        transit = data.run("Q_TRANSIT_FEASIBILITY")
        if transit.empty:
            st.markdown('<div class="gp-source">No transit records.</div>',
                        unsafe_allow_html=True)
        else:
            st.plotly_chart(charts.transit_feasibility(transit),
                            use_container_width=True,
                            config=charts.bare_config())
            impossible = int(transit["exceeds_plausible_speed"].sum())
            C.source_note(
                f"{impossible:,} deliveries sit inside the shaded region. This "
                "is the most immediately legible signal in the application "
                "because it needs no explanation: a truck cannot cover four "
                "hundred kilometres in under an hour."
            )

    with dcol:
        C.section("Attrition by district")
        districts = data.run("Q_DISTRICT_ATTRITION")
        if districts.empty:
            st.markdown('<div class="gp-source">No district data.</div>',
                        unsafe_allow_html=True)
        else:
            st.plotly_chart(
                charts.horizontal_bar(
                    districts["district"], districts["attrition_rate"] * 100,
                    colour=FLAG_RED,
                    height=max(240, 26 * len(districts) + 60),
                    value_fmt="{:.0f}%",
                    hover="%{y}: %{x:.1f}% attrition<extra></extra>",
                ),
                use_container_width=True, config=charts.bare_config(),
            )

            # The cross-tab filter. This is a real handoff, not a caption.
            chosen = st.selectbox(
                "carry a district into The Wall",
                ["none"] + districts["district"].tolist(),
                key="gp_l_district",
            )
            if chosen != "none":
                st.session_state["gp_focus_district"] = chosen
                st.markdown(
                    C.chip(f"{chosen} carried to The Wall", "chain"),
                    unsafe_allow_html=True,
                )

    # ---------------------------------------------------------------- S6
    C.section("Calibration")
    st.markdown(
        "The synthetic attrition on this tab is tuned against a published "
        "figure rather than chosen to look dramatic. The World Food Programme "
        "reported, in its State of Palestine situation report of 6 June 2025:"
    )
    st.markdown(
        '<div class="gp-card"><div class="gp-card-blurb">'
        "&ldquo;590 trucks moved from Ashdod to Kerem Shalom, of which 371 "
        "were collected inside Gaza; organised criminal looting estimated by "
        "field monitors at about 20 percent of cases.&rdquo;"
        "</div></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"That ratio is **62.9 percent**. The delivery rate above is "
        f"**{float(f['delivery_rate'] or 0) * 100:.1f} percent**. The "
        "aggregate is calibrated to the published figure; the individual "
        "delivery events behind it are modelled, and this tab does not claim "
        "otherwise."
    )
    C.source_note(
        "WFP State of Palestine External Situation Report 55, 6 June 2025. "
        "The aggregate is calibrated to this figure. The individual delivery "
        "events are synthetic and are not claimed to be real."
    )

    # ---------------------------------------------------------------- S7
    C.section("The handoff")
    st.markdown(
        "Selecting a district above carries the filter into **The Wall**, "
        "where the same district returns under privacy protection. The two "
        "tabs are deliberately joined: this one shows you where the money "
        "stopped, and the next one refuses to tell you which person it "
        "stopped short of."
    )

    C.provenance_footer(
        "IATI transaction records where available. Delivery events synthetic, "
        "with attrition rates tuned so the aggregate delivery share sits close "
        "to the published WFP ratio of 371 collected from 590 moved."
    )
