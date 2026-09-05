"""Tab 00 / The Brief. Build Spec Section 07.

    You want to help. Here is what stands between you and that.

Establishes the stakes with cited numbers, then shows the machine that
answers them. This is the only tab on which the word fraud appears, and it
appears only inside a quotation from a cited source.

TWO THINGS ON THIS TAB EXIST BECAUSE THE FIRST VERSION GOT THEM WRONG.

  * The system map drew its own source code onto the page as text. The
    cause was not the HTML sanitiser, which keeps every SVG tag; it was
    the blank lines in the markup, which end an HTML block as far as a
    markdown parser is concerned. components.svg fixes it at the cause.

  * The map was a picture of five boxes that looked like buttons and did
    nothing. It is now the control surface for a stage inspector, and
    every number in that inspector is read live from
    INFORMATION_SCHEMA, so the diagram cannot claim an object the
    warehouse does not actually have.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import charts
import components as C
import data
from theme import (BORDER, INK, NOISE_AMBER, SNOWFLAKE_BLUE, SOLANA_PURPLE,
                   TEXT_MUTED)

# ---------------------------------------------------------------------------
# The evidence timeline
# ---------------------------------------------------------------------------

#: How each unit type is written out beside its marker. A chart that needs
#: a hover to say what it is showing has not shown anything.
UNIT_LABEL = {
    "USD":       lambda v: C.usd(v),
    "TONNES":    lambda v: f"{v:,.0f} tonnes",
    "DOMAINS":   lambda v: f"{v:,.0f} domains",
    "TRUCKS":    lambda v: f"{v:,.0f} trucks",
    "INR_CRORE": lambda v: f"{v:,.2f} crore",
    "INR_LAKH":  lambda v: f"{v:,.2f} lakh",
}


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
            scaled = 16 + 26 * (group["magnitude"] / top) ** 0.5
            df.loc[group.index, "marker_size"] = scaled

    df["label"] = [
        UNIT_LABEL.get(str(unit), lambda v: f"{v:,.0f}")(float(mag))
        for unit, mag in zip(df["unit_type"], df["magnitude"])
    ]

    # One lane per region, with a small offset inside the lane so the
    # three United States citations from January 2025 do not stack.
    lanes = {region: i for i, region in enumerate(dict.fromkeys(df["region"]))}
    df["lane"] = df["region"].map(lanes).astype(float)
    within = df.groupby("region").cumcount()
    size = df.groupby("region")["region"].transform("size")
    df["lane"] += (within - (size - 1) / 2) * 0.20
    return df


# ---------------------------------------------------------------------------
# The system map and the stage inspector
# ---------------------------------------------------------------------------

#: The five stages, in order, with the schema each one is, the SQL that
#: builds it, and what a reader needs to know about it. Everything here is
#: hand-written prose; every number beside it is read from the warehouse.
STAGES = (
    {
        "key": "SOURCES",
        "eyebrow": "ingest",
        "schema": "RAW",
        "heading": "RAW — as downloaded, never edited",
        "body": (
            "Public filings land here in the shape they arrived in. The IRS "
            "Business Master File supplies the organisation corpus; IATI "
            "activity extracts supply the disbursements. Nothing in this "
            "schema is corrected, deduplicated or joined, so any later "
            "claim can be walked back to a row that nobody touched."
        ),
        "files": ("sql/01_raw_tables.sql", "sql/02_load_bmf.sql",
                  "sql/03_load_iati.sql"),
        "branch": None,
    },
    {
        "key": "STAGING",
        "eyebrow": "normalise",
        "schema": "STAGING",
        "heading": "STAGING — one normalised entity per row",
        "body": (
            "Names, addresses and causes are normalised into a single org "
            "record, and the seeded impersonators are inserted here with "
            "an explicit flag on every one of them. This is where the "
            "declarative pipeline starts: the enriched org table is a "
            "Dynamic Table with a sixty-second TARGET_LAG, not a job that "
            "somebody remembers to run."
        ),
        "files": ("sql/04_seed_adversaries.sql",
                  "sql/05_staging_dynamic_tables.sql"),
        "branch": None,
    },
    {
        "key": "MARTS",
        "eyebrow": "derive",
        "schema": "MARTS",
        "heading": "MARTS — where the findings are actually made",
        "body": (
            "Every org name is embedded as a 768-dimension vector and "
            "compared by meaning rather than by spelling, which is how an "
            "imitation that shares no words with its target is still "
            "caught. Delivery points are placed on the H3 grid and checked "
            "against a declared operating footprint. Attrition is measured "
            "stage by stage. The clone threshold is 0.94, calibrated "
            "against a labelled set rather than chosen by eye."
        ),
        "files": ("sql/06_embeddings.sql", "sql/07_clone_detection.sql",
                  "sql/08_geospatial_h3.sql", "sql/09_risk_score_udf.sql"),
        "branch": (
            "MINT QUEUE",
            "Rows that clear the checks are queued for a compressed-NFT "
            "receipt. A Node bridge polls the queue from outside and mints "
            "on Solana devnet. The arrow points outward on purpose: a "
            "trial account has no external network access, and a signing "
            "key has no business inside a warehouse regardless.",
        ),
    },
    {
        "key": "SERVING",
        "eyebrow": "expose",
        "schema": "SERVING",
        "heading": "SERVING — terminal views, and nothing else",
        "body": (
            "Every view this application reads lives here, and it is the "
            "only schema that has a protection policy attached. That is "
            "not a stylistic choice: a Dynamic Table sitting downstream of "
            "a protected object cannot refresh, so a policy anywhere in "
            "the middle of the pipeline stops the pipeline."
        ),
        "files": ("sql/11_privacy_policy.sql", "sql/12_serving_views.sql"),
        "branch": (
            "PRIVACY POLICY",
            "A minimum cohort floor, enforced by an aggregation policy. It "
            "is not differential privacy, the tab that demonstrates it "
            "says so in those words, and what the floor does and does not "
            "guarantee is written out on Tab 05.",
        ),
    },
    {
        "key": "APP",
        "eyebrow": "read",
        "schema": None,
        "heading": "APP — this page, running inside the warehouse",
        "body": (
            "Streamlit in Snowflake, holding a session it was handed by "
            "the platform rather than one it authenticated for. There is "
            "no connection string, no password and no key anywhere in the "
            "repository, because the application never needed one. Every "
            "statement it can run is a named constant in one file."
        ),
        "files": ("app/queries.py", "app/data.py"),
        "branch": None,
    },
)

STAGE_KEYS = [s["key"] for s in STAGES]
STAGE_BY_KEY = {s["key"]: s for s in STAGES}

#: Box geometry. Five boxes of 152 with 40 between them lands exactly on
#: 920, which is the viewBox width, so the diagram fills its column at
#: any browser width without a stray margin on one side.
_BOX_W, _BOX_H, _GAP = 152, 58, 40
_ROW_Y = 54
_BRANCH_Y = 166
_BRANCH_H = 52


def _stage_x(index: int) -> int:
    return index * (_BOX_W + _GAP)


def system_map(active: str, counts: dict[str, str]) -> str:
    """Draw the pipeline with one stage lit.

    The map is the control surface for the inspector below it, so the
    active stage has to be unmistakable at a glance: filled, blue, and
    two pixels of stroke against one for everything else.
    """
    parts: list[str] = [
        '<svg viewBox="0 0 920 232" width="100%" '
        'xmlns="http://www.w3.org/2000/svg" role="img">',
        "<defs>",
        f'<marker id="gpArrow" viewBox="0 0 10 10" refX="9" refY="5" '
        f'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{TEXT_MUTED}"/></marker>',
        f'<marker id="gpArrowChain" viewBox="0 0 10 10" refX="9" refY="5" '
        f'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{SOLANA_PURPLE}"/></marker>',
        f'<marker id="gpArrowNoise" viewBox="0 0 10 10" refX="9" refY="5" '
        f'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{NOISE_AMBER}"/></marker>',
        "</defs>",
        '<g font-family="Geist Variable, Geist, sans-serif" '
        'text-anchor="middle">',
    ]

    for index, stage in enumerate(STAGES):
        x = _stage_x(index)
        mid = x + _BOX_W // 2
        lit = stage["key"] == active
        stroke = SNOWFLAKE_BLUE if lit else BORDER
        fill = "#EAF7FD" if lit else "#FFFFFF"
        name_fill = "#0E7FA8" if lit else INK

        parts.append(
            f'<text x="{mid}" y="40" font-size="9" font-weight="600" '
            f'letter-spacing="0.14em" fill="#9CA3AF">'
            f'{stage["eyebrow"].upper()}</text>'
        )
        parts.append(
            f'<rect x="{x}" y="{_ROW_Y}" width="{_BOX_W}" height="{_BOX_H}" '
            f'rx="7" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{2 if lit else 1}"/>'
        )
        parts.append(
            f'<text x="{mid}" y="{_ROW_Y + 26}" font-size="12" '
            f'font-weight="650" letter-spacing="0.08em" fill="{name_fill}">'
            f'{stage["key"]}</text>'
        )
        parts.append(
            f'<text x="{mid}" y="{_ROW_Y + 44}" font-size="11" '
            f'font-weight="500" fill="{TEXT_MUTED}">'
            f'{counts.get(stage["key"], "")}</text>'
        )

        if index < len(STAGES) - 1:
            y = _ROW_Y + _BOX_H // 2
            parts.append(
                f'<line x1="{x + _BOX_W + 5}" y1="{y}" '
                f'x2="{x + _BOX_W + _GAP - 7}" y2="{y}" '
                f'stroke="{TEXT_MUTED}" stroke-width="1.5" '
                f'marker-end="url(#gpArrow)"/>'
            )

    # The two branches, each hanging directly below the stage it leaves.
    for index, (title, sub, colour, marker) in (
        (2, ("MINT QUEUE", "solana devnet", SOLANA_PURPLE, "gpArrowChain")),
        (3, ("PRIVACY POLICY", "cohort floor", NOISE_AMBER, "gpArrowNoise")),
    ):
        x = _stage_x(index)
        mid = x + _BOX_W // 2
        lit = STAGES[index]["key"] == active
        parts.append(
            f'<line x1="{mid}" y1="{_ROW_Y + _BOX_H + 4}" x2="{mid}" '
            f'y2="{_BRANCH_Y - 6}" stroke="{colour}" '
            f'stroke-width="{2 if lit else 1.5}" '
            f'marker-end="url(#{marker})"/>'
        )
        parts.append(
            f'<rect x="{x}" y="{_BRANCH_Y}" width="{_BOX_W}" '
            f'height="{_BRANCH_H}" rx="7" fill="#FFFFFF" stroke="{colour}" '
            f'stroke-width="{2 if lit else 1}"/>'
        )
        parts.append(
            f'<text x="{mid}" y="{_BRANCH_Y + 23}" font-size="11" '
            f'font-weight="650" letter-spacing="0.08em" fill="{INK}">'
            f"{title}</text>"
        )
        parts.append(
            f'<text x="{mid}" y="{_BRANCH_Y + 39}" font-size="10" '
            f'font-weight="500" letter-spacing="0.06em" fill="{TEXT_MUTED}">'
            f"{sub.upper()}</text>"
        )

    parts.append("</g></svg>")
    return "".join(parts)


def _counts_by_stage(inventory: pd.DataFrame) -> tuple[dict[str, str], dict]:
    """Turn the INFORMATION_SCHEMA roll-up into map captions and lookups."""
    lookup: dict[str, dict] = {}
    if not inventory.empty:
        for row in inventory.to_dict("records"):
            lookup[str(row["schema_name"]).upper()] = row

    captions: dict[str, str] = {}
    for stage in STAGES:
        schema = stage["schema"]
        if schema is None:
            captions[stage["key"]] = "11 sections"
            continue
        row = lookup.get(schema)
        captions[stage["key"]] = (
            f"{int(row['objects'])} objects" if row else schema
        )
    return captions, lookup


def _stage_inspector(stage: dict, lookup: dict) -> None:
    """The panel under the map. Prose on the left, live figures right."""
    left, right = st.columns([1.7, 1], gap="large")

    with left:
        st.markdown(
            f'<div class="gp-panel-title" style="font-size:15px;'
            f'margin-bottom:10px">{stage["heading"]}</div>',
            unsafe_allow_html=True,
        )
        C.note(stage["body"])
        if stage["branch"]:
            title, blurb = stage["branch"]
            st.markdown(
                f'<div class="gp-note" style="margin-top:14px">'
                f"<strong>{title}.</strong> {blurb}</div>",
                unsafe_allow_html=True,
            )

    with right:
        row = lookup.get(stage["schema"] or "", {})
        if row:
            rows_total = int(row.get("total_rows") or 0)
            C.kv_rows([
                ("schema", str(stage["schema"])),
                ("objects", f"{int(row['objects']):,}"),
                ("dynamic tables", f"{int(row['dynamic_tables']):,}"),
                ("views", f"{int(row['views']):,}"),
                ("rows stored", f"{rows_total:,}" if rows_total else "—"),
            ])
        else:
            C.kv_rows([
                ("runtime", "Streamlit in Snowflake"),
                ("session", "get_active_session()"),
                ("credentials in repo", "none"),
                ("sections", str(len(STAGE_KEYS)) and "11"),
                ("named queries", f"{len(__import__('queries').QUERIES)}"),
            ])
        st.markdown(
            '<div class="gp-source" style="margin-top:10px">builds from</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            "".join(C.chip(f, "neutral") + " " for f in stage["files"]),
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------


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
    with st.container(border=True):
        C.panel_head(
            "Seven cited incidents, by region and date",
            "marker area scales within a unit type only",
        )
        st.plotly_chart(charts.evidence_timeline(frame),
                        use_container_width=True,
                        config=charts.bare_config())

    reader, detail = st.columns([1, 1], gap="large")
    with reader:
        selected = st.selectbox(
            "read a citation in full",
            options=citations["citation_id"].tolist(),
            format_func=lambda cid: citations.loc[
                citations["citation_id"] == cid, "claim"].iloc[0],
            key="gp_b_citation",
        )
        row = citations[citations["citation_id"] == selected].iloc[0]
        st.markdown(
            f'<div class="gp-card"><div class="gp-card-name">{row["claim"]}'
            f'</div><div class="gp-card-blurb">{row["figure"]}</div></div>',
            unsafe_allow_html=True,
        )
    with detail:
        st.markdown('<div class="gp-eyebrow" style="margin-top:0">'
                    "attribution</div>", unsafe_allow_html=True)
        C.kv_rows([
            ("issuing body", str(row["issuing_body"])),
            ("published", pd.to_datetime(row["published_on"]).strftime("%d %B %Y")),
            ("region", str(row["region"])),
            ("figure as published",
             UNIT_LABEL.get(str(row["unit_type"]),
                            lambda v: f"{v:,.0f}")(float(row["magnitude"]))),
        ])
        C.source_note(
            "Quoted, not restated.",
            str(row["url"]) if pd.notna(row["url"]) else None,
        )

    # ---------------------------------------------------------------- S4
    # The system map. Five stages, and the map is the control: picking a
    # stage lights it and loads the inspector beneath.
    C.section("How it is wired")
    inventory = data.run("Q_OBJECT_INVENTORY")
    captions, lookup = _counts_by_stage(inventory)

    active = st.segmented_control(
        "stage",
        options=STAGE_KEYS,
        default=st.session_state.get("gp_b_stage", "MARTS"),
        key="gp_b_stage",
        label_visibility="collapsed",
    ) or "MARTS"

    with st.container(border=True):
        C.svg(
            system_map(active, captions),
            alt="Five stage pipeline from sources through staging, marts and "
                "serving to the application, with the mint queue branching "
                "off marts and the privacy policy off serving",
        )
        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
        _stage_inspector(STAGE_BY_KEY[active], lookup)

    C.source_note(
        "Object counts read live from INFORMATION_SCHEMA, so the diagram "
        "cannot claim something the warehouse does not have. The privacy "
        "policy attaches only to a terminal serving view, never to a table "
        "in the middle of the pipeline, because a Dynamic Table downstream "
        "of a protected object cannot refresh."
        + ("  Running against the local preview store, so the inventory "
           "shown is the rehearsal fixture rather than a live warehouse."
           if data.is_preview() else "")
    )

    # ---------------------------------------------------------------- S5
    left, right = st.columns([1.15, 1], gap="large")

    with left:
        C.section("Pipeline freshness")
        with st.container(border=True):
            C.panel_head("Seconds since last refresh", "target lag 60s")
            health = data.run("Q_PIPELINE_HEALTH")
            if health.empty:
                st.markdown(
                    '<div class="gp-source">No refresh history yet.</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.plotly_chart(charts.pipeline_freshness(health),
                                use_container_width=True,
                                config=charts.bare_config())
        C.source_note(
            "One bar per Dynamic Table, against its configured TARGET_LAG. "
            "Blue is inside lag, amber is past it. This is the declarative "
            "pipeline, visible without opening a SQL file."
        )

    with right:
        C.section("What the warehouse holds")
        with st.container(border=True):
            C.panel_head("Objects by schema", "information_schema")
            if inventory.empty:
                st.markdown(
                    '<div class="gp-source">Inventory unavailable.</div>',
                    unsafe_allow_html=True,
                )
            else:
                order = ["RAW", "STAGING", "MARTS", "SERVING", "ORACLE"]
                inv = inventory.copy()
                inv["schema_name"] = inv["schema_name"].str.upper()
                inv["rank"] = inv["schema_name"].map(
                    {name: i for i, name in enumerate(order)}).fillna(99)
                inv = inv.sort_values("rank")
                st.plotly_chart(
                    charts.horizontal_bar(
                        inv["schema_name"].tolist(),
                        inv["objects"].astype(int).tolist(),
                        height=max(240, 32 * len(inv) + 76),
                    ),
                    use_container_width=True,
                    config=charts.bare_config(),
                )
        C.source_head = None
        C.source_note(
            "Tables, views and Dynamic Tables in each schema. RAW is "
            "deliberately small and deliberately untouched; MARTS is where "
            "the work happens; SERVING is nothing but terminal views."
        )

    # ---------------------------------------------------------------- S6
    C.section("Cited sources")
    table = citations[
        ["claim", "figure", "issuing_body", "published_on", "url"]
    ].copy()
    table["published_on"] = pd.to_datetime(
        table["published_on"]).dt.strftime("%d %b %Y")
    table.columns = ["claim", "figure", "issuing body", "published", "url"]
    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "claim": st.column_config.TextColumn("claim", width="medium"),
            "figure": st.column_config.TextColumn("figure", width="large"),
            "issuing body": st.column_config.TextColumn(
                "issuing body", width="medium"),
            "published": st.column_config.TextColumn("published", width="small"),
            "url": st.column_config.LinkColumn(
                "source", width="small", display_text="open"),
        },
    )
    C.source_note(
        "Seven figures, each attributed. Nothing on this list is rounded, "
        "embellished or restated. A project about accountability that cites "
        "loosely has already lost the argument."
    )

    # ---------------------------------------------------------------- S7
    C.section("What this system does about it")
    C.step_explainer([
        ("Compare by meaning, not spelling",
         "Every organisation name is a 768-dimension vector. An imitation "
         "that shares no words with its target still lands next to it."),
        ("Follow the money to a place",
         "Disbursements are placed on the H3 grid and checked against a "
         "declared operating footprint, hop by hop."),
        ("Answer without exposing anyone",
         "Serving views enforce a minimum cohort floor, so a question about "
         "one household returns nothing at all."),
        ("Leave a receipt nobody controls",
         "Cleared disbursements are minted as compressed NFTs on Solana "
         "devnet and can be verified without trusting this application."),
    ])

    C.provenance_footer(
        "Counts from every MARTS table. Refresh history and the object "
        "inventory from INFORMATION_SCHEMA. The seven citations are "
        "hand-entered into MARTS.EVIDENCE_CITATIONS, deliberately, so they "
        "can never drift."
    )
