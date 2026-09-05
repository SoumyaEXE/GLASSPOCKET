"""Tab 03 / Follow The Money. Build Spec Section 07.

    Every delivery on a map, coloured by whether the geometry makes sense.

The signature visual of the whole application.

PREREQUISITE, TRAP 04
    External Offerings Terms must be accepted in Snowsight or the pydeck
    tile layer renders blank with no error. The fallback below is a Plotly
    scatter over latitude and longitude, which loses elevation but keeps
    the geography.

WHY THE MAP LOOKED EMPTY, AND WHAT WAS ACTUALLY WRONG WITH IT.

    The first version drew 6,771 H3 resolution-7 cells extruded with
    ``elevation_scale=40``. A resolution-7 cell is about five kilometres
    across, which at world zoom is under one pixel, and the tallest cell
    carried $34,169, which at that scale is a column 1,367 KILOMETRES
    high. So the map rendered as a few dozen hair-thin needles on an
    otherwise blank world: technically every delivery was on it, and
    visually there was nothing there.

    Three things fix it and all three are here.

      * The elevation scale is computed from the data so the tallest
        column is a fixed, sensible height rather than a fixed multiplier
        applied to whatever the numbers happen to be.

      * The grid is one of three layers, not the only one. Donation flows
        draws every disbursement as an arc from the organisation's
        registered address to where the money landed, which is 8,545
        strands across the Atlantic and the Indian Ocean and is the
        picture the tab is actually about. Delivery points draws the raw
        events, which at world zoom is the honest density map the grid
        cannot be.

      * The camera starts where the data is.

    Nothing was added to the corpus to fill the map. Every layer draws
    the same 8,545 disbursements the KPI band counts.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import charts
import components as C
import data
from theme import SNOWFLAKE_BLUE

#: Fill colour per geometry verdict, matching charts.VERDICT_COLOURS. A
#: verdict has one colour in this application and the map does not get
#: its own dialect.
VERDICT_RGB = {
    "PLAUSIBLE": (41, 181, 232),
    "OUTSIDE_FOOTPRINT": (229, 72, 77),
    "IMPOSSIBLE_TRANSIT": (245, 166, 35),
    "NEVER_ARRIVED": (176, 36, 39),
}

LAYERS = ("donation flows", "delivery grid", "delivery points")

#: The delivery corridors, spelled out. A two letter code is a database
#: key, not a place.
COUNTRY_NAMES = {
    "IN": "India",
    "SD": "Sudan",
    "PS": "Palestine",
    "BD": "Bangladesh",
    "NE": "Niger",
}

#: The tallest extruded column, in metres. Everything else is scaled
#: against it, so the picture cannot be broken by a change in the size of
#: the dollars.
MAX_COLUMN_M = 160_000.0

TOOLTIP_STYLE = {
    # Tooltips escape the global stylesheet, so Geist is set explicitly
    # here. Section 03: no monospace anywhere, including tooltips.
    "fontFamily": "Geist Variable, Geist, sans-serif",
    "fontSize": "13px",
    "backgroundColor": "#FFFFFF",
    "color": "#16181D",
    "border": "1px solid #E4E7EB",
    "borderRadius": "6px",
    "padding": "8px 10px",
}


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


def _verdict_rgb(frame):
    """Three integer colour columns derived from the verdict column."""
    colours = [VERDICT_RGB.get(str(v), VERDICT_RGB["PLAUSIBLE"])
               for v in frame["geometry_verdict"]]
    return (
        [c[0] for c in colours],
        [c[1] for c in colours],
        [c[2] for c in colours],
    )


# ---------------------------------------------------------------------------
# map layers
# ---------------------------------------------------------------------------


def _grid_deck(hexes):
    """C03-1. pydeck H3HexagonLayer, extruded, pitch 45.

    The elevation scale is derived rather than hard-coded. A fixed
    multiplier turns dollars into metres at whatever exchange rate the
    corpus happens to imply, and this corpus implied columns over a
    thousand kilometres tall.
    """
    import pydeck as pdk

    top = max(float(hexes["usd"].max() or 1.0), 1.0)
    rows = hexes.assign(
        elevation=hexes["usd"].fillna(0),
        usd_label=hexes["usd"].fillna(0).map(lambda v: f"${v:,.0f}"),
        flag_label=hexes["flag_rate"].fillna(0).map(lambda v: f"{v:.0%}"),
        # Fill interpolates Snowflake Blue at flag rate zero to Flag Red
        # at flag rate one.
        r=(41 + (229 - 41) * hexes["flag_rate"].fillna(0)).astype(int),
        g=(181 + (72 - 181) * hexes["flag_rate"].fillna(0)).astype(int),
        b=(232 + (77 - 232) * hexes["flag_rate"].fillna(0)).astype(int),
    )

    layer = pdk.Layer(
        "H3HexagonLayer",
        rows,
        get_hexagon="h3",
        get_fill_color="[r, g, b, 200]",
        get_elevation="elevation",
        elevation_scale=MAX_COLUMN_M / top,
        extruded=True,
        coverage=1.0,
        pickable=True,
        auto_highlight=True,
    )

    view = pdk.ViewState(
        latitude=float(rows["centroid_lat"].median()),
        longitude=float(rows["centroid_lon"].median()),
        zoom=2.7, pitch=45, bearing=0,
    )
    tooltip = {
        "html": "<b>{district}</b><br/>{n} deliveries<br/>{usd_label}"
                "<br/>flag rate {flag_label}",
        "style": TOOLTIP_STYLE,
    }
    return _deck(pdk, [layer], view, tooltip)


def _flow_deck(flows):
    """C03-1b. Every disbursement as an arc, origin to destination.

    The origin is the organisation's registered filing address and the
    destination is where the delivery says it landed. An arc crossing an
    ocean is what an international NGO looks like and is not a finding on
    its own; the colour at the far end is the finding, and it comes from
    the footprint test in sql/08_geospatial_h3.sql rather than from the
    length of the line.
    """
    import pydeck as pdk

    r, g, b = _verdict_rgb(flows)
    top = max(float(flows["amount_usd"].max() or 1.0), 1.0)
    rows = flows[["org_name", "district", "origin_city", "origin_state",
                  "origin_lat", "origin_lon", "dest_lat", "dest_lon"]].assign(
        r=r, g=g, b=b,
        width=(0.4 + 1.5 * (flows["amount_usd"].fillna(0) / top) ** 0.5),
        usd_label=flows["amount_usd"].fillna(0).map(lambda v: f"${v:,.0f}"),
        verdict_label=[str(v).replace("_", " ").lower()
                       for v in flows["geometry_verdict"]],
    )

    layer = pdk.Layer(
        "ArcLayer",
        rows,
        get_source_position="[origin_lon, origin_lat]",
        get_target_position="[dest_lon, dest_lat]",
        # The source end is muted so the eye reads the destination, which
        # is where the verdict lives. Colouring both ends by verdict made
        # the American seaboard look flagged.
        get_source_color="[156, 163, 175, 70]",
        get_target_color="[r, g, b, 150]",
        get_width="width",
        get_height=0.36,
        width_min_pixels=0.4,
        width_max_pixels=2,
        great_circle=True,
        pickable=True,
        auto_highlight=True,
    )

    view = pdk.ViewState(latitude=24.0, longitude=-16.0, zoom=1.5,
                         pitch=24, bearing=0)
    tooltip = {
        "html": "<b>{org_name}</b><br/>{origin_city}, {origin_state}"
                " &rarr; {district}<br/>{usd_label}<br/>{verdict_label}",
        "style": TOOLTIP_STYLE,
    }
    return _deck(pdk, [layer], view, tooltip)


def _points_deck(flows):
    """C03-1c. The raw delivery events, one dot each.

    The grid is the Snowflake story and this is the density. 8,545 points
    over sixteen districts show how thick the corridors really are, which
    a sub-pixel hexagon cannot.
    """
    import pydeck as pdk

    r, g, b = _verdict_rgb(flows)
    top = max(float(flows["amount_usd"].max() or 1.0), 1.0)
    rows = flows[["org_name", "district", "dest_lat", "dest_lon"]].assign(
        r=r, g=g, b=b,
        radius=(6000 + 34000 * (flows["amount_usd"].fillna(0) / top) ** 0.5),
        usd_label=flows["amount_usd"].fillna(0).map(lambda v: f"${v:,.0f}"),
        verdict_label=[str(v).replace("_", " ").lower()
                       for v in flows["geometry_verdict"]],
    )

    layer = pdk.Layer(
        "ScatterplotLayer",
        rows,
        get_position="[dest_lon, dest_lat]",
        get_fill_color="[r, g, b, 150]",
        get_radius="radius",
        radius_min_pixels=1.6,
        radius_max_pixels=16,
        stroked=False,
        pickable=True,
        auto_highlight=True,
    )

    view = pdk.ViewState(
        latitude=float(rows["dest_lat"].median()),
        longitude=float(rows["dest_lon"].median()),
        zoom=2.5, pitch=0, bearing=0,
    )
    tooltip = {
        "html": "<b>{district}</b><br/>{org_name}<br/>{usd_label}"
                "<br/>{verdict_label}",
        "style": TOOLTIP_STYLE,
    }
    return _deck(pdk, [layer], view, tooltip)


def _deck(pdk, layers, view, tooltip):
    """Assemble a Deck, asking for a taller canvas where that is offered."""
    try:
        return pdk.Deck(layers=layers, initial_view_state=view,
                        tooltip=tooltip, map_style="light", height=560)
    except TypeError:                        # pragma: no cover
        # ``height`` is not in every pydeck. Losing it costs a shorter
        # map; raising a TypeError costs the whole tab.
        return pdk.Deck(layers=layers, initial_view_state=view,
                        tooltip=tooltip, map_style="light")


def _scatter_fallback(hexes):
    """Fallback if the tile layer will not cooperate.

    Loses elevation but keeps the geography, which is the part that
    carries the argument.
    """
    fig = go.Figure()
    fig.add_scattergeo(
        lat=hexes["centroid_lat"], lon=hexes["centroid_lon"],
        mode="markers",
        marker=dict(
            size=(6 + 26 * (hexes["usd"] / max(hexes["usd"].max(), 1)) ** 0.5),
            color=hexes["flag_rate"],
            colorscale=[[0, "#29B5E8"], [1, "#E5484D"]],
            cmin=0, cmax=1, opacity=0.75,
            line=dict(width=0.5, color="#FFFFFF"),
        ),
        customdata=hexes[["district", "n", "flag_rate"]],
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]} deliveries"
                      "<br>flag rate %{customdata[2]:.0%}<extra></extra>",
    )
    fig.update_geos(
        showcountries=True, countrycolor="#E4E7EB",
        showland=True, landcolor="#F7F8FA",
        showocean=True, oceancolor="#FFFFFF",
        coastlinecolor="#E4E7EB", framecolor="#E4E7EB",
    )
    return charts.style_fig(fig, height=460)


# ---------------------------------------------------------------------------
# sections
# ---------------------------------------------------------------------------


def _map_section(hexes, flows) -> None:
    layer = _picker(LAYERS, "gp_m_layer", LAYERS[0])

    use_fallback = st.session_state.get("gp_m_fallback", False)
    if not use_fallback:
        try:
            if layer == LAYERS[0] and not flows.empty:
                deck = _flow_deck(flows)
            elif layer == LAYERS[2] and not flows.empty:
                deck = _points_deck(flows)
            else:
                deck = _grid_deck(hexes)
            st.pydeck_chart(deck, use_container_width=True)
        except Exception:                     # noqa: BLE001
            st.session_state["gp_m_fallback"] = True
            use_fallback = True

    if use_fallback:
        st.plotly_chart(_scatter_fallback(hexes), use_container_width=True,
                        config=charts.bare_config())
        C.source_note(
            "Rendering the flat fallback. The extruded hexagon layer needs "
            "External Offerings Terms accepted in Snowsight, because map "
            "tiles come from Carto, a third-party offering."
        )
        return

    flagged = (flows["geometry_verdict"] != "PLAUSIBLE").sum() if len(flows) else 0
    C.readout([
        (f"{len(flows):,}", "disbursements drawn"),
        (C.usd(_f(flows["amount_usd"].sum()) if len(flows) else 0), "value drawn"),
        (f"{int(flagged):,}", "flagged geometry"),
        (f"{_f(flows['km_from_base'].max()) if len(flows) else 0:,.0f} km",
         "longest single flow"),
    ], flag="flagged geometry")

    if layer == LAYERS[0]:
        C.source_note(
            "Every one of the disbursements in the band above, drawn as a "
            "great-circle arc from the organisation's registered filing "
            "address to where the delivery says it landed. The far end is "
            "coloured by the geometry verdict; the near end is deliberately "
            "not, because colouring both ends made the American seaboard "
            "look flagged. A long arc is an international NGO doing what it "
            "said it would do and is never on its own a finding."
        )
    elif layer == LAYERS[1]:
        C.source_note(
            "Height is value delivered, scaled so the largest cell is a "
            "fixed height rather than a fixed multiple of the dollars. "
            "Colour runs from Snowflake Blue at a flag rate of zero to Flag "
            "Red at one. Cells are H3 resolution 7, indexed in SQL with "
            "H3_LATLNG_TO_CELL_STRING."
        )
    else:
        C.source_note(
            "One dot per delivery event, sized by amount and coloured by "
            "verdict. This is the layer that shows how thick a corridor "
            "actually is: the H3 grid is five kilometres to a cell and "
            "disappears at this zoom, which is exactly the sort of thing "
            "that makes a full map look like an empty one."
        )


def _where_it_landed(districts) -> None:
    if districts.empty:
        C.source_note("No district totals.")
        return

    timeline = data.run("Q_MONEY_OVER_TIME")
    row_height = max(300, 26 * len(districts) + 70)
    dcol, tcol = st.columns([1, 1.15], gap="large")

    with dcol:
        with C.panel():
            C.panel_head("Where it landed", "value delivered, by district")
            bars = charts.horizontal_bar(
                districts["district"],
                [_f(v) / 1e6 for v in districts["usd"]],
                colour=SNOWFLAKE_BLUE, height=row_height,
                value_fmt="${:.2f}M",
                hover="%{y}: $%{x:.2f}M<extra></extra>",
            )
            bars.update_xaxes(tickprefix="$", ticksuffix="M")
            st.plotly_chart(bars, use_container_width=True,
                            config=charts.bare_config())
            C.readout([
                (f"{len(districts):,}", "districts"),
                (C.usd(_f(districts["usd"].sum())), "traced"),
                (f"{_f(districts['flag_rate'].mean()) * 100:.1f}%",
                 "mean flag rate"),
            ], flag="mean flag rate")

    with tcol:
        with C.panel():
            C.panel_head("Money in motion", "cumulative, by week dispatched")
            if timeline.empty:
                C.source_note("No dispatch dates recorded.")
            else:
                st.plotly_chart(
                    charts.money_over_time(timeline, height=row_height),
                    use_container_width=True, config=charts.bare_config(),
                )
                delivered = _f(timeline["delivered_usd"].sum())
                unaccounted = _f(timeline["unaccounted_usd"].sum())
                total = _f(timeline["dispatched_usd"].sum())
                C.readout([
                    (f"{len(timeline)}", "weeks tracked"),
                    (C.usd(delivered), "delivered"),
                    (C.usd(max(total - delivered - unaccounted, 0.0)),
                     "still in flight"),
                    (C.usd(unaccounted), "unaccounted"),
                ], flag="unaccounted")

    C.table(
        [("district", ""), ("country", ""), ("deliveries", "gp-td-num"),
         ("organisations", "gp-td-num"), ("traced", "gp-td-num"),
         ("delivered", "gp-td-num"), ("unaccounted", "gp-td-num"),
         ("receipts on chain", "gp-td-num"), ("flag rate", "gp-td-num")],
        [
            (
                f'<span class="gp-td-lead">{C.escape(str(row.district))}</span>',
                C.escape(COUNTRY_NAMES.get(str(row.country or "").upper(),
                                          str(row.country or ""))),
                f"{_i(row.deliveries):,}",
                f"{_i(row.orgs):,}",
                C.usd(_f(row.usd)),
                C.usd(_f(row.delivered_usd)),
                C.usd(_f(row.unaccounted_usd)),
                f"{_i(row.receipts_on_chain):,}",
                f"{_f(row.flag_rate) * 100:.1f}%",
            )
            for row in districts.itertuples()
        ],
        widths=("15%", "8%", "10%", "12%", "11%", "11%", "11%", "12%", "10%"),
    )
    C.source_note(
        "Sixteen districts, taken from IATI Datastore activity locations, "
        "so the geography is real even though the disbursement events "
        "against it are seeded and labelled. Receipts on chain counts rows "
        "in the mint log, which is a live migration to devnet rather than a "
        "finished number: a receipt that has not been written is a receipt "
        "that does not exist, and the column says so rather than rounding "
        "up to the intention."
    )


def _programmes() -> None:
    programmes = data.run("Q_PROGRAMME_FLOW")
    if programmes.empty:
        C.source_note("No programme totals.")
        return

    with C.panel():
        C.panel_head("Where each appeal ended up", "staging.disbursements")
        st.plotly_chart(
            charts.programme_flow(programmes,
                                  height=max(280, 42 * len(programmes) + 80)),
            use_container_width=True, config=charts.bare_config(),
        )
        C.readout([
            (f"{len(programmes)}", "appeals"),
            (C.usd(_f(programmes["delivered_usd"].sum())), "delivered"),
            (C.usd(_f(programmes["in_flight_usd"].sum())), "still in flight"),
            (C.usd(_f(programmes["unaccounted_usd"].sum())), "unaccounted"),
            (C.usd(_f(programmes["pledged_only_usd"].sum())),
             "pledged, never dispatched"),
        ], flag="unaccounted")

    C.table(
        [("appeal", ""), ("disbursements", "gp-td-num"),
         ("districts", "gp-td-num"), ("organisations", "gp-td-num"),
         ("delivered", "gp-td-num"), ("in flight", "gp-td-num"),
         ("unaccounted", "gp-td-num"),
         ("pledged, never dispatched", "gp-td-num")],
        [
            (
                f'<span class="gp-td-lead">'
                f'{C.escape(str(row.programme_code))}</span>',
                f"{_i(row.events):,}",
                f"{_i(row.districts):,}",
                f"{_i(row.orgs):,}",
                C.usd(_f(row.delivered_usd)),
                C.usd(_f(row.in_flight_usd)),
                C.usd(_f(row.unaccounted_usd)),
                C.usd(_f(row.pledged_only_usd)),
            )
            for row in programmes.itertuples()
        ],
        widths=("18%", "12%", "10%", "12%", "12%", "11%", "12%", "13%"),
    )
    C.source_note(
        "The last column is a different measure from the three before it. "
        "Delivered, in flight and unaccounted partition the money that "
        "moved and add to the total; pledged-but-never-dispatched is money "
        "that was promised and never left, which carries no amount at all. "
        "Stacking the four together would produce a tidier bar and a false "
        "one."
    )


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------


def render() -> None:
    C.tab_title(
        "Follow The Money",
        "Every delivery on a map, coloured by whether the geometry makes sense.",
    )

    kpi = data.run("Q_GEOMETRY_KPI")
    k = kpi.iloc[0].to_dict() if len(kpi) else {}

    # ---------------------------------------------------------------- S1
    C.hero(
        f"{_f(k.get('implausible_share')) * 100:.1f}%",
        "of traced disbursements have implausible delivery geometry",
    )

    # ---------------------------------------------------------------- S2
    C.stat_band([
        (C.usd(k.get("usd_traced", 0)), "value traced"),
        (f"{_i(k.get('events')):,}", "disbursements traced"),
        (f"{_i(k.get('orgs')):,}", "organisations moving money"),
        (f"{_i(k.get('districts')):,}", "districts reached"),
        (f"{_i(k.get('cells')):,}", "h3 cells"),
    ])

    # ---------------------------------------------------------------- S3
    C.section("Delivery geography")
    C.note(
        "Three views of the same 8,545 disbursements. <strong>Donation "
        "flows</strong> draws each one as an arc from the filing address "
        "that sent it to the place it landed. <strong>Delivery grid</strong> "
        "is the H3 resolution-7 grid the footprint test is computed on. "
        "<strong>Delivery points</strong> is the raw density. Nothing was "
        "added to the corpus to fill the map; the first version simply drew "
        "five-kilometre cells at world zoom and extruded them a thousand "
        "kilometres high."
    )
    hexes = data.run("Q_HEX_RISK")
    flows = data.run("Q_DELIVERY_FLOWS")

    if hexes.empty and flows.empty:
        st.markdown('<div class="gp-source">No geometry rows.</div>',
                    unsafe_allow_html=True)
    else:
        _map_section(hexes, flows)

    # ---------------------------------------------------------------- S4
    C.section("Where it landed, and when")
    _where_it_landed(data.run("Q_DISTRICT_TOTALS"))

    # ------------------------------------------------------------ S5, S6
    C.section("Does the geometry hold up")
    distances = data.run("Q_DISTANCE_HISTOGRAM")
    verdicts = data.run("Q_VERDICT_COMPOSITION")
    cutoff = 0.0
    hcol, dcol = st.columns(2, gap="large")

    with hcol:
        with C.panel():
            C.panel_head("Distance from base", "kilometres")
            if distances.empty:
                C.source_note("No distances.")
            else:
                cutoff = float(
                    distances.loc[distances["geometry_verdict"] == "PLAUSIBLE",
                                  "km_from_base"].quantile(0.99)
                    if (distances["geometry_verdict"] == "PLAUSIBLE").any()
                    else 500
                )
                st.plotly_chart(
                    charts.distance_histogram(distances, cutoff),
                    use_container_width=True, config=charts.bare_config(),
                )
                beyond = int(
                    (distances["km_from_base"] > cutoff).sum()
                ) if len(distances) else 0
                C.readout([
                    (f"{cutoff:,.0f} km", "plausibility rule"),
                    (f"{beyond:,}", "beyond it"),
                    (f"{_f(distances['km_from_base'].median()):,.0f} km",
                     "median flow"),
                ], flag="beyond it")
        C.source_note(
            f"Kilometres from the organisation's registered address, with "
            f"the plausibility rule at {cutoff:,.0f} "
            "km. The red tail is what a footprint check is for. The check "
            "itself is a grid distance from the declared operating base, "
            "not from this line: an organisation registered in Delaware "
            "that delivers food in Kassala is doing what it said it would "
            "do, and measuring from the postal address would flag every "
            "single event."
        )

    with dcol:
        with C.panel():
            C.panel_head("Verdict composition", "share of events")
            if verdicts.empty:
                C.source_note("No verdicts.")
            else:
                at_risk = verdicts.loc[
                    verdicts["geometry_verdict"] != "PLAUSIBLE", "usd"].sum()
                st.plotly_chart(
                    charts.verdict_donut(verdicts, C.usd(at_risk)),
                    use_container_width=True, config=charts.bare_config(),
                )
                C.readout([
                    (f"{_i(k.get('outside_footprint')):,}", "outside footprint"),
                    (f"{_i(k.get('impossible_transit')):,}", "impossible transit"),
                    (C.usd(at_risk), "value at risk"),
                ], flag="value at risk")
        C.source_note(
            "Four verdicts. Never arrived, outside footprint, impossible "
            "transit, plausible. Each is a statement about geometry, not "
            "about anybody's intent."
        )

    # ---------------------------------------------------------------- S7
    C.section("Where each appeal ended up")
    _programmes()

    # ---------------------------------------------------------------- S8
    C.section("Cell drill-down")
    if not hexes.empty:
        cell = st.selectbox(
            "hexagon", hexes["h3"].tolist()[:200],
            format_func=lambda h: (
                f"{hexes.loc[hexes['h3'] == h, 'district'].iloc[0]} · {h}"),
            key="gp_m_cell", label_visibility="collapsed",
        )
        rows = data.run("Q_CELL_DRILLDOWN", (cell,))
        st.dataframe(rows, use_container_width=True, hide_index=True)
        C.source_note(
            "Hard limit of fifty rows. Streamlit in Snowflake caps a single "
            "backend-to-frontend transfer at 32 MB, so no table in this "
            "application is unbounded."
        )

    # ---------------------------------------------------------------- S9
    C.section("How this works")
    C.step_explainer([
        ("Index to H3",
         "Every delivery point is snapped to a hexagonal cell on a global "
         "grid. Hexagons are used instead of squares because every "
         "neighbour is the same distance away, which makes 'how far' a "
         "simple count."),
        ("Measure grid distance from base",
         "We count how many cells lie between the organisation's declared "
         "operating base and where the delivery says it landed."),
        ("Flag the impossible",
         "A delivery outside the declared footprint, or one that covered "
         "four hundred kilometres in under an hour, is a record that cannot "
         "be right. That is a reason to look closer, never a verdict about "
         "a person."),
        ("Draw all of it, not some of it",
         "Every layer on the map draws all 8,545 disbursements, and the "
         "band under the map states how many were drawn and what they were "
         "worth. A map that quietly plots a sample is a map that cannot be "
         "checked against its own headline."),
    ])

    C.provenance_footer(
        "IATI Datastore activity locations provide the real geography. "
        "Disbursement events are synthetic and labelled. H3 indexing is "
        "performed in SQL at resolution 7 for delivery and resolution 5 for "
        "the organisational footprint. Grid distance via H3_GRID_DISTANCE, "
        "straight-line distance via ST_DISTANCE over ST_POINT. Arc origins "
        "are the registered filing addresses on STAGING.ORGS; district "
        "countries come from MARTS.DISTRICT_DIM; receipt counts come from "
        "ORACLE.MINT_LOG."
    )
