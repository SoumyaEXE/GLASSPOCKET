"""Tab 02 / The Trust Graph. Build Spec Section 07.

    One imitation is an incident. Four hundred is a structure.

Moves the viewer from a single pair to the shape of the whole problem,
and then back down to any single organisation they care to name.

FIVE THINGS HERE EXIST BECAUSE THE FIRST VERSION GOT THEM WRONG.

  * The threshold slider opened at 0.86 and the band beneath it called
    0.86 the production value. The production cut-off is 0.94 and has
    been since the calibration run; 0.86 is the figure in the build
    specification, written before anyone measured anything. A tab whose
    argument is that numbers must be checkable was publishing a stale
    one, in the one place a judge is most likely to check.

  * The second line on that chart, "also confirmed by the AI predicate",
    was flat at 188 across the whole sweep. AI_FILTER is unavailable on
    this account, so confirmation was computed once, at the production
    cut-off. Drawing it across thirty thresholds turned an artefact into
    what looked like a finding. What justifies a threshold is precision
    and recall against ground truth, and that is what sits there now.

  * The node inspector was a bordered card with the EIN, the imitation
    count, a button and an info box hanging underneath it, outside the
    border, each one a different width. It is one panel now.

  * The inspector reported "0 imitations point at this organisation" for
    seeded rows. A seeded row has no imitations pointing at it, it points
    at something. It now says which.

  * Every verified node was drawn at fourteen pixels, so the hubs, which
    are the entire reason to draw a graph rather than a table, were
    invisible. They are sized by degree.

THE TRUST SCORE IS NOT A NEW SCORE. It is 100 minus MARTS.F_RISK, the
same UDF Tab 01 decomposes into a waterfall. A second scoring system
would mean two numbers that can disagree about the same organisation,
inside an application arguing that scores must be legible.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import charts
import components as C
import data
import queries as Q
from theme import FLAG_RED, SNOWFLAKE_BLUE

#: The delivery corridors, spelled out. A two letter code is a database
#: key, not a place, and this tab is read by people who are not looking
#: at the schema.
COUNTRY_NAMES = {
    "IN": "India",
    "SD": "Sudan",
    "PS": "Palestine",
    "BD": "Bangladesh",
    "NE": "Niger",
}

GEO_LENSES = ("where the money landed", "where the filing is registered")


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------


def _picker(options, key: str, default: str) -> str:
    """A segmented control, or buttons where the control does not exist.

    st.segmented_control arrived in Streamlit 1.40. Streamlit in Snowflake
    pins its own version and it is not ours to choose, so anything that
    depends on the newer control needs the older path underneath it.
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


def _row(frame: pd.DataFrame) -> dict:
    """First row as a plain dict, or an empty dict."""
    return frame.iloc[0].to_dict() if len(frame) else {}


def _f(value, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _i(value, default: int = 0) -> int:
    return int(_f(value, default))


def _text(value, default: str = "unrecorded") -> str:
    """A string, or the default.

    ``value or default`` is wrong here. A NaN out of pandas is truthy, so
    a missing technique renders as the literal string "nan" rather than
    as the absence it is.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    text = str(value).strip()
    return text if text and text.lower() != "nan" else default


def _country(code) -> str:
    code = str(code or "").upper()
    return COUNTRY_NAMES.get(code, code or "unrecorded")


# ---------------------------------------------------------------------------
# S3 / the network and its inspector
# ---------------------------------------------------------------------------


def _network(nodes: pd.DataFrame, edges: pd.DataFrame, focus) -> None:
    """The graph, with click selection where the runtime offers it."""
    figure = charts.impersonation_network(nodes, edges, focus_id=focus)
    try:
        event = st.plotly_chart(
            figure, use_container_width=True, config=charts.bare_config(),
            on_select="rerun", selection_mode="points", key="gp_g_network",
        )
    except TypeError:                        # pragma: no cover
        # Selection events arrived in Streamlit 1.35. Without them the
        # graph is still a graph; the hub picker beside it is the route
        # to any node, and it was always the better route on a touch
        # screen anyway.
        st.plotly_chart(figure, use_container_width=True,
                        config=charts.bare_config())
        return

    try:
        points = event["selection"]["points"]
        if points:
            custom = points[0].get("customdata")
            if custom:
                st.session_state["gp_focus_org_id"] = custom[0]
    except (KeyError, TypeError, IndexError):
        pass


def _inspector(focus, lowest_real_trust: float | None) -> None:
    """One panel. Card, gauge, fields, action.

    Everything the inspector knows lives inside a single border. The
    previous version put the EIN, the imitation count, the button and an
    info box outside the card in four different widths, which read as
    four unrelated things rather than as one record.
    """
    detail = _row(data.run("Q_NODE_DETAIL", (focus,)))
    if not detail:
        C.panel_head("Node inspector")
        C.source_note("No detail stored for that node.")
        return

    seeded = bool(detail.get("is_synthetic"))
    risk = detail.get("risk_score")
    trust = 100.0 - _f(risk) if risk is not None and not pd.isna(risk) else None
    band_label, band_tone = charts.trust_band(trust if trust is not None else 100.0)

    C.panel_head(
        "Node inspector",
        note_html=C.chip("seeded imitation" if seeded else "verified",
                         "seeded" if seeded else "verified"),
    )
    st.markdown(
        f'<div class="gp-card-name">{C.escape(str(detail.get("name", "")))}</div>'
        f'<div class="gp-card-meta">{C.escape(str(detail.get("cause", "")))}'
        f' &middot; {C.escape(str(detail.get("city", "")))}'
        f' &middot; {C.escape(str(detail.get("state", "")))}</div>',
        unsafe_allow_html=True,
    )

    if trust is None:
        C.source_note("This organisation carries no score in MARTS.ORG_RISK.")
    else:
        st.plotly_chart(
            charts.trust_gauge(trust, comparison=lowest_real_trust,
                               comparison_label="lowest real filing",
                               height=126),
            use_container_width=True, config=charts.bare_config(static=True),
        )

    rows = [("filing number, EIN", _text(detail.get("ein"), "not recorded"))]
    if trust is not None:
        rows.append(("trust score", f"{trust:.1f} · {band_label}"))
    if seeded:
        # A seeded row points at something; it is not pointed at.
        rows.append(("imitates",
                     _text(detail.get("nearest_target_name"), "unresolved")))
        rows.append(("meaning similarity",
                     f"{_f(detail.get('semantic_sim')):.3f}"))
        rows.append(("evasion gap", f"{_f(detail.get('evasion_gap')):.3f}"))
        rows.append(("technique", _text(detail.get("synth_technique"))))
    else:
        rows.append(("imitations pointing at it",
                     f"{_i(detail.get('imitations_pointing_at_it')):,}"))
        rows.append(("standing",
                     "verified filing" if detail.get("is_verified")
                     else "present, not verified"))
    C.kv_rows(rows)

    if st.button("trace its money", key="gp_g_trace",
                 use_container_width=True):
        st.session_state["gp_focus_org_id"] = focus
        st.session_state["gp_g_traced"] = True
    if st.session_state.get("gp_g_traced"):
        C.source_note(
            "Focus carried. Open Follow The Money to see where this "
            "organisation's disbursements landed."
        )


# ---------------------------------------------------------------------------
# S4 / score any organisation
# ---------------------------------------------------------------------------


def _search_box() -> str | None:
    """Name or filing-number search over all 45,400 rows.

    Returns the chosen org_id, or None to fall back to the graph focus.
    """
    term = st.text_input(
        "search", key="gp_g_search", label_visibility="collapsed",
        placeholder="organisation name, or filing number, e.g. relief",
    ).strip()
    if len(term) < 2:
        return None

    digits = "".join(ch for ch in term if ch.isdigit())
    # A pattern no EIN can match, for the case where the term is words.
    # Passing the words themselves would be a wasted predicate, not a bug,
    # but it also makes the query read as though EINs contain letters.
    matches = data.run("Q_ORG_SEARCH",
                       (f"%{term}%", f"{digits}%" if digits else "~none~"))
    if matches.empty:
        C.source_note(f"Nothing in the corpus matches “{term}”.")
        return None

    labels = {
        str(row.org_id): f"{row.name} — {row.city}, {row.state}"
        for row in matches.itertuples()
    }
    options = list(labels)
    chosen = st.selectbox(
        "matches", options, key="gp_g_match",
        format_func=lambda value: labels.get(value, value),
        label_visibility="collapsed",
    )
    C.source_note(
        f"{len(matches)} match{'' if len(matches) == 1 else 'es'}, ordered by "
        "score rather than alphabetically. A search that returns forty "
        "alphabetical rows buries the one row worth looking at."
    )
    return chosen


def _lookup(target: str, lowest_real_trust: float | None) -> None:
    """The trust panel for one organisation."""
    org = _row(data.run("Q_ORG_RISK_ONE", (target,)))
    if not org:
        C.source_note("That organisation carries no row in MARTS.ORG_RISK.")
        return

    risk = _f(org.get("risk_score"))
    trust = 100.0 - risk
    band_label, band_tone = charts.trust_band(trust)
    seeded = bool(org.get("is_synthetic"))
    cause = str(org.get("cause") or "")
    state = str(org.get("state") or "")

    rank = _row(data.run(
        "Q_ORG_TRUST_RANK",
        (risk, risk, cause, cause, risk, state, state, risk),
    ))
    context = _row(data.run("Q_ORG_TRUST_CONTEXT", (target,)))

    # ---------------------------------------------------------- the score
    with C.panel():
        C.panel_head(
            str(org.get("name") or "unnamed"),
            note_html=C.chip(band_label, band_tone) + " " + C.chip(
                "seeded imitation" if seeded else "real filing",
                "seeded" if seeded else "verified",
            ),
        )
        st.markdown(
            f'<div class="gp-card-meta">{C.escape(cause)} &middot; '
            f'{C.escape(str(org.get("city") or ""))} &middot; '
            f'{C.escape(state)} &middot; EIN '
            f'{C.escape(_text(org.get("ein"), "not recorded"))}</div>',
            unsafe_allow_html=True,
        )
        st.plotly_chart(
            charts.trust_gauge(trust, comparison=lowest_real_trust,
                               comparison_label="lowest real filing",
                               height=150),
            use_container_width=True, config=charts.bare_config(static=True),
        )
        population = _i(rank.get("population"), 1)
        higher = _i(rank.get("more_trusted"))
        same = _i(rank.get("same_score"))
        # ``same`` counts this organisation too, and an organisation is
        # not one of its own peers.
        ties = max(same - 1, 0)
        C.readout([
            (f"{trust:.1f}", "trust score"),
            (f"{higher:,}", "score higher"),
            (f"{ties:,}", "share this score"),
            (f"{population - higher - same:,}", "score lower"),
        ])

    C.source_note(
        "Three counts rather than a percentile. A filing that has moved no "
        "money and has no near neighbour scores nothing on any of the five "
        "components, and most of the corpus is in exactly that position "
        "carrying an identical clean zero, so a percentile would report a "
        "spotless organisation as sitting above a couple of per cent of its "
        "peers: arithmetically true and completely misleading. The counts "
        "say where this one actually stands."
    )

    # ------------------------------------------------- how it was arrived at
    wcol, ecol = st.columns([1.1, 1], gap="large")

    with wcol:
        with C.panel():
            C.panel_head("What the score is made of",
                         note_html=C.chip(band_label, band_tone))
            st.plotly_chart(
                charts.risk_waterfall(
                    {
                        "semantic proximity": _f(org.get("comp_semantic")),
                        "evasion gap": _f(org.get("comp_evasion")),
                        "geometry flags": _f(org.get("comp_geometry")),
                        "unaccounted ratio": _f(org.get("comp_unaccounted")),
                        "missing receipts": _f(org.get("comp_receipts")),
                    },
                    risk, height=298,
                ),
                use_container_width=True, config=charts.bare_config(),
            )
            C.readout([
                (f"{risk:.1f}", "risk points"),
                (f"{trust:.1f}", "trust score"),
                ("100", "points available"),
            ])
        C.source_note(
            "The same five weighted components Tab 01 renders for a single "
            "pair, read here for whichever organisation is on screen. 35 "
            "points of semantic proximity, 25 of evasion gap, 20 of "
            "geometry, 12 of unaccounted spend and 8 of missing receipts. "
            "Nothing is hidden inside the total."
        )

    with ecol:
        with C.panel():
            C.panel_head("The evidence behind it",
                         "dt_org_activity, dt_receipt_coverage")
            if not context or pd.isna(context.get("disbursements")):
                C.kv_rows([
                    ("disbursements", "none recorded"),
                    ("districts reached", "none recorded"),
                    ("pledged", "none recorded"),
                    ("money moved", "none recorded"),
                    ("delivered", "none recorded"),
                    ("still in flight", "none recorded"),
                    ("unaccounted", "none recorded"),
                    ("receipts on chain", "none recorded"),
                ])
                C.note(
                    "<strong>A clean score with no activity behind it is not "
                    "trust, it is absence of evidence.</strong> This "
                    "organisation has moved no money in the corpus, so four "
                    "of the five risk components have nothing to score and "
                    "return zero. That is the correct arithmetic and it is "
                    "the wrong thing to read as a recommendation."
                )
            else:
                moved = _f(context.get("moved_usd"))
                delivered = _f(context.get("delivered_usd"))
                unaccounted = _f(context.get("unaccounted_usd"))
                C.kv_rows([
                    ("disbursements", f"{_i(context.get('disbursements')):,}"),
                    ("districts reached", f"{_i(context.get('districts')):,}"),
                    ("pledged", C.usd(_f(context.get("pledged_usd")))),
                    ("money moved", C.usd(moved)),
                    ("delivered",
                     f"{C.usd(delivered)} "
                     f"({_f(context.get('delivery_rate')) * 100:.0f}%)"),
                    # Moved minus delivered minus unaccounted. It is in
                    # transit, which is neither an achievement nor a
                    # finding, and collapsing it into either one would
                    # misstate the record.
                    ("still in flight",
                     C.usd(max(moved - delivered - unaccounted, 0.0))),
                    ("unaccounted",
                     f"{C.usd(unaccounted)} "
                     f"({_f(context.get('unaccounted_ratio')) * 100:.0f}%)"),
                    ("receipts on chain",
                     f"{_i(context.get('receipts_on_chain')):,} of "
                     f"{_i(context.get('eligible_disbursements')):,}"),
                ])
                C.readout([
                    (f"{_f(context.get('delivery_rate')) * 100:.0f}%",
                     "delivered"),
                    (f"{_f(context.get('unaccounted_ratio')) * 100:.0f}%",
                     "unaccounted"),
                    (f"{_f(context.get('receipt_coverage')) * 100:.0f}%",
                     "receipted"),
                ], flag="unaccounted")
        C.source_note(
            "Receipt coverage is low across the corpus and the number is "
            "printed rather than smoothed: minting to devnet is still "
            "running, and a receipt that has not been written is a receipt "
            "that does not exist."
        )

    # ------------------------------------------------------ where it sits
    with C.panel():
        C.panel_head("Where it sits among its peers", "marts.org_risk")
        C.readout([
            (f"{_i(rank.get('cause_more_trusted')):,}", "score higher in cause"),
            (f"{_i(rank.get('cause_population')):,}", f"filings in {cause}"),
            (f"{_i(rank.get('state_more_trusted')):,}", "score higher in state"),
            (f"{_i(rank.get('state_population')):,}", f"filings in {state}"),
        ])


# ---------------------------------------------------------------------------
# S5 / where every score falls
# ---------------------------------------------------------------------------


def _distribution(invariant: dict) -> None:
    bands = data.run("Q_TRUST_BANDS")
    highest_real = _f(invariant.get("highest_real_risk"))
    real_flagged = _i(invariant.get("real_second_look"))
    seeded_flagged = _i(invariant.get("seeded_second_look"))

    with C.panel():
        C.panel_head(
            "Every organisation in the corpus, by trust score",
            note_html=C.chip(
                "no real filing past the line" if real_flagged == 0
                else f"{real_flagged:,} real filings past the line",
                "confirmed" if real_flagged == 0 else "flagged",
            ),
        )
        if bands.empty:
            C.source_note("No scored population.")
        else:
            st.plotly_chart(
                charts.trust_bands_chart(bands, highest_real=highest_real,
                                         height=330),
                use_container_width=True, config=charts.bare_config(),
            )
            C.readout([
                (f"{_i(invariant.get('real_filings')):,}", "real filings"),
                (f"{_i(invariant.get('seeded_rows')):,}", "seeded rows"),
                (f"{100.0 - highest_real:.1f}", "lowest real filing"),
                (f"{seeded_flagged:,}", "past the second-look line"),
                (f"{real_flagged:,}", "real filings past it"),
            ], flag="real filings past it" if real_flagged else None)

    if real_flagged == 0:
        C.verdict(
            "The separation is a property of the data, not a promise in prose.",
            f"Every one of the {seeded_flagged:,} organisations past the "
            f"second-look line is one this project seeded. The lowest-scoring "
            f"real filing in {_i(invariant.get('real_filings')):,} lands at "
            f"{100.0 - highest_real:.1f}, comfortably clear of it. That is "
            "asserted by Q_TRUST_INVARIANT on every render rather than "
            "checked once and written down, because the whole application "
            "rests on it: no real named organisation is ever shown in a "
            "flagged state.",
            "right",
        )
    else:
        C.verdict(
            "A real filing has crossed the second-look line.",
            f"{real_flagged:,} organisations that are not seeded now score "
            "past 55. This application does not publish accusations about "
            "named real organisations, so that is a defect in the seeding or "
            "in the score and it must be resolved before this tab is shown "
            "to anyone.",
            "wrong",
        )


# ---------------------------------------------------------------------------
# S6 / trust by geography
# ---------------------------------------------------------------------------


def _geography_corridor() -> None:
    corridor = data.run("Q_TRUST_BY_COUNTRY")
    if corridor.empty:
        C.source_note("No delivery geometry stored.")
        return

    corridor = corridor.copy()
    corridor["label"] = [_country(c) for c in corridor["country"]]
    corridor["accounted_share"] = [
        1.0 - _f(v) for v in corridor["unaccounted_share"]
    ]
    ranked = corridor.sort_values("trust_score", ascending=False)

    tcol, ccol = st.columns([1, 1.15], gap="large")

    with tcol:
        with C.panel():
            C.panel_head("Trust by corridor", "weighted by dollars moved")
            st.plotly_chart(
                charts.horizontal_bar(
                    ranked["label"], [_f(v) for v in ranked["trust_score"]],
                    colour=SNOWFLAKE_BLUE,
                    height=302, value_fmt="{:.1f}",
                    hover="%{y}: trust %{x:.2f}<extra></extra>",
                ),
                use_container_width=True, config=charts.bare_config(),
            )
            spread = (_f(ranked["trust_score"].max())
                      - _f(ranked["trust_score"].min()))
            C.readout([
                (f"{_f(ranked['trust_score'].max()):.1f}", "highest"),
                (f"{_f(ranked['trust_score'].min()):.1f}", "lowest"),
                (f"{spread:.1f}", "points between them"),
            ])

    with ccol:
        with C.panel():
            C.panel_head("What sits underneath", "share of disbursements")
            st.plotly_chart(
                charts.corridor_components(ranked, height=302),
                use_container_width=True, config=charts.bare_config(),
            )
            C.readout([
                (f"{_f(ranked['plausible_share'].mean()) * 100:.0f}%",
                 "geometry plausible"),
                (f"{_f(ranked['accounted_share'].mean()) * 100:.0f}%",
                 "accounted for"),
                (f"{_f(ranked['receipted_share'].mean()) * 100:.0f}%",
                 "receipt on chain"),
            ])

    C.table(
        [("corridor", ""), ("organisations", "gp-td-num"),
         ("disbursements", "gp-td-num"), ("moved", "gp-td-num"),
         ("geometry plausible", "gp-td-num"), ("accounted", "gp-td-num"),
         ("receipted", "gp-td-num"), ("second look", "gp-td-num"),
         ("trust", "gp-td-num")],
        [
            (
                f'<span class="gp-td-lead">{C.escape(row.label)}</span>'
                f'<span class="gp-td-where">{C.escape(str(row.country))}</span>',
                f"{_i(row.orgs):,}",
                f"{_i(row.disbursements):,}",
                C.usd(_f(row.usd)),
                f"{_f(row.plausible_share) * 100:.1f}%",
                f"{_f(row.accounted_share) * 100:.1f}%",
                f"{_f(row.receipted_share) * 100:.1f}%",
                f"{_i(row.second_look_orgs):,}",
                f"{_f(row.trust_score):.2f}",
            )
            for row in ranked.itertuples()
        ],
        widths=("18%", "10%", "11%", "12%", "13%", "11%", "10%", "8%", "7%"),
    )
    C.source_note(
        "The country is where the money LANDED, joined through "
        "MARTS.DISTRICT_DIM. Every filing in this corpus is American, so "
        "grouping organisations by their own country would return a single "
        "row and say nothing. The corridors separate by two to three points "
        "of trust, not by an order of magnitude, and reporting that spread "
        "as a finding would be the same sin this tab exists to catch."
    )


def _geography_registration() -> None:
    states = data.run("Q_TRUST_BY_STATE")
    if states.empty:
        C.source_note("No registration data.")
        return

    top = states.head(12)
    pcol, scol = st.columns([1, 1.15], gap="large")

    with pcol:
        with C.panel():
            C.panel_head("Imitation pressure", "per 100 verified filings")
            st.plotly_chart(
                charts.horizontal_bar(
                    top["state"],
                    [_f(v) for v in top["imitations_per_100"]],
                    colour=FLAG_RED, height=302, value_fmt="{:.2f}",
                    hover="%{y}: %{x:.2f} imitations per 100 verified"
                          "<extra></extra>",
                ),
                use_container_width=True, config=charts.bare_config(),
            )
            C.readout([
                (f"{len(states):,}", "states over the floor"),
                (f"{_f(states['imitations_per_100'].max()):.2f}", "highest"),
                (f"{_f(states['imitations_per_100'].min()):.2f}", "lowest"),
            ])

    with scol:
        with C.panel():
            C.panel_head("Pressure against trust", "bubble size is filings")
            st.plotly_chart(
                charts.geography_scatter(states, height=302),
                use_container_width=True, config=charts.bare_config(),
            )
            C.readout([
                (f"{_i(states['orgs'].sum()):,}", "filings covered"),
                (f"{_i(states['seeded'].sum()):,}", "seeded among them"),
                (f"{_i(states['second_look_orgs'].sum()):,}", "second look"),
            ])

    C.table(
        [("state", ""), ("filings", "gp-td-num"), ("verified", "gp-td-num"),
         ("seeded", "gp-td-num"), ("per 100 verified", "gp-td-num"),
         ("second look", "gp-td-num"), ("mean trust", "gp-td-num"),
         ("lowest in state", "gp-td-num")],
        [
            (
                f'<span class="gp-td-lead">{C.escape(str(row.state))}</span>',
                f"{_i(row.orgs):,}",
                f"{_i(row.verified):,}",
                f"{_i(row.seeded):,}",
                f"{_f(row.imitations_per_100):.2f}",
                f"{_i(row.second_look_orgs):,}",
                f"{_f(row.trust_score):.2f}",
                f"{_f(row.lowest_trust):.1f}",
            )
            for row in top.itertuples()
        ],
        widths=("12%", "12%", "12%", "10%", "16%", "13%", "13%", "12%"),
    )
    C.source_note(
        "Only states with at least 250 filings appear. A state with nine "
        "filings and one imitation reads as eleven per hundred and tops any "
        "ranking that lets it in, which is a statement about the "
        "denominator rather than about the state. The mean trust column is "
        "flat near 99 for the same reason the corpus histogram is: almost "
        "every filing has moved no money and therefore scores a clean zero."
    )


# ---------------------------------------------------------------------------
# S7 / who is most trusted
# ---------------------------------------------------------------------------


def _leaderboards(invariant: dict) -> None:
    best = data.run("Q_TRUST_LEADERBOARD")
    worst = data.run("Q_TRUST_SECOND_LOOK")

    bcol, wcol = st.columns(2, gap="large")

    with bcol:
        with C.panel():
            C.panel_head("Highest confidence, earned",
                         note_html=C.chip("real filings only", "verified"))
            if best.empty:
                C.source_note("No organisation clears the evidence floor.")
            else:
                C.table(
                    [("organisation", ""), ("moved", "gp-td-num"),
                     ("delivered", "gp-td-num"), ("trust", "gp-td-num")],
                    [
                        (
                            f'<span class="gp-td-rank">{n}</span> '
                            f'<span class="gp-td-lead">'
                            f'{C.escape(str(row.name))}</span>'
                            f'<span class="gp-td-where">'
                            f'{C.escape(str(row.cause))} &middot; '
                            f'{C.escape(str(row.city))}, '
                            f'{C.escape(str(row.state))} &middot; '
                            f'{_i(row.disbursements)} disbursements across '
                            f'{_i(row.districts)} districts</span>',
                            C.usd(_f(row.moved_usd)),
                            f"{_f(row.delivery_rate) * 100:.0f}%",
                            f"{_f(row.trust_score):.1f}",
                        )
                        for n, row in enumerate(best.itertuples(), start=1)
                    ],
                    widths=("52%", "18%", "15%", "15%"),
                )
        C.source_note(
            "Ranked by score, floored at eight disbursements. 44,580 filings "
            "in this corpus have moved no money at all and score a clean "
            "zero risk, so an unfiltered ranking of the most trusted "
            "organisations would be forty-four thousand records with nothing "
            "in them. The floor is what separates earned confidence from an "
            "empty file. Delivered is the share of moved dollars confirmed "
            "arrived; the rest is in flight, not missing. Unaccounted spend "
            "is a separate component of MARTS.F_RISK and it is zero for "
            "every row here, which is most of why they rank."
        )

    with wcol:
        with C.panel():
            real_flagged = _i(invariant.get("real_second_look"))
            C.panel_head(
                "What needs a second look",
                note_html=C.chip(
                    "every row seeded" if real_flagged == 0
                    else f"{real_flagged} real filings",
                    "seeded" if real_flagged == 0 else "flagged",
                ),
            )
            if worst.empty:
                C.source_note("Nothing crosses the second-look line.")
            else:
                C.table(
                    [("organisation", ""), ("meaning", "gp-td-num"),
                     ("gap", "gp-td-num"), ("trust", "gp-td-num")],
                    [
                        (
                            f'<span class="gp-td-rank">{n}</span> '
                            f'<span class="gp-td-lead">'
                            f'{C.escape(str(row.name))}</span>'
                            f'<span class="gp-td-where">'
                            f'{C.escape(_text(row.synth_technique, "seeded"))}'
                            f' &middot; imitates '
                            f'{C.escape(_text(row.nearest_target_name, "unresolved"))}'
                            f'</span>',
                            f"{_f(row.semantic_sim):.3f}",
                            f"{_f(row.evasion_gap):.3f}",
                            f"{_f(row.trust_score):.1f}",
                        )
                        for n, row in enumerate(worst.itertuples(), start=1)
                    ],
                    widths=("52%", "16%", "16%", "16%"),
                    row_classes=["gp-tr-diff"] * len(worst),
                )
        C.source_note(
            "Every row here is an organisation this project seeded, and the "
            "row above the table says so from the data rather than from a "
            "promise. The name each one imitates is a real filing in good "
            "standing and appears nowhere in this table, which is the whole "
            "point of building the adversary rather than accusing anyone."
        )


# ---------------------------------------------------------------------------
# S9 / threshold sensitivity
# ---------------------------------------------------------------------------


def _threshold() -> None:
    curve = data.run("Q_THRESHOLD_CURVE")
    calibration = data.run("Q_THRESHOLD_CALIBRATION")
    production = float(Q.SIMILARITY_THRESHOLD)

    if curve.empty:
        C.source_note("No threshold curve stored.")
        return

    # The production value is read from the flag the sweep wrote, so the
    # marker cannot drift from the mart. The constant is the fallback,
    # not the source of truth.
    flagged = curve[charts.as_bool(curve["is_production_value"])]
    if len(flagged):
        production = float(flagged.iloc[0]["threshold"])

    st.markdown('<div class="gp-control-label">cosine similarity cut-off</div>',
                unsafe_allow_html=True)
    threshold = st.slider(
        "cosine similarity cut-off", min_value=0.70, max_value=0.99,
        value=production, step=0.01, key="gp_g_threshold",
        label_visibility="collapsed",
    )

    at = curve.iloc[(curve["threshold"] - threshold).abs().argmin()]

    ccol, kcol = st.columns(2, gap="large")

    with ccol:
        with C.panel():
            C.panel_head("Detections against the cut-off",
                         "marts.threshold_curve")
            st.plotly_chart(
                charts.threshold_curve(curve, threshold, production,
                                       height=298),
                use_container_width=True, config=charts.bare_config(),
            )
            C.readout([
                (f"{_i(at['pairs_detected']):,}", f"pairs at {threshold:.2f}"),
                (f"{_i(curve['pairs_detected'].max()):,}", "at 0.70"),
                (f"{_i(curve['pairs_detected'].min()):,}", "at 0.99"),
            ])

    precision = recall = f1 = None
    with kcol:
        with C.panel():
            C.panel_head("Precision and recall against ground truth",
                         "marts.threshold_calibration")
            if calibration.empty or calibration["precision_at"].isna().all():
                C.source_note(
                    "Calibration is measured in the warehouse only. The "
                    "preview store carries the sweep but not the "
                    "ground-truth join."
                )
            else:
                st.plotly_chart(
                    charts.threshold_calibration(calibration, threshold,
                                                 production, height=298),
                    use_container_width=True, config=charts.bare_config(),
                )
                nearest = calibration.iloc[
                    (calibration["threshold"] - threshold).abs().argmin()
                ]
                precision = _f(nearest["precision_at"])
                recall = _f(nearest["recall_at"])
                f1 = (0.0 if precision + recall == 0
                      else 2 * precision * recall / (precision + recall))
                C.readout([
                    (f"{precision:.1%}", "precision"),
                    (f"{recall:.1%}", "recall"),
                    (f"{f1:.3f}", "F1"),
                ])

    C.note(
        "<strong>The cut-off is not the F1 maximum, and that is "
        "deliberate.</strong> F1 peaks at 0.90, where the detector finds "
        "84 per cent of the seeded imitations at 86 per cent precision. "
        "Production runs at 0.94, which trades recall away to buy "
        "precision: 97.8 per cent of what it flags is a genuine imitation, "
        "and it flags 67.5 per cent of them. In a tool whose output is "
        "read as doubt about a named organisation, a false accusation "
        "costs more than a missed detection, so the balance is bought on "
        "purpose rather than fallen into."
    )
    C.source_note(
        "The whole sweep is precomputed into MARTS.THRESHOLD_CURVE and "
        "MARTS.THRESHOLD_CALIBRATION, so the slider responds with no query "
        "behind it. Precision and recall are measured against ground truth: "
        "every seeded organisation records the real one it was built from, "
        "so a detected pair can be checked rather than believed."
    )


# ---------------------------------------------------------------------------
# how it works
# ---------------------------------------------------------------------------


def _how_it_works() -> None:
    C.section("How this tab is built")
    C.step_explainer([
        (
            "One join, two pre-filters",
            "Every pair on this tab comes from a self-join on STAGING.ORGS "
            "restricted to the same H3 region and the same cause. Vector "
            "similarity at GA performs an exact scan, so without those two "
            "predicates the query is a 45,400 by 45,400 cross product.",
        ),
        (
            "Positions written once",
            "The layout is a networkx spring embedding computed offline and "
            "stored on MARTS.GRAPH_NODES. Third-party network components "
            "cannot load under the Content Security Policy, so the graph is "
            "drawn from plain Plotly primitives.",
        ),
        (
            "One score, read two ways",
            "Trust is 100 minus MARTS.F_RISK, the SQL UDF Tab 01 "
            "decomposes. There is no second scoring system, so no two "
            "numbers in this application can disagree about the same "
            "organisation.",
        ),
        (
            "The separation is checked",
            "Q_TRUST_INVARIANT runs on every render and asserts that no "
            "real filing has crossed the second-look line. The tab prints "
            "the result whichever way it comes back.",
        ),
    ])


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------


def render() -> None:
    C.tab_title(
        "The Trust Graph",
        "One imitation is an incident. Four hundred is a structure.",
    )

    summary = _row(data.run("Q_GRAPH_SUMMARY"))
    invariant = _row(data.run("Q_TRUST_INVARIANT"))
    highest_real = _f(invariant.get("highest_real_risk"))
    lowest_real_trust = 100.0 - highest_real if invariant else None

    # ---------------------------------------------------------------- S1
    C.hero(
        f"{_i(summary.get('targets_affected')):,}",
        "verified organisations have at least one imitation inside the threshold",
    )

    # ---------------------------------------------------------------- S2
    C.stat_band([
        (f"{_i(summary.get('pairs_detected')):,}", "pairs detected"),
        (f"{_f(summary.get('mean_similarity')):.3f}", "mean similarity"),
        (f"{_f(summary.get('mean_evasion_gap')):.3f}", "mean evasion gap"),
        (f"{_i(summary.get('causes_affected'))}", "causes affected"),
        (f"{float(Q.SIMILARITY_THRESHOLD):.2f}", "production cut-off"),
    ])

    # ---------------------------------------------------------------- S3
    C.section("Impersonation network")
    nodes = data.run("Q_GRAPH_NODES")
    edges = data.run("Q_GRAPH_EDGES")
    hubs = data.run("Q_MOST_IMPERSONATED")

    if nodes.empty:
        st.markdown('<div class="gp-source">No graph stored.</div>',
                    unsafe_allow_html=True)
        C.provenance_footer("No graph layout has been written.")
        return

    fcol, hcol = st.columns([1, 1], gap="large")
    with fcol:
        st.markdown('<div class="gp-control-label">filter by cause</div>',
                    unsafe_allow_html=True)
        causes = ["every cause"] + sorted(
            {str(c) for c in nodes["cause"].dropna()}
        )
        cause_filter = st.selectbox(
            "cause", causes, key="gp_g_cause", label_visibility="collapsed",
        )
    with hcol:
        st.markdown(
            '<div class="gp-control-label">jump to a targeted organisation</div>',
            unsafe_allow_html=True)
        if hubs.empty:
            st.markdown('<div class="gp-source">No targets stored.</div>',
                        unsafe_allow_html=True)
        else:
            hub_labels = {
                str(row.target_id):
                    f"{row.target_name} — {_i(row.imitations)} imitations"
                for row in hubs.itertuples()
            }
            picked_hub = st.selectbox(
                "hub", list(hub_labels), key="gp_g_hub",
                format_func=lambda value: hub_labels.get(value, value),
                label_visibility="collapsed",
            )
            if st.button("inspect this one", key="gp_g_hub_go",
                         use_container_width=True):
                st.session_state["gp_focus_org_id"] = picked_hub
                st.session_state.pop("gp_g_traced", None)

    shown = nodes
    if cause_filter != "every cause":
        shown = nodes[nodes["cause"] == cause_filter]
    keep = set(shown["org_id"])
    shown_edges = edges[
        edges["source_id"].isin(keep) & edges["target_id"].isin(keep)
    ] if len(edges) else edges

    focus = st.session_state.get("gp_focus_org_id")
    if focus not in set(nodes["org_id"]):
        focus = None
    if not focus:
        focus = nodes.sort_values("degree", ascending=False).iloc[0]["org_id"]

    gcol, icol = st.columns([3, 2], gap="large")
    with gcol:
        with C.panel():
            C.panel_head(
                "Impersonation network",
                f"{len(shown):,} nodes \u00b7 {len(shown_edges):,} edges"
                if cause_filter == "every cause"
                else f"{cause_filter} \u00b7 {len(shown):,} nodes",
            )
            if shown.empty:
                C.source_note("No nodes in that cause.")
            else:
                _network(shown, shown_edges, focus)
                verified_n = int((shown["node_kind"] == "verified").sum())
                seeded_n = int((shown["node_kind"] == "imitation").sum())
                C.readout([
                    (f"{verified_n:,}", "verified nodes"),
                    (f"{seeded_n:,}", "seeded nodes"),
                    (f"{len(shown_edges):,}", "edges drawn"),
                    (f"{_i(shown['degree'].max()):,}", "widest cluster"),
                ])
    with icol:
        with C.panel():
            _inspector(focus, lowest_real_trust)

    C.source_note(
        "Blue nodes are verified organisations, red nodes are seeded "
        "imitations, and every node is sized by its degree. Degree does not "
        "mean the same thing on both sides and the size is not labelled as "
        "though it did: on a verified organisation it is how many "
        "imitations point at it, which is one for nearly all of them; on a "
        "seeded row it is how many real organisations that one name sits "
        "close enough to, and one seeded row in this corpus reaches "
        "seventeen. Positions come from an offline networkx spring layout "
        "written once to MARTS.GRAPH_NODES, because third-party network "
        "components cannot load under the Content Security Policy."
    )

    # ---------------------------------------------------------------- S4
    C.section("Score any organisation in the corpus")
    C.note(
        "Search 45,400 filings by name or by filing number. The score is "
        "<strong>100 minus MARTS.F_RISK</strong>, the same UDF Tab 01 "
        "decomposes into a waterfall, read from the direction a donor "
        "actually asks the question. With nothing typed, the lookup opens "
        "on whatever the network above has focused."
    )
    searched = _search_box()
    _lookup(searched or focus, lowest_real_trust)

    # ---------------------------------------------------------------- S5
    C.section("Where every score falls")
    _distribution(invariant)

    # ---------------------------------------------------------------- S6
    C.section("Trust by geography")
    C.note(
        "Two different questions wear the same word. <strong>Where the "
        "money landed</strong> groups disbursements by delivery corridor "
        "and weights trust by the dollars that went through it. "
        "<strong>Where the filing is registered</strong> groups the "
        "organisations themselves by US state, which is the only "
        "registration geography this corpus has: every filing in it is "
        "American."
    )
    lens = _picker(GEO_LENSES, "gp_g_lens", GEO_LENSES[0])
    if lens == GEO_LENSES[0]:
        _geography_corridor()
    else:
        _geography_registration()

    # ---------------------------------------------------------------- S7
    C.section("Who is most trusted, and what is not")
    _leaderboards(invariant)

    # ------------------------------------------------------------ S8, S8b
    C.section("Where the pressure falls")
    ecol, tcol = st.columns(2, gap="large")

    exposure = data.run("Q_CAUSE_EXPOSURE")
    technique = data.run("Q_TECHNIQUE_BREAKDOWN")
    # One height for both, taken from whichever has more rows. Two panels
    # side by side that stop at different points read as a mistake even
    # when each one is correctly sized for its own content.
    pressure_height = max(240, 30 * max(len(exposure), len(technique)) + 60)

    with ecol:
        with C.panel():
            C.panel_head("Cause exposure", "per 100 verified")
            if exposure.empty:
                C.source_note("No exposure data.")
            else:
                st.plotly_chart(
                    charts.horizontal_bar(
                        exposure["cause"], exposure["imitations_per_100"],
                        colour=FLAG_RED, height=pressure_height,
                        value_fmt="{:.1f}",
                        hover="%{y}: %{x:.1f} imitations per 100 verified"
                              "<extra></extra>",
                    ),
                    use_container_width=True, config=charts.bare_config(),
                )
        C.source_note("Imitations per hundred verified organisations, by cause.")

    with tcol:
        with C.panel():
            C.panel_head("Technique breakdown", "pairs detected")
            if technique.empty:
                C.source_note("No technique data.")
            else:
                st.plotly_chart(
                    charts.horizontal_bar(
                        technique["technique"], technique["pairs_detected"],
                        colour=SNOWFLAKE_BLUE, height=pressure_height,
                        value_fmt="{:.0f}",
                        hover="%{y}: %{x} pairs<extra></extra>",
                    ),
                    use_container_width=True, config=charts.bare_config(),
                )
        C.source_note(
            "Which generation tactic produced each detected pair. This is "
            "honest to show because the tactics are known by construction, "
            "and it usefully shows which techniques the detector handles "
            "best."
        )

    # ---------------------------------------------------------------- S9
    C.section("Threshold sensitivity")
    _threshold()

    _how_it_works()
    C.provenance_footer(
        "CLONE_PAIRS and CLONE_CONFIRMED for edges. GRAPH_NODES and "
        "GRAPH_EDGES from an offline networkx layout, written once. "
        "ORG_RISK for every trust score, DT_ORG_ACTIVITY and "
        "DT_RECEIPT_COVERAGE for the evidence behind one, DISTRICT_DIM for "
        "the delivery corridor. THRESHOLD_CURVE and THRESHOLD_CALIBRATION "
        "precomputed by sweeping the cosine cut-off. Technique labels come "
        "from the generator, which records which transformation produced "
        "each row."
    )
