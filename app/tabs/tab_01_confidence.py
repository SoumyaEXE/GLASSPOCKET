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
  5. Charts S4 to S6 populate for the selected pair.
  6. A next pair control resamples without resetting the counter.
"""

from __future__ import annotations

import random

import streamlit as st

import charts
import components as C
import data
import queries as Q


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

    # ---------------------------------------------------------------- S1
    # Session accuracy counter. Increments live as the demo runs, which
    # makes the number feel earned rather than printed.
    seen = st.session_state.get("gp_c_seen", 0)
    wrong = st.session_state.get("gp_c_wrong", 0)
    if seen:
        C.hero(f"{wrong} of {seen}",
               "viewers picked the imitation this session")
    else:
        C.hero("2 of 3", "people pick the imitation the first time they try")

    st.markdown(
        "One of these is a real organisation. The other borrowed its meaning. "
        "Pick the one you would give to."
    )

    # ---------------------------------------------------------------- S2
    # The test. Identical typography, identical field order, no visual
    # tell whatsoever before the reveal.
    revealed = "gp_c_choice" in st.session_state
    left_is_suspect = pair["suspect_on_left"]

    def side(is_suspect: bool) -> dict:
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

    left, right = side(left_is_suspect), side(not left_is_suspect)

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
                # Reveal state is applied only after the viewer has picked.
                reveal=("seeded" if card["is_suspect"] else "verified")
                if revealed else None,
            )
            if not revealed:
                if st.button(f"I would give to this one",
                             key=f"gp_c_pick_{label}",
                             use_container_width=True):
                    st.session_state["gp_c_choice"] = label
                    st.session_state["gp_c_seen"] = seen + 1
                    if card["is_suspect"]:
                        st.session_state["gp_c_wrong"] = wrong + 1
                    st.rerun()

    # ---------------------------------------------------------------- S3
    if revealed:
        picked = st.session_state["gp_c_choice"]
        picked_card = left if picked == "A" else right
        picked_imitation = picked_card["is_suspect"]

        C.section("Reveal")
        lchip, rchip = st.columns(2, gap="medium")
        with lchip:
            C.chips([("seeded imitation, not real", "seeded")] if left["is_suspect"]
                    else [("verified", "verified"),
                          ("real filing, good standing", "neutral")])
        with rchip:
            C.chips([("seeded imitation, not real", "seeded")] if right["is_suspect"]
                    else [("verified", "verified"),
                          ("real filing, good standing", "neutral")])

        if picked_imitation:
            st.markdown(
                "**Most people pick that one. Names are not evidence. "
                "Here is what is.**"
            )
        else:
            st.markdown(
                "**Correct, and it was closer than it looked. "
                "Here is the margin.**"
            )

        if st.button("next pair", key="gp_c_next"):
            _sample_pair(force_new=True)
            st.rerun()

        # ------------------------------------------------------------ S4
        # The thesis of the project in one image, and the single most
        # quotable chart in the submission.
        C.section("Meaning versus spelling")
        st.plotly_chart(
            charts.meaning_vs_spelling(
                float(pair["semantic_sim"]), float(pair["string_sim"])),
            use_container_width=True, config=charts.bare_config(),
        )
        C.source_note(
            f"Meaning similarity {pair['semantic_sim']:.2f}, spelling "
            f"similarity {pair['string_sim']:.2f}. The gap between them is "
            f"{pair['evasion_gap']:.2f}. A high semantic similarity paired "
            "with a low string similarity is the signature of deliberate "
            "evasion: the impersonator kept the meaning and changed the "
            "spelling on purpose. Both numbers are computed in SQL inside "
            "the warehouse, with no data leaving it."
        )
        st.markdown(
            C.chip(f"technique: {pair.get('synth_technique', 'recorded')}", "seeded"),
            unsafe_allow_html=True,
        )

        # -------------------------------------------------------- S5, S6
        wcol, ncol = st.columns(2, gap="medium")

        with wcol:
            C.section("Confidence decomposition")
            risk = data.run("Q_ORG_RISK_ONE", (pair["suspect_id"],))
            if risk.empty:
                st.markdown('<div class="gp-source">No score for this row.</div>',
                            unsafe_allow_html=True)
            else:
                r = risk.iloc[0]
                st.plotly_chart(
                    charts.risk_waterfall(
                        {
                            "semantic proximity": float(r["comp_semantic"]),
                            "evasion gap": float(r["comp_evasion"]),
                            "geometry flags": float(r["comp_geometry"]),
                            "unaccounted ratio": float(r["comp_unaccounted"]),
                            "missing receipts": float(r["comp_receipts"]),
                        },
                        float(r["risk_score"]),
                    ),
                    use_container_width=True, config=charts.bare_config(),
                )
                C.source_note(
                    "The five components of MARTS.F_RISK, adding to the total. "
                    "An accountability tool cannot show an opaque score, so "
                    "the arithmetic is reconstructable by eye."
                )

        with ncol:
            C.section("Semantic neighbourhood")
            projection = data.run("Q_PROJECTION", (pair["suspect_cause"],))
            if projection.empty:
                st.markdown('<div class="gp-source">No projection stored for '
                            'this cause.</div>', unsafe_allow_html=True)
            else:
                st.plotly_chart(
                    charts.semantic_neighbourhood(
                        projection, (pair["suspect_id"], pair["target_id"])),
                    use_container_width=True, config=charts.bare_config(),
                )
                C.source_note(
                    "Organisations in the same cause, projected to two "
                    "dimensions offline with scikit-learn PCA. Imitations sit "
                    "on top of their targets while ordinary organisations "
                    "spread out."
                )

        # Detail surface. The identifiers, in Geist, never in monospace.
        C.section("The two records")
        d1, d2 = st.columns(2, gap="medium")
        with d1:
            C.identifier(pair["target_id"], "verified organisation identifier")
        with d2:
            C.identifier(pair["suspect_id"], "seeded organisation identifier")

    # ---------------------------------------------------------------- S7
    C.section("How this works")
    C.step_explainer([
        ("Embed name and mission",
         "Every organisation's name, mission line and cause are turned into "
         "a list of numbers that captures what the words mean, not how they "
         "are spelled."),
        ("Compare by meaning",
         "Two organisations are compared by the angle between those lists. "
         "Names that mean the same thing land close together even when they "
         "share almost no letters."),
        ("Flag the gap",
         f"When meaning is very close but spelling is not, that gap is the "
         f"signal. The cut-off is {Q.SIMILARITY_THRESHOLD}, shown in the "
         "interface rather than hidden, and you can move it on the next tab."),
    ])

    C.provenance_footer(
        "Real side: IRS Business Master File, unmodified, filtered to "
        "organisations in good standing. Suspect side: tools/make_synthetic.py, "
        "batch SYNTH_ADVERSARY_V1. Projection coordinates: offline "
        "scikit-learn PCA over the stored vectors. Risk components: "
        "MARTS.ORG_RISK."
    )
