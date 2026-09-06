"""Tab 05 / The Wall. Build Spec Section 07.

    Now try to use this tool to find one specific person.

Every tab before this one shows the system finding things. This one
shows it refusing to find something, on purpose, then shows exactly
where each refusal stops working.

WHY THIS TAB CAME BACK, AND WHAT CHANGED WHILE IT WAS GONE
    It was cut two days before submission because the guarantee behind
    it was not the guarantee the spec asked for. The spec wanted a
    Snowflake privacy policy with a differential privacy budget, and
    sql/11_privacy_policy.sql recorded that the DDL did not parse on
    this deployment:

        CREATE PRIVACY BUDGET ...            -> unexpected 'BUDGET'
        ALTER VIEW ... SET PRIVACY POLICY -> unexpected 'PRIVACY'

    Both statements were malformed. There is no CREATE PRIVACY BUDGET
    statement in Snowflake for an account to be missing: a budget is
    created by being named in a policy body. And the attach clause is
    ADD PRIVACY POLICY, not SET. A parser error says a statement is
    malformed; it does not say a feature is absent, and this build spent
    a weekend treating those as the same fact.

    Written in syntax that exists, on the same account and warehouse, it
    works. So the tab returns with all three regimes on screen at once
    rather than two, and the comparison between them is the argument.

WHAT IS ON SCREEN, AND WHERE EACH NUMBER COMES FROM

    PRIVILEGED.V_BENEFICIARY_OUTCOMES_TRUE  no policy, exact. Readable
        only by a privileged role: GP_ANALYST has no USAGE on that
        schema at all, which is what stops this column from being a
        second query the analyst could have run for themselves.

    SERVING.V_BENEFICIARY_OUTCOMES  aggregation policy, MIN_GROUP_SIZE
        50, ENTITY KEY beneficiary_id. Exact above the floor, silent
        below it.

    SERVING.V_BENEFICIARY_DP  privacy policy, 0.1 epsilon per aggregate
        against a budget of 300. Never refuses, never exact.

    Everything on this tab counts PEOPLE and never rows, and that is now
    enforced by the platform rather than by discipline: the privacy
    engine refuses COUNT(*) outright with "infinite multiplier", because
    a beneficiary holds up to five rows here and the query itself has to
    deduplicate on the entity key.

THE FINDINGS THIS TAB MEASURES RATHER THAN ASSERTS

    1. Of the 842 questions that name a district, a programme and a
       month, not one clears the floor. Not one.

    2. That is not the floor being cautious. 202 of those combinations
       hold exactly one person and every one of the 842 sits below the
       floor, so a guarantee that answered them would be naming
       somebody.

    3. The floor is still not enough. Seventeen scopes, sixteen of them
       districts, leak a group below the floor to two questions the
       policy answers happily. The smallest such group is twelve people,
       in Nyala, and the policy returns it exactly and identically every
       time it is asked.

    4. The budget breaks that attack: thirty runs of the same pair
       through the privacy policy recovered a mean of 14.8 against a
       true 12, with a standard deviation of 18.2 and four runs
       returning a negative number of people. And the budget as
       configured here is still set above the cost of grinding through
       that noise. Section seven does the arithmetic and says so.
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
    """The question, in words, so a reader can see what they asked."""
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


def _question(floor: int) -> tuple[dict, dict]:
    C.section("Narrow the question")

    options = data.run("Q_FILTER_OPTIONS")
    districts = ["any"] + sorted(options["district"].dropna().unique().tolist())
    programmes = ["any"] + sorted(
        options["programme_code"].dropna().unique().tolist())
    months = ["any"] + sorted(options["month_key"].dropna().unique().tolist())

    with C.panel():
        C.panel_head("Ask about a group of people",
                     "marts.beneficiary_facts, entirely synthetic")
        c1, c2, c3, c4 = st.columns(4, gap="small")
        with c1:
            district = st.selectbox("district", districts, key="gp_w_district")
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

        C.readout([
            (f"{cohort:,}", "people in this group"),
            (f"{truth['records']:,}", "records behind them"),
            (str(floor), "the cohort floor"),
            ("below the floor" if cohort < floor else "above the floor",
             "before anything is asked"),
        ], flag="below the floor" if cohort < floor else None)

        C.source_note(
            "The group size is shown before any query runs, and it is read "
            "from the privileged twin rather than through a policy. That is "
            "not a leak in the design: it is the counterfactual this tab "
            "exists to compare against, and it is labelled as such wherever "
            "it appears. In a deployment there is no privileged twin and no "
            "preview of the group size."
        )
    return filters, truth


# ---------------------------------------------------------------------------
# S3 / three answers to one question
# ---------------------------------------------------------------------------


def _three_answers(filters: dict, truth: dict, floor: int,
                   ledger: data.PrivacyLedger) -> dict:
    C.section("The same question, asked of three objects")

    released = data.released_answer(filters, ledger)
    dp = data.dp_answer(filters, ledger)
    cohort = truth["cohort"]
    refused = released.get("refused")

    with C.panel():
        C.panel_head(
            "One set of facts, three policies",
            note_html=C.chip(_describe(filters), "neutral"),
        )
        cohort_value = "withheld" if refused else f"{_i(released['cohort']):,}"
        cohort_sub = (f"a group of {cohort:,} is below the floor of {floor}, "
                      "so nothing at all is released"
                      if refused else "released exactly, to the person")

        error = dp.get("cohort") is None
        dp_value = "unavailable" if error else f"{_i(dp['cohort']):,}"
        dp_sub = ("the privacy engine refused this query shape" if error else
                  f"{_i(dp['cohort']) - cohort:+,} from the truth, and a "
                  "different number every time it is asked")

        C.compare_row(
            {"label": "no policy", "value": f"{cohort:,}", "tone": "truth",
             "sub_html": '<span class="gp-obj">privileged.'
                         'v_beneficiary_outcomes_true</span><br>'
                         "exact, and unreadable by the analyst role"},
            {"label": "aggregation policy", "value": cohort_value,
             "tone": "noise",
             "sub_html": '<span class="gp-obj">serving.'
                         'v_beneficiary_outcomes</span><br>' + cohort_sub},
            {"label": "differential privacy", "value": dp_value, "tone": "dp",
             "sub_html": '<span class="gp-obj">serving.'
                         'v_beneficiary_dp</span><br>' + dp_sub},
        )

        if refused:
            C.verdict(
                f"The floor refuses. The budget answers, and the answer is "
                f"worth nothing",
                f"A group of {cohort:,} is below the floor of {floor}, so the "
                "aggregation policy releases nothing at all for "
                f"{_describe(filters)}: not a rounded figure, not a noisy "
                "one, not a smaller aggregate. Nothing. The privacy policy "
                "never refuses, and at this cohort size the noise is larger "
                "than the number, so what comes back is an answer in shape "
                "only. Both are protecting the same people. Only one of them "
                "tells you that it is.",
                "right",
            )
        else:
            C.verdict(
                "Above the floor the two guarantees diverge completely",
                f"A group of {cohort:,} clears the floor, so the aggregation "
                "policy hands back the true value to the person. That is "
                "convenient, and it is exactly what leaves the differencing "
                "attack below open: an exact answer can be subtracted from "
                "another exact answer. The budget will not give you an exact "
                "anything, ever, which costs you precision on every honest "
                "question in order to cost an attacker their arithmetic.",
                "neutral",
            )

        C.source_note(
            "Three objects over identical facts in MARTS.BENEFICIARY_FACTS, "
            "differing only in the policy attached. The two protected reads "
            "run as GP_ANALYST with USE SECONDARY ROLES NONE, because "
            "switching primary role is not enough: users default to "
            "DEFAULT_SECONDARY_ROLES ALL, which keeps ACCOUNTADMIN active "
            "underneath and would quietly exempt the query from the policy "
            "it is meant to be testing."
        )

    if dp.get("simulated"):
        C.source_note(
            "Preview mode. The differential privacy column is drawn locally "
            "from a Laplace distribution shaped to the standard deviation "
            "measured in the warehouse, not returned by Snowflake. In the "
            "deployed build it is a real query against a real privacy policy."
        )
    return dp


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
    n_district = landscape[landscape["filters_applied"] == 1]

    with C.panel():
        C.panel_head("Where the wall falls",
                     "privileged.v_beneficiary_outcomes_true")
        C.note(
            f"Three filters over the corpus make <b>{total:,}</b> distinct "
            "questions. Every one of them is a dot, at the number of people "
            "actually behind it. The line is the floor, and everything left "
            "of it is a question this tool will not answer, however it is "
            "phrased."
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
            f"{_i(deepest['people'].max()):,} people against a floor of "
            f"{floor}. That is a stronger statement than any single refusal: "
            "on this data, a question specific enough to locate somebody is "
            "a question that cannot be asked at all.",
            "right",
        )
        C.source_note(
            "Eight GROUPING SETS in one statement. GROUPING() returns 1 for "
            "a column the set aggregated away, so three minus the sum of the "
            "three is how many filters that question applies. It reads the "
            "privileged twin, and it has to: the point is to show the "
            "refused questions beside the permitted ones, and a protected "
            "view cannot report a refused question by construction. The SQL "
            "is Q_COHORT_LANDSCAPE in app/queries.py."
        )

    with C.panel():
        C.panel_head("The same questions, counted", "how narrowing collapses")
        st.plotly_chart(
            charts.narrowing_ladder(landscape, floor, height=252),
            use_container_width=True, config=charts.bare_config(),
        )
        C.source_note(
            f"One filter and half of it is answerable. Two and most of it is "
            f"not. Three and none of it is. The collapse is a cliff rather "
            f"than a slope, which is what a floor does, and where the cliff "
            f"falls is a property of the corpus rather than of the policy. "
            f"The single-filter row is {int((n_district['people'] >= floor).sum())} "
            f"answerable of {len(n_district):,}."
        )


# ---------------------------------------------------------------------------
# S5 / why the floor has to be blunt
# ---------------------------------------------------------------------------


def _frontier(floor: int) -> None:
    C.section("Why the floor has to be this blunt")
    cells = data.qi_cells()
    profile = data.qi_profile()
    if cells.empty or not profile:
        C.note("No microdata profile available.")
        return

    with C.panel():
        C.panel_head("The re-identification frontier",
                     "k-anonymity, measured rather than asserted")
        C.note(
            "District, programme and month name nobody on their own. Put the "
            "three together and they are a <b>quasi-identifier</b>: the "
            "combination that lets somebody who knows a little about a "
            "person find their row. This counts how many people share each "
            "combination, which is the k of k-anonymity read off the corpus "
            "rather than promised by a policy."
        )
        st.plotly_chart(
            charts.qi_frontier(cells, floor, height=300),
            use_container_width=True, config=charts.bare_config(),
        )
        C.readout([
            (f"{profile['cells']:,}", "combinations that exist"),
            (f"{profile['singletons']:,}", "holding exactly one person"),
            (f"{profile['median_k']:.0f}", "people in the median combination"),
            (f"{profile['under_floor']:,} of {profile['cells']:,}",
             "below the floor"),
        ], flag="holding exactly one person")
        C.verdict(
            f"{profile['singletons']:,} combinations identify a single person",
            f"The largest combination in the corpus holds "
            f"{profile['max_k']:,} people and the median holds "
            f"{profile['median_k']:.0f}. Against a floor of {floor}, "
            f"{profile['under_floor']:,} of {profile['cells']:,} combinations "
            "sit below it. So the refusal in the section above is not the "
            "policy being cautious with a generous dataset. It is the only "
            "available behaviour on a sparse one: a guarantee that answered "
            "these questions would, two hundred times over, be answering "
            "about one person by name.",
            "right",
        )
        C.source_note(
            "Counted over the privileged twin, for the same reason as the "
            "landscape: a cell of one is precisely what a protected view "
            "will not report. The bars are truncated on the right so the "
            "shape near the floor stays legible; the readout is over every "
            "cell. Q_QI_CELLS in app/queries.py."
        )


# ---------------------------------------------------------------------------
# S6 / what the floor does not stop
# ---------------------------------------------------------------------------


def _differencing(floor: int) -> pd.DataFrame:
    C.section("What the floor does not stop")
    leaks = data.differencing_sweep()
    if leaks.empty:
        C.note("No pair of permitted questions in this corpus isolates a "
               "group below the floor.")
        return leaks

    worst = leaks.iloc[0]
    with C.panel():
        C.panel_head(
            "Two permitted questions, subtracted",
            note_html=C.chip("a cohort floor does not prevent this", "flagged"),
        )
        C.note(
            "Both questions below are about <b>" + str(worst["scope"]) +
            f"</b>, both clear the floor of {floor}, and the policy answers "
            "both of them exactly. Ask them one after the other and subtract."
        )
        C.kv_rows([
            ("everyone in scope", f"{_i(worst['everyone']):,} people"),
            (f"those receiving at least "
             f"{C.usd(_f(worst['threshold']), precise=True)}",
             f"{_i(worst['received_something']):,} people"),
            ("the difference",
             f"{_i(worst['learned_about'])} people, who received nothing"),
        ])
        st.plotly_chart(
            charts.differencing_leaks(leaks, floor, height=max(
                300, 24 * len(leaks) + 90)),
            use_container_width=True, config=charts.bare_config(),
        )
        C.readout([
            (f"{len(leaks):,}", "scopes where the attack lands"),
            (f"{_i(leaks['learned_about'].min())}",
             "people in the smallest group exposed"),
            (f"{_i(leaks['learned_about'].max())}", "in the largest"),
            ("0", "queries the policy refused"),
        ], flag="scopes where the attack lands")
        C.verdict(
            f"You have just learned about {_i(worst['learned_about'])} people "
            "without asking about them",
            f"That group is smaller than the floor of {floor}, so it could "
            "never have been asked about directly, and it was not. It fell "
            "out of subtracting two answers the policy was happy to give, "
            "and nothing in this deployment noticed or could have noticed. "
            "Note what you now know about them: not a total, but that they "
            "exist, how many they are, where they are, and that they "
            "received nothing at all. A cohort floor protects a group by "
            "refusing to describe it. It has no answer for a group that is "
            "never described, only inferred.",
            "wrong",
        )
        C.source_note(
            "Every row is one scope at the threshold that isolates its "
            "smallest group. The gap scales with the size of the scope, so "
            "it sits far above the floor across the whole corpus and below "
            "it inside a single district: narrowing the question is supposed "
            "to be the thing the floor stops, and here it is the thing that "
            "makes the attack work. The ladder starts at one dollar because "
            "that is the boundary between having been helped and not having "
            "been, which is the group an attacker would want."
        )
    return leaks


# ---------------------------------------------------------------------------
# S7 / the same attack, under the budget
# ---------------------------------------------------------------------------


def _under_budget(leaks: pd.DataFrame, floor: int) -> None:
    C.section("The same attack, under the budget")
    if leaks.empty:
        return

    worst = leaks.iloc[0]
    scope = str(worst["scope"])
    gap = _f(worst["learned_about"])
    sd = data.DP_MEASURED_SD
    # Measured over thirty runs of the pair against the warehouse rather
    # than composed from the single-query figure. Textbook composition
    # would give 13.2; the observed spread is wider, and using the wider
    # number moves the conclusion against this build rather than for it.
    sd_diff = data.DP_MEASURED_PAIR_SD
    # Averaging n trials divides the standard error by root n, so
    # resolving the gap to within a person needs n above sd_diff squared.
    trials_needed = int(round(sd_diff ** 2))
    queries_needed = trials_needed * 2
    epsilon_needed = queries_needed * data.DP_EPSILON
    queries_allowed = int(data.DP_BUDGET_LIMIT / data.DP_EPSILON)

    with C.panel():
        C.panel_head("Signal against noise",
                     f"the {int(gap)}-person group in {scope}")
        C.note(
            f"The group the floor leaks is <b>{int(gap)} people</b>. The "
            "noise on a single answer from the privacy policy has a standard "
            f"deviation of <b>{sd:.1f} people</b>, measured over twenty-five "
            "repeats of the unfiltered count against the warehouse. The "
            "attack subtracts two answers, so it carries both draws, and "
            "thirty runs of the pair measured <b>"
            f"{sd_diff:.1f}</b>. The thing being estimated is smaller than "
            "the error bar on the estimate, and in four of those thirty runs "
            "the attack recovered a negative number of people."
        )
        run_it = st.button("run the attack through the budget",
                           key="gp_w_attack", type="primary")
        if run_it:
            st.session_state["gp_w_trials"] = data.dp_attack_trial(
                {"district": scope} if worst["dimension"] == "district"
                else {}, threshold=_f(worst["threshold"]), trials=8)
        trials = st.session_state.get("gp_w_trials")
        if trials is not None and not trials.empty:
            st.plotly_chart(
                charts.dp_attack(trials, gap, height=300),
                use_container_width=True, config=charts.bare_config(),
            )
            recovered = trials["recovered"]
            close = int((recovered - gap).abs().le(2).sum())
            C.readout([
                (f"{recovered.mean():.0f}", "mean recovered"),
                (f"{int(gap)}", "the true answer"),
                (f"{recovered.min():.0f} to {recovered.max():.0f}",
                 "range across trials"),
                (f"{close} of {len(trials)}", "within two people of the truth"),
            ], flag="range across trials")
        else:
            C.note(
                "Press the button. Each trial issues the same two questions "
                "the aggregation policy answered exactly, through the "
                "privacy policy instead, and subtracts them. The floor "
                "returns the same number every time. The budget will not "
                "return the same number twice."
            )

        C.verdict(
            "The budget breaks the attack, and this budget does not break "
            "it far enough",
            f"Averaging trials shrinks the error by the square root of the "
            f"count, so recovering a {int(gap)}-person group to within one "
            f"person needs roughly <b>{trials_needed:,} trials</b>, which is "
            f"{queries_needed:,} queries and {epsilon_needed:.0f} epsilon. "
            f"The policy deployed here sets BUDGET_LIMIT to "
            f"{data.DP_BUDGET_LIMIT:.0f} at {data.DP_EPSILON} per aggregate, "
            f"which permits {queries_allowed:,}. So a patient attacker "
            "finishes with budget to spare. Noise alone does not stop "
            "repetition; a limit set below the cost of the attack is what "
            "stops it, and the limit in sql/11b_differential_privacy.sql is "
            f"set above it. Anything under about {epsilon_needed:.0f} would "
            "close it, at the price of the honest analyst running out too.",
            "wrong",
        )
        C.source_note(
            "The composition arithmetic assumes independent noise on every "
            "query, which is the worst case for the defender and the right "
            "assumption to design against. A deployment that returned a "
            "cached answer to an identical repeated query would raise the "
            "attack's cost without changing the epsilon accounting. Snowflake "
            "does not publish its exact calibration, so the standard "
            "deviation here is reported as a measurement and never "
            "back-solved into a claimed epsilon."
        )


# ---------------------------------------------------------------------------
# S8 / the syntax error
# ---------------------------------------------------------------------------


def _syntax_error() -> None:
    C.section("The limitation that was a syntax error")
    with C.panel():
        C.panel_head("What was recorded, and what was true",
                     "docs/platform_constraints.md")
        C.note(
            "This tab shipped for a weekend without its third column, on the "
            "recorded finding that differential privacy was absent from this "
            "deployment. That finding rested on two statements, and both of "
            "them were malformed."
        )
        C.table(
            [("what was run", "gp-td-lead"),
             ("what came back", ""),
             ("what was actually wrong", "")],
            [
                ["CREATE PRIVACY BUDGET ...",
                 "syntax error at position 26 unexpected 'BUDGET'",
                 "There is no such statement. A budget is created by being "
                 "named inside a privacy policy body."],
                ["ALTER VIEW ... SET PRIVACY POLICY",
                 "syntax error at position 36 unexpected 'PRIVACY'",
                 "The clause is ADD PRIVACY POLICY. Replacing one is DROP "
                 "then ADD inside a single ALTER."],
                ["MODIFY COLUMN ... SET PRIVACY DOMAIN (0, 5000)",
                 "syntax error, unexpected '('",
                 "Ranges are SET PRIVACY DOMAIN BETWEEN (0, 5000); lists are "
                 "SET PRIVACY DOMAIN IN ('a', 'b'). Neither accepts a "
                 "subquery."],
            ],
            widths=["30%", "30%", "40%"],
        )
        C.verdict(
            "A parser error says a statement is malformed, not that a "
            "feature is missing",
            "docs/platform_constraints.md opens by boasting that every claim "
            "in it comes from running the statement rather than reading the "
            "documentation. That is exactly backwards. Running a statement "
            "tells you what that statement does. Only the documentation "
            "tells you whether it was the right statement. Two of that "
            "file's ten findings rested on this error; the other eight are "
            "capability messages rather than syntax errors, and those stand.",
            "wrong",
        )
        C.sql_block(
            "CREATE OR REPLACE PRIVACY POLICY SERVING.beneficiary_dp_policy\n"
            "  AS () RETURNS PRIVACY_BUDGET ->\n"
            "  PRIVACY_BUDGET(BUDGET_NAME              => 'gp_analysts',\n"
            "                 BUDGET_LIMIT             => 300,\n"
            "                 MAX_BUDGET_PER_AGGREGATE => 0.1);\n\n"
            "ALTER VIEW SERVING.V_BENEFICIARY_DP\n"
            "  ADD PRIVACY POLICY SERVING.beneficiary_dp_policy\n"
            "  ENTITY KEY (beneficiary_id);",
            "the same intent, in syntax that exists",
        )
        C.source_note(
            "Getting the policy attached was the easy half. Getting a query "
            "past it took three more refusals: 510242 until every column "
            "carried a privacy domain, 210007 until the query itself "
            "deduplicated on the entity key, and a separate refusal on "
            "GROUP BY over an unbounded key. The surviving query shape is "
            "COUNT(DISTINCT beneficiary_id) with filters, which is exactly "
            "the question this tab exists to ask. Every constraint is "
            "written up in sql/11b_differential_privacy.sql."
        )


# ---------------------------------------------------------------------------
# S9 / the log
# ---------------------------------------------------------------------------


def _log(ledger: data.PrivacyLedger, floor: int) -> None:
    C.section("Query log")
    with C.panel():
        C.panel_head("Every question asked this session",
                     "the same list, read two ways")
        log = ledger.log()
        if log.empty:
            C.note("Nothing asked yet.")
        else:
            st.plotly_chart(charts.query_log(log, floor),
                            use_container_width=True,
                            config=charts.bare_config())
            spent = ledger.epsilon_spent
            C.readout([
                (f"{ledger.asked:,}", "asked"),
                (f"{ledger.refused:,}", "refused by the floor"),
                ("none", "budget the floor draws down"),
                (f"{spent:.1f} of {data.DP_BUDGET_LIMIT:.0f}",
                 "epsilon the budget would have"),
            ])
        C.source_note(
            "Under the aggregation policy this list is a log and nothing "
            "more: a refused query costs an attacker a retry and a permitted "
            "one costs nothing at all, so the count never limits anything. "
            "Under the privacy policy the same list is an account, because "
            "Snowflake charges epsilon for every aggregate whether or not "
            "the answer was useful. That difference is the whole of what a "
            "budget buys."
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
           "people: the smallest group the cohort floor will answer about")
    C.note(
        "Everything so far has been this system finding things. This is the "
        "one place it refuses &mdash; and then shows you exactly where each "
        "refusal stops working."
    )

    mechanisms = data.run("Q_PRIVACY_MECHANISMS")
    if not mechanisms.empty:
        with C.panel():
            C.panel_head("Three regimes over one set of facts",
                         "serving.v_privacy_mechanisms")
            C.table(
                [("object", "gp-td-lead"), ("mechanism", ""),
                 ("what it guarantees", "")],
                [[str(r["object_name"]).lower(), str(r["label"]),
                  str(r["note"])] for _, r in mechanisms.iterrows()],
                widths=["28%", "18%", "54%"],
            )
            C.source_note(
                "Read from the warehouse rather than written into the "
                "interface, so a policy detached in Snowflake cannot keep "
                "being described here."
            )

    # ---------------------------------------------------------------- S2
    filters, truth = _question(floor)

    # ---------------------------------------------------------------- S3
    _three_answers(filters, truth, floor, ledger)

    # ---------------------------------------------------------------- S4
    _landscape(floor, truth["cohort"])

    # ---------------------------------------------------------------- S5
    _frontier(floor)

    # ---------------------------------------------------------------- S6
    leaks = _differencing(floor)

    # ---------------------------------------------------------------- S7
    _under_budget(leaks, floor)

    # ---------------------------------------------------------------- S8
    _syntax_error()

    # ---------------------------------------------------------------- S9
    _log(ledger, floor)

    if data.is_preview():
        C.source_note(
            "Preview mode. Both guarantees are applied in Python here. In "
            "the deployed build the floor is an aggregation policy on "
            "SERVING.V_BENEFICIARY_OUTCOMES with an entity key on "
            "beneficiary_id, and the noise is a privacy policy on "
            "SERVING.V_BENEFICIARY_DP with a budget; Snowflake does both. "
            "The floor's refusal arrives as a NULL aggregate rather than as "
            "an error, which is the same withholding wearing different "
            "clothes and is handled as a refusal rather than read as a zero."
        )

    # --------------------------------------------------------------- S10
    C.section("What each guarantee costs")
    C.step_explainer([
        (
            "What the cohort floor gives you",
            f"No aggregate over fewer than {floor} beneficiaries, counted as "
            "distinct people rather than rows, enforced by Snowflake on the "
            "object. Changing the query, the tool or the client does not get "
            "around it. Above the floor, the true value to the cent.",
        ),
        (
            "What the cohort floor costs you",
            "It adds no noise, so released answers are exact and can be "
            "subtracted from each other. It has no budget, so asking is "
            "free. Sixteen districts in this corpus leak a group below the "
            "floor to two questions it answers happily.",
        ),
        (
            "What the budget gives you",
            "Noise calibrated per query from the declared privacy domains, "
            "and a charge in epsilon for every aggregate whether or not it "
            "was useful. It never refuses, so it never confirms that a group "
            "is small, and it makes repetition cost something.",
        ),
        (
            "What the budget costs you",
            "Every honest answer is wrong by a little, and small groups are "
            "wrong by more than they are large. A cohort of four comes back "
            "as anything between zero and thirty. And the limit has to be "
            "set below the cost of the attack you are defending against, "
            "which the section above shows this one is not.",
        ),
        (
            "Why both are on screen at once",
            "They are not alternatives on a scale from weak to strong. They "
            "fail in opposite directions: one is honest about refusing and "
            "exact when it answers, the other never refuses and is never "
            "exact. Showing one without the other is how a build ends up "
            "claiming a guarantee it does not have.",
        ),
    ])

    C.provenance_footer(
        "Entirely synthetic beneficiary records. No real personal data enters "
        "this project at any point, which is itself the correct engineering "
        "decision. The protected objects are SERVING.V_BENEFICIARY_OUTCOMES "
        "under an aggregation policy and SERVING.V_BENEFICIARY_DP under a "
        "privacy policy, both with an entity key on beneficiary_id. The true "
        "column reads the unprotected twin under a privileged role, and all "
        "three are labelled on screen. Cohorts are counted as distinct "
        "beneficiaries throughout, because the privacy engine refuses to "
        "count anything else."
    )
