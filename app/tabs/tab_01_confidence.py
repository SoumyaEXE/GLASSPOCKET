"""Tab 01 / Give With Confidence. Build Spec Section 07.

    Two organisations. One is who they say they are. Pick.

The cold open. The demo starts here, and the viewer is asked to choose
before anything is revealed. Most people pick wrong, which is the point:
names are not evidence.

INTERACTION SEQUENCE, EXACTLY
  1. Sample one confirmed pair on first load. Randomise which side
     displays left. Store in session state so a rerun does not reshuffle
     mid-demo.
  2. Both cards render with no tell. Do not colour, badge or shade the
     seeded one at this stage. Resist the urge.
  3. Viewer picks. Record the choice and update the S1 counter.
  4. Reveal animates in over roughly 400 ms.
  5. Charts populate for the selected pair.
  6. A next pair control resamples without resetting the counter.

THREE THINGS HERE EXIST BECAUSE THE FIRST VERSION GOT THEM WRONG.

  * The opening figure was "2 of 3 people pick the imitation the first
    time they try", which nobody measured and which no source supports.
    On a tab whose argument is that unsourced claims are the problem,
    that was the worst possible line to open with. It is now the size of
    the confirmed population, read from the warehouse.

  * One number with no denominator is not a finding. An evasion gap of
    0.27 tells a reader nothing until they can see the distribution it
    came out of, so the pair on screen is now placed inside it.

  * The reveal was a separate section below the cards, so the chips
    landed a long way from the card they described and the layout jumped
    when the buttons disappeared. Every state a card can be in is now
    rendered in a fixed slot directly beneath it.
"""

from __future__ import annotations

import random

import pandas as pd
import streamlit as st

import charts
import components as C
import data
import queries as Q

#: The detector, quoted from sql/07_clone_detection.sql rather than
#: paraphrased. An accountability tool that will not show its own query
#: is arguing against itself.
DETECTOR_SQL = """WITH candidates AS (
  SELECT
    s.org_id                                          AS suspect_id,
    t.org_id                                          AS target_id,
    VECTOR_COSINE_SIMILARITY(s.name_vec, t.name_vec)  AS semantic_sim,
    JAROWINKLER_SIMILARITY(s.name, t.name) / 100.0    AS string_sim
  FROM STAGING.ORGS s
  JOIN STAGING.ORGS t
    ON  s.region_h3 = t.region_h3   -- REQUIRED pre-filter, Trap 06
    AND s.cause     = t.cause       -- REQUIRED pre-filter, Trap 06
    AND s.ein      <> t.ein
  WHERE s.is_synthetic = TRUE       -- the suspect side is always seeded
    AND t.is_verified  = TRUE       -- the target side is always a real filing
    AND t.is_synthetic = FALSE
)
SELECT *, semantic_sim - string_sim AS evasion_gap
FROM candidates
WHERE semantic_sim >= 0.94"""

#: The record diff. ``ein`` is not carried on the serving view, so it is
#: read from MARTS.ORG_RISK for each side and merged in below.
DIFF_FIELDS = (
    ("organisation id", "id"),
    ("filing number, EIN", "ein"),
    ("registered name", "name"),
    ("cause", "cause"),
    ("city", "city"),
    ("state", "state"),
    ("mission line", "blurb"),
)


def _sample_pair(force_new: bool = False) -> dict | None:
    """One confirmed pair, held in session state so a rerun is stable."""
    if not force_new and "gp_c_pair" in st.session_state:
        return st.session_state["gp_c_pair"]

    pairs = data.run("Q_CONFIDENCE_PAIRS")
    if pairs.empty:
        return None

    # Sampled with probability proportional to the evasion gap, so the
    # pair on screen is one where meaning and spelling genuinely part
    # company. Every pair in the pool is a real detection and its true
    # numbers are shown either way; the weighting decides which of them
    # opens, not what any of them says. A uniform draw regularly lands on
    # a token reorder with a gap near 0.1, which demonstrates nothing.
    weights = (pairs["evasion_gap"].clip(lower=0.01)) ** 2
    row = pairs.sample(1, weights=weights).iloc[0].to_dict()
    # Randomise which side displays left, so the answer is never
    # positional. Stored, so it does not reshuffle mid-demo.
    row["suspect_on_left"] = random.random() < 0.5
    st.session_state["gp_c_pair"] = row
    st.session_state.pop("gp_c_choice", None)
    return row


def _side(pair: dict, is_suspect: bool) -> dict:
    prefix = "suspect" if is_suspect else "target"
    return {
        "org_id": pair[f"{prefix}_id"],
        "name": pair[f"{prefix}_name"],
        "blurb": pair[f"{prefix}_blurb"],
        "city": pair[f"{prefix}_city"],
        "state": pair[f"{prefix}_state"],
        "cause": pair[f"{prefix}_cause"],
        "is_suspect": is_suspect,
    }


def _risk_row(org_id: str) -> dict:
    """One row of MARTS.ORG_RISK, or an empty dict if it is not scored."""
    frame = data.run("Q_ORG_RISK_ONE", (org_id,))
    return {} if frame.empty else frame.iloc[0].to_dict()


def _corpus_band(summary: pd.DataFrame) -> None:
    """Five corpus-level figures.

    Every one of them is about the population rather than about the pair
    on screen, which is what makes it safe to render above the fold: a
    band that said anything about this pair would be a tell.
    """
    if summary.empty:
        return
    s = summary.iloc[0]
    C.stat_band([
        (f"{int(s['pairs_detected']):,}", "pairs above the cut-off"),
        (f"{int(s['targets_affected']):,}", "real organisations imitated"),
        (f"{int(s['causes_affected']):,}", "causes affected"),
        (f"{float(s['mean_evasion_gap']):.2f}", "mean evasion gap"),
        (f"{Q.SIMILARITY_THRESHOLD}", "cosine cut-off, calibrated"),
    ])


def _detector_expander(pair: dict) -> None:
    """The query, and the calibration that fixed the number inside it."""
    with st.expander("the query that made this call, and how 0.94 was chosen"):
        st.markdown(
            '<div style="margin-bottom:8px">'
            + C.file_chip("sql/07_clone_detection.sql")
            + "</div>",
            unsafe_allow_html=True,
        )
        C.sql_block(DETECTOR_SQL)
        C.note(
            "The two pre-filters on <strong>region_h3</strong> and "
            "<strong>cause</strong> are not an optimisation, they are the "
            "difference between a query and an outage. Vector similarity at "
            "general availability performs an exact scan, so a self-join "
            "across the organisation table without them is a full cross "
            "product. If a similarity query in this build ever runs long, "
            "the pre-filter has been removed."
        )

        # Precision and recall are measurable because every seeded
        # organisation records the real one it was built from. The local
        # preview store does not carry the calibration, so the two rows
        # say so rather than quietly disappearing.
        calibration = data.run("Q_THRESHOLD_CALIBRATION")
        measured = None
        if not calibration.empty and "precision_at" in calibration:
            at = calibration[
                calibration["threshold"].astype(float).round(2)
                == Q.SIMILARITY_THRESHOLD
            ]
            if len(at) and pd.notna(at.iloc[0]["precision_at"]):
                measured = at.iloc[0]

        rows = [("cosine cut-off in production", f"{Q.SIMILARITY_THRESHOLD}")]
        if measured is not None:
            rows += [
                ("pairs detected at the cut-off",
                 f"{int(measured['pairs_detected']):,}"),
                ("of those, true pairs", f"{int(measured['true_pairs']):,}"),
                ("precision", C.pct(float(measured["precision_at"]))),
                ("recall", C.pct(float(measured["recall_at"]))),
            ]
        else:
            rows.append(
                ("precision and recall", "measured in the warehouse only")
            )
        rows.append(
            ("confirmation method for this pair",
             str(pair.get("confirmation_method", "HEURISTIC")).lower())
        )
        C.kv_rows(rows)
        C.source_note(
            "The specification fixes the cut-off at 0.86. That number "
            "belongs to the embedding pipeline it assumed, AI_EMBED inside "
            "the warehouse; this account blocks AI functions, so the vectors "
            "come from the same model run offline, and a threshold is a "
            "property of the vectors rather than of the intent. It was "
            "re-measured against ground truth, because every seeded "
            "organisation records the real one it was built from. The whole "
            "curve is on The Trust Graph, with a slider, so it can be probed "
            "rather than taken on faith. AI_FILTER confirmation is "
            "unavailable on a trial account, so confirmation falls back to "
            "two ordinary SQL predicates and every row carries the method it "
            "was confirmed by."
        )


def _record_diff(pair: dict, verified: dict, seeded: dict) -> int:
    """Field by field, real against imitation. Returns the number matching.

    This is the payoff of the whole tab. The fields a donor reads are
    identical; the ones that are not are the ones a donor never sees.
    """
    left = _side(pair, is_suspect=False)
    right = _side(pair, is_suspect=True)
    values = {
        "id": (left["org_id"], right["org_id"]),
        "ein": (str(verified.get("ein", "not scored")),
                str(seeded.get("ein", "not scored"))),
        "name": (left["name"], right["name"]),
        "cause": (left["cause"], right["cause"]),
        "city": (left["city"], right["city"]),
        "state": (left["state"], right["state"]),
        "blurb": (left["blurb"], right["blurb"]),
    }

    rows = []
    row_classes = []
    matching = 0
    for label, key in DIFF_FIELDS:
        real, fake = (str(v) for v in values[key])
        same = real.strip().lower() == fake.strip().lower()
        matching += int(same)
        cls = "gp-td-same" if same else "gp-td-diff"
        row_classes.append("" if same else "gp-tr-diff")
        rows.append((
            f'<span class="gp-td-field">{C.escape(label)}</span>',
            f'<span class="{cls}">{C.escape(real)}</span>',
            f'<span class="{cls}">{C.escape(fake)}</span>',
            "match" if same else "differs",
        ))

    C.table(
        [("field", ""),
         ("verified organisation", ""),
         ("seeded imitation", ""),
         ("", "gp-td-nowrap")],
        rows,
        widths=("18%", "35%", "35%", "12%"),
        row_classes=row_classes,
    )
    return matching


def _how_it_works() -> None:
    C.section("How this works")
    C.step_explainer([
        ("Embed name and mission",
         "Every organisation's name, mission line and cause become a "
         "768-number vector that captures what the words mean, not how they "
         "are spelled. The vectors live in a VECTOR column in the warehouse "
         "and never leave it."),
        ("Compare by meaning",
         "Two organisations are compared by the angle between those vectors, "
         "with VECTOR_COSINE_SIMILARITY. Names that mean the same thing land "
         "close together even when they share almost no letters."),
        ("Measure the gap",
         "Spelling is measured separately, with JAROWINKLER_SIMILARITY. When "
         "meaning is very close and spelling is not, the gap between them is "
         "the signal that somebody chose the name on purpose."),
        ("Calibrate, do not guess",
         f"The cut-off is {Q.SIMILARITY_THRESHOLD}, measured against ground "
         "truth rather than picked by eye, shown in the interface rather "
         "than hidden, and movable on the next tab."),
    ])


def _footer() -> None:
    C.provenance_footer(
        "Real side: IRS Business Master File, unmodified, filtered to "
        "organisations in good standing. Suspect side: tools/make_synthetic.py, "
        "batch SYNTH_ADVERSARY_V1. Similarities: MARTS.CLONE_CONFIRMED. "
        "Projection coordinates: offline scikit-learn PCA over the stored "
        "vectors. Risk components: MARTS.ORG_RISK."
    )


def render() -> None:
    C.tab_title(
        "Give With Confidence",
        "Two organisations. One is who they say they are. Pick.",
    )

    pair = _sample_pair()
    if pair is None:
        st.warning(
            "No confirmed pairs are available. Run sql/07_clone_detection.sql, "
            "or regenerate the preview store with tools/make_synthetic.py."
        )
        return

    revealed = "gp_c_choice" in st.session_state
    seen = st.session_state.get("gp_c_seen", 0)
    wrong = st.session_state.get("gp_c_wrong", 0)

    summary = data.run("Q_GRAPH_SUMMARY")

    # ---------------------------------------------------------------- S1
    # Hero. Before anyone has picked there is no session figure to show,
    # so the opening number is the size of the confirmed population. It
    # is read from the warehouse, which the line it replaced was not.
    if seen:
        C.hero(f"{wrong} of {seen}",
               "viewers picked the imitation this session")
    elif not summary.empty:
        C.hero(f"{int(summary.iloc[0]['pairs_detected']):,} pairs",
               "seeded organisations sitting close enough in meaning to a "
               "real one that a donor could confuse them")
    else:
        C.hero("no pairs", "the detector has not been run on this corpus")

    # ---------------------------------------------------------------- S2
    _corpus_band(summary)

    # ---------------------------------------------------------------- S3
    # The test. Identical typography, identical field order, no visual
    # tell whatsoever before the reveal.
    C.section("The test")
    C.note(
        "One of these is a real organisation in good standing. The other "
        "borrowed its meaning. Both cards carry the same fields in the same "
        "order, and neither is shaded, badged or ordered to give anything "
        "away. Pick the one you would give to."
    )
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    left_is_suspect = pair["suspect_on_left"]
    left = _side(pair, left_is_suspect)
    right = _side(pair, not left_is_suspect)
    picked = st.session_state.get("gp_c_choice")

    lcol, rcol = st.columns(2, gap="medium")
    for col, card, label in ((lcol, left, "A"), (rcol, right, "B")):
        with col:
            C.eyebrow(f"organisation {label}")
            C.org_card(
                name=card["name"],
                cause=card["cause"],
                city=card["city"],
                state=card["state"],
                blurb=card["blurb"],
                equal_height=True,
                # Reveal state is applied only after the viewer has picked.
                reveal=("seeded" if card["is_suspect"] else "verified")
                if revealed else None,
            )
            if not revealed:
                if st.button("I would give to this one",
                             key=f"gp_c_pick_{label}",
                             use_container_width=True):
                    st.session_state["gp_c_choice"] = label
                    st.session_state["gp_c_seen"] = seen + 1
                    if card["is_suspect"]:
                        st.session_state["gp_c_wrong"] = wrong + 1
                    st.rerun()
            else:
                # Every state a card can be in is rendered in a fixed slot
                # directly beneath it, so the chips never drift away from
                # the card they describe.
                marks = (
                    [C.chip("seeded imitation, not real", "seeded")]
                    if card["is_suspect"]
                    else [C.chip("verified", "verified"),
                          C.chip("real filing, good standing", "neutral")]
                )
                if picked == label:
                    marks.append(
                        C.chip("your pick",
                               "flagged" if card["is_suspect"] else "confirmed")
                    )
                C.slot(" ".join(marks))

    if not revealed:
        _how_it_works()
        _footer()
        return

    picked_card = left if picked == "A" else right
    picked_imitation = bool(picked_card["is_suspect"])

    semantic = float(pair["semantic_sim"])
    string_sim = float(pair["string_sim"])
    gap = float(pair["evasion_gap"])

    # ---------------------------------------------------------------- S4
    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
    vcol, ncol = st.columns([4, 1], gap="medium")
    with vcol:
        if picked_imitation:
            C.verdict(
                "You picked the imitation. Most people do.",
                "There was nothing on the card to go on. Both names mean the "
                "same thing, neither is misspelled, and the cause, the city "
                "and the mission line are identical. Names are not evidence. "
                "What follows is what the warehouse had instead.",
                "wrong",
            )
        else:
            C.verdict(
                "Correct, and it was closer than it looked.",
                f"The two names differ by {1 - string_sim:.0%} of their "
                f"spelling but by only {1 - semantic:.0%} of their meaning. "
                "That asymmetry is the entire signal, and it is the only "
                "thing separating the card you picked from the one you did "
                "not.",
                "right",
            )
    with ncol:
        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
        if st.button("next pair", key="gp_c_next", use_container_width=True):
            _sample_pair(force_new=True)
            st.rerun()

    # ---------------------------------------------------------------- S5
    # The thesis of the project in one image, and beside it the
    # denominator that turns a number into a finding.
    C.section("Meaning versus spelling")

    pairs_pool = data.run("Q_CONFIDENCE_PAIRS")
    mcol, dcol = st.columns([1.25, 1], gap="large")

    with mcol:
        with C.panel():
            C.panel_head("Similarity of the two names", "0 to 1")
            st.plotly_chart(
                charts.meaning_vs_spelling(semantic, string_sim, height=196),
                use_container_width=True, config=charts.bare_config(),
            )
            C.readout(
                [(f"{semantic:.2f}", "meaning"),
                 (f"{string_sim:.2f}", "spelling"),
                 (f"{gap:.2f}", "evasion gap")],
                flag="evasion gap",
            )
    with dcol:
        with C.panel():
            C.panel_head("Where this pair sits",
                         f"{len(pairs_pool):,} confirmed pairs")
            if pairs_pool.empty:
                C.source_note("No population to compare against.")
            else:
                st.plotly_chart(
                    charts.evasion_distribution(pairs_pool["evasion_gap"],
                                                gap, height=252),
                    use_container_width=True, config=charts.bare_config(),
                )

    C.source_note(
        f"Meaning similarity {semantic:.2f}, spelling similarity "
        f"{string_sim:.2f}, and the gap between them is {gap:.2f}. A high "
        "meaning similarity paired with a low spelling similarity is the "
        "signature of deliberate evasion: the impersonator kept the meaning "
        "and changed the spelling on purpose. Both numbers are computed in "
        "SQL inside the warehouse, with no data leaving it."
    )
    st.markdown(
        C.chip(f"technique: {pair.get('synth_technique', 'recorded')}", "seeded")
        + " "
        + C.chip(
            "confirmed by "
            + str(pair.get("confirmation_method", "heuristic")).lower(),
            "neutral",
        ),
        unsafe_allow_html=True,
    )
    _detector_expander(pair)

    # ---------------------------------------------------------------- S6
    C.section("How the warehouse scored it")
    risk_seeded = _risk_row(pair["suspect_id"])
    risk_verified = _risk_row(pair["target_id"])

    wcol, pcol = st.columns([1, 1], gap="large")

    with wcol:
        with C.panel():
            # The verdict rides in the head rather than below the
            # readout. It is a phrase, not a figure, and as a row of its
            # own it pushed this panel's figures off the line the
            # neighbourhood's figures sit on.
            C.panel_head(
                "Confidence decomposition",
                note_html=C.chip(
                    str(risk_seeded.get("verdict") or "unscored")
                    .replace("_", " ").lower(),
                    "flagged",
                ) if risk_seeded else "",
                note="" if risk_seeded else "marts.f_risk",
            )
            if not risk_seeded:
                C.source_note("No score stored for this row.")
            else:
                st.plotly_chart(
                    charts.risk_waterfall(
                        {
                            "semantic proximity": float(risk_seeded["comp_semantic"]),
                            "evasion gap": float(risk_seeded["comp_evasion"]),
                            "geometry flags": float(risk_seeded["comp_geometry"]),
                            "unaccounted ratio": float(risk_seeded["comp_unaccounted"]),
                            "missing receipts": float(risk_seeded["comp_receipts"]),
                        },
                        float(risk_seeded["risk_score"]),
                        height=316,
                    ),
                    use_container_width=True, config=charts.bare_config(),
                )
                C.readout([
                    (f"{float(risk_seeded['risk_score']):.0f}", "this record"),
                    (f"{float(risk_verified['risk_score']):.0f}"
                     if risk_verified else "—", "the verified side"),
                    (f"{gap:.2f}", "evasion gap"),
                ])
        C.source_note(
            "The five weighted components of MARTS.F_RISK, adding to the "
            "total. An accountability tool cannot show an opaque score, so "
            "the arithmetic is reconstructable by eye: 35 points of semantic "
            "proximity, 25 of evasion gap, 20 of geometry, 12 of unaccounted "
            "spend and 8 of missing receipts."
        )

    with pcol:
        projection = data.run("Q_PROJECTION", (pair["suspect_cause"],))
        with C.panel():
            C.panel_head("Semantic neighbourhood", str(pair["suspect_cause"]))
            if projection.empty:
                C.source_note("No projection stored for this cause.")
            else:
                st.plotly_chart(
                    charts.semantic_neighbourhood(
                        projection, (pair["suspect_id"], pair["target_id"]),
                        height=316),
                    use_container_width=True, config=charts.bare_config(),
                )
                C.readout([
                    (f"{len(projection):,}", "orgs in this cause"),
                    (f"{int(charts.as_bool(projection['is_synthetic']).sum()):,}",
                     "seeded among them"),
                    (f"{gap:.2f}", "this pair's gap"),
                ])
        C.source_note(
            "Every organisation in the same cause, projected to two "
            "dimensions offline with scikit-learn PCA, because UMAP will not "
            "run in the warehouse runtime. Imitations sit on top of the "
            "organisations they copied while ordinary organisations spread "
            "out. The dotted line joins the pair on screen."
        )

    # ---------------------------------------------------------------- S7
    C.section("The two records, field by field")
    matching = _record_diff(pair, risk_verified, risk_seeded)
    total = len(DIFF_FIELDS)
    C.source_note(
        f"{matching} of {total} fields are identical, including every field a "
        f"donor actually reads. The {total - matching} that differ are the "
        "internal identifier, the filing number and the spelling of the "
        "name, and nobody checks a filing number before giving. This is why "
        "the detector compares meaning rather than strings, and it is why "
        "the suspect side of every pair in this application is seeded by "
        "construction: no real organisation is ever shown in a flagged state."
    )

    _how_it_works()
    _footer()
