"""Tab 04 / The Last Mile. Build Spec Section 07.

    Money does not vanish at the source. It vanishes between the warehouse
    and the person.

Selecting a district here carries the filter into Tab 05, where the same
district returns under privacy protection. Narrate that handoff in the
demo: it is the moment the two halves of the argument join.

TWO THINGS ON THIS TAB WERE WRONG, AND THEY WERE WRONG IN THE SAME WAY.

    Both of them took a number that was easy to compute and put a label
    on it that the number did not earn. Restyling either one would have
    made a false claim prettier, so both were rebuilt from the query up.

    1. THE TRANSIT CHART CALLED 6,828 DELIVERIES PHYSICALLY IMPOSSIBLE.

       It shaded everything under a 90 km/h line and counted what fell
       inside. The warehouse records 199 as IMPOSSIBLE_TRANSIT, so the
       chart overstated its own finding by a factor of thirty-four. The
       data was fine; the line was nonsense. ``km_from_base`` is measured
       from the organisation's registered filing address, which is in the
       United States, to a delivery on another continent: ten thousand
       kilometres in two days is 218 km/h, which is air freight behaving
       exactly like air freight. And 90 km/h was never the shipped test.
       The rule in sql/08_geospatial_h3.sql is
       ``transit_hours = 0 AND km_from_base > 400``, which is a different
       and much narrower statement: a delivery recorded as arriving in
       the same hour it left, four hundred kilometres away.

       So the section now plots the implied speed itself against two
       labelled reference speeds, and reports the shipped rule's matches
       as the separate, smaller, real number they are.

    2. THE DISTRICT BARS CALLED MONEY IN A WAREHOUSE ATTRITION.

       ``attrition_rate`` divided everything that was not DELIVERED by
       everything moved, which put still-in-flight dollars in the same
       bucket as dollars nobody can account for. The bars read 34 to 42
       percent against a real unaccounted share near 12. That is the
       precise conflation this application exists to argue against, and
       it was sitting on the tab that makes the argument.

       Delivered, still in flight and unaccounted are now three
       separately-computed columns, stacked and named.

THE ARITHMETIC THAT HOLDS EVERYWHERE ON THIS TAB.

    pledged = dispatched + never dispatched
    dispatched = delivered + still in flight + unaccounted

    Nothing on this tab adds two of those and calls the sum progress.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import charts
import components as C
import data
from theme import CONFIRMED_GREEN, FLAG_RED, NEUTRAL, NOISE_AMBER, SNOWFLAKE_BLUE

#: The published ratio the synthetic attrition is tuned against: 371
#: trucks collected inside Gaza from 590 moved to the crossing. WFP State
#: of Palestine External Situation Report 55, 6 June 2025.
WFP_COLLECTED = 371
WFP_MOVED = 590
WFP_RATIO = WFP_COLLECTED / WFP_MOVED

#: The rule that actually ships, from sql/08_geospatial_h3.sql. Quoted
#: here so the prose on the tab cannot drift away from the SQL.
SHIPPED_RULE_KM = 400

#: Delivery corridors, spelled out. A two letter code is a database key,
#: not a place. Same mapping as Tab 03; a country has one name in this
#: application.
COUNTRY_NAMES = {
    "IN": "India",
    "SD": "Sudan",
    "PS": "Palestine",
    "BD": "Bangladesh",
    "NE": "Niger",
}

LENSES = ("by district", "by corridor")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _f(value, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _i(value, default: int = 0) -> int:
    return int(_f(value, default))


def _pct(value: float, digits: int = 1) -> str:
    return f"{value * 100:.{digits}f}%"


def _country(code) -> str:
    code = "" if code is None or pd.isna(code) else str(code)
    return COUNTRY_NAMES.get(code, code or "unrecorded")


def _picker(options, key: str, default: str) -> str:
    """A segmented control, or buttons where the control does not exist.

    st.segmented_control arrived in Streamlit 1.40 and Streamlit in
    Snowflake pins its own version, so the older path has to be there.
    """
    state_key = f"{key}_value"
    chosen = st.session_state.get(state_key, default)
    if chosen not in options:
        chosen = default

    control = getattr(st, "segmented_control", None)
    if control is not None:
        selected = control(key, options=list(options), default=chosen,
                           key=key, label_visibility="collapsed")
        if selected:
            st.session_state[state_key] = selected
            return selected
        return chosen

    for column, option in zip(st.columns(len(options), gap="small"), options):
        with column:
            if st.button(option, key=f"{key}_{option}",
                         use_container_width=True,
                         type="primary" if option == chosen else "secondary"):
                st.session_state[state_key] = option
                chosen = option
    return chosen


def _swatch(colour: str, label: str) -> str:
    """An inline legend token, for a panel head rather than a chart."""
    return ('<span class="gp-swatch"><i style="background:' + colour
            + '"></i>' + label + "</span>")


# ---------------------------------------------------------------------------
# S3 / the ladder
# ---------------------------------------------------------------------------


def _ladder(f) -> dict:
    """The five figures every section on this tab is measured against."""
    pledged = _f(f["pledged_usd"])
    dispatched = _f(f["dispatched_usd"])
    delivered = _f(f["delivered_usd"])
    unaccounted = _f(f["unaccounted_usd"])
    never = max(_f(f["never_dispatched_usd"]), 0.0)
    return {
        "pledged_usd": pledged,
        "dispatched_usd": dispatched,
        "delivered_usd": delivered,
        "unaccounted_usd": unaccounted,
        "never_dispatched_usd": never,
        "in_flight_usd": max(dispatched - delivered - unaccounted, 0.0),
        "delivery_rate": _f(f["delivery_rate"]),
        "events": _i(f["events"]),
    }


def _flow_section(stages: dict) -> None:
    C.section("From a pledge to a person")
    with C.panel():
        C.panel_head(
            "Every dollar in the corpus, and where it stopped",
            note_html=(
                _swatch(CONFIRMED_GREEN, "delivered")
                + _swatch(SNOWFLAKE_BLUE, "in flight")
                + _swatch(FLAG_RED, "unaccounted")
                + _swatch(NEUTRAL, "never dispatched")
            ),
        )
        st.plotly_chart(
            charts.attrition_sankey(stages, height=380),
            use_container_width=True, config=charts.bare_config(),
        )
        C.readout([
            (C.usd(stages["never_dispatched_usd"]), "never left the pledge"),
            (C.usd(stages["in_flight_usd"]), "still in flight"),
            (C.usd(stages["unaccounted_usd"]), "unaccounted"),
            (_pct(stages["delivery_rate"]), "delivered of dispatched"),
        ], flag="unaccounted")
        C.source_note(
            "Link width is dollars. The ribbon into unaccounted is red and "
            "is deliberately the heaviest element on the tab, because it is "
            "the one the sector's annual reports tend to render as a "
            "footnote. The ribbon beside it is blue and is not a finding: "
            "that money is in a warehouse, not missing, and the two are "
            "never added together here."
        )


# ---------------------------------------------------------------------------
# S4 / where it stops
# ---------------------------------------------------------------------------


def _where_it_stops() -> None:
    C.section("Where it stops")
    lens = _picker(LENSES, "gp_l_lens", LENSES[0])

    if lens == "by corridor":
        frame = data.run("Q_CORRIDOR_ATTRITION")
        if frame.empty:
            C.note("No corridor data.")
            return
        frame = frame.assign(place=[_country(c) for c in frame["country"]])
        label_column = "place"
        # panel_head escapes its note, so the separator is the literal
        # character. An entity here renders as &MIDDOT; on the page.
        where = "marts.delivery_geometry · marts.district_dim"
        lead = (
            "Five corridors, ordered by the share of what passed through "
            "them that nobody can account for. The spread is narrow on "
            "purpose: the generator was tuned to one published national "
            "ratio, so a corridor that stood far apart from the others "
            "would be an artefact of the tuning rather than a finding."
        )
    else:
        frame = data.run("Q_DISTRICT_ATTRITION")
        if frame.empty:
            C.note("No district data.")
            return
        frame = frame.assign(place=frame["district"])
        label_column = "place"
        where = "marts.delivery_geometry"
        lead = (
            "Sixteen districts, ordered by the share of what passed through "
            "them that nobody can account for. Read the red segment, not "
            "the length of the bar: every bar is the same length, because "
            "each one is that district's own money divided three ways."
        )

    moved = float(frame["moved_usd"].sum())
    delivered = float(frame["delivered_usd"].sum())
    in_flight = float(frame["in_flight_usd"].sum())
    unaccounted = float(frame["unaccounted_usd"].sum())
    worst = frame.iloc[0]
    best = frame.iloc[-1]

    with C.panel():
        C.panel_head("Delivered, in flight, unaccounted", where)
        C.note(lead)
        st.plotly_chart(
            charts.attrition_split(
                frame, label_column,
                height=max(300, 30 * len(frame) + 110),
            ),
            use_container_width=True, config=charts.bare_config(),
        )
        C.readout([
            (str(len(frame)), "places"),
            (C.usd(moved), "moved through them"),
            (_pct(_f(worst["unaccounted_rate"])),
             f"widest gap, {worst['place']}"),
            (_pct(_f(best["unaccounted_rate"])),
             f"narrowest, {best['place']}"),
        ], flag=f"widest gap, {worst['place']}")
        C.source_note(
            "Shares of dollars moved, not of dollars pledged. Money that "
            "was pledged and never dispatched carries no amount at all and "
            "cannot be split three ways, so it is reported once, in the "
            "flow diagram above, and left out of every bar here rather "
            "than silently folded into one of them."
        )

    rows = []
    for row in frame.itertuples():
        rows.append([
            row.place,
            _country(getattr(row, "country", None))
            if lens == "by district" else f"{_i(getattr(row, 'districts', 0))}",
            f"{_i(row.events):,}",
            C.usd(_f(row.moved_usd)),
            C.usd(_f(row.delivered_usd)),
            C.usd(_f(row.in_flight_usd)),
            C.usd(_f(row.unaccounted_usd)),
            _pct(_f(row.delivery_rate)),
            _pct(_f(row.unaccounted_rate)),
            f"{_f(row.mean_transit_hours):.0f} h",
        ])
    C.table(
        [
            ("place", "gp-td-lead"),
            ("corridor" if lens == "by district" else "districts", ""),
            ("events", "gp-td-num"),
            ("moved", "gp-td-num"),
            ("delivered", "gp-td-num"),
            ("in flight", "gp-td-num"),
            ("unaccounted", "gp-td-num"),
            ("delivered share", "gp-td-num"),
            ("unaccounted share", "gp-td-num"),
            ("mean transit", "gp-td-num"),
        ],
        rows,
    )
    C.source_note(
        "The last two columns are the same two dollar columns as shares of "
        "what moved, which is what the bars above are drawn from. Mean "
        "transit is over deliveries that recorded both a dispatch and an "
        "arrival; an unaccounted delivery never recorded an arrival, so it "
        "contributes no hours rather than contributing a zero."
    )


# ---------------------------------------------------------------------------
# S5 / calibration, made visible
# ---------------------------------------------------------------------------


def _calibration(stages: dict) -> None:
    C.section("Calibration")
    weekly = data.run("Q_DELIVERY_RATE_WEEKLY")

    left, right = st.columns([3, 2], gap="medium")

    with left:
        with C.panel():
            C.panel_head("Weekly delivery rate against the published ratio",
                         "marts.delivery_geometry")
            if weekly.empty:
                C.note("No weekly series.")
            else:
                st.plotly_chart(
                    charts.delivery_rate_weekly(
                        weekly,
                        benchmark=WFP_RATIO,
                        benchmark_label=(
                            f"WFP published ratio, {WFP_RATIO * 100:.1f}%"),
                        height=306,
                    ),
                    use_container_width=True, config=charts.bare_config(),
                )
                rates = [_f(v) for v in weekly["delivery_rate"]]
                C.readout([
                    (str(len(weekly)), "weeks"),
                    (_pct(min(rates)), "quietest week"),
                    (_pct(max(rates)), "best week"),
                    (_pct(stages["delivery_rate"]), "whole corpus"),
                ])

    with right:
        with C.panel():
            C.panel_head("What it is tuned to", "wfp sitrep 55")
            st.markdown(
                '<div class="gp-card"><div class="gp-card-blurb">'
                "&ldquo;590 trucks moved from Ashdod to Kerem Shalom, of "
                "which 371 were collected inside Gaza; organised criminal "
                "looting estimated by field monitors at about 20 percent of "
                "cases.&rdquo;"
                "</div></div>",
                unsafe_allow_html=True,
            )
            C.kv_rows([
                ("published ratio",
                 f"{WFP_COLLECTED} of {WFP_MOVED}, {WFP_RATIO * 100:.1f}%"),
                ("this corpus", _pct(stages["delivery_rate"])),
                ("difference",
                 f"{abs(stages['delivery_rate'] - WFP_RATIO) * 100:.2f} "
                 "percentage points"),
                ("what is real", "the ratio"),
                ("what is modelled", "every delivery behind it"),
            ])
            C.source_note(
                "WFP State of Palestine External Situation Report 55, "
                "6 June 2025. The aggregate is calibrated to this figure. "
                "The individual delivery events are synthetic and are not "
                "claimed to be real."
            )

    C.source_note(
        "A calibrated headline is a claim about one number, so the weeks it "
        "is made of are drawn beside it. The corpus sits "
        f"{abs(stages['delivery_rate'] - WFP_RATIO) * 100:.2f} points from "
        "the published ratio, and the weekly spread around it is the "
        "residue the tuning leaves behind rather than something the "
        "generator was asked to produce."
    )


# ---------------------------------------------------------------------------
# S6 / transit, honestly
# ---------------------------------------------------------------------------


def _transit() -> None:
    C.section("Could it physically have got there")
    transit = data.run("Q_TRANSIT_FEASIBILITY")
    audit = data.run("Q_TRANSIT_RULE_AUDIT")
    if transit.empty or audit.empty:
        C.note("No transit records.")
        return
    a = audit.iloc[0]

    rule_matches = _i(a["rule_matches"])
    labelled = _i(a["labelled"])
    masked = _i(a["masked"])
    above_truck = _i(a["above_truck"])
    with_speed = _i(a["with_speed"])
    median_kmh = _f(a["median_kmh"])

    with C.panel():
        C.panel_head(
            "Implied speed of every delivery that has one",
            note_html=(
                _swatch(NEUTRAL, "road")
                + _swatch(SNOWFLAKE_BLUE, "air freight")
                + _swatch(NOISE_AMBER, "above cruise")
            ),
        )
        st.plotly_chart(
            charts.transit_speed_profile(
                transit, instantaneous=rule_matches, height=352),
            use_container_width=True, config=charts.bare_config(),
        )
        C.readout([
            (f"{with_speed:,}", "with a finite speed"),
            (f"{median_kmh:,.0f} km/h", "median implied speed"),
            (f"{_i(a['above_jet']):,}", "above jet cruise"),
            (f"{rule_matches:,}", "arrived in the hour they left"),
        ], flag="arrived in the hour they left")

    with C.panel():
        C.panel_head("What the rule actually says",
                     "sql/08_geospatial_h3.sql")
        C.note(
            "This section used to plot hours against kilometres and shade "
            "everything under a ninety kilometre an hour line as physically "
            f"impossible. That shading caught <b>{above_truck:,}</b> of "
            f"<b>{with_speed:,}</b> deliveries. It was not a finding, it was "
            "a broken ruler: the distance is measured from the "
            "organisation's registered filing address in the United States "
            "to a delivery on another continent, so ten thousand kilometres "
            f"in two days is {median_kmh:,.0f} km/h, which is air freight "
            "doing what air freight does. A test that flags four deliveries "
            "in five has found nothing."
        )
        C.sql_block(
            "CASE\n"
            "  WHEN status = 'UNACCOUNTED'   THEN 'NEVER_ARRIVED'\n"
            "  WHEN hops > max_hops          THEN 'OUTSIDE_FOOTPRINT'\n"
            "  WHEN transit_hours < 1\n"
            f"   AND km_from_base > {SHIPPED_RULE_KM}  THEN 'IMPOSSIBLE_TRANSIT'\n"
            "  ELSE 'PLAUSIBLE'\n"
            "END",
            "the shipped rule, marts.delivery_geometry",
        )
        C.readout([
            (f"{rule_matches:,}", "match the transit rule"),
            (f"{labelled:,}", "carry the label"),
            (f"{masked:,}", "already failed an earlier rule"),
            (C.usd(_f(a["rule_usd"])), "worth"),
        ])
        C.note(
            f"The CASE is ordered, so the {masked:,} deliveries that fail "
            "the transit rule <i>and</i> land outside the declared footprint "
            "are labelled by whichever branch matched first. They are "
            "counted once, not twice, which is why the number on the map "
            f"reads {labelled:,} and the number of records that fail this "
            f"particular test reads {rule_matches:,}. Both are true and "
            "they are different questions."
        )
        C.source_note(
            "A delivery recorded as arriving in the hour it left has no "
            "implied speed, only a division by zero, so it is annotated on "
            "the chart rather than binned into it. Putting it in the "
            "histogram would place the fastest events in the corpus at the "
            "slow end of it. This remains a reason to look closer, never a "
            "verdict about a person."
        )


# ---------------------------------------------------------------------------
# S7 / the handoff
# ---------------------------------------------------------------------------


def _handoff(districts) -> None:
    C.section("The handoff")
    C.note(
        "This tab shows you where the money stopped. The next one refuses "
        "to tell you which person it stopped short of. Carry a district "
        "across and the same filter returns under an aggregation policy, "
        "which is the moment the two halves of the argument join."
    )

    names = list(districts["district"]) if "district" in districts else []
    with C.panel():
        C.panel_head("Carry a district into The Wall", "marts.delivery_geometry")
        chosen = st.selectbox(
            "district",
            ["none"] + names,
            key="gp_l_district",
            label_visibility="collapsed",
        )
        if chosen == "none":
            C.note(
                "Nothing is carried yet. The Wall opens on the whole "
                "corpus until a district is chosen here."
            )
            return

        st.session_state["gp_focus_district"] = chosen
        ladder = data.run("Q_DISTRICT_LADDER", (chosen,))
        if ladder.empty:
            C.note("No records for that district.")
            return
        d = ladder.iloc[0]
        moved = _f(d["moved_usd"])
        delivered = _f(d["delivered_usd"])
        unaccounted = _f(d["unaccounted_usd"])

        st.markdown(C.chip(f"{chosen} carried to The Wall", "chain"),
                    unsafe_allow_html=True)
        C.kv_rows([
            ("deliveries", f"{_i(d['events']):,}"),
            ("organisations", f"{_i(d['orgs']):,}"),
            ("pledged", C.usd(_f(d["pledged_usd"]))),
            ("moved", C.usd(moved)),
            ("delivered", C.usd(delivered)),
            ("still in flight", C.usd(_f(d["in_flight_usd"]))),
            ("unaccounted", C.usd(unaccounted)),
            ("outside the declared footprint",
             f"{_i(d['outside_footprint']):,} deliveries"),
            ("arrived in the hour they left",
             f"{_i(d['impossible_transit']):,} deliveries"),
            ("mean transit", f"{_f(d['mean_transit_hours']):.0f} hours"),
        ])
        C.readout([
            (_pct(delivered / moved if moved else 0.0), "delivered"),
            (_pct(unaccounted / moved if moved else 0.0), "unaccounted"),
            (f"{_i(d['orgs']):,}", "organisations involved"),
        ], flag="unaccounted")
        C.source_note(
            "Every figure here is an aggregate. No beneficiary column is "
            "selected by this query, and that is not an oversight: the "
            "next tab is the one allowed to answer questions about people, "
            "and it only answers them under a policy."
        )


# ---------------------------------------------------------------------------
# how it works
# ---------------------------------------------------------------------------


def _how_it_works() -> None:
    C.section("How this tab works")
    C.step_explainer([
        ("Split the money four ways, once",
         "Pledged separates into dispatched and never dispatched. "
         "Dispatched separates into delivered, still in flight and "
         "unaccounted. Those are the only buckets on this tab and nothing "
         "here adds two of them together."),
        ("Rank places by the gap, not by the total",
         "A district is ordered by the share of what passed through it "
         "that nobody can account for. Ranking by dollars would rank by "
         "size, and the largest district would top the list every time "
         "whether or not anything went wrong in it."),
        ("Check the physics against a real speed",
         "Every delivery with a dispatch and an arrival gets an implied "
         "speed, read against a truck and a freight aircraft. Almost all "
         "of them sit in the air-freight band, which is the boring and "
         "correct answer. The records worth a second look are the ones "
         "that recorded no elapsed time at all."),
        ("Calibrate to something published, and show the spread",
         "The aggregate delivery rate is tuned to a World Food Programme "
         "ratio from June 2025. The weekly series is drawn beside it so a "
         "single tuned percentage cannot pass itself off as a measurement."),
        ("Hand the district over, and stop",
         "The selector carries a district into The Wall. This tab never "
         "names a person, and the query behind the handoff does not select "
         "a column that could."),
    ])


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------


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
    stages = _ladder(flow.iloc[0])

    districts = data.run("Q_DISTRICT_ATTRITION")

    # ---------------------------------------------------------------- S1
    C.hero(
        _pct(stages["delivery_rate"], 1),
        "of dispatched value reaches a confirmed delivery",
    )

    # ---------------------------------------------------------------- S2
    C.stat_band([
        (C.usd(stages["pledged_usd"]), "pledged"),
        (C.usd(stages["dispatched_usd"]), "dispatched"),
        (C.usd(stages["delivered_usd"]), "delivered"),
        (C.usd(stages["in_flight_usd"]), "still in flight"),
        (C.usd(stages["unaccounted_usd"]), "unaccounted"),
    ])
    C.source_note(
        f"{stages['events']:,} disbursement events. Pledged is dispatched "
        "plus never dispatched; dispatched is the three cards to its right. "
        "The fourth card is the one that is routinely reported as though it "
        "were the fifth."
    )

    # ---------------------------------------------------------------- S3
    _flow_section(stages)

    # ---------------------------------------------------------------- S4
    _where_it_stops()

    # ---------------------------------------------------------------- S5
    _calibration(stages)

    # ---------------------------------------------------------------- S6
    _transit()

    # ---------------------------------------------------------------- S7
    _handoff(districts)

    _how_it_works()

    C.provenance_footer(
        "IATI transaction records where available. Delivery events "
        "synthetic, with attrition tuned so the aggregate delivery share "
        "sits close to the published WFP ratio of 371 collected from 590 "
        "moved. Status splits and geometry verdicts come from "
        "MARTS.DELIVERY_GEOMETRY; corridor names come from "
        "MARTS.DISTRICT_DIM. Straight-line distance via ST_DISTANCE over "
        "ST_POINT, grid distance via H3_GRID_DISTANCE, both computed in "
        "SQL rather than in the application."
    )
