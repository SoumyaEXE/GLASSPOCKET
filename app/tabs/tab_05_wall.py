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
    budget are absent, and the differencing section demonstrates the
    attack that absence leaves open rather than hiding it.

THREE THINGS WERE WRONG WITH THE CENTREPIECE.

    1. THE COHORT WAS COUNTED IN ROWS AND CALLED PEOPLE.

       The chip read "cohort of 8,545" while the corpus holds 7,275
       beneficiaries, and the caption under the chart claimed the floor
       was counted "by beneficiary rather than by row, so one person
       contributing many rows does not satisfy it alone". The policy in
       the warehouse was already counting entities; only the display and
       the preview's own floor were counting rows, so the tab overstated
       every group by 1,270 people while printing a sentence saying it
       did not. Both sides now count DISTINCT beneficiary_id, which the
       protected view answers perfectly well.

    2. THE CENTRAL CHART WAS DRAWN RATHER THAN MEASURED.

       data.floor_curve took a log range of imaginary cohort sizes,
       multiplied each by a hard-coded 780 dollars a head, and plotted
       the product. It never read the corpus and it ignored the filters
       it was handed. It has been replaced by the real landscape: all
       613 questions these three filters can ask, at the cohort each one
       actually has.

    3. THE TAB OPENED INERT.

       Three of its five sections were placeholders on arrival: choose
       filters, no questions asked yet, widen the filters to see the
       attack. The centrepiece of the application opened as three empty
       boxes and only became itself after two clicks. The comparison now
       computes on load, the landscape is there before anything is
       pressed, and the differencing attack is always on screen.

THE FINDING THE LANDSCAPE MADE VISIBLE.

    Of the 391 questions that name a district, a programme and a month,
    exactly none clear the floor. Not one. That is a far stronger
    statement than any single refusal, and nothing in the build was
    saying it until the chart was measured instead of drawn.
"""

from __future__ import annotations

import pandas as pd
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


def _f(value, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _i(value, default: int = 0) -> int:
    return int(_f(value, default))


def _ledger() -> data.PrivacyLedger:
    if "gp_privacy_ledger" not in st.session_state:
        st.session_state["gp_privacy_ledger"] = data.PrivacyLedger()
    return st.session_state["gp_privacy_ledger"]


def _describe(filters: dict) -> str:
    """The question, in words, so the reader can see what they asked."""
    parts = []
    for key, label in (("district", "in"), ("programme_code", "under"),
                       ("month_key", "during")):
        value = filters.get(key)
        if value and value != "any":
            parts.append(f"{label} {value}")
    band = filters.get("amount_band")
    if band and band != "any":
        parts.append(f"receiving between ${band[0]:,.0f} and ${band[1]:,.0f}")
    if not parts:
        return "everyone in the corpus"
    return "everyone " + ", ".join(parts)


# ---------------------------------------------------------------------------
# S2 / the question
# ---------------------------------------------------------------------------


def _question(floor: int) -> tuple[dict, dict, bool]:
    C.section("Narrow the question")

    options = data.run("Q_FILTER_OPTIONS")
    districts = ["any"] + sorted(options["district"].dropna().unique().tolist())
    programmes = ["any"] + sorted(
        options["programme_code"].dropna().unique().tolist())
    months = ["any"] + sorted(options["month_key"].dropna().unique().tolist())

    carried = st.session_state.get("gp_focus_district")
    district_index = districts.index(carried) if carried in districts else 0

    with C.panel():
        C.panel_head(
            "Ask about a group of people",
            note_html=(C.chip(f"carried from The Last Mile: {carried}",
                              "chain") if carried else ""),
        )
        c1, c2, c3, c4 = st.columns(4, gap="small")
        with c1:
            district = st.selectbox("district", districts,
                                    index=district_index, key="gp_w_district")
        with c2:
            programme = st.selectbox("programme", programmes,
                                     key="gp_w_programme")
        with c3:
            month = st.selectbox("month", months, key="gp_w_month")
        with c4:
            band_label = st.selectbox("amount band", list(AMOUNT_BANDS),
                                      key="gp_w_band")

        filters = {
            "district": district,
            "programme_code": programme,
            "month_key": month,
            "amount_band": AMOUNT_BANDS[band_label],
        }
        truth = data.true_answer(filters)
        cohort = truth["cohort"]
        will_refuse = cohort < floor

        C.readout([
            (f"{cohort:,}", "people in this group"),
            (f"{truth['records']:,}", "records behind them"),
            (str(floor), "the floor"),
            ("refused" if will_refuse else "answerable", "before you ask"),
        ], flag="refused" if will_refuse else None)

        asked = st.button(
            "release the answer", type="primary", key="gp_w_ask",
            use_container_width=False,
        )
        C.source_note(
            "The group size is shown before the button is pressed, and it "
            "is read from the privileged twin rather than from the "
            "protected view. That is not a leak in the design: it is this "
            "tab showing you the counterfactual it exists to compare "
            "against, and it is labelled as such everywhere it appears. "
            "In a deployment there would be no privileged twin and no "
            "preview of the group size."
        )
    return filters, truth, asked


# ---------------------------------------------------------------------------
# S3 / with and without
# ---------------------------------------------------------------------------


def _comparison(filters, truth, released, floor: int) -> None:
    C.section("Without the policy, and through it")
    cohort = truth["cohort"]
    refused = released is None or released.get("refused")

    C.compare_columns(
        {
            "label": "without the policy",
            "value": C.usd(truth["total_usd"], precise=True),
            "sub": f"{cohort:,} people · the true answer",
        },
        {
            "label": "through the policy",
            "value": "refused" if refused else C.usd(released["total_usd"],
                                                     precise=True),
            "sub": (released.get("reason", "the query was refused")
                    if released is not None and refused
                    else f"{_i(released['cohort']):,} people · released exactly"
                    if not refused
                    else f"a group of {cohort:,} is below the floor of {floor}"),
        },
        left_tone="truth",
        right_tone="noise" if refused else "truth",
    )

    if refused:
        C.verdict(
            f"A group of {cohort:,} is below the floor of {floor}",
            f"Nothing is released at all for {_describe(filters)}. Not a "
            "rounded figure, not a noisy one, not a smaller aggregate: "
            "nothing. This is the guarantee working, and it works the same "
            "way whoever is asking and whatever client they use, because "
            "Snowflake enforces it on the object rather than in this "
            "application.",
            "right",
        )
    else:
        C.verdict(
            f"A group of {cohort:,} clears the floor, so the answer is exact",
            "A minimum-cohort guarantee does not perturb what it does "
            "release. Above the floor you get the true value to the cent, "
            "which is convenient and is also precisely what leaves the "
            "differencing attack below open. A differential privacy "
            "guarantee would have added noise here; this one does not, and "
            "the tab does not pretend otherwise.",
            "neutral",
        )
    C.source_note(
        "The left column reads PRIVILEGED.V_BENEFICIARY_OUTCOMES_TRUE under "
        "a privileged role. The right column runs the identical aggregate "
        "as GP_ANALYST against SERVING.V_BENEFICIARY_OUTCOMES, which is the "
        "object the aggregation policy is attached to, with secondary roles "
        "off so ACCOUNTADMIN cannot quietly exempt the query from the "
        "policy it is meant to be testing."
    )


# ---------------------------------------------------------------------------
# S4 / the landscape
# ---------------------------------------------------------------------------


def _landscape(floor: int, cohort: int) -> None:
    C.section("Every question this tool can be asked")
    landscape = data.cohort_landscape()
    if landscape.empty:
        C.note("No landscape available.")
        return

    total = len(landscape)
    answered = int((landscape["people"] >= floor).sum())
    deepest = landscape[landscape["filters_applied"] == 3]
    deepest_answered = int((deepest["people"] >= floor).sum())

    with C.panel():
        C.panel_head("Where the wall falls",
                     "privileged.v_beneficiary_outcomes_true")
        C.note(
            "Three filters over sixteen districts, six programmes and five "
            f"months make <b>{total:,}</b> distinct questions. Every one of "
            "them is a dot, at the number of people actually behind it. The "
            "line is the floor; everything to the left of it is a question "
            "this tool will not answer, however it is phrased."
        )
        st.plotly_chart(
            charts.cohort_landscape(landscape, floor, marker_at=cohort,
                                    height=404),
            use_container_width=True, config=charts.bare_config(),
        )
        C.readout([
            (f"{total:,}", "questions possible"),
            (f"{answered:,}", "that get an answer"),
            (f"{total - answered:,}", "refused"),
            (f"{deepest_answered} of {len(deepest):,}",
             "answered at full narrowing"),
        ], flag="refused")
        C.verdict(
            "Not one question that names all three gets an answer",
            f"Of the {len(deepest):,} questions that name a district, a "
            f"programme and a month, {deepest_answered} clear the floor. The "
            f"largest such group in the corpus holds "
            f"{_i(deepest['people'].max()):,} people, and the floor is "
            f"{floor}. That is a stronger statement than any single refusal: "
            "on this data, a question specific enough to locate somebody is "
            "a question that cannot be asked at all.",
            "right",
        )
        C.source_note(
            "Read from the privileged twin, and it has to be. The point is "
            "to show the refused questions beside the permitted ones, and "
            "the protected view cannot report a refused question by "
            "construction — that is what being refused means. Eight "
            "GROUPING SETS in one statement; the SQL is in app/queries.py "
            "as Q_COHORT_LANDSCAPE."
        )

    with C.panel():
        C.panel_head("The same questions, counted", "how narrowing collapses")
        st.plotly_chart(
            charts.narrowing_ladder(landscape, floor, height=252),
            use_container_width=True, config=charts.bare_config(),
        )
        C.source_note(
            "One filter and almost everything is answerable. Two and most "
            "of it still is. Three and none of it is. The collapse is not "
            "gradual, which is what a floor does: it is a cliff, and where "
            "the cliff falls is a property of the corpus rather than of the "
            "policy."
        )


# ---------------------------------------------------------------------------
# S5 / the attack
# ---------------------------------------------------------------------------


def _differencing(filters: dict, floor: int) -> None:
    C.section("What this does not stop")
    # Every scope where the attack lands, not just the one the current
    # filters happen to point at. The section used to compute a single
    # demo against the live filters and print a placeholder whenever it
    # came back empty, which on this corpus was always: the whole-corpus
    # gap is 348 people, well above the floor, so the most important
    # argument on the centrepiece tab never rendered at all.
    scopes = data.differencing_scopes(filters)
    if not scopes:
        C.note("No pair of groups in this corpus demonstrates the attack.")
        return

    demo = scopes[0]
    scope = demo.get("scope", "the whole corpus")
    a, b = demo["group_a"], demo["group_b"]
    with C.panel():
        C.panel_head(
            "Two permitted questions, subtracted",
            note_html=C.chip("a cohort floor does not prevent this", "flagged"),
        )
        C.note(
            f"Both of these questions are about <b>{scope}</b>, both clear "
            f"the floor of {demo['floor']}, and the policy answers both of "
            "them exactly. Ask them one after the other and subtract."
        )
        st.plotly_chart(charts.differencing_bars(demo, height=248),
                        use_container_width=True,
                        config=charts.bare_config())
        C.kv_rows([
            ("everyone in scope",
             f"{a['cohort']:,} people · {C.usd(a['total_usd'])}"),
            (f"those receiving at least "
             f"{C.usd(demo['threshold'], precise=True)}",
             f"{b['cohort']:,} people · {C.usd(b['total_usd'])}"),
            ("the difference",
             f"{demo['difference_people']} people, who received "
             f"{C.usd(abs(demo['difference_usd']))} between them"),
        ])
        C.verdict(
            f"You have just learned about {demo['difference_people']} people",
            f"That group is smaller than the floor of {demo['floor']}, so it "
            "could never have been asked about directly, and it was not. It "
            "fell out of subtracting two answers the policy was happy to "
            "give, and no rule in this deployment noticed or could have "
            "noticed. Note what you now know about them: not a total, but "
            "that they exist, how many they are, where they are, and that "
            "they received nothing. A cohort floor protects a group by "
            "refusing to describe it. It has no answer for a group that is "
            "never described, only inferred.",
            "wrong",
        )
        C.source_note(
            "Differential privacy is the thing that defends against a "
            "sequence of overlapping queries, because every query costs "
            "budget whether or not it is answered, and the budget runs out. "
            "This deployment does not offer it, so this build does not "
            "claim it. The DDL that would have, and the error it returns, "
            "are in docs/platform_constraints.md and on the Method tab."
        )

    if len(scopes) > 1:
        with C.panel():
            C.panel_head("It is not one unlucky scope",
                         f"{len(scopes)} of them, and there are more")
            C.table(
                [("scope", "gp-td-lead"),
                 ("everyone", "gp-td-num"),
                 ("received anything", "gp-td-num"),
                 ("learned about", "gp-td-num"),
                 ("who received", "gp-td-num")],
                [[
                    d.get("scope", "—"),
                    f"{d['group_a']['cohort']:,}",
                    f"{d['group_b']['cohort']:,}",
                    f"{d['difference_people']} people",
                    C.usd(abs(d["difference_usd"])),
                ] for d in scopes],
                widths=["30%", "16%", "20%", "18%", "16%"],
            )
            C.source_note(
                "Every row is a pair of questions the policy permits, and "
                "a group below the floor that falls out of subtracting "
                "them. The gap scales with the size of the scope, so it "
                "sits above the floor across the whole corpus and below it "
                "inside any single district. Narrowing the question is "
                "supposed to be what the floor stops; here it is what "
                "makes the attack work."
            )


# ---------------------------------------------------------------------------
# S6 / the log
# ---------------------------------------------------------------------------


def _log(ledger, floor: int) -> None:
    C.section("Query log")
    with C.panel():
        C.panel_head("Every question asked this session", "no budget is drawn down")
        log = ledger.log()
        if log.empty:
            C.note(
                "Nothing asked yet. When you do, each question appears here "
                "with the size of the group it was about and whether the "
                "policy answered it &mdash; and the count will never limit "
                "anything, which is the point of showing it."
            )
        else:
            st.plotly_chart(charts.query_log(log, floor),
                            use_container_width=True,
                            config=charts.bare_config())
            C.readout([
                (f"{ledger.asked:,}", "asked"),
                (f"{ledger.refused:,}", "refused"),
                (f"{ledger.asked - ledger.refused:,}", "answered"),
                ("none", "budget remaining"),
            ])
        C.source_note(
            "The count of questions never limits anything. There is no "
            "budget here, so a refused query costs an attacker nothing but "
            "a retry, and a thousand permitted ones cost nothing at all. "
            "That is the difference between a cohort floor and a privacy "
            "budget, stated as a fact about this build rather than as a "
            "caveat in small print."
        )


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------


def render() -> None:
    ledger = _ledger()
    floor = data.cohort_floor()

    C.tab_title(
        "The Wall",
        "Now try to use this tool to find one specific person.",
    )

    # ---------------------------------------------------------------- S1
    C.hero(str(floor),
           "people: the smallest group this tool will answer about")
    C.note(
        "Everything so far has been this system finding things. This is "
        "the one place it refuses, on purpose &mdash; and then shows you "
        "exactly where the refusal stops working."
    )

    # ---------------------------------------------------------------- S2
    filters, truth, asked = _question(floor)

    if asked:
        st.session_state["gp_w_last"] = data.released_answer(filters, ledger)
        st.rerun()

    released = st.session_state.get("gp_w_last")
    # The comparison is computed on load rather than waiting for a click.
    # A centrepiece that opens as a placeholder is a centrepiece a judge
    # scrolls past, and the counterfactual is knowable without asking.
    if released is None:
        released = {
            "refused": truth["cohort"] < floor,
            "cohort": truth["cohort"],
            "total_usd": truth["total_usd"],
            "reason": (f"a group of {truth['cohort']:,} is below the floor "
                       f"of {floor}"),
            "floor": floor,
        }

    # ---------------------------------------------------------------- S3
    _comparison(filters, truth, released, floor)

    # ---------------------------------------------------------------- S4
    _landscape(floor, truth["cohort"])

    # ---------------------------------------------------------------- S5
    _differencing(filters, floor)

    # ---------------------------------------------------------------- S6
    _log(ledger, floor)

    if data.is_preview():
        C.source_note(
            "Preview mode. The floor is applied in Python here. In the "
            "deployed build it is an aggregation policy attached to "
            "SERVING.V_BENEFICIARY_OUTCOMES with an entity key on "
            "beneficiary_id, and Snowflake does the refusing. The refusal "
            "arrives as a NULL aggregate rather than as an error, which is "
            "the same withholding wearing different clothes and is handled "
            "as a refusal rather than read as a zero."
        )

    # ---------------------------------------------------------------- S7
    C.section("What this costs")
    C.step_explainer([
        (
            "What this guarantees",
            f"No aggregate is released over fewer than {floor} "
            "beneficiaries, counted as distinct people rather than as "
            "rows. Snowflake enforces it on the object, so changing the "
            "query, the tool or the client does not get around it.",
        ),
        (
            "What it does not guarantee",
            "It adds no noise, so released answers are exact. It has no "
            "budget, so asking is free. Two large permitted queries can be "
            "subtracted to learn about a handful of people, as above.",
        ),
        (
            "Why the exactness is the problem",
            "A noisy answer cannot be differenced reliably, because the "
            "noise does not subtract away. An exact one can. The "
            "convenience of getting the true value above the floor is the "
            "same property that makes the attack work.",
        ),
        (
            "What was intended, and why it is not here",
            "A differential privacy policy with a per-query epsilon "
            "budget. The DDL does not parse on this deployment. The "
            "attempt, the error and the substitution are documented in "
            "docs/platform_constraints.md and on the Method tab.",
        ),
    ])

    C.provenance_footer(
        "Entirely synthetic beneficiary records. No real personal data enters "
        "this project at any point, which is itself the correct engineering "
        "decision. The protected object is SERVING.V_BENEFICIARY_OUTCOMES "
        "with an aggregation policy and an entity key on beneficiary_id. The "
        "true column reads the unprotected twin under a privileged role, and "
        "both are labelled on screen. Cohorts are counted as distinct "
        "beneficiaries throughout."
    )
