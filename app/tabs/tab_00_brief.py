"""Tab 00 / The Brief. Build Spec Section 07.

    You want to help. Here is what stands between you and that.

Establishes the stakes with cited numbers. This is the only tab on which
the word fraud appears, and it appears only inside a quotation from a
cited source.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import charts
import components as C
import data
from theme import (BORDER, CONFIRMED_GREEN, FLAG_RED, INK, NOISE_AMBER,
                   SNOWFLAKE_BLUE, SOLANA_PURPLE, TEXT_MUTED)


def _timeline_frame(citations: pd.DataFrame) -> pd.DataFrame:
    """Lay the citations out for C00-1.

    Marker area scales with magnitude, normalised WITHIN each unit type,
    because dollars and tonnes are not comparable and pretending otherwise
    would be exactly the kind of sloppy presentation this tab argues
    against.
    """
    df = citations.copy()
    df["published_on"] = pd.to_datetime(df["published_on"])

    df["marker_size"] = 18.0
    for unit, group in df.groupby("unit_type"):
        top = group["magnitude"].max()
        if top and top > 0:
            scaled = 16 + 30 * (group["magnitude"] / top) ** 0.5
            df.loc[group.index, "marker_size"] = scaled

    # A jittered category lane so markers do not collide.
    lanes = {region: i for i, region in enumerate(dict.fromkeys(df["region"]))}
    df["lane"] = df["region"].map(lanes).astype(float)
    df["lane"] += df.groupby("region").cumcount() * 0.22
    return df


SYSTEM_MAP_SVG = f"""
<svg viewBox="0 0 560 190" width="100%" height="190"
     xmlns="http://www.w3.org/2000/svg" role="img"
     aria-label="Five stage pipeline from sources to serving, with privacy
                 and mint queue branches">
  <defs>
    <marker id="gpArrow" viewBox="0 0 10 10" refX="9" refY="5"
            markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="{TEXT_MUTED}"/>
    </marker>
  </defs>
  <g font-family="Geist Variable, Geist, sans-serif" font-size="11"
     font-weight="600" letter-spacing="0.09em" text-anchor="middle">
    <rect x="6"   y="34" width="94" height="40" rx="6" fill="#FFFFFF"
          stroke="{BORDER}"/>
    <text x="53"  y="59" fill="{INK}">SOURCES</text>
    <rect x="122" y="34" width="94" height="40" rx="6" fill="#FFFFFF"
          stroke="{BORDER}"/>
    <text x="169" y="59" fill="{INK}">STAGING</text>
    <rect x="238" y="34" width="94" height="40" rx="6" fill="#FFFFFF"
          stroke="{BORDER}"/>
    <text x="285" y="59" fill="{INK}">MARTS</text>
    <rect x="354" y="34" width="94" height="40" rx="6" fill="#FFFFFF"
          stroke="{SNOWFLAKE_BLUE}"/>
    <text x="401" y="59" fill="{INK}">SERVING</text>
    <rect x="470" y="34" width="84" height="40" rx="6" fill="#FFFFFF"
          stroke="{BORDER}"/>
    <text x="512" y="59" fill="{INK}">APP</text>

    <line x1="102" y1="54" x2="118" y2="54" stroke="{TEXT_MUTED}"
          stroke-width="1.5" marker-end="url(#gpArrow)"/>
    <line x1="218" y1="54" x2="234" y2="54" stroke="{TEXT_MUTED}"
          stroke-width="1.5" marker-end="url(#gpArrow)"/>
    <line x1="334" y1="54" x2="350" y2="54" stroke="{TEXT_MUTED}"
          stroke-width="1.5" marker-end="url(#gpArrow)"/>
    <line x1="450" y1="54" x2="466" y2="54" stroke="{TEXT_MUTED}"
          stroke-width="1.5" marker-end="url(#gpArrow)"/>

    <rect x="330" y="122" width="142" height="40" rx="6" fill="#FFFFFF"
          stroke="{NOISE_AMBER}"/>
    <text x="401" y="147" fill="{INK}">PRIVACY POLICY</text>
    <line x1="401" y1="78" x2="401" y2="118" stroke="{NOISE_AMBER}"
          stroke-width="1.5" marker-end="url(#gpArrow)"/>

    <rect x="150" y="122" width="142" height="40" rx="6" fill="#FFFFFF"
          stroke="{SOLANA_PURPLE}"/>
    <text x="221" y="147" fill="{INK}">MINT QUEUE</text>
    <line x1="285" y1="78" x2="240" y2="118" stroke="{SOLANA_PURPLE}"
          stroke-width="1.5" marker-end="url(#gpArrow)"/>
  </g>
</svg>
"""


def render() -> None:
    C.tab_title(
        "The Brief",
        "You want to help. Here is what stands between you and that.",
    )

    citations = data.run("Q_EVIDENCE")

    # ---------------------------------------------------------------- S1
    # Hero. The IC3 figure, the largest number in the entire application.
    # Caption carries the source inline.
    ic3 = citations[citations["citation_id"] == "IC3_2024"]
    C.hero(
        "$96,000,000",
        "reported lost to fraudulent charities, crowdfunding accounts and "
        "disaster relief campaigns, United States, 2024",
    )
    if len(ic3):
        C.source_note(
            "FBI IC3 Public Service Announcement I-011625, 16 January 2025. "
            "More than 4,500 complaints.",
            str(ic3.iloc[0]["url"]) if pd.notna(ic3.iloc[0]["url"]) else None,
        )

    # ---------------------------------------------------------------- S2
    kpi = data.run("Q_KPI")
    if len(kpi):
        k = kpi.iloc[0]
        C.stat_band([
            (f"{int(k['orgs_indexed']):,}", "orgs indexed"),
            (f"{int(k['disbursements_traced']):,}", "disbursements traced"),
            (f"{int(k['receipts_on_chain']):,}", "receipts on chain"),
            (f"{int(k['needs_second_look']):,}", "need a second look"),
            (f"{int(k['pipeline_objects_fresh'])}", "pipeline objects fresh"),
        ])

    # ---------------------------------------------------------------- S3
    C.section("Evidence timeline")
    frame = _timeline_frame(citations)
    st.plotly_chart(charts.evidence_timeline(frame), use_container_width=True,
                    config=charts.bare_config())

    selected = st.selectbox(
        "read a citation in full",
        options=citations["citation_id"].tolist(),
        format_func=lambda cid: citations.loc[
            citations["citation_id"] == cid, "claim"].iloc[0],
        key="gp_b_citation",
    )
    row = citations[citations["citation_id"] == selected].iloc[0]
    st.markdown(
        f'<div class="gp-card"><div class="gp-card-name">{row["claim"]}</div>'
        f'<div class="gp-card-blurb">{row["figure"]}</div></div>',
        unsafe_allow_html=True,
    )
    C.source_note(
        f"{row['issuing_body']}, "
        f"{pd.to_datetime(row['published_on']).strftime('%d %B %Y')}.",
        str(row["url"]) if pd.notna(row["url"]) else None,
    )

    # ------------------------------------------------------------ S4, S5
    left, right = st.columns(2, gap="medium")

    with left:
        C.section("Pipeline freshness")
        health = data.run("Q_PIPELINE_HEALTH")
        if health.empty:
            st.markdown('<div class="gp-source">No refresh history yet.</div>',
                        unsafe_allow_html=True)
        else:
            st.plotly_chart(charts.pipeline_freshness(health),
                            use_container_width=True,
                            config=charts.bare_config())
            C.source_note(
                "Seconds since the last refresh of each Dynamic Table, against "
                "its configured TARGET_LAG. Blue is inside lag, amber is past "
                "it. This is the declarative pipeline, visible without opening "
                "a SQL file."
            )

    with right:
        C.section("System map")
        st.markdown(SYSTEM_MAP_SVG, unsafe_allow_html=True)
        C.source_note(
            "Five stages. The privacy policy attaches only to a terminal "
            "serving view, never to a table in the middle of the pipeline, "
            "because a Dynamic Table downstream of a protected object cannot "
            "refresh."
        )

    # ---------------------------------------------------------------- S6
    C.section("Cited sources")
    table = citations[["claim", "figure", "issuing_body", "published_on", "url"]].copy()
    table["published_on"] = pd.to_datetime(table["published_on"]).dt.strftime("%d %b %Y")
    table.columns = ["claim", "figure", "issuing body", "published", "url"]
    st.dataframe(table, use_container_width=True, hide_index=True,
                 column_config={"url": st.column_config.LinkColumn("source")})
    C.source_note(
        "Seven figures, each attributed. Nothing on this list is rounded, "
        "embellished or restated. A project about accountability that cites "
        "loosely has already lost the argument."
    )

    C.provenance_footer(
        "Counts from every MARTS table. Refresh history from "
        "INFORMATION_SCHEMA. The seven citations are hand-entered into "
        "MARTS.EVIDENCE_CITATIONS, deliberately, so they can never drift."
    )
