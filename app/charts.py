"""Chart styling contract. Build Spec Section 03.

Every Plotly figure in the application passes through `style_fig` so that
styling cannot drift between tabs. The chart rules are enforced here
rather than remembered:

  * No chart titles inside the figure. The title is a Streamlit heading
    above it, so typography stays consistent.
  * No gridlines on the x axis.
  * No legend unless two or more series genuinely overlap.
  * Colour carries meaning strictly according to the palette, so a red
    bar always means flagged and an amber line always means privacy
    noise.
  * Animation is used exactly twice in the whole application: the Tab 01
    reveal and the Tab 05 noise curve.
"""

from __future__ import annotations

import plotly.graph_objects as go

from theme import (
    BORDER,
    CATEGORICAL,
    CONFIRMED_GREEN,
    FLAG_RED,
    INK,
    NEUTRAL,
    NOISE_AMBER,
    SNOWFLAKE_BLUE,
    SOLANA_PURPLE,
    TEXT,
    TEXT_MUTED,
)

FONT = "Geist Variable, Geist, -apple-system, sans-serif"

#: Verdict colours, fixed across every tab that renders a verdict.
VERDICT_COLOURS = {
    "PLAUSIBLE": SNOWFLAKE_BLUE,
    "OUTSIDE_FOOTPRINT": FLAG_RED,
    "IMPOSSIBLE_TRANSIT": NOISE_AMBER,
    "NEVER_ARRIVED": "#B02427",
}


def style_fig(fig: go.Figure, height: int = 340, legend: bool = False) -> go.Figure:
    """The single styling gate. Route every figure through it."""
    fig.update_layout(
        font=dict(family=FONT, size=13, color=TEXT),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=8, r=8, t=28, b=8),
        height=height,
        showlegend=legend,
        hoverlabel=dict(
            font_family=FONT,
            font_size=13,
            bgcolor="#FFFFFF",
            bordercolor=BORDER,
            font_color=TEXT,
        ),
        xaxis=dict(showgrid=False, zeroline=False, linecolor=BORDER),
        yaxis=dict(gridcolor="#F0F2F4", zeroline=False, linecolor=BORDER),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            font=dict(family=FONT, size=12, color=TEXT_MUTED),
        ),
        colorway=CATEGORICAL,
        dragmode=False,
    )
    return fig


def no_axes(fig: go.Figure) -> go.Figure:
    """Hide axes entirely. Used by the Tab 02 network graph."""
    fig.update_xaxes(visible=False, showgrid=False, zeroline=False)
    fig.update_yaxes(visible=False, showgrid=False, zeroline=False)
    return fig


def bare_config(*, static: bool = False) -> dict:
    """Plotly config. The modebar is default chrome, so it is removed."""
    return {
        "displayModeBar": False,
        "staticPlot": static,
        "scrollZoom": False,
        "doubleClick": False,
    }


# ---------------------------------------------------------------------------
# C01-1 / Meaning versus spelling
# ---------------------------------------------------------------------------


def meaning_vs_spelling(semantic: float, string: float) -> go.Figure:
    """Grouped horizontal bar. The single most quotable image in the build.

    Two bars, semantic similarity in Snowflake Blue and string similarity
    in Neutral. The visible gap is annotated in Flag Red. Bars 28 px tall,
    axis 0 to 1 with ticks every 0.25.
    """
    gap = semantic - string
    fig = go.Figure()
    fig.add_bar(
        y=["meaning", "spelling"],
        x=[semantic, string],
        orientation="h",
        marker=dict(color=[SNOWFLAKE_BLUE, NEUTRAL], cornerradius=6),
        width=[0.42, 0.42],
        text=[f"{semantic:.2f}", f"{string:.2f}"],
        textposition="outside",
        textfont=dict(family=FONT, size=14, color=TEXT),
        hovertemplate="%{y}: %{x:.3f}<extra></extra>",
    )
    # The gap, annotated between the two bars. The arrow spans string ->
    # semantic and the label sits clear of the arrowhead, so the text is
    # never clipped by it however small the gap is.
    fig.add_annotation(
        x=string, y=0.5,
        ax=semantic, ay=0.5,
        xref="x", yref="y", axref="x", ayref="y",
        text="",
        showarrow=True, arrowhead=3, arrowsize=1, arrowwidth=1.5,
        arrowcolor=FLAG_RED, arrowside="start+end",
    )
    fig.add_annotation(
        x=max(semantic, string), y=0.5,
        xref="x", yref="y",
        text=f"evasion gap {gap:.2f}",
        showarrow=False,
        xanchor="left", xshift=10,
        font=dict(family=FONT, size=13, color=FLAG_RED),
    )
    fig.update_xaxes(range=[0, 1.12], dtick=0.25, showgrid=False)
    fig.update_yaxes(autorange="reversed")
    return style_fig(fig, height=260)


# ---------------------------------------------------------------------------
# C01-2 / Confidence decomposition
# ---------------------------------------------------------------------------


def risk_waterfall(components: dict[str, float], total: float) -> go.Figure:
    """Waterfall reconstructing the risk score by hand.

    An accountability tool cannot show an opaque score, so this chart
    exists to make the arithmetic reconstructable by eye. Contributions in
    Flag Red, total bar in ink.
    """
    labels = list(components.keys()) + ["total"]
    values = list(components.values()) + [total]
    measures = ["relative"] * len(components) + ["total"]

    fig = go.Figure(
        go.Waterfall(
            orientation="v",
            measure=measures,
            x=labels,
            y=values,
            text=[f"{v:.1f}" for v in values],
            textposition="outside",
            textfont=dict(family=FONT, size=12, color=TEXT),
            connector=dict(line=dict(color=BORDER, width=1)),
            increasing=dict(marker=dict(color=FLAG_RED)),
            decreasing=dict(marker=dict(color=SNOWFLAKE_BLUE)),
            totals=dict(marker=dict(color=INK)),
            hovertemplate="%{x}: %{y:.2f}<extra></extra>",
        )
    )
    fig.update_yaxes(range=[0, max(105, total * 1.2)])
    return style_fig(fig, height=340)


# ---------------------------------------------------------------------------
# C01-3 / Semantic neighbourhood
# ---------------------------------------------------------------------------


def semantic_neighbourhood(df, selected_pair: tuple[str, str] | None = None):
    """Two-dimensional PCA projection of the embedding space.

    Verified are Neutral dots, imitations are Flag Red, the selected pair
    is highlighted with a connecting line and both labels shown.
    Imitations visibly sit on top of their targets while ordinary
    organisations spread out.
    """
    fig = go.Figure()

    real = df[~df["is_synthetic"]]
    fake = df[df["is_synthetic"]]

    fig.add_scatter(
        x=real["pc1"], y=real["pc2"], mode="markers",
        marker=dict(size=6, color=NEUTRAL, opacity=0.35,
                    line=dict(width=0)),
        name="verified",
        customdata=real[["name"]],
        hovertemplate="%{customdata[0]}<extra></extra>",
    )
    fig.add_scatter(
        x=fake["pc1"], y=fake["pc2"], mode="markers",
        marker=dict(size=8, color=FLAG_RED, opacity=0.85,
                    line=dict(width=0)),
        name="seeded imitation",
        customdata=fake[["name"]],
        hovertemplate="%{customdata[0]}<extra></extra>",
    )

    if selected_pair:
        suspect_id, target_id = selected_pair
        pair = df[df["org_id"].isin([suspect_id, target_id])]
        if len(pair) == 2:
            fig.add_scatter(
                x=pair["pc1"], y=pair["pc2"], mode="markers+lines+text",
                line=dict(color=INK, width=1.5, dash="dot"),
                marker=dict(size=13, color=INK, line=dict(width=2, color="#FFFFFF")),
                text=pair["name"],
                textposition="top center",
                textfont=dict(family=FONT, size=12, color=INK),
                name="selected pair",
                hoverinfo="skip",
            )

    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return style_fig(fig, height=380, legend=True)


# ---------------------------------------------------------------------------
# C02-1 / Impersonation network
# ---------------------------------------------------------------------------


def impersonation_network(nodes, edges):
    """Force-style graph built from plain Plotly traces.

    Third-party network components cannot load under the Content Security
    Policy (Trap 03), so the graph is drawn from primitives. Positions
    come from an offline networkx spring layout stored on MARTS.GRAPH_NODES.
    """
    fig = go.Figure()

    # Edges first so nodes sit on top. Opacity scales with similarity.
    if len(edges):
        edge_x, edge_y = [], []
        for row in edges.itertuples():
            edge_x += [row.source_x, row.target_x, None]
            edge_y += [row.source_y, row.target_y, None]
        fig.add_scatter(
            x=edge_x, y=edge_y, mode="lines",
            line=dict(color="rgba(107,114,128,0.28)", width=0.8),
            hoverinfo="skip", showlegend=False,
        )

    verified = nodes[nodes["node_kind"] == "verified"]
    imitation = nodes[nodes["node_kind"] == "imitation"]

    fig.add_scatter(
        x=verified["x"], y=verified["y"], mode="markers",
        marker=dict(size=14, color=SNOWFLAKE_BLUE,
                    line=dict(width=1.5, color="#FFFFFF")),
        name="verified",
        customdata=verified[["org_id", "name", "cause", "city", "state"]],
        hovertemplate="<b>%{customdata[1]}</b><br>%{customdata[2]}"
                      "<br>%{customdata[3]}, %{customdata[4]}<extra></extra>",
    )
    fig.add_scatter(
        x=imitation["x"], y=imitation["y"], mode="markers",
        marker=dict(size=7, color=FLAG_RED,
                    line=dict(width=1, color="#FFFFFF")),
        name="seeded imitation",
        customdata=imitation[["org_id", "name", "cause", "city", "state"]],
        hovertemplate="<b>%{customdata[1]}</b><br>%{customdata[2]}"
                      "<br>%{customdata[3]}, %{customdata[4]}<extra></extra>",
    )

    fig = style_fig(fig, height=460, legend=True)
    return no_axes(fig)


# ---------------------------------------------------------------------------
# C02-3 / Threshold sensitivity
# ---------------------------------------------------------------------------


def threshold_curve(df, marker_at: float = 0.86) -> go.Figure:
    """Two lines over the precomputed sweep, with the production value marked.

    It shows the threshold was chosen rather than guessed, and lets a
    sceptical judge probe the model live instead of taking a number on
    faith. The curve is precomputed so the slider responds with no query.
    """
    fig = go.Figure()
    fig.add_scatter(
        x=df["threshold"], y=df["pairs_detected"], mode="lines",
        line=dict(color=SNOWFLAKE_BLUE, width=2.5),
        name="pairs detected",
        hovertemplate="threshold %{x:.2f}: %{y} pairs<extra></extra>",
    )
    fig.add_scatter(
        x=df["threshold"], y=df["pairs_ai_confirmed"], mode="lines",
        line=dict(color=SOLANA_PURPLE, width=2, dash="dot"),
        name="also confirmed by the AI predicate",
        hovertemplate="threshold %{x:.2f}: %{y} confirmed<extra></extra>",
    )
    fig.add_vline(
        x=marker_at, line=dict(color=INK, width=1.5, dash="dash"),
        annotation_text=f"production {marker_at:.2f}",
        annotation_position="top",
        annotation_font=dict(family=FONT, size=12, color=INK),
    )
    fig.update_xaxes(title=None, dtick=0.05)
    return style_fig(fig, height=320, legend=True)


# ---------------------------------------------------------------------------
# C03-2 / Distance from base, C03-3 / Verdict composition
# ---------------------------------------------------------------------------


def distance_histogram(df, cutoff_km: float) -> go.Figure:
    """Kilometres from registered base with a plausibility rule.

    The tail beyond the rule renders red, because a red bar always means
    flagged.
    """
    plausible = df[df["km_from_base"] <= cutoff_km]["km_from_base"]
    beyond = df[df["km_from_base"] > cutoff_km]["km_from_base"]

    fig = go.Figure()
    fig.add_histogram(
        x=plausible, nbinsx=44, marker=dict(color=SNOWFLAKE_BLUE),
        name="within footprint",
        hovertemplate="%{x} km: %{y} deliveries<extra></extra>",
    )
    fig.add_histogram(
        x=beyond, nbinsx=44, marker=dict(color=FLAG_RED),
        name="beyond footprint",
        hovertemplate="%{x} km: %{y} deliveries<extra></extra>",
    )
    fig.add_vline(
        x=cutoff_km, line=dict(color=INK, width=1.5, dash="dash"),
        annotation_text="plausibility rule",
        annotation_position="top right",
        annotation_font=dict(family=FONT, size=12, color=INK),
    )
    fig.update_layout(barmode="overlay")
    return style_fig(fig, height=300, legend=True)


def verdict_donut(df, centre_value: str) -> go.Figure:
    """Four segments, centre carries value at risk."""
    fig = go.Figure(
        go.Pie(
            labels=df["geometry_verdict"],
            values=df["events"],
            hole=0.62,
            sort=False,
            marker=dict(
                colors=[VERDICT_COLOURS.get(v, NEUTRAL) for v in df["geometry_verdict"]],
                line=dict(color="#FFFFFF", width=2),
            ),
            textinfo="none",
            hovertemplate="%{label}<br>%{value} events, %{percent}<extra></extra>",
        )
    )
    fig.add_annotation(
        text=f"<b>{centre_value}</b><br><span style='font-size:11px;color:{TEXT_MUTED}'>VALUE AT RISK</span>",
        x=0.5, y=0.5, showarrow=False,
        font=dict(family=FONT, size=22, color=INK),
    )
    return style_fig(fig, height=300, legend=True)


# ---------------------------------------------------------------------------
# C04-1 / Sankey, C04-2 / Transit feasibility
# ---------------------------------------------------------------------------


def attrition_sankey(stages: dict) -> go.Figure:
    """Pledged to delivered, four node columns, link width in dollars.

    The link into unaccounted is Flag Red and is deliberately the visually
    heaviest element on the tab.
    """
    labels = [
        "pledged", "dispatched", "never dispatched", "delivered", "unaccounted",
    ]
    source = [0, 0, 1, 1]
    target = [1, 2, 3, 4]
    values = [
        stages["dispatched_usd"],
        max(0.0, stages["never_dispatched_usd"]),
        stages["delivered_usd"],
        stages["unaccounted_usd"],
    ]
    link_colours = [
        "rgba(41,181,232,0.45)",   # pledged -> dispatched
        "rgba(107,114,128,0.35)",  # pledged -> never dispatched
        "rgba(23,163,74,0.45)",    # dispatched -> delivered
        "rgba(229,72,77,0.75)",    # dispatched -> unaccounted, heaviest
    ]

    fig = go.Figure(
        go.Sankey(
            arrangement="snap",
            node=dict(
                label=labels,
                pad=26,
                thickness=16,
                line=dict(color=BORDER, width=1),
                color=[SNOWFLAKE_BLUE, SNOWFLAKE_BLUE, NEUTRAL,
                       CONFIRMED_GREEN, FLAG_RED],
                hovertemplate="%{label}: $%{value:,.0f}<extra></extra>",
            ),
            link=dict(
                source=source, target=target, value=values, color=link_colours,
                hovertemplate="$%{value:,.0f}<extra></extra>",
            ),
            textfont=dict(family=FONT, size=13, color=TEXT),
        )
    )
    return style_fig(fig, height=400)


def transit_feasibility(df, max_kmh: float = 90.0) -> go.Figure:
    """Transit time against distance, with a shaded impossible region.

    The most immediately legible signal in the whole application because
    it needs no explanation: a truck cannot cover four hundred kilometres
    in under an hour.
    """
    ok = df[~df["exceeds_plausible_speed"]]
    bad = df[df["exceeds_plausible_speed"]]
    max_km = float(df["km_from_base"].max() or 1)

    fig = go.Figure()
    # The impossible region: below the plausible-speed line.
    fig.add_scatter(
        x=[0, max_km, max_km, 0],
        y=[0, max_km / max_kmh, 0, 0],
        fill="toself",
        fillcolor="rgba(229,72,77,0.07)",
        line=dict(width=0),
        hoverinfo="skip",
        showlegend=False,
    )
    fig.add_scatter(
        x=[0, max_km], y=[0, max_km / max_kmh], mode="lines",
        line=dict(color=FLAG_RED, width=1.5, dash="dash"),
        name=f"{max_kmh:.0f} km/h",
        hoverinfo="skip",
    )
    fig.add_scatter(
        x=ok["km_from_base"], y=ok["transit_hours"], mode="markers",
        marker=dict(size=6, color=SNOWFLAKE_BLUE, opacity=0.55),
        name="plausible",
        customdata=ok[["disbursement_id"]],
        hovertemplate="%{customdata[0]}<br>%{x:.0f} km in %{y:.1f} h<extra></extra>",
    )
    fig.add_scatter(
        x=bad["km_from_base"], y=bad["transit_hours"], mode="markers",
        marker=dict(size=8, color=FLAG_RED, opacity=0.9),
        name="physically impossible",
        customdata=bad[["disbursement_id"]],
        hovertemplate="%{customdata[0]}<br>%{x:.0f} km in %{y:.1f} h<extra></extra>",
    )
    fig.update_xaxes(title=dict(text="kilometres from registered base",
                                font=dict(family=FONT, size=12, color=TEXT_MUTED)))
    fig.update_yaxes(title=dict(text="hours in transit",
                                font=dict(family=FONT, size=12, color=TEXT_MUTED)))
    return style_fig(fig, height=340, legend=True)


# ---------------------------------------------------------------------------
# C05-1 / Noise against cohort size, C05-3 / Repeated queries
# ---------------------------------------------------------------------------


def noise_curve(df, animate: bool = False) -> go.Figure:
    """True value in ink, released value in Noise Amber with a shaded band.

    X is cohort size, logarithmic, one to ten thousand. Lines converge
    right and diverge violently left. This is the picture of a privacy
    guarantee.
    """
    fig = go.Figure()
    fig.add_scatter(
        x=df["cohort"], y=df["released_hi"], mode="lines",
        line=dict(width=0), hoverinfo="skip", showlegend=False,
    )
    fig.add_scatter(
        x=df["cohort"], y=df["released_lo"], mode="lines",
        line=dict(width=0), fill="tonexty",
        fillcolor="rgba(245,166,35,0.16)",
        name="plausible range", hoverinfo="skip",
    )
    fig.add_scatter(
        x=df["cohort"], y=df["true_value"], mode="lines",
        line=dict(color=INK, width=2.5),
        name="true value",
        hovertemplate="cohort %{x}: %{y:,.0f}<extra></extra>",
    )
    fig.add_scatter(
        x=df["cohort"], y=df["released_value"], mode="lines",
        line=dict(color=NOISE_AMBER, width=2.5),
        name="released value",
        hovertemplate="cohort %{x}: %{y:,.0f}<extra></extra>",
    )
    fig.update_xaxes(type="log", title=dict(
        text="cohort size", font=dict(family=FONT, size=12, color=TEXT_MUTED)))
    # Both axes are logarithmic. On a linear y axis the large right-hand
    # values dominate and the divergence at the left, which is the entire
    # point of the chart, becomes invisible.
    fig.update_yaxes(type="log", title=dict(
        text="value released", font=dict(family=FONT, size=12, color=TEXT_MUTED)))
    fig = style_fig(fig, height=360, legend=True)

    if animate:
        # On first render only, sweep a marker right to left over roughly
        # 1.4 seconds, so the divergence is felt rather than read. This is
        # the second and final permitted animation in the application.
        sweep = df.iloc[::-1].reset_index(drop=True)
        step_ms = max(20, int(1400 / max(len(sweep), 1)))
        fig.add_scatter(
            x=[sweep["cohort"].iloc[0]], y=[sweep["released_value"].iloc[0]],
            mode="markers",
            marker=dict(size=13, color=NOISE_AMBER,
                        line=dict(width=2, color="#FFFFFF")),
            name="sweep", showlegend=False, hoverinfo="skip",
        )
        fig.frames = [
            go.Frame(data=[go.Scatter(x=[row.cohort], y=[row.released_value])],
                     traces=[len(fig.data) - 1], name=str(i))
            for i, row in enumerate(sweep.itertuples())
        ]
        fig.update_layout(
            updatemenus=[dict(
                type="buttons", visible=False, showactive=False,
                buttons=[dict(
                    label="play", method="animate",
                    args=[None, dict(
                        frame=dict(duration=step_ms, redraw=False),
                        transition=dict(duration=0),
                        fromcurrent=True, mode="immediate")],
                )],
            )],
        )

    return fig


def budget_burndown(df) -> go.Figure:
    """Per-query consumption, stacked. A narrow query costs far more."""
    fig = go.Figure()
    fig.add_bar(
        x=df["query_n"], y=df["epsilon_spent"],
        marker=dict(color=[
            FLAG_RED if narrow else NOISE_AMBER for narrow in df["is_narrow"]
        ], cornerradius=3),
        hovertemplate="query %{x}: epsilon %{y:.4f}<extra></extra>",
    )
    fig.update_xaxes(title=dict(text="query", font=dict(
        family=FONT, size=12, color=TEXT_MUTED)), dtick=1)
    return style_fig(fig, height=280)


def repeated_query_box(samples, true_value: float) -> go.Figure:
    """Spread of released answers across repeated identical queries.

    Tight around the truth for a large cohort, enormous and centred
    nowhere useful for a cohort of one. This is what defeats the averaging
    objection.
    """
    fig = go.Figure()
    fig.add_box(
        x=samples,
        marker=dict(color=NOISE_AMBER),
        line=dict(color=NOISE_AMBER, width=1.5),
        fillcolor="rgba(245,166,35,0.18)",
        boxpoints="all", jitter=0.5, pointpos=0,
        name="released answers",
        hovertemplate="%{x:,.0f}<extra></extra>",
    )
    fig.add_vline(
        x=true_value, line=dict(color=INK, width=2),
        annotation_text="true value",
        annotation_position="top",
        annotation_font=dict(family=FONT, size=12, color=INK),
    )
    fig.update_yaxes(visible=False)
    return style_fig(fig, height=260)


# ---------------------------------------------------------------------------
# C06-1 / Expected against actual, C06-2 / Mint activity
# ---------------------------------------------------------------------------


def receipt_gap(df) -> go.Figure:
    """Two cumulative step lines. Where they separate, fill the gap red.

    The visual argument is that a missing receipt is itself a finding,
    which is the entire reason a public ledger belongs in this design.
    """
    fig = go.Figure()
    fig.add_scatter(
        x=df["day"], y=df["cum_actual"], mode="lines",
        line=dict(color=SOLANA_PURPLE, width=2.5, shape="hv"),
        name="receipts confirmed on chain",
        hovertemplate="%{x|%d %b}: %{y} on chain<extra></extra>",
    )
    fig.add_scatter(
        x=df["day"], y=df["cum_expected"], mode="lines",
        line=dict(color=SNOWFLAKE_BLUE, width=2.5, shape="hv"),
        fill="tonexty", fillcolor="rgba(229,72,77,0.16)",
        name="verified in the warehouse",
        hovertemplate="%{x|%d %b}: %{y} expected<extra></extra>",
    )
    if len(df):
        last = df.iloc[-1]
        if last["cum_gap"] > 0:
            fig.add_annotation(
                x=last["day"],
                y=(last["cum_expected"] + last["cum_actual"]) / 2,
                text=f"no receipt<br>{int(last['cum_gap'])}",
                showarrow=True, arrowhead=2, arrowcolor=FLAG_RED,
                font=dict(family=FONT, size=12, color=FLAG_RED),
                ax=-46, ay=0,
            )
    return style_fig(fig, height=340, legend=True)


def mint_activity(df) -> go.Figure:
    """One point per compressed NFT over time.

    Exists to confirm to a sceptical judge that the volume is genuine
    rather than three hand-made tokens created for a screenshot.
    """
    fig = go.Figure()
    fig.add_scatter(
        x=df["minted_at"], y=df["amount_band"], mode="markers",
        marker=dict(size=7, color=SOLANA_PURPLE, opacity=0.6),
        customdata=df[["asset_id"]],
        hovertemplate="%{customdata[0]}<br>%{x|%d %b %H:%M}<extra></extra>",
    )
    return style_fig(fig, height=300)


# ---------------------------------------------------------------------------
# C07-1 / Value history
# ---------------------------------------------------------------------------


def value_history(df) -> go.Figure:
    """Score for the selected organisation across Time Travel offsets.

    An operator can alter the present but not the record of the past,
    which is the warehouse-side counterpart to the on-chain receipt.
    """
    fig = go.Figure()
    fig.add_scatter(
        x=df["as_of"], y=df["risk_score"], mode="lines+markers",
        line=dict(color=SNOWFLAKE_BLUE, width=2.5, shape="hv"),
        marker=dict(size=8, color=INK),
        hovertemplate="%{x}<br>score %{y:.1f}<extra></extra>",
    )
    changes = df[df["risk_score"].diff().fillna(0) != 0]
    for row in changes.itertuples():
        fig.add_annotation(
            x=row.as_of, y=row.risk_score,
            text=f"{row.risk_score:.0f}",
            showarrow=True, arrowhead=2, arrowcolor=TEXT_MUTED,
            font=dict(family=FONT, size=12, color=INK), ay=-28,
        )
    return style_fig(fig, height=300)


# ---------------------------------------------------------------------------
# C00-1 / Evidence timeline, C00-2 / Pipeline freshness
# ---------------------------------------------------------------------------


def evidence_timeline(df) -> go.Figure:
    """Cited incidents plotted over time.

    Marker area scales with magnitude, normalised WITHIN each unit type
    since dollars and tonnes are not comparable. Colour by region using
    the categorical palette in order.
    """
    fig = go.Figure()
    regions = list(dict.fromkeys(df["region"]))
    for idx, region in enumerate(regions):
        sub = df[df["region"] == region]
        fig.add_scatter(
            x=sub["published_on"], y=sub["lane"], mode="markers",
            marker=dict(
                size=sub["marker_size"],
                color=CATEGORICAL[idx % len(CATEGORICAL)],
                opacity=0.85, line=dict(width=1.5, color="#FFFFFF"),
            ),
            name=region,
            customdata=sub[["claim", "figure", "issuing_body"]],
            hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[2]}<extra></extra>",
        )

    # Two annotations pinned permanently, per the specification.
    for cid, text, shift in (
        ("BFOREAI_LA_FIRES", "119 lookalike domains in six days", -40),
        ("WFP_GAZA_TRUCKS", "590 trucks moved, 371 collected", 40),
    ):
        row = df[df["citation_id"] == cid]
        if len(row):
            row = row.iloc[0]
            fig.add_annotation(
                x=row["published_on"], y=row["lane"], text=text,
                showarrow=True, arrowhead=2, arrowcolor=TEXT_MUTED,
                font=dict(family=FONT, size=12, color=INK),
                ay=shift, bgcolor="rgba(255,255,255,0.92)",
                bordercolor=BORDER, borderwidth=1, borderpad=5,
            )

    fig.update_yaxes(visible=False, range=[-0.6, 3.6])
    return style_fig(fig, height=320, legend=True)


def pipeline_freshness(df) -> go.Figure:
    """One bar per Dynamic Table, with a dashed rule at the TARGET_LAG.

    Bars inside lag render Snowflake Blue, bars past it render Noise
    Amber. It is how a judge sees the declarative pipeline without opening
    a SQL file, and it proves the warehouse is live rather than a static
    extract.
    """
    colours = [
        SNOWFLAKE_BLUE if within else NOISE_AMBER for within in df["within_lag"]
    ]
    fig = go.Figure()
    fig.add_bar(
        y=df["short_name"], x=df["seconds_since_refresh"], orientation="h",
        marker=dict(color=colours, cornerradius=4),
        text=[f"{s:.0f}s" for s in df["seconds_since_refresh"]],
        textposition="outside",
        textfont=dict(family=FONT, size=12, color=TEXT),
        hovertemplate="%{y}: %{x:.0f}s since refresh<extra></extra>",
    )
    lag = float(df["target_lag_seconds"].iloc[0]) if len(df) else 60.0
    fig.add_vline(
        x=lag, line=dict(color=INK, width=1.5, dash="dash"),
        annotation_text=f"target lag {lag:.0f}s",
        annotation_position="top",
        annotation_font=dict(family=FONT, size=12, color=INK),
    )
    fig.update_yaxes(autorange="reversed")
    return style_fig(fig, height=max(220, 34 * len(df) + 60))


# ---------------------------------------------------------------------------
# C09-1 / Confidence against delivery rate
# ---------------------------------------------------------------------------


def confidence_scatter(df) -> go.Figure:
    """Bubble scatter. The warm counterpart to Tab 01's cold open.

    X is confirmed delivery rate, Y is receipt coverage, bubble area is
    value moved, colour by cause. The upper right quadrant is shaded and
    labelled: give here with confidence. Every dot is a real organisation.
    """
    fig = go.Figure()

    fig.add_shape(
        type="rect", x0=0.7, x1=1.02, y0=0.7, y1=1.02,
        fillcolor="rgba(41,181,232,0.08)", line=dict(width=0), layer="below",
    )
    fig.add_annotation(
        x=0.86, y=1.0, text="give here with confidence",
        showarrow=False,
        font=dict(family=FONT, size=12, color="#0E7FA8"),
    )

    causes = list(dict.fromkeys(df["cause"]))
    sizeref = 2.0 * max(float(df["value_moved_usd"].max() or 1), 1) / (46.0 ** 2)
    for idx, cause in enumerate(causes):
        sub = df[df["cause"] == cause]
        fig.add_scatter(
            x=sub["delivery_rate"], y=sub["receipt_coverage"], mode="markers",
            marker=dict(
                size=sub["value_moved_usd"], sizemode="area",
                sizeref=sizeref, sizemin=5,
                color=CATEGORICAL[idx % len(CATEGORICAL)],
                opacity=0.7, line=dict(width=1, color="#FFFFFF"),
            ),
            name=cause,
            customdata=sub[["name", "city", "state", "value_moved_usd"]],
            hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}, %{customdata[2]}"
                          "<br>delivery %{x:.0%} &middot; receipts %{y:.0%}"
                          "<br>$%{customdata[3]:,.0f} moved<extra></extra>",
        )

    fig.update_xaxes(range=[0, 1.05], tickformat=".0%", title=dict(
        text="confirmed delivery rate",
        font=dict(family=FONT, size=12, color=TEXT_MUTED)))
    fig.update_yaxes(range=[0, 1.05], tickformat=".0%", title=dict(
        text="receipt coverage",
        font=dict(family=FONT, size=12, color=TEXT_MUTED)))
    return style_fig(fig, height=420, legend=True)


def horizontal_bar(labels, values, *, colour=SNOWFLAKE_BLUE, height=280,
                   value_fmt="{:.1f}", hover="%{y}: %{x}<extra></extra>"):
    """Generic horizontal bar. Used by cause exposure and technique breakdown."""
    fig = go.Figure()
    fig.add_bar(
        y=list(labels), x=list(values), orientation="h",
        marker=dict(color=colour, cornerradius=4),
        text=[value_fmt.format(v) for v in values],
        textposition="outside",
        textfont=dict(family=FONT, size=12, color=TEXT),
        hovertemplate=hover,
    )
    fig.update_yaxes(autorange="reversed")
    return style_fig(fig, height=height)
