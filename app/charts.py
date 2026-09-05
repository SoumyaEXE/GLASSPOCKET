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
  * Animation is used once in the whole application: the Tab 01 reveal.
    The specification permits a second, a sweep over the Tab 05 noise
    curve, but that chart does not exist in this build: the deployment
    has no differential privacy DDL, so there is no noise to sweep over.
"""

from __future__ import annotations

import math

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


def as_bool(series):
    """Coerce a column to a real boolean mask.

    Snowflake returns BOOLEAN as a Python object column that can contain
    None, and `~column` on that raises

        TypeError: bad operand type for unary ~: 'NoneType'

    which is how The Last Mile died in the warehouse while working
    locally, where DuckDB hands back a numpy bool column. A missing
    verdict is treated as not-flagged, because inventing a flag is worse
    than missing one in a tool that exists to avoid false accusations.
    """
    return series.fillna(False).astype(bool)

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


def meaning_vs_spelling(semantic: float, string: float,
                        *, height: int = 220) -> go.Figure:
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
    fig = style_fig(fig, height=height)
    # style_fig merges its own xaxis, yaxis and margin into the layout, so
    # anything set before it is silently overwritten. Style first, then
    # override. The right-hand headroom is where the gap label sits; with
    # a 0.97 bar and no headroom it is clipped by the plotting area.
    fig.update_xaxes(range=[0, 1.34], dtick=0.25, showgrid=True,
                     gridcolor="#F0F2F4",
                     tickfont=dict(family=FONT, size=12, color=TEXT_MUTED))
    fig.update_yaxes(autorange="reversed", showgrid=False,
                     tickfont=dict(family=FONT, size=13, color=TEXT))
    fig.update_layout(margin=dict(l=8, r=8, t=16, b=8))
    return fig


# ---------------------------------------------------------------------------
# C01-2 / Confidence decomposition
# ---------------------------------------------------------------------------


def risk_waterfall(components: dict[str, float], total: float,
                   *, height: int = 300) -> go.Figure:
    """Waterfall reconstructing the risk score by hand.

    An accountability tool cannot show an opaque score, so this chart
    exists to make the arithmetic reconstructable by eye. Contributions
    in Flag Red, total bar in ink.

    IT RUNS HORIZONTALLY BECAUSE THE COMPONENT NAMES ARE PHRASES. Five
    labels reading "semantic proximity", "unaccounted ratio" and
    "missing receipts" cannot sit side by side under a vertical
    waterfall in a half-width column without colliding, and Plotly's
    answer to that collision is to rotate them, which is worse. Turned on
    its side the labels are a left-hand column and read straight.
    """
    labels = list(components.keys()) + ["total"]
    values = list(components.values()) + [total]
    measures = ["relative"] * len(components) + ["total"]

    fig = go.Figure(
        go.Waterfall(
            orientation="h",
            measure=measures,
            y=labels,
            x=values,
            text=[f"{v:.1f}" for v in values],
            textposition="outside",
            textfont=dict(family=FONT, size=12, color=TEXT),
            connector=dict(line=dict(color=BORDER, width=1)),
            increasing=dict(marker=dict(color=FLAG_RED)),
            decreasing=dict(marker=dict(color=SNOWFLAKE_BLUE)),
            totals=dict(marker=dict(color=INK)),
            hovertemplate="%{y}: %{x:.2f}<extra></extra>",
        )
    )
    fig = style_fig(fig, height=height)
    fig.update_xaxes(range=[0, max(100.0, float(total)) * 1.18],
                     showgrid=True, gridcolor="#F0F2F4", dtick=25,
                     tickfont=dict(family=FONT, size=12, color=TEXT_MUTED))
    fig.update_yaxes(autorange="reversed", showgrid=False,
                     tickfont=dict(family=FONT, size=12, color=TEXT))
    fig.update_layout(margin=dict(l=8, r=8, t=14, b=8))
    return fig


def evasion_distribution(gaps, marker: float, *, height: int = 300):
    """Where one pair sits in the whole confirmed population.

    A single pair showing an evasion gap of 0.27 means nothing on its
    own: the reader has no idea whether that is ordinary or extreme. The
    histogram supplies the missing denominator, and the marker says
    where the pair on screen falls in it. This is the difference between
    reporting a number and reporting a finding.
    """
    values = [float(v) for v in gaps]
    below = sum(1 for v in values if v <= float(marker))
    percentile = 100.0 * below / max(len(values), 1)

    fig = go.Figure()
    fig.add_histogram(
        x=values, nbinsx=26,
        marker=dict(color="#DCE1E6", line=dict(width=0)),
        hovertemplate="gap %{x:.2f}: %{y} pairs<extra></extra>",
        name="confirmed pairs",
    )
    fig = style_fig(fig, height=height)
    fig.add_vline(x=float(marker), line=dict(color=FLAG_RED, width=2))
    fig.add_annotation(
        x=float(marker), y=1.0, yref="paper", yanchor="bottom",
        text=f"this pair &#183; {percentile:.0f}th percentile",
        showarrow=False, xanchor="right" if percentile > 60 else "left",
        xshift=-6 if percentile > 60 else 6,
        font=dict(family=FONT, size=12, color=FLAG_RED),
    )
    fig.update_xaxes(title=None, showgrid=True, gridcolor="#F0F2F4",
                     tickformat=".2f",
                     tickfont=dict(family=FONT, size=12, color=TEXT_MUTED))
    fig.update_yaxes(showgrid=True, gridcolor="#F0F2F4",
                     tickfont=dict(family=FONT, size=12, color=TEXT_MUTED))
    fig.update_layout(margin=dict(l=8, r=8, t=30, b=8), bargap=0.06)
    return fig


# ---------------------------------------------------------------------------
# C01-3 / Semantic neighbourhood
# ---------------------------------------------------------------------------


def semantic_neighbourhood(df, selected_pair: tuple[str, str] | None = None,
                           *, height: int = 380):
    """Two-dimensional PCA projection of the embedding space.

    Verified are Neutral dots, imitations are Flag Red, the selected pair
    is highlighted with a connecting line and both labels shown.
    Imitations visibly sit on top of their targets while ordinary
    organisations spread out.
    """
    fig = go.Figure()

    synthetic = as_bool(df["is_synthetic"])
    real = df[~synthetic]
    fake = df[synthetic]

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
                # One label above and one below. Both organisation names
                # are long and the two markers sit almost on top of each
                # other by construction, so a single position puts one
                # label straight through the other.
                textposition=["top center", "bottom center"],
                textfont=dict(family=FONT, size=12, color=INK),
                name="selected pair",
                cliponaxis=False,
                hoverinfo="skip",
            )

    fig = style_fig(fig, height=height, legend=True)
    # The axes carry no meaning here, but the range does: an organisation
    # name is forty characters wide and the two labelled markers sit near
    # the middle of the cloud, so without padding the label runs off the
    # edge of the figure and is cut in half.
    span_x = float(df["pc1"].max() - df["pc1"].min()) or 1.0
    span_y = float(df["pc2"].max() - df["pc2"].min()) or 1.0
    fig.update_xaxes(visible=False,
                     range=[float(df["pc1"].min()) - span_x * 0.34,
                            float(df["pc1"].max()) + span_x * 0.34])
    fig.update_yaxes(visible=False,
                     range=[float(df["pc2"].min()) - span_y * 0.12,
                            float(df["pc2"].max()) + span_y * 0.12])
    fig.update_layout(margin=dict(l=8, r=8, t=8, b=8))
    return fig


# ---------------------------------------------------------------------------
# C02-1 / Impersonation network
# ---------------------------------------------------------------------------


def impersonation_network(nodes, edges, *, focus_id: str | None = None,
                          height: int = 452):
    """Force-style graph built from plain Plotly traces.

    Third-party network components cannot load under the Content Security
    Policy (Trap 03), so the graph is drawn from primitives. Positions
    come from an offline networkx spring layout stored on MARTS.GRAPH_NODES.

    EVERY NODE IS SIZED BY ITS DEGREE, which is the whole reason to draw
    a graph rather than a table. At a fixed radius every node looked
    equally involved and the hubs were invisible.

    Degree does not mean the same thing on both sides and the tab says
    so rather than papering over it. On a verified organisation it is how
    many imitations point at it, which in this corpus is one for almost
    all of them and two for a handful. On a seeded row it is how many
    real organisations that one name sits close enough to, and one seeded
    row reaches seventeen of them. Calling the size "imitations" would
    have been a clean label and a false one.

    The axes are locked to the same scale. A spring layout is only
    meaningful if one unit across is one unit down, and letting the
    container stretch x independently turns a symmetric layout into an
    ellipse that implies structure the data does not have.
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
            line=dict(color="rgba(107,114,128,0.30)", width=0.8),
            hoverinfo="skip", showlegend=False,
        )

    verified = nodes[nodes["node_kind"] == "verified"]
    imitation = nodes[nodes["node_kind"] == "imitation"]

    # One scale across both kinds, so a big marker means the same amount
    # of graph wherever it appears.
    top = float(nodes["degree"].fillna(0).astype(float).max() or 1.0)

    def _sizes(frame, base: float, span: float):
        if not len(frame):
            return []
        degree = frame["degree"].fillna(0).astype(float).clip(lower=0)
        return base + span * (degree / top) ** 0.55

    fig.add_scatter(
        x=verified["x"], y=verified["y"], mode="markers",
        marker=dict(size=_sizes(verified, 9.0, 15.0), color=SNOWFLAKE_BLUE,
                    line=dict(width=1.4, color="#FFFFFF")),
        name="verified organisation",
        customdata=verified[["org_id", "name", "cause", "city", "state",
                             "degree"]],
        hovertemplate="<b>%{customdata[1]}</b><br>%{customdata[2]}"
                      "<br>%{customdata[3]}, %{customdata[4]}"
                      "<br>%{customdata[5]} imitation(s) point at it"
                      "<extra></extra>",
    )
    fig.add_scatter(
        x=imitation["x"], y=imitation["y"], mode="markers",
        marker=dict(size=_sizes(imitation, 5.0, 15.0), color=FLAG_RED,
                    line=dict(width=1, color="#FFFFFF")),
        name="seeded imitation",
        customdata=imitation[["org_id", "name", "cause", "city", "state",
                              "degree"]],
        hovertemplate="<b>%{customdata[1]}</b><br>%{customdata[2]}"
                      "<br>%{customdata[3]}, %{customdata[4]}"
                      "<br>sits close to %{customdata[5]} real organisation(s)"
                      "<extra></extra>",
    )

    # The selected node gets a ring rather than a colour change, so the
    # verified/seeded reading of the palette is never overloaded.
    if focus_id is not None and len(nodes):
        hit = nodes[nodes["org_id"] == focus_id]
        if len(hit):
            fig.add_scatter(
                x=hit["x"], y=hit["y"], mode="markers",
                marker=dict(size=30, color="rgba(0,0,0,0)",
                            line=dict(width=2, color=INK)),
                hoverinfo="skip", showlegend=False,
            )

    fig = style_fig(fig, height=height, legend=True)
    fig = no_axes(fig)
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    fig.update_layout(margin=dict(l=4, r=4, t=34, b=4))
    return fig


# ---------------------------------------------------------------------------
# C02-3 / Threshold sensitivity and calibration
# ---------------------------------------------------------------------------


def threshold_curve(df, marker_at: float, production: float,
                    *, height: int = 300) -> go.Figure:
    """Detections against the cut-off, on a log axis.

    THE Y AXIS IS LOGARITHMIC BECAUSE THE RANGE IS FOUR ORDERS OF
    MAGNITUDE. The sweep runs from 27,212 pairs at 0.70 to 52 at 0.99. On
    a linear axis everything from 0.86 upward is pinned to the floor and
    the production end of the curve, which is the only part anyone is
    deciding anything about, reads as a flat line at zero.

    The confirmed-pairs series that used to sit on this chart has been
    removed. AI_FILTER is unavailable on this account, so confirmation
    was computed once, at the production cut-off, and plotting it across
    the sweep drew a horizontal line at 188 that looked like a finding
    and was an artefact. What actually justifies the threshold is
    precision and recall against ground truth, which is the panel beside
    this one.
    """
    fig = go.Figure()
    fig.add_scatter(
        x=df["threshold"], y=df["pairs_detected"], mode="lines",
        line=dict(color=SNOWFLAKE_BLUE, width=2.5, shape="spline"),
        fill="tozeroy", fillcolor="rgba(41,181,232,0.10)",
        name="pairs detected",
        hovertemplate="cut-off %{x:.2f}: %{y:,} pairs<extra></extra>",
    )
    fig = style_fig(fig, height=height)
    # dtick=1 on a log axis is one decade per tick. Without it Plotly
    # labels the minor ticks too and the axis reads 2, 10k, 5, 1000, 5.
    fig.update_yaxes(type="log", dtick=1, title=dict(
        text="pairs detected, log scale",
        font=dict(family=FONT, size=11, color=TEXT_MUTED)))
    fig.update_xaxes(dtick=0.05, showgrid=False)
    fig.add_vline(
        x=production, line=dict(color=INK, width=1.5, dash="dash"),
        annotation_text=f"production {production:.2f}",
        annotation_position="top left",
        annotation_font=dict(family=FONT, size=11, color=INK),
    )
    if abs(float(marker_at) - float(production)) > 0.004:
        fig.add_vline(
            x=marker_at, line=dict(color=FLAG_RED, width=1.5),
            annotation_text=f"you are at {marker_at:.2f}",
            annotation_position="top right",
            annotation_font=dict(family=FONT, size=11, color=FLAG_RED),
        )
    return fig


def threshold_calibration(df, marker_at: float, production: float,
                          *, height: int = 300) -> go.Figure:
    """Precision, recall and F1 against ground truth.

    Every seeded organisation records the real one it was built from, so
    a detected pair can be checked rather than believed. This is the
    chart that says the cut-off was chosen: it is not at the F1 maximum,
    and the tab says why not.
    """
    precision = [float(v or 0) for v in df["precision_at"]]
    recall = [float(v or 0) for v in df["recall_at"]]
    f1 = [
        0.0 if (p + r) == 0 else 2 * p * r / (p + r)
        for p, r in zip(precision, recall)
    ]

    fig = go.Figure()
    for name, series, colour, dash in (
        ("precision", precision, CONFIRMED_GREEN, "solid"),
        ("recall", recall, NOISE_AMBER, "solid"),
        ("F1", f1, NEUTRAL, "dot"),
    ):
        fig.add_scatter(
            x=df["threshold"], y=series, mode="lines",
            line=dict(color=colour, width=2.5 if dash == "solid" else 2,
                      dash=dash),
            name=name,
            hovertemplate="cut-off %{x:.2f}: " + name + " %{y:.3f}<extra></extra>",
        )
    fig = style_fig(fig, height=height, legend=True)
    fig.update_yaxes(range=[0, 1.08], tickformat=".0%")
    fig.update_xaxes(dtick=0.05, showgrid=False)

    if f1:
        best = max(range(len(f1)), key=lambda i: f1[i])
        fig.add_vline(
            x=float(df["threshold"].iloc[best]),
            line=dict(color=NEUTRAL, width=1, dash="dot"),
            annotation_text=f"F1 peaks at {float(df['threshold'].iloc[best]):.2f}",
            annotation_position="bottom left",
            annotation_font=dict(family=FONT, size=11, color=TEXT_MUTED),
        )
    fig.add_vline(
        x=production, line=dict(color=INK, width=1.5, dash="dash"),
        annotation_text=f"production {production:.2f}",
        annotation_position="top left",
        annotation_font=dict(family=FONT, size=11, color=INK),
    )
    if abs(float(marker_at) - float(production)) > 0.004:
        fig.add_vline(x=marker_at, line=dict(color=FLAG_RED, width=1.5))
    return fig


# ---------------------------------------------------------------------------
# C02-4 / Trust. The score any organisation carries, and where it falls.
#
# TRUST IS 100 MINUS MARTS.F_RISK. There is no second scoring system in
# this application; these charts render the published UDF from the other
# direction because a donor asks "can I trust this one", not "what is
# this one's risk component vector".
# ---------------------------------------------------------------------------

#: Trust bands, high to low. The 45 boundary is not decorative: it is
#: 100 minus the 55 at which MARTS.ORG_RISK writes 'needs a second look',
#: so the red band on every gauge is exactly the verdict in the mart.
TRUST_BANDS = (
    (90.0, 100.0, "#EAF7FD", SNOWFLAKE_BLUE, "strong"),
    (65.0, 90.0, "#F7F8FA", NEUTRAL, "ordinary"),
    (45.0, 65.0, "#FEF6E7", NOISE_AMBER, "thin"),
    (0.0, 45.0, "#FDECEC", FLAG_RED, "needs a second look"),
)


def trust_band(score: float) -> tuple[str, str]:
    """(label, chip tone) for a trust score. One definition, used everywhere."""
    value = float(score or 0)
    for low, _high, _fill, _ink, label in TRUST_BANDS:
        if value >= low:
            return label, {
                "strong": "verified",
                "ordinary": "neutral",
                "thin": "seeded",
                "needs a second look": "flagged",
            }[label]
    return "needs a second look", "flagged"


def trust_gauge(score: float, *, comparison: float | None = None,
                comparison_label: str = "corpus median",
                height: int = 132) -> go.Figure:
    """A banded 0-100 rule with the score marked on it.

    A bare number is not a judgement. 72 means nothing until the reader
    can see that the second-look line is at 45 and that most of the
    corpus sits above 90, so the bands are drawn rather than described.
    """
    value = max(0.0, min(100.0, float(score or 0)))
    fig = go.Figure()

    # A transparent trace so the axes exist; the bands are shapes.
    fig.add_scatter(x=[value], y=[0], mode="markers",
                    marker=dict(size=0.1, color="rgba(0,0,0,0)"),
                    hoverinfo="skip", showlegend=False)
    fig = style_fig(fig, height=height)

    for low, high, fill, _ink, label in TRUST_BANDS:
        fig.add_shape(type="rect", x0=low, x1=high, y0=-0.34, y1=0.34,
                      line=dict(width=0), fillcolor=fill, layer="below")
        fig.add_annotation(
            x=(low + high) / 2, y=-0.40, yanchor="top", text=label,
            showarrow=False,
            font=dict(family=FONT, size=10, color=TEXT_MUTED),
        )

    if comparison is not None:
        fig.add_shape(type="line", x0=float(comparison), x1=float(comparison),
                      y0=-0.34, y1=0.34,
                      line=dict(color=TEXT_MUTED, width=1.5, dash="dot"))
        fig.add_annotation(
            x=float(comparison), y=0.42, yanchor="bottom",
            text=comparison_label, showarrow=False,
            font=dict(family=FONT, size=10, color=TEXT_MUTED),
        )

    _label, tone = trust_band(value)
    ink = {"verified": SNOWFLAKE_BLUE, "neutral": INK,
           "seeded": NOISE_AMBER, "flagged": FLAG_RED}[tone]
    fig.add_shape(type="line", x0=value, x1=value, y0=-0.46, y1=0.46,
                  line=dict(color=ink, width=3))
    fig.add_annotation(
        x=value, y=0.52, yanchor="bottom", text=f"<b>{value:.1f}</b>",
        showarrow=False, font=dict(family=FONT, size=15, color=ink),
    )

    fig.update_xaxes(range=[0, 100], tickvals=[0, 25, 50, 75, 100],
                     showgrid=False, zeroline=False, linecolor=BORDER)
    fig.update_yaxes(range=[-0.95, 0.95], visible=False)
    fig.update_layout(margin=dict(l=8, r=8, t=26, b=8))
    return fig


def trust_bands_chart(df, *, highest_real: float | None = None,
                      height: int = 320) -> go.Figure:
    """Where every organisation in the corpus falls, real against seeded.

    THIS IS THE SAFETY PROPERTY DRAWN RATHER THAN PROMISED. The blue
    series stops before the second-look line and the red series is
    everything past it, which is the same statement Q_TRUST_INVARIANT
    makes in counters. If the two ever overlapped past 45 this
    application would be publishing an accusation about a named real
    organisation, and the chart would show it before any prose did.

    The count axis is logarithmic. 44,644 filings sit in the top band and
    four seeded rows sit beside them; on a linear axis the entire seeded
    distribution, which is the subject of the tab, is a flat smear.
    """
    trust_mid = [100.0 - (float(v) + 2.5) for v in df["risk_floor"]]
    fig = go.Figure()
    fig.add_bar(
        x=trust_mid, y=[int(v) for v in df["real_filings"]],
        name="real filings", marker=dict(color=SNOWFLAKE_BLUE),
        hovertemplate="trust %{x:.0f}: %{y:,} real filings<extra></extra>",
    )
    fig.add_bar(
        x=trust_mid, y=[int(v) for v in df["seeded_rows"]],
        name="seeded imitations", marker=dict(color=FLAG_RED),
        hovertemplate="trust %{x:.0f}: %{y:,} seeded<extra></extra>",
    )
    fig = style_fig(fig, height=height, legend=True)
    fig.update_layout(barmode="overlay", bargap=0.12)
    fig.update_traces(opacity=0.85)
    fig.update_yaxes(type="log", dtick=1, title=dict(
        text="organisations, log scale",
        font=dict(family=FONT, size=11, color=TEXT_MUTED)))
    fig.update_xaxes(range=[0, 102], dtick=10, autorange=False, title=dict(
        text="trust score",
        font=dict(family=FONT, size=11, color=TEXT_MUTED)))
    fig.add_vline(
        x=45, line=dict(color=INK, width=1.5, dash="dash"),
        annotation_text="second-look line",
        annotation_position="top left",
        annotation_font=dict(family=FONT, size=11, color=INK),
    )
    if highest_real is not None:
        fig.add_vline(
            x=100.0 - float(highest_real),
            line=dict(color=SNOWFLAKE_BLUE, width=1.5, dash="dot"),
            annotation_text="lowest real filing",
            annotation_position="bottom right",
            annotation_font=dict(family=FONT, size=11, color=SNOWFLAKE_BLUE),
        )
    return fig


def corridor_components(df, *, height: int = 300) -> go.Figure:
    """Three shares per corridor as a dot plot rather than grouped bars.

    Grouped bars for three series over five categories is fifteen
    rectangles competing for the same baseline. What a reader wants here
    is the spread within each row, and dots on a shared rule give it
    directly.
    """
    labels = list(df["label"])
    fig = go.Figure()
    for name, column, colour in (
        ("geometry plausible", "plausible_share", SNOWFLAKE_BLUE),
        ("accounted for", "accounted_share", CONFIRMED_GREEN),
        ("receipt on chain", "receipted_share", SOLANA_PURPLE),
    ):
        fig.add_scatter(
            x=[float(v or 0) for v in df[column]], y=labels,
            mode="markers", name=name,
            marker=dict(size=13, color=colour,
                        line=dict(width=1.5, color="#FFFFFF")),
            hovertemplate="%{y} &#183; " + name + " %{x:.1%}<extra></extra>",
        )
    fig = style_fig(fig, height=height, legend=True)
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(range=[0, 1.02], tickformat=".0%", showgrid=True,
                     gridcolor="#F0F2F4", dtick=0.25)
    return fig


def geography_scatter(df, *, label_top: int = 12,
                      height: int = 340) -> go.Figure:
    """Imitation pressure against mean trust, one bubble per state.

    Two rankings side by side answer "which is worst at each" and nothing
    else. Plotted against one another they answer whether the two
    failures travel together, which is the question worth asking, and in
    this corpus they do not: the seeding is uniform by construction and
    the scatter shows that honestly instead of implying a pattern.

    ONLY THE FIRST ``label_top`` ROWS CARRY A LABEL. The frame arrives
    ordered by pressure, so those are exactly the states named in the bar
    chart beside this one: the bar names them, the scatter places them.
    Labelling all twenty-six put nine two-letter codes on top of each
    other in the middle of the cluster, which is where the interesting
    thing is, and a rule that picks a subset has to be a rule rather than
    a taste.
    """
    sizes = [float(v) for v in df["orgs"]]
    top = max(sizes or [1.0])
    labels = [
        str(name) if n < label_top else ""
        for n, name in enumerate(df["state"])
    ]
    fig = go.Figure()
    fig.add_scatter(
        x=[float(v or 0) for v in df["imitations_per_100"]],
        y=[float(v or 0) for v in df["trust_score"]],
        mode="markers+text",
        text=labels,
        textposition="top center",
        textfont=dict(family=FONT, size=10, color=TEXT_MUTED),
        cliponaxis=False,
        marker=dict(
            size=[10 + 26 * (v / top) ** 0.5 for v in sizes],
            color=SNOWFLAKE_BLUE, opacity=0.55,
            line=dict(width=1.2, color="#FFFFFF"),
        ),
        # The state rides in customdata rather than in ``text``, because
        # the unlabelled bubbles have no text and would otherwise hover
        # as an anonymous bold nothing.
        customdata=df[["orgs", "seeded", "second_look_orgs", "state"]],
        hovertemplate="<b>%{customdata[3]}</b><br>%{customdata[0]:,} filings"
                      "<br>%{customdata[1]} seeded"
                      "<br>%{x:.2f} imitations per 100 verified"
                      "<br>mean trust %{y:.2f}<extra></extra>",
    )
    fig = style_fig(fig, height=height)
    fig.update_xaxes(title=dict(
        text="imitations per 100 verified filings",
        font=dict(family=FONT, size=11, color=TEXT_MUTED)),
        showgrid=True, gridcolor="#F0F2F4")
    fig.update_yaxes(title=dict(
        text="mean trust score",
        font=dict(family=FONT, size=11, color=TEXT_MUTED)))
    return fig


# ---------------------------------------------------------------------------
# C03-4 / Money in motion, C03-5 / Programme flow
#
# THE FOUR STATUSES ARE NEVER COLLAPSED. Delivered, in flight and
# unaccounted are three different things, and a chart that adds the first
# two together and calls the result progress is the chart this whole
# project exists to argue against. Pledged-but-never-dispatched is a
# fourth, and it is a different measure from the other three, so it is
# reported in the table rather than stacked into the same bar.
# ---------------------------------------------------------------------------


def money_over_time(df, *, height: int = 300) -> go.Figure:
    """Cumulative dollars traced, split by where they ended up.

    The three bands stack to the total because the three statuses
    partition it exactly: every dispatched dollar is delivered, still in
    flight, or unaccounted for. Money that was pledged and never
    dispatched carries no amount at all and is therefore not in this
    chart; it is in the programme table, where it can be named as the
    separate thing it is.
    """
    weeks = list(df["week"])
    delivered, in_flight, unaccounted = [], [], []
    d_run = f_run = u_run = 0.0
    for row in df.itertuples():
        total = float(row.dispatched_usd or 0)
        deliv = float(row.delivered_usd or 0)
        unacc = float(row.unaccounted_usd or 0)
        d_run += deliv
        u_run += unacc
        f_run += max(total - deliv - unacc, 0.0)
        delivered.append(d_run)
        in_flight.append(f_run)
        unaccounted.append(u_run)

    fig = go.Figure()
    for name, series, colour in (
        ("delivered", delivered, CONFIRMED_GREEN),
        ("still in flight", in_flight, SNOWFLAKE_BLUE),
        ("unaccounted", unaccounted, FLAG_RED),
    ):
        fig.add_scatter(
            x=weeks, y=series, mode="lines", name=name,
            stackgroup="one",
            line=dict(width=1.5, color=colour),
            fillcolor=colour,
            opacity=0.85,
            hovertemplate="%{x|%d %b}: " + name + " $%{y:,.0f}<extra></extra>",
        )
    fig = style_fig(fig, height=height, legend=True)
    fig.update_layout(legend_traceorder="normal")
    fig.update_yaxes(tickprefix="$", separatethousands=True, title=dict(
        text="cumulative dollars traced",
        font=dict(family=FONT, size=11, color=TEXT_MUTED)))
    fig.update_xaxes(showgrid=False, tickformat="%d %b")
    return fig


def programme_flow(df, *, height: int = 300) -> go.Figure:
    """One stacked bar per appeal, split by where the money ended up."""
    fig = go.Figure()
    for name, column, colour in (
        ("delivered", "delivered_usd", CONFIRMED_GREEN),
        ("still in flight", "in_flight_usd", SNOWFLAKE_BLUE),
        ("unaccounted", "unaccounted_usd", FLAG_RED),
    ):
        fig.add_bar(
            y=list(df["programme_code"]),
            x=[float(v or 0) for v in df[column]],
            orientation="h", name=name,
            marker=dict(color=colour),
            hovertemplate="%{y}<br>" + name + " $%{x:,.0f}<extra></extra>",
        )
    fig = style_fig(fig, height=height, legend=True)
    # A horizontal stack reads left to right, so the legend has to as
    # well. Plotly's default reverses it to match vertical stacking.
    fig.update_layout(barmode="stack", bargap=0.36, legend_traceorder="normal")
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(tickprefix="$", separatethousands=True, showgrid=True,
                     gridcolor="#F0F2F4")
    return fig


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


#: Verdict labels as English. The column holds database enum values
#: and the legend is read by people, not by the parser.
VERDICT_LABELS = {
    "PLAUSIBLE": "plausible",
    "OUTSIDE_FOOTPRINT": "outside footprint",
    "IMPOSSIBLE_TRANSIT": "impossible transit",
    "NEVER_ARRIVED": "never arrived",
}


def verdict_donut(df, centre_value: str) -> go.Figure:
    """Four segments, centre carries value at risk."""
    fig = go.Figure(
        go.Pie(
            labels=[VERDICT_LABELS.get(str(v), str(v).replace("_", " ").lower())
                    for v in df["geometry_verdict"]],
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
# C04-1 / Sankey, C04-2 / Transit, C04-3 / Where it stops, C04-4 / Calibration
#
# THE FOUR STATUSES ARE NEVER COLLAPSED, HERE EITHER. Tab 03 says that
# about a stacked area; it holds with more force on this tab, because
# this is the tab that names the leak. Money that is still in a warehouse
# has not gone missing. Money nobody can account for has. A chart that
# adds the two together and calls the sum attrition is the chart the
# whole application argues against, and the shipped version of the
# district bars was exactly that chart.
# ---------------------------------------------------------------------------


def attrition_sankey(stages: dict, *, height: int = 400) -> go.Figure:
    """Pledged to delivered, four node columns, link width in dollars.

    The link into unaccounted is Flag Red and is deliberately the visually
    heaviest element on the tab.

    The node labels carry their own dollars. A Sankey without them is a
    picture of proportions that the reader has to translate back into
    money by hovering, and the two figures the tab is actually about are
    the two leaks, which are the two smallest ribbons on the diagram.
    """
    dispatched = max(0.0, float(stages.get("dispatched_usd") or 0))
    never = max(0.0, float(stages.get("never_dispatched_usd") or 0))
    delivered = max(0.0, float(stages.get("delivered_usd") or 0))
    unaccounted = max(0.0, float(stages.get("unaccounted_usd") or 0))
    in_flight = max(0.0, dispatched - delivered - unaccounted)

    def _m(value: float) -> str:
        return f"${value / 1e6:,.2f}m"

    labels = [
        "pledged  " + _m(dispatched + never),
        "dispatched  " + _m(dispatched),
        "never dispatched  " + _m(never),
        "delivered  " + _m(delivered),
        "still in flight  " + _m(in_flight),
        "unaccounted  " + _m(unaccounted),
    ]
    source = [0, 0, 1, 1, 1]
    target = [1, 2, 3, 4, 5]
    values = [dispatched, never, delivered, in_flight, unaccounted]
    link_colours = [
        "rgba(41,181,232,0.42)",   # pledged -> dispatched
        "rgba(107,114,128,0.32)",  # pledged -> never dispatched
        "rgba(23,163,74,0.42)",    # dispatched -> delivered
        "rgba(41,181,232,0.34)",   # dispatched -> still in flight
        "rgba(229,72,77,0.78)",    # dispatched -> unaccounted, heaviest
    ]

    fig = go.Figure(
        go.Sankey(
            arrangement="snap",
            node=dict(
                label=labels,
                pad=24,
                thickness=15,
                line=dict(color=BORDER, width=1),
                color=[SNOWFLAKE_BLUE, SNOWFLAKE_BLUE, NEUTRAL,
                       CONFIRMED_GREEN, SNOWFLAKE_BLUE, FLAG_RED],
                hovertemplate="%{label}<extra></extra>",
            ),
            link=dict(
                source=source, target=target, value=values, color=link_colours,
                hovertemplate="$%{value:,.0f}<extra></extra>",
            ),
            textfont=dict(family=FONT, size=12, color=TEXT),
        )
    )
    fig = style_fig(fig, height=height)
    # A node label on the rightmost column needs room to sit to the right
    # of its own bar, and the default margin clips it mid-word.
    fig.update_layout(margin=dict(l=8, r=8, t=18, b=8))
    return fig


# The two speed regimes the transit section is drawn against. Neither is
# a rule this build enforces; they are there so the distribution has
# something to be read against, and both are labelled on the chart.
ROAD_KMH = 90.0     # a loaded truck on a good road
JET_KMH = 900.0     # a freight aircraft at cruise


def transit_speed_profile(df, *, instantaneous: int = 0,
                          height: int = 340) -> go.Figure:
    """Implied speed of every delivery that has a finite one.

    WHY THIS REPLACED THE SCATTER IT USED TO BE.

        The old chart plotted transit hours against kilometres from base
        and shaded everything under a 90 km/h line as physically
        impossible. It labelled 6,828 of 8,545 deliveries that way, while
        the warehouse records 199 as IMPOSSIBLE_TRANSIT. The shading was
        wrong, not the data: km_from_base is measured from the
        organisation's registered filing address in the United States,
        the delivery is on another continent, and 10,000 kilometres in
        two days is 218 km/h, which is air freight doing exactly what air
        freight does. A rule that flags four deliveries in five has not
        found anything.

        So the axis is the implied speed itself, on a log scale, read
        against two labelled reference speeds rather than against a
        threshold this build never shipped. The distribution sits in the
        air-freight band, which is the honest reading, and the tail past
        cruise speed is visible as a tail rather than as an accusation.

    ``instantaneous`` is the count of deliveries recorded as arriving in
    the hour they were dispatched. They have no implied speed at all,
    only a division by zero, so they are annotated rather than binned:
    putting them in a histogram would place the fastest events in the
    corpus at the slow end of it.
    """
    speeds = [float(v) for v in df["implied_kmh"] if v is not None and v == v]
    speeds = [v for v in speeds if v > 0]
    low = min(speeds + [ROAD_KMH]) * 0.92
    high = max(speeds + [JET_KMH]) * 1.06

    # Explicit edges so the two reference speeds are bin boundaries. A
    # bin that straddles 90 km/h cannot be coloured honestly, and the
    # whole point of the colouring is that each bar sits in one regime.
    def _log_edges(a: float, b: float, n: int) -> list[float]:
        step = (math.log(b) - math.log(a)) / n
        return [math.exp(math.log(a) + step * k) for k in range(n + 1)]

    edges = (_log_edges(low, ROAD_KMH, 2)[:-1]
             + _log_edges(ROAD_KMH, JET_KMH, 22)[:-1]
             + _log_edges(JET_KMH, high, 8))

    counts = [0] * (len(edges) - 1)
    for value in speeds:
        lo, hi = 0, len(counts) - 1
        while lo < hi:                       # the bin whose right edge clears it
            mid = (lo + hi) // 2
            if value <= edges[mid + 1]:
                hi = mid
            else:
                lo = mid + 1
        counts[lo] += 1

    centres, colours, widths, hovers = [], [], [], []
    for k, n in enumerate(counts):
        a, b = edges[k], edges[k + 1]
        # A bar on a log axis is still positioned and sized in ordinary
        # data units. Plotly places its two edges at x plus or minus half
        # the width and maps those through the log afterwards, so the
        # centre is the arithmetic one and the width is kilometres per
        # hour. Sizing it in decades is what rendered thirty-two
        # hairlines the first time this chart was drawn.
        centres.append((a + b) / 2.0)
        widths.append(b - a)
        # The edges are built by exp of log, so a reference speed comes
        # back as 900.0000000000001 rather than as 900 and a strict
        # comparison paints the bar below cruise as though it were above.
        if b <= ROAD_KMH * 1.000001:
            colours.append(NEUTRAL)
            band = "at road speed"
        elif b <= JET_KMH * 1.000001:
            colours.append(SNOWFLAKE_BLUE)
            band = "in the air-freight band"
        else:
            colours.append(NOISE_AMBER)
            band = "above jet cruise"
        hovers.append(
            f"{a:,.0f} to {b:,.0f} km/h &middot; {n:,} deliveries {band}"
        )

    fig = go.Figure()
    fig.add_bar(
        x=centres, y=counts, width=widths,
        marker=dict(color=colours, line=dict(width=0)),
        customdata=hovers,
        hovertemplate="%{customdata}<extra></extra>",
        showlegend=False,
    )
    for speed, label, anchor in (
        (ROAD_KMH, "a truck on a good road, 90 km/h", "left"),
        (JET_KMH, "freight aircraft at cruise, 900 km/h", "right"),
    ):
        fig.add_vline(x=speed,
                      line=dict(color=TEXT_MUTED, width=1, dash="dot"))
        # The line takes its x in data units and the annotation takes its
        # x in axis units, which on a log axis are decades. Passing the
        # speed to both put the label at ten to the ninetieth power,
        # which is off the chart and renders as nothing at all.
        fig.add_annotation(
            x=math.log10(speed), y=1.0, xref="x", yref="paper",
            text=label, showarrow=False,
            xanchor=anchor, yanchor="bottom",
            xshift=6 if anchor == "left" else -6,
            font=dict(family=FONT, size=11, color=TEXT_MUTED),
        )

    fig = style_fig(fig, height=height)
    # style_fig sets a 28 px top margin and a reference line's own label
    # does not fit in it. update_layout merges recursively, so the
    # override has to come after the styling gate rather than before.
    fig.update_layout(margin=dict(l=8, r=8, t=46, b=8), bargap=0.06)
    # A log axis left to itself labels its minor ticks, and over a range
    # this narrow the result reads 8, 9, 100, 2, 3, 4 rather than as
    # speeds. The ticks are named explicitly instead.
    ticks = [t for t in (80, 100, 150, 200, 300, 500, 700, 1000, 1500, 2000)
             if low <= t <= high]
    fig.update_xaxes(
        type="log", range=[math.log10(low), math.log10(high)],
        tickmode="array", tickvals=ticks,
        ticktext=[f"{t:,}" for t in ticks],
        title=dict(text="implied speed, kilometres per hour",
                   font=dict(family=FONT, size=12, color=TEXT_MUTED)),
    )
    fig.update_yaxes(
        title=dict(text="deliveries",
                   font=dict(family=FONT, size=12, color=TEXT_MUTED)),
    )
    if instantaneous:
        fig.add_annotation(
            xref="paper", yref="paper", x=1.0, y=0.86,
            xanchor="right", yanchor="top", align="right", showarrow=False,
            text=(f"<b>{instantaneous:,} more are not on this chart</b><br>"
                  "recorded arriving in the hour they left,<br>"
                  "four hundred kilometres away or further"),
            font=dict(family=FONT, size=11, color=FLAG_RED),
            bgcolor="rgba(255,255,255,0.86)",
            bordercolor=FLAG_RED, borderwidth=1, borderpad=7,
        )
    return fig


def attrition_split(df, label_column: str, *, height: int = 420,
                    as_share: bool = True) -> go.Figure:
    """One horizontal bar per place, split by where the money ended up.

    Three segments, three statuses, three colours that mean the same
    thing on every tab in the build. As a share by default, because the
    question the section asks is which corridor loses the most of what
    passes through it, and a dollar bar answers a different question:
    which corridor is biggest.
    """
    labels = list(df[label_column])
    moved = [max(float(v or 0), 1.0) for v in df["moved_usd"]]
    fig = go.Figure()
    for name, column, colour in (
        ("delivered", "delivered_usd", CONFIRMED_GREEN),
        ("still in flight", "in_flight_usd", SNOWFLAKE_BLUE),
        ("unaccounted", "unaccounted_usd", FLAG_RED),
    ):
        raw = [float(v or 0) for v in df[column]]
        if as_share:
            values = [100.0 * v / m for v, m in zip(raw, moved)]
            hover = ("%{y}<br>" + name
                     + " %{x:.1f}% &middot; $%{customdata:,.0f}<extra></extra>")
        else:
            values = raw
            hover = "%{y}<br>" + name + " $%{x:,.0f}<extra></extra>"
        # Only the unaccounted segment is labelled. Every bar is the same
        # length here, so the eye has nothing to compare except that one
        # segment, and asking the reader to judge four percentage points
        # by the width of a red block is asking too much. Labelling all
        # three would put three numbers on a bar to make one point.
        #
        # The label sits outside the bar, not inside it. Inside, Plotly
        # drops any label its own segment is too narrow to hold, which
        # silently unlabelled five of the sixteen districts and made the
        # five that lost their label look like the ones with nothing to
        # report. Outside, every label is drawn and they line up in a
        # column, which is easier to read down than a staggered set.
        label_kw = {}
        if as_share and column == "unaccounted_usd":
            label_kw = dict(
                text=[f"{v:.1f}%" for v in values],
                textposition="outside",
                textfont=dict(family=FONT, size=11, color=FLAG_RED),
                cliponaxis=False, constraintext="none",
            )
        fig.add_bar(
            y=labels, x=values, orientation="h", name=name,
            marker=dict(color=colour),
            customdata=raw,
            hovertemplate=hover,
            **label_kw,
        )
    fig = style_fig(fig, height=height, legend=True)
    # A horizontal stack reads left to right and so must its legend;
    # Plotly reverses the order by default to match vertical stacking.
    fig.update_layout(barmode="stack", bargap=0.34, legend_traceorder="normal")
    fig.update_yaxes(autorange="reversed")
    if as_share:
        # The range runs past 100 to leave the outside labels somewhere to
        # sit; the ticks stop at 100, because 108 percent of a thing is
        # not a number this chart should appear to be offering.
        fig.update_xaxes(range=[0, 109], showgrid=True, gridcolor="#F0F2F4",
                         tickmode="array",
                         tickvals=[0, 20, 40, 60, 80, 100],
                         ticktext=["0%", "20%", "40%", "60%", "80%", "100%"])
    else:
        fig.update_xaxes(tickprefix="$", separatethousands=True, showgrid=True,
                         gridcolor="#F0F2F4")
    return fig


def delivery_rate_weekly(df, *, benchmark: float, benchmark_label: str,
                         height: int = 300) -> go.Figure:
    """Weekly delivery rate against the published ratio it is tuned to.

    A calibrated aggregate is a claim about one number. Drawing the weeks
    it is made of shows the spread that tuning leaves behind, which is
    the part a single headline percentage hides.
    """
    weeks = list(df["week"])
    rate = [100.0 * float(v or 0) for v in df["delivery_rate"]]
    moved = [float(v or 0) for v in df["moved_usd"]]

    fig = go.Figure()
    fig.add_scatter(
        x=weeks, y=rate, mode="lines+markers",
        line=dict(color=SNOWFLAKE_BLUE, width=2, shape="spline", smoothing=0.6),
        marker=dict(size=6, color=SNOWFLAKE_BLUE,
                    line=dict(width=1.5, color="#FFFFFF")),
        customdata=moved,
        name="weekly delivery rate",
        hovertemplate=("week of %{x|%d %b}<br>%{y:.1f}% delivered"
                       " of $%{customdata:,.0f} moved<extra></extra>"),
    )
    fig.add_hline(
        y=benchmark * 100.0,
        line=dict(color=CONFIRMED_GREEN, width=1.4, dash="dash"),
        annotation_text=benchmark_label,
        annotation_position="bottom right",
        annotation_font=dict(family=FONT, size=11, color=CONFIRMED_GREEN),
    )
    fig = style_fig(fig, height=height)
    span = max(rate + [benchmark * 100.0]) - min(rate + [benchmark * 100.0])
    pad = max(span * 0.35, 2.0)
    fig.update_yaxes(
        range=[min(rate + [benchmark * 100.0]) - pad,
               max(rate + [benchmark * 100.0]) + pad],
        ticksuffix="%",
        title=dict(text="share of dispatched dollars delivered",
                   font=dict(family=FONT, size=11, color=TEXT_MUTED)),
    )
    fig.update_xaxes(showgrid=False, tickformat="%d %b")
    return fig


# ---------------------------------------------------------------------------
# C05-1 / Noise against cohort size, C05-3 / Repeated queries
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# C06-1 / Expected against actual, C06-2 / Mint activity
# ---------------------------------------------------------------------------


def receipt_gap(df, *, height: int = 340) -> go.Figure:
    """Two cumulative step lines. Where they separate, fill the gap red.

    The visual argument is that a missing receipt is itself a finding,
    which is the entire reason a public ledger belongs in this design.

    WHAT THE SHAPE OF THIS CHART ACTUALLY SAYS.

        The purple line is flat at zero for four months and then steps up
        once. That is not four months of neglect, and reading it that way
        is the trap the first version of this chart walked into by
        annotating only the final gap. Minting is a migration: it began
        on one day, ran for twenty-two minutes, and wrote as many leaves
        as devnet SOL allowed. The date it began is marked on the chart
        so the flat stretch is read as "before the bridge existed" rather
        than as "nobody bothered".

        The red area is still the finding. It is just a finding about how
        far the migration has got, not about a record that was quietly
        skipped.
    """
    fig = go.Figure()
    fig.add_scatter(
        x=df["day"], y=df["cum_actual"], mode="lines",
        line=dict(color=SOLANA_PURPLE, width=2.5, shape="hv"),
        name="receipts confirmed on chain",
        hovertemplate="%{x|%d %b}: %{y:,} on chain<extra></extra>",
    )
    fig.add_scatter(
        x=df["day"], y=df["cum_expected"], mode="lines",
        line=dict(color=SNOWFLAKE_BLUE, width=2.5, shape="hv"),
        fill="tonexty", fillcolor="rgba(229,72,77,0.16)",
        name="verified in the warehouse",
        hovertemplate="%{x|%d %b}: %{y:,} expected<extra></extra>",
    )

    # The day the ledger first heard about any of this.
    started = None
    for row in df.itertuples():
        if float(getattr(row, "cum_actual", 0) or 0) > 0:
            started = row.day
            break
    if started is not None:
        fig.add_vline(
            x=started, line=dict(color=SOLANA_PURPLE, width=1, dash="dot"),
        )
        fig.add_annotation(
            x=started, y=1.0, xref="x", yref="paper",
            text="minting begins", showarrow=False,
            xanchor="right", yanchor="bottom", xshift=-6,
            font=dict(family=FONT, size=11, color=SOLANA_PURPLE),
        )

    if len(df):
        last = df.iloc[-1]
        if float(last["cum_gap"] or 0) > 0:
            fig.add_annotation(
                x=last["day"],
                y=(float(last["cum_expected"]) + float(last["cum_actual"])) / 2,
                text=f"awaiting a receipt<br>{int(last['cum_gap']):,}",
                showarrow=True, arrowhead=2, arrowcolor=FLAG_RED,
                font=dict(family=FONT, size=12, color=FLAG_RED),
                ax=-64, ay=0,
                bgcolor="rgba(255,255,255,0.86)",
            )
    fig = style_fig(fig, height=height, legend=True)
    fig.update_yaxes(separatethousands=True, title=dict(
        text="cumulative records",
        font=dict(family=FONT, size=11, color=TEXT_MUTED)))
    return fig


def mint_progress(df, label_column: str, *, height: int = 300) -> go.Figure:
    """How far the migration has got, per band or per appeal.

    THIS REPLACED A STRIP OF DOTS THAT SAID NOTHING.

        The old chart put one marker per mint on a time axis against the
        amount band. Every mint in the corpus landed inside one
        twenty-two minute window, so all of them piled onto three
        horizontal lines and the picture was three solid purple bars. It
        was offered as proof that the volume was genuine, and it could
        not have distinguished three hundred mints from three.

        What is actually worth showing is the part that is not finished:
        how many records are queued against how many the ledger has, per
        group, so no group can be quietly ahead of the others.
    """
    labels = list(df[label_column])
    queued = [int(v or 0) for v in df["queued"]]
    covered = [int(v or 0) for v in df["covered"]]
    remaining = [max(q - c, 0) for q, c in zip(queued, covered)]

    fig = go.Figure()
    fig.add_bar(
        y=labels, x=covered, orientation="h", name="on the ledger",
        marker=dict(color=SOLANA_PURPLE),
        hovertemplate="%{y}<br>%{x:,} on the ledger<extra></extra>",
    )
    fig.add_bar(
        y=labels, x=remaining, orientation="h", name="still queued",
        marker=dict(color="#E9EBEF"),
        text=[f"{c:,} of {q:,}" for c, q in zip(covered, queued)],
        textposition="outside",
        textfont=dict(family=FONT, size=11, color=TEXT_MUTED),
        cliponaxis=False, constraintext="none",
        hovertemplate="%{y}<br>%{x:,} still queued<extra></extra>",
    )
    fig = style_fig(fig, height=height, legend=True)
    fig.update_layout(barmode="stack", bargap=0.4, legend_traceorder="normal")
    fig.update_yaxes(autorange="reversed")
    top = max(queued + [1])
    fig.update_xaxes(range=[0, top * 1.22], separatethousands=True,
                     showgrid=True, gridcolor="#F0F2F4")
    return fig


# ---------------------------------------------------------------------------
# C07-1 / Value history
# ---------------------------------------------------------------------------


def _ago(seconds: float) -> str:
    """A negative second offset, spelled the way a person reads a clock."""
    seconds = float(seconds)
    # The preview replays an edit as a positive pseudo-offset, which is
    # its way of saying "after you pressed the button". Running that
    # through the same arithmetic as a real negative offset would print a
    # change you just made as though it had happened half an hour ago.
    if seconds >= 0:
        return "after the edit"
    seconds = abs(seconds)
    if seconds < 90:
        return "now" if seconds < 5 else f"{seconds:.0f}s ago"
    if seconds < 3600:
        return f"{seconds / 60:.0f} min ago"
    hours = seconds / 3600
    return "1 hour ago" if abs(hours - 1) < 0.05 else f"{hours:.1f} hours ago"


def value_history(df, *, height: int = 300) -> go.Figure:
    """Score for the selected organisation across Time Travel offsets.

    An operator can alter the present but not the record of the past,
    which is the warehouse-side counterpart to the on-chain receipt.

    The x axis used to be the raw offset column, so it read
    -3601, -3600.5, -3600 and the reader was asked to translate negative
    seconds into a moment in time. The offsets are the query parameter,
    not the label: they are spelled here as the clock reading they stand
    for, and the ticks are placed only where a query was actually made
    rather than wherever a linear axis felt like putting one.
    """
    as_of = [float(v) for v in df["as_of"]]
    scores = [float(v) for v in df["risk_score"]]
    verdicts = [str(v) for v in df["verdict"]]

    # A category axis, not a numeric one. The offsets are 60, 120, 300,
    # 600, 1800 and 3600 seconds, so on a linear axis four of the six
    # readings crowd into the last sixth of the width and their labels
    # overlap into each other. They are six discrete queries rather than
    # a continuous series, and spacing them evenly is both legible and
    # closer to what they are.
    labels = [_ago(v) for v in as_of]

    fig = go.Figure()
    fig.add_scatter(
        x=labels, y=scores, mode="lines+markers",
        line=dict(color=SNOWFLAKE_BLUE, width=2.5, shape="hv"),
        marker=dict(size=9, color=INK, line=dict(width=2, color="#FFFFFF")),
        customdata=[[w] for w in verdicts],
        hovertemplate="%{x}<br>score %{y:.1f}"
                      "<br>%{customdata[0]}<extra></extra>",
    )
    # Label only where the value moved. Labelling a flat line at every
    # point prints the same number six times and says nothing.
    previous = None
    for label, y in zip(labels, scores):
        if previous is not None and abs(y - previous) > 1e-9:
            fig.add_annotation(
                x=label, y=y, text=f"{y:.0f}",
                showarrow=True, arrowhead=2, arrowcolor=TEXT_MUTED,
                font=dict(family=FONT, size=12, color=INK), ay=-28,
            )
        previous = y

    fig = style_fig(fig, height=height)
    fig.update_xaxes(
        type="category", categoryorder="array", categoryarray=labels,
        title=dict(text="read at this Time Travel offset",
                   font=dict(family=FONT, size=11, color=TEXT_MUTED)),
    )
    span = (max(scores) - min(scores)) if scores else 0.0
    pad = max(span * 0.4, 3.0)
    fig.update_yaxes(
        range=[min(scores) - pad, max(scores) + pad] if scores else None,
        title=dict(text="risk score",
                   font=dict(family=FONT, size=11, color=TEXT_MUTED)),
    )
    return fig


# ---------------------------------------------------------------------------
# C00-1 / Evidence timeline, C00-2 / Pipeline freshness
# ---------------------------------------------------------------------------


def evidence_timeline(df) -> go.Figure:
    """Cited incidents on a dated chart, one row per citation.

    Two earlier versions of this were wrong in instructive ways.

    The first hid the y-axis and let the markers float, so the vertical
    position meant nothing a reader could name and nothing was legible
    without hovering. The second gave each region a lane, which fixed the
    axis but not the collisions: three of the seven United States
    citations were published inside nineteen days, so on any date scale
    that also shows a 2023 incident they land on top of each other.

    One row per citation is the version that works. Nothing can collide,
    the row label carries the claim, the marker carries the figure in
    words, and colour still groups the rows by region. The chart is
    readable in a screenshot with no pointer anywhere near it, which is
    the bar for every figure on this tab.

    Marker area scales WITHIN a unit type only. Tonnes and dollars are
    not comparable and sizing them against each other would be the exact
    sloppiness this tab objects to.
    """
    fig = go.Figure()

    # A rule along each row, so the horizontal position is read against
    # something rather than against empty space.
    for row_index in range(len(df)):
        fig.add_shape(
            type="line", xref="paper", x0=0, x1=1,
            yref="y", y0=row_index, y1=row_index,
            line=dict(color="#F0F2F4", width=1), layer="below",
        )

    regions = list(dict.fromkeys(df["region"]))
    for idx, region in enumerate(regions):
        sub = df[df["region"] == region]
        fig.add_scatter(
            x=sub["published_on"], y=sub["row"], mode="markers+text",
            marker=dict(
                size=sub["marker_size"],
                color=CATEGORICAL[idx % len(CATEGORICAL)],
                opacity=0.9, line=dict(width=1.5, color="#FFFFFF"),
            ),
            text=sub["label"], textposition="middle right",
            textfont=dict(family=FONT, size=12, color=TEXT),
            cliponaxis=False,
            name=region,
            customdata=sub[["claim", "figure", "issuing_body"]],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>%{customdata[1]}"
                "<br>%{customdata[2]}<extra></extra>"
            ),
        )

    # style_fig merges its own xaxis, yaxis and margin into the layout,
    # so anything set before it is silently overwritten. Style first.
    fig = style_fig(fig, height=max(300, 44 * len(df) + 80), legend=True)

    # Room at both ends: the first marker should not touch the axis, and
    # the last one's label needs somewhere to sit.
    span = df["published_on"].max() - df["published_on"].min()
    fig.update_xaxes(
        range=[df["published_on"].min() - span * 0.06,
               df["published_on"].max() + span * 0.17],
        showgrid=True, gridcolor="#F0F2F4", tickformat="%b %Y",
        tickfont=dict(family=FONT, size=12, color=TEXT_MUTED),
        ticks="outside", ticklen=4, tickcolor=BORDER,
    )
    fig.update_yaxes(
        visible=True, showgrid=False, showline=False, ticks="",
        tickmode="array",
        tickvals=list(df["row"]), ticktext=list(df["row_label"]),
        tickfont=dict(family=FONT, size=12, color=TEXT),
        range=[len(df) - 0.5, -0.5],   # oldest citation at the top
        automargin=True,
    )
    fig.update_layout(margin=dict(l=8, r=8, t=16, b=8))
    return fig


def pipeline_freshness(df) -> go.Figure:
    """One bar per Dynamic Table, with a dashed rule at the TARGET_LAG.

    Bars inside lag render Snowflake Blue, bars past it render Noise
    Amber. It is how a judge sees the declarative pipeline without opening
    a SQL file, and it proves the warehouse is live rather than a static
    extract.
    """
    colours = [
        SNOWFLAKE_BLUE if within else NOISE_AMBER
        for within in as_bool(df["within_lag"])
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
    fig = style_fig(fig, height=max(240, 32 * len(df) + 76))
    fig.update_yaxes(autorange="reversed")
    top = max(lag, float(df["seconds_since_refresh"].max()) if len(df) else lag)
    fig.update_xaxes(range=[0, top * 1.18], showgrid=True, gridcolor="#F0F2F4")
    fig.update_layout(margin=dict(l=8, r=8, t=34, b=8))
    return fig


# ---------------------------------------------------------------------------
# C09-1 / Confidence against delivery rate
# ---------------------------------------------------------------------------


def confidence_scatter(df, *, height: int = 420) -> go.Figure:
    """Bubble scatter. The warm counterpart to Tab 01's cold open.

    X is confirmed delivery rate, Y is receipt coverage, bubble area is
    value moved. Every dot is a real organisation.

    TWO THINGS WERE WRONG WITH THE FIRST VERSION.

        It coloured by cause, and this corpus has twenty-five causes, so
        the chart arrived under five rows of legend that pushed the plot
        off the fold and told the reader nothing: the cause of a dot is a
        fact about that dot, which is what a hover is for, not a
        dimension anyone was comparing.

        And it shaded a quadrant at seventy percent on both axes and
        labelled it "give here with confidence" while the highest receipt
        coverage in the corpus was fifty-seven percent, so the box it
        pointed at was empty by construction. A recommendation region
        that cannot contain anything is worse than none.

    The split that does carry meaning is whether the ledger has heard of
    an organisation at all, because minting is a migration in progress.
    That is two colours and a two-item legend, and the y axis reads as a
    statement about the migration rather than about the organisations.
    """
    has = df[df["receipt_coverage"] > 0]
    awaiting = df[df["receipt_coverage"] <= 0]
    sizeref = 2.0 * max(float(df["value_moved_usd"].max() or 1), 1) / (44.0 ** 2)

    fig = go.Figure()
    for sub, name, colour, opacity in (
        (awaiting, "awaiting a receipt", NEUTRAL, 0.32),
        (has, "receipts on chain", SOLANA_PURPLE, 0.72),
    ):
        if not len(sub):
            continue
        fig.add_scatter(
            x=sub["delivery_rate"], y=sub["receipt_coverage"], mode="markers",
            marker=dict(
                size=sub["value_moved_usd"], sizemode="area",
                sizeref=sizeref, sizemin=4, color=colour,
                opacity=opacity, line=dict(width=1, color="#FFFFFF"),
            ),
            name=name,
            customdata=sub[["name", "city", "state", "value_moved_usd", "cause"]],
            hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[4]}"
                          "<br>%{customdata[1]}, %{customdata[2]}"
                          "<br>delivery %{x:.0%} &middot; receipts %{y:.0%}"
                          "<br>$%{customdata[3]:,.0f} moved<extra></extra>",
        )

    top = max(float(df["receipt_coverage"].max() or 0.0), 0.05)
    fig.update_xaxes(range=[0.25, 1.04], tickformat=".0%", title=dict(
        text="confirmed delivery rate",
        font=dict(family=FONT, size=12, color=TEXT_MUTED)))
    fig.update_yaxes(range=[-top * 0.06, top * 1.12], tickformat=".0%",
                     title=dict(
                         text="receipt coverage",
                         font=dict(family=FONT, size=12, color=TEXT_MUTED)))
    return style_fig(fig, height=height, legend=True)


def cause_signals(df, *, height: int = 380) -> go.Figure:
    """Median delivery and median receipt coverage, per cause, on one row.

    THIS REPLACED SIX EMPTY SUBPLOTS.

        The small multiples plotted every organisation in a cause on its
        own pair of axes. With receipt coverage near zero for most of the
        corpus, all six panels drew the same flat line along the bottom,
        six times, and shared axes made every one of them look identical
        because they were.

        A dot plot compares the causes directly, which is the comparison
        the section was for, and it survives a signal that is mostly zero
        because a median of zero is a legible position on a line rather
        than a smear against an axis.
    """
    causes = list(df["cause"])
    fig = go.Figure()
    for row in df.itertuples():
        fig.add_scatter(
            x=[float(row.delivery_rate), float(row.receipt_coverage)],
            y=[row.cause, row.cause], mode="lines",
            line=dict(color=BORDER, width=1.5),
            showlegend=False, hoverinfo="skip",
        )
    for column, name, colour in (
        ("receipt_coverage", "median receipt coverage", SOLANA_PURPLE),
        ("delivery_rate", "median delivery rate", CONFIRMED_GREEN),
    ):
        fig.add_scatter(
            x=[float(v) for v in df[column]], y=causes, mode="markers",
            marker=dict(size=11, color=colour,
                        line=dict(width=1.5, color="#FFFFFF")),
            name=name,
            customdata=[int(v) for v in df["orgs"]],
            hovertemplate="%{y}<br>" + name
                          + " %{x:.0%}<br>%{customdata} organisations"
                            "<extra></extra>",
        )
    fig = style_fig(fig, height=height, legend=True)
    fig.update_layout(legend_traceorder="reversed")
    fig.update_xaxes(range=[-0.03, 1.04], tickformat=".0%", showgrid=True,
                     gridcolor="#F0F2F4")
    fig.update_yaxes(autorange="reversed")
    return fig


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
    fig = style_fig(fig, height=height)
    fig.update_yaxes(autorange="reversed")
    # An outside label on the longest bar needs somewhere to sit, or it
    # is clipped by the edge of the plotting area.
    top = max([float(v) for v in values] or [1.0])
    fig.update_xaxes(range=[0, top * 1.16], showgrid=True, gridcolor="#F0F2F4")
    return fig


def schema_inventory(df, height: int | None = None) -> go.Figure:
    """Objects per schema, split by what kind of object each one is.

    A single bar of "14 objects" says less than it looks like it does.
    Splitting it shows the shape of the build directly: RAW is a handful
    of plain tables nobody edits, MARTS carries the Dynamic Tables, and
    SERVING is nothing but views because that is the only schema anything
    is allowed to read.
    """
    plain = (df["objects"].astype(int)
             - df["dynamic_tables"].astype(int)
             - df["views"].astype(int)).clip(lower=0)
    fig = go.Figure()
    for name, series, colour in (
        ("tables", plain, NEUTRAL),
        ("dynamic tables", df["dynamic_tables"].astype(int), SNOWFLAKE_BLUE),
        ("views", df["views"].astype(int), "#8DD9F5"),
    ):
        fig.add_bar(
            y=df["schema_name"], x=series, orientation="h", name=name,
            marker=dict(color=colour),
            hovertemplate="%{y}: %{x} " + name + "<extra></extra>",
        )
    fig = style_fig(fig, height=height or max(240, 34 * len(df) + 76),
                    legend=True)
    # Plotly lists a stacked legend in reverse so it matches the stacking
    # order top-down; here the bars are horizontal, so normal order is
    # the one that matches what the eye reads left to right.
    fig.update_layout(barmode="stack", bargap=0.42, legend_traceorder="normal")
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(showgrid=True, gridcolor="#F0F2F4", dtick=5)
    return fig
