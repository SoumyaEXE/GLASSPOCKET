"""Tab 05 / The Wall. Build Spec Section 07, with the Section 10 fallback.

    Now try to use this tool to find one specific person.

THIS IS THE CENTREPIECE AND IT IS NEVER CUT.

Every tab before it shows the system finding things. This one shows the
system refusing to find something, on purpose, and then shows you exactly
where that refusal stops working.

WHAT SHIPS HERE, AND WHY IT IS NOT WHAT THE SPEC ASKED FOR
    The spec specifies a Snowflake privacy policy with a differential
    privacy budget. That DDL does not parse on the target deployment:

        CREATE PRIVACY BUDGET ...  -> syntax error, unexpected 'BUDGET'
        ALTER VIEW ... SET PRIVACY POLICY ... -> syntax error

    Section 10 supplies the fallback, and this tab takes it: an
    aggregation policy with MIN_GROUP_SIZE => 50, relabelled honestly as
    a minimum-cohort guarantee rather than a differential privacy one.

    The refusal is real and Snowflake enforces it. The noise and the
    budget are absent, and section S6 demonstrates the attack that
    absence leaves open rather than hiding it.
"""

from __future__ import annotations

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
    floor = data.cohort_floor()

    C.tab_title(
        "The Wall",
        "Now try to use this tool to find one specific person.",
    )

    # ---------------------------------------------------------------- S1
    # Hero. The floor itself, because that is the number that governs
    # every answer this tab will and will not give.
    C.hero(str(floor), "beneficiaries: the smallest group this tool will answer about")

    st.markdown(
        "Everything so far has been this system finding things. "
        "Now try to make it find one person."
    )

    # ---------------------------------------------------------------- S2
    C.section("Narrow the question")

    options = data.run("Q_FILTER_OPTIONS")
    districts = ["any"] + sorted(options["district"].dropna().unique().tolist())
    programmes = ["any"] + sorted(options["programme_code"].dropna().unique().tolist())
    months = ["any"] + sorted(options["month_key"].dropna().unique().tolist())

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

    if cohort < floor:
        tone = "flagged"
        note = f"cohort of {cohort:,}: below the floor, this will be refused"
    elif cohort < floor * 3:
        tone = "seeded"
        note = f"cohort of {cohort:,}: close to the floor"
    else:
        tone = "verified"
        note = f"cohort of {cohort:,}"
    st.markdown(C.chip(note, tone), unsafe_allow_html=True)

    if st.button("release the answer", type="primary", key="gp_w_ask"):
        st.session_state["gp_w_last"] = data.released_answer(filters, ledger)
        st.rerun()

    released = st.session_state.get("gp_w_last")

    # ---------------------------------------------------------------- S3
    C.section("Without the policy, and through it")

    if released is None:
        st.markdown(
            '<div class="gp-source">Choose filters and release an answer. '
            'Start broad, then narrow, and watch the right-hand column stop '
            'answering.</div>',
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
            f"**Cohort of {cohort:,}. Below the floor of {floor}, so nothing "
            "is released at all. This is the guarantee working.**"
        )
    else:
        C.compare_columns(
            {
                "label": "without the policy",
                "value": C.usd(truth["total_usd"], precise=True),
                "sub": f"count {truth['cohort']:,} · the true answer",
            },
            {
                "label": "through the policy",
                "value": C.usd(released["total_usd"], precise=True),
                "sub": f"count {released['cohort']:,.0f} · released exactly",
            },
            right_tone="truth",
        )
        st.markdown(
            f"The group clears the floor, so the answer is released **exactly**. "
            "A minimum-cohort guarantee does not perturb what it does release. "
            "That is the difference between this and a differential privacy "
            "guarantee, and it matters below."
        )

    # ---------------------------------------------------------------- S4
    C.section("What gets answered")
    st.plotly_chart(
        charts.cohort_floor_curve(data.floor_curve(filters)),
        use_container_width=True, config=charts.bare_config(),
    )
    C.source_note(
        f"Left of the line the tool returns nothing, however the question is "
        f"phrased. Right of it the true value is released. The floor is "
        f"{floor} entities, counted by beneficiary rather than by row, so one "
        "person contributing many rows does not satisfy it alone."
    )

    # ------------------------------------------------------------ S5, S6
    left, right = st.columns(2, gap="medium")

    with left:
        C.section("Query log")
        log = ledger.log()
        if log.empty:
            st.markdown('<div class="gp-source">No questions asked yet '
                        'this session.</div>', unsafe_allow_html=True)
        else:
            st.plotly_chart(
                charts.query_log(log, floor),
                use_container_width=True, config=charts.bare_config(),
            )
            C.source_note(
                f"{ledger.asked} asked, {ledger.refused} refused. Note that "
                "the count of questions never limits anything: there is no "
                "budget here, and a refused query costs the attacker nothing "
                "but a retry."
            )

    with right:
        C.section("What this does not stop")
        demo = data.differencing_demo(filters)
        if demo is None:
            st.markdown(
                '<div class="gp-source">Widen the filters to see the '
                'differencing attack this floor cannot prevent.</div>',
                unsafe_allow_html=True,
            )
        else:
            a, b = demo["group_a"], demo["group_b"]
            st.markdown(
                f"Two questions, **both allowed**, because both groups clear "
                f"the floor of {demo['floor']}:"
            )
            st.markdown(
                f"- everyone in scope: **{a['cohort']:,}** people, "
                f"{C.usd(a['total_usd'])}\n"
                f"- everyone receiving at least "
                f"{C.usd(demo['threshold'], precise=True)}: "
                f"**{b['cohort']:,}** people, {C.usd(b['total_usd'])}"
            )
            st.markdown(
                f"Subtract them and you have learned about "
                f"**{demo['difference_people']} people** who never formed a "
                f"group large enough to ask about directly, and that they "
                f"received {C.usd(abs(demo['difference_usd']))} between them."
            )
            st.markdown(
                C.chip("a cohort floor does not prevent this", "flagged"),
                unsafe_allow_html=True,
            )
            C.source_note(
                "Differential privacy is the thing that defends against a "
                "sequence of overlapping queries, because every query costs "
                "budget whether or not it is answered. This deployment does "
                "not offer it, so this build does not claim it."
            )

    if data.is_preview():
        C.source_note(
            "Preview mode. The floor is applied in Python here. In the "
            "deployed build it is an aggregation policy attached to "
            "SERVING.V_BENEFICIARY_OUTCOMES with an entity key on "
            "beneficiary_id, and Snowflake does the refusing."
        )

    # ---------------------------------------------------------------- S7
    C.section("What this costs")
    C.step_explainer([
        (
            "What this guarantees",
            f"No aggregate is released over fewer than {floor} beneficiaries. "
            "Snowflake enforces it on the object, so changing the query, the "
            "tool or the client does not get around it.",
        ),
        (
            "What it does not guarantee",
            "It adds no noise, so released answers are exact. It has no "
            "budget, so asking is free. Two large permitted queries can be "
            "subtracted to learn about a handful of people, as above.",
        ),
        (
            "What was intended, and why it is not here",
            "A differential privacy policy with a per-query epsilon budget. "
            "The DDL does not parse on this deployment. The attempt, the "
            "error and the substitution are documented in "
            "docs/platform_constraints.md and on the Method tab.",
        ),
    ])

    C.provenance_footer(
        "Entirely synthetic beneficiary records. No real personal data enters "
        "this project at any point, which is itself the correct engineering "
        "decision. The protected object is SERVING.V_BENEFICIARY_OUTCOMES "
        "with an aggregation policy and an entity key on beneficiary_id. The "
        "true column reads the unprotected twin under a privileged role, and "
        "both are labelled on screen."
    )
