"""Tab 05 / The Wall. Build Spec Section 07.

    Now try to use this tool to find one specific person. You will not be
    able to.

THIS IS THE CENTREPIECE AND IT IS NEVER CUT.

Every tab before it shows the system finding things. This one shows the
system refusing to find something, on purpose, with a mathematical
guarantee. It is the strongest single screen in the submission.

The line to deliver over the diverging lines of C05-1:

    "Every accountability project has the same unsolved problem. To prove
    aid reached people you have to publish data about those people. This
    is the part where the tool protects them from me, from you, and from
    itself."
"""

from __future__ import annotations

import numpy as np
import streamlit as st

import charts
import components as C
import data

AMOUNT_BANDS = {
    "any": "any",
    "0 to 500": (0.0, 500.0),
    "500 to 2K": (500.0, 2000.0),
    "2K to 10K": (2000.0, 10000.0),
}


def _ledger() -> data.PrivacyLedger:
    if "gp_privacy_ledger" not in st.session_state:
        st.session_state["gp_privacy_ledger"] = data.PrivacyLedger()
    return st.session_state["gp_privacy_ledger"]


def render() -> None:
    ledger = _ledger()

    # ---------------------------------------------------------------- S1
    # Hero. Live remaining privacy budget, counting down as the viewer
    # queries. Not a printed number: it moves while you watch.
    C.tab_title(
        "The Wall",
        "Now try to use this tool to find one specific person. "
        "You will not be able to.",
    )
    C.hero(
        f"{ledger.share_remaining * 100:.0f}%",
        "privacy budget remaining in this window",
    )
    C.meter(ledger.share_remaining)

    st.markdown(
        "Everything so far has been this system finding things. "
        "Now try to make it find one person."
    )

    # ---------------------------------------------------------------- S2
    # Filter console. This is the attack surface.
    C.section("Narrow the question")

    options = data.run("Q_FILTER_OPTIONS")
    districts = ["any"] + sorted(options["district"].dropna().unique().tolist())
    programmes = ["any"] + sorted(options["programme_code"].dropna().unique().tolist())
    months = ["any"] + sorted(options["month_key"].dropna().unique().tolist())

    # A district selected on Tab 04 arrives here, so the handoff between
    # the two tabs is real rather than narrated.
    carried = st.session_state.get("gp_focus_district")
    district_index = districts.index(carried) if carried in districts else 0
    if carried:
        st.markdown(
            C.chip(f"district carried from Follow The Money: {carried}", "neutral"),
            unsafe_allow_html=True,
        )

    c1, c2, c3, c4 = st.columns(4, gap="small")
    with c1:
        district = st.selectbox("district", districts, index=district_index,
                                key="gp_w_district")
    with c2:
        programme = st.selectbox("programme", programmes, key="gp_w_programme")
    with c3:
        month = st.selectbox("month", months, key="gp_w_month")
    with c4:
        band_label = st.selectbox("amount band", list(AMOUNT_BANDS), key="gp_w_band")

    filters = {
        "district": district,
        "programme_code": programme,
        "month_key": month,
        "amount_band": AMOUNT_BANDS[band_label],
    }

    truth = data.true_answer(filters)
    cohort = truth["cohort"]

    # Cohort chip. Amber under fifty, red at one.
    if cohort <= 1:
        tone, note = "flagged", "cohort of one"
    elif cohort < 50:
        tone, note = "seeded", f"estimated cohort: {cohort} people"
    else:
        tone, note = "verified", f"estimated cohort: {cohort:,} people"
    st.markdown(C.chip(note, tone), unsafe_allow_html=True)

    if st.button("release the answer", type="primary", key="gp_w_ask"):
        st.session_state["gp_w_last"] = data.released_answer(filters, ledger)
        # Rerun so the hero reports the budget AFTER this query has been
        # charged for. A budget meter that lags the query it paid for
        # would undercut the whole point of the tab.
        st.rerun()

    released = st.session_state.get("gp_w_last")

    # ---------------------------------------------------------------- S3
    # Dual columns. True answer beside released answer, labelled
    # unambiguously. The left column is the counterfactual that would
    # exist without the policy.
    C.section("Without the policy, and through it")

    if released is None:
        st.markdown(
            '<div class="gp-source">Choose filters and release an answer. '
            'Start broad, then narrow, and watch the two columns separate.'
            '</div>',
            unsafe_allow_html=True,
        )
    elif released.get("refused"):
        C.compare_columns(
            {
                "label": "without the policy",
                "value": C.usd(truth["total_usd"], precise=True),
                "sub": f"count {truth['cohort']:,} · the true answer",
            },
            {
                "label": "through the policy",
                "value": "refused",
                "sub": released.get("reason", "the query was refused"),
            },
        )
        st.markdown(
            C.chip("the guarantee held: the query was refused", "flagged"),
            unsafe_allow_html=True,
        )
    else:
        divergence = abs(released["total_usd"] - truth["total_usd"])
        share = divergence / max(truth["total_usd"], 1)
        C.compare_columns(
            {
                "label": "without the policy",
                "value": C.usd(truth["total_usd"], precise=True),
                "sub": f"count {truth['cohort']:,} · the true answer, ink",
            },
            {
                "label": "through the policy",
                "value": C.usd(released["total_usd"], precise=True),
                "sub": (f"count ~{released['cohort']:,.0f} · the released answer"
                        + (" · large" if share > 0.25 else "")),
            },
        )
        if cohort <= 1:
            st.markdown(
                "Cohort of one. The released answer is now noise, and your "
                "privacy budget is spent. This is the guarantee working."
            )
        elif share > 0.25:
            st.markdown(
                f"The two columns differ by {C.usd(divergence)}. The narrower "
                "the question, the more the answer has to be protected."
            )
        else:
            st.markdown(
                "The cohort is large, so the released answer sits close to the "
                "true one. The guarantee costs almost nothing here, which is "
                "the point: it only bites when a question gets personal."
            )

    if data.is_preview():
        C.source_note(
            "Preview mode. The noise here is a local Laplace mechanism with a "
            "real epsilon ledger, not the Snowflake privacy policy. In the "
            "deployed build the policy is attached to "
            "SERVING.V_BENEFICIARY_OUTCOMES with an entity key on "
            "beneficiary_id, and Snowflake applies the noise."
        )

    # ---------------------------------------------------------------- S4
    # The picture of a privacy guarantee.
    C.section("Noise against cohort size")
    curve = data.noise_curve_frame(filters)
    st.plotly_chart(
        charts.noise_curve(curve, animate=not st.session_state.get("gp_w_seen")),
        use_container_width=True, config=charts.bare_config(),
    )
    st.session_state["gp_w_seen"] = True
    C.source_note(
        "Lines converge to the right and diverge violently to the left. A "
        "question about ten thousand people is answered almost exactly. A "
        "question about one person is not answered at all."
    )

    # ------------------------------------------------------------ S5, S6
    left, right = st.columns(2, gap="medium")

    with left:
        C.section("Budget burn-down")
        burndown = ledger.burndown()
        if burndown.empty:
            st.markdown(
                '<div class="gp-source">No budget spent yet this session.</div>',
                unsafe_allow_html=True,
            )
        else:
            st.plotly_chart(
                charts.budget_burndown(burndown),
                use_container_width=True, config=charts.bare_config(),
            )
            C.source_note(
                "Red bars are narrow queries. A narrow question costs far more "
                "budget than a broad one, because isolating few people raises "
                "the sensitivity of the answer."
            )

    with right:
        C.section("Repeated queries")
        if st.button("run this ten times", key="gp_w_repeat"):
            st.session_state["gp_w_samples"] = data.repeated_releases(filters, n=40)
        samples = st.session_state.get("gp_w_samples")
        if samples:
            st.plotly_chart(
                charts.repeated_query_box(samples, truth["total_usd"]),
                use_container_width=True, config=charts.bare_config(),
            )
            spread = float(np.std(samples))
            C.source_note(
                f"Spread {C.usd(spread)} around a true value of "
                f"{C.usd(truth['total_usd'])}. Repeated attempts do not average "
                "toward the truth, because in a real deployment the budget "
                "depletes long before enough samples exist."
            )
        else:
            st.markdown(
                '<div class="gp-source">Defeats the averaging objection: ask '
                'the same question repeatedly and see where the answers land.'
                '</div>',
                unsafe_allow_html=True,
            )

    # Reset control. Demo mode only, and the interface says so.
    reset_col, note_col = st.columns([1, 4], gap="small")
    with reset_col:
        if st.button("reset budget", key="gp_w_reset"):
            ledger.reset()
            st.session_state.pop("gp_w_last", None)
            st.session_state.pop("gp_w_samples", None)
            st.rerun()
    with note_col:
        C.source_note(
            "Demo mode only. A production deployment would not expose a budget "
            "reset, because being able to refill the budget is the same as not "
            "having one."
        )

    # ---------------------------------------------------------------- S7
    C.section("What this costs")
    C.step_explainer([
        (
            "What differential privacy guarantees",
            "Any single person's record can be added or removed from this "
            "dataset without meaningfully changing any answer the system "
            "releases. That is a mathematical property, not a promise.",
        ),
        (
            "What it cannot do",
            "It does not make the data anonymous, it does not stop a "
            "determined operator with direct table access, and it cannot "
            "protect a person who is the only member of every cohort they "
            "belong to.",
        ),
        (
            "Why we pay for it",
            "To prove aid reached people you have to publish data about "
            "those people. Noise and a finite budget are the price of "
            "publishing the finding without publishing the person.",
        ),
    ])

    C.provenance_footer(
        "Entirely synthetic beneficiary records. No real personal data enters "
        "this project at any point, which is itself the correct engineering "
        "decision. The protected object is SERVING.V_BENEFICIARY_OUTCOMES with "
        "a privacy policy and an entity key on beneficiary_id. The true column "
        "reads the unprotected twin under a privileged role, and both are "
        "labelled on screen."
    )
