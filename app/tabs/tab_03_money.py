"""Tab 03 / Follow The Money. Build Spec Section 07.

    Every delivery on a map, coloured by whether the geometry makes sense.

The signature visual of the whole application.

PREREQUISITE, TRAP 04
    External Offerings Terms must be accepted in Snowsight or the pydeck
    tile layer renders blank with no error. The fallback below is a Plotly
    scatter over latitude and longitude, which loses elevation but keeps
    the geography.
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

import charts
import components as C
import data


def _hex_layer(hexes):
    """C03-1. pydeck H3HexagonLayer, extruded, pitch 45."""
    import pydeck as pdk

    rows = hexes.assign(
        elevation=hexes["usd"].fillna(0),
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
        get_fill_color="[r, g, b, 190]",
        get_elevation="elevation",
        elevation_scale=40,
        extruded=True,
        coverage=0.92,
        pickable=True,
        auto_highlight=True,
    )

    view = pdk.ViewState(
        latitude=float(rows["centroid_lat"].median()),
        longitude=float(rows["centroid_lon"].median()),
        zoom=2.4,
        pitch=45,
        bearing=0,
    )

    # Tooltips escape the global stylesheet, so Geist is set explicitly
    # here. Section 03: no monospace anywhere, including tooltips.
    tooltip = {
        "html": "<b>{district}</b><br/>{n} deliveries<br/>"
                "flag rate {flag_rate}",
        "style": {
            "fontFamily": "Geist Variable, Geist, sans-serif",
            "fontSize": "13px",
            "backgroundColor": "#FFFFFF",
            "color": "#16181D",
            "border": "1px solid #E4E7EB",
            "borderRadius": "6px",
            "padding": "8px 10px",
        },
    }

    return pdk.Deck(
        layers=[layer], initial_view_state=view, tooltip=tooltip,
        map_style="light",
    )


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


def render() -> None:
    C.tab_title(
        "Follow The Money",
        "Every delivery on a map, coloured by whether the geometry makes sense.",
    )

    kpi = data.run("Q_GEOMETRY_KPI")
    k = kpi.iloc[0] if len(kpi) else {}

    # ---------------------------------------------------------------- S1
    C.hero(
        f"{float(k.get('implausible_share', 0) or 0) * 100:.1f}%",
        "of traced disbursements have implausible delivery geometry",
    )

    # ---------------------------------------------------------------- S2
    C.stat_band([
        (f"{int(k.get('cells', 0) or 0):,}", "hex cells"),
        (C.usd(k.get("usd_traced", 0)), "value traced"),
        (f"{int(k.get('outside_footprint', 0) or 0):,}", "outside footprint"),
        (f"{int(k.get('impossible_transit', 0) or 0):,}", "impossible transit"),
    ])

    # ---------------------------------------------------------------- S3
    C.section("Delivery geography")
    hexes = data.run("Q_HEX_RISK")

    if hexes.empty:
        st.markdown('<div class="gp-source">No geometry rows.</div>',
                    unsafe_allow_html=True)
    else:
        use_fallback = st.session_state.get("gp_m_fallback", False)
        if not use_fallback:
            try:
                st.pydeck_chart(_hex_layer(hexes), use_container_width=True)
            except Exception:                 # noqa: BLE001
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
        else:
            C.source_note(
                "Height is value delivered. Colour runs from Snowflake Blue at "
                "a flag rate of zero to Flag Red at one. Cells are H3 "
                "resolution 7, indexed in SQL with H3_LATLNG_TO_CELL_STRING."
            )

    # ------------------------------------------------------------ S4, S5
    hcol, dcol = st.columns(2, gap="medium")

    with hcol:
        C.section("Distance from base")
        distances = data.run("Q_DISTANCE_HISTOGRAM")
        if distances.empty:
            st.markdown('<div class="gp-source">No distances.</div>',
                        unsafe_allow_html=True)
        else:
            cutoff = float(
                distances.loc[distances["geometry_verdict"] == "PLAUSIBLE",
                              "km_from_base"].quantile(0.99)
                if (distances["geometry_verdict"] == "PLAUSIBLE").any() else 500
            )
            st.plotly_chart(charts.distance_histogram(distances, cutoff),
                            use_container_width=True,
                            config=charts.bare_config())
            C.source_note(
                f"Kilometres from the organisation's declared operating base, "
                f"with the plausibility rule at {cutoff:,.0f} km. The red tail "
                "is what a footprint check is for."
            )

    with dcol:
        C.section("Verdict composition")
        verdicts = data.run("Q_VERDICT_COMPOSITION")
        if verdicts.empty:
            st.markdown('<div class="gp-source">No verdicts.</div>',
                        unsafe_allow_html=True)
        else:
            at_risk = verdicts.loc[
                verdicts["geometry_verdict"] != "PLAUSIBLE", "usd"].sum()
            st.plotly_chart(
                charts.verdict_donut(verdicts, C.usd(at_risk)),
                use_container_width=True, config=charts.bare_config(),
            )
            C.source_note(
                "Four verdicts. Never arrived, outside footprint, impossible "
                "transit, plausible. Each is a statement about geometry, not "
                "about anybody's intent."
            )

    # ---------------------------------------------------------------- S6
    C.section("Cell drill-down")
    if not hexes.empty:
        cell = st.selectbox(
            "hexagon", hexes["h3"].tolist()[:200],
            format_func=lambda h: (
                f"{hexes.loc[hexes['h3'] == h, 'district'].iloc[0]} · {h}"),
            key="gp_m_cell",
        )
        rows = data.run("Q_CELL_DRILLDOWN", (cell,))
        st.dataframe(rows, use_container_width=True, hide_index=True)
        C.source_note(
            "Hard limit of fifty rows. Streamlit in Snowflake caps a single "
            "backend-to-frontend transfer at 32 MB, so no table in this "
            "application is unbounded."
        )

    # ---------------------------------------------------------------- S7
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
    ])

    C.provenance_footer(
        "IATI Datastore activity locations provide the real geography. "
        "Disbursement events are synthetic and labelled. H3 indexing is "
        "performed in SQL at resolution 7 for delivery and resolution 5 for "
        "the organisational footprint. Grid distance via H3_GRID_DISTANCE, "
        "straight-line distance via ST_DISTANCE over ST_POINT."
    )
