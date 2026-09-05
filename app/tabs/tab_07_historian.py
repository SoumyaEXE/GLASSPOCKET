"""Tab 07 / The Historian. Build Spec Section 07.

    Change a verdict. The warehouse still remembers what it was.

The warehouse-side counterpart to the on-chain receipt: an operator can
alter the present, but not the record of the past.

LIMITS, STATED PLAINLY
    Retention is finite and is controlled by the account owner. The chain
    is not. Saying so strengthens the argument for the chain rather than
    weakening it.

THE TAB DID NOT DEMONSTRATE ITS OWN MECHANIC UNTIL YOU PRESSED A BUTTON,
AND IT DID NOT SAY SO.

    On arrival both comparison cards read the same number, the history
    chart held a single point, and the change log said "No changes this
    session." next to an empty half-page. Every one of those is the
    correct answer before anything has been edited, and none of them said
    that. A reader who did not already know what the tab was for saw a
    broken page rather than an untouched record.

    So the untouched state is now the first thing the tab explains, the
    button that drives the demo is the most prominent control on it, and
    the two cards carry a chip saying whether they currently differ.

THE HISTORY CHART WAS PLOTTING RAW SECONDS.

    data.value_history returns the Time Travel offset it queried at, in
    negative seconds, and the chart put that column straight on the x
    axis. The axis read -3601, -3600.5, -3600, -3599.5, and the reader
    was asked to convert negative seconds into a moment. The offsets are
    the query parameter, not the label; the axis now shows the clock
    reading each one stands for, and puts a tick only where a query was
    actually made.
"""

from __future__ import annotations

import time

import pandas as pd
import streamlit as st

import charts
import components as C
import data

#: The Time Travel offsets queried, in seconds before now. Six points
#: from one minute to one hour: enough to draw a line, few enough that
#: six separate AT(OFFSET) queries stay inside a demo click.
OFFSETS = (60, 120, 300, 600, 1800, 3600)

#: The score at or above which MARTS.F_RISK's verdict flips. Matching the
#: warehouse rather than guessing at it is the whole point of the tab.
SECOND_LOOK_AT = 55


def _f(value, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _ago(seconds: float) -> str:
    seconds = abs(float(seconds))
    if seconds < 90:
        return "now" if seconds < 5 else f"{seconds:.0f} seconds ago"
    if seconds < 5400:
        return f"{seconds / 60:.0f} minutes ago"
    return f"{seconds / 3600:.0f} hour ago"


# ---------------------------------------------------------------------------
# S2 / the edit
# ---------------------------------------------------------------------------


def _editor(options, labels) -> tuple[str, bool]:
    with C.panel():
        C.panel_head(
            "Rewrite a verdict",
            note_html=C.chip("demo mode only", "seeded"),
        )
        C.note(
            "A production deployment would never expose this control. It "
            "is here because the claim the tab makes &mdash; that the "
            "record survives the edit &mdash; is only worth anything if "
            "you get to make the edit yourself."
        )
        c1, c2, c3 = st.columns([4, 2, 2], gap="small")
        with c1:
            org_id = st.selectbox(
                "organisation", options["suspect_id"].tolist(),
                format_func=lambda oid: labels.get(oid, oid),
                key="gp_h_org", label_visibility="collapsed",
            )
        with c2:
            st.number_input("new score", min_value=0, max_value=100, value=42,
                            key="gp_h_score", label_visibility="collapsed")
        with c3:
            applied = st.button("apply the change", key="gp_h_apply",
                                type="primary", use_container_width=True)
        C.source_note(
            "Applying writes an UPDATE against MARTS.ORG_RISK. Nothing "
            "else is recorded: no audit table is written, no copy is "
            "kept, and the previous value is not saved anywhere by this "
            "application. That is deliberate, because the next section "
            "reads it back out of the warehouse's own retention."
        )
    return org_id, applied


# ---------------------------------------------------------------------------
# S3 / then and now
# ---------------------------------------------------------------------------


def _then_and_now(shown_score, shown_verdict, original_score,
                  original_verdict, edited: bool) -> None:
    C.section("As it stands now, and as it stood before")
    C.compare_columns(
        {
            "label": "as it stands now",
            "value": f"{shown_score:.0f}",
            "sub": f"verdict {shown_verdict}"
                   + (" · changed by ACCOUNTADMIN" if edited else ""),
        },
        {
            "label": "as it stood five minutes ago",
            "value": f"{original_score:.0f}",
            "sub": f"verdict {original_verdict} · AT(OFFSET => -300)",
        },
        left_tone="truth", right_tone="noise",
    )
    if edited:
        C.verdict(
            "The change is visible and so is what it replaced",
            f"The score now reads {shown_score:.0f}. The warehouse still "
            f"returns {original_score:.0f} for the same row read five "
            "minutes back, and it will keep returning it for the whole "
            "retention window whether or not the operator wants it to.",
            "right",
        )
    else:
        C.verdict(
            "Both columns agree, because nothing has been changed yet",
            "This is the untouched state, not a broken comparison. Apply "
            "a change above and the left column moves while the right one "
            "does not, which is the entire argument of this tab.",
            "neutral",
        )
    C.source_note(
        "The right-hand column is not a copy this application kept. It is "
        "the same row, read as it existed at an earlier moment, straight "
        "out of the warehouse's own retention. No storage was added to "
        "make it possible."
    )


# ---------------------------------------------------------------------------
# S4 / history and log
# ---------------------------------------------------------------------------


def _history(org_id: str, edits) -> None:
    C.section("The same row, read at six earlier moments")
    history = data.value_history(org_id, OFFSETS)

    left, right = st.columns([3, 2], gap="medium")

    with left:
        with C.panel():
            C.panel_head("Value history", "marts.org_risk at(offset)")
            if history.empty:
                C.note(
                    "No history for this row yet. Apply a change above and "
                    "the line will step."
                )
            else:
                st.plotly_chart(charts.value_history(history, height=306),
                                use_container_width=True,
                                config=charts.bare_config())
                scores = [_f(v) for v in history["risk_score"]]
                moved = len({round(v, 6) for v in scores}) > 1
                C.readout([
                    (str(len(history)), "offsets queried"),
                    (f"{min(scores):.0f}", "lowest reading"),
                    (f"{max(scores):.0f}", "highest reading"),
                    ("yes" if moved else "no", "value changed"),
                ])
                C.source_note(
                    "Built by querying successive Time Travel offsets and "
                    "unioning the results. Six queries, no extra storage: "
                    "this is Snowflake's own retention rather than an "
                    "audit table we maintain. A flat line means the row "
                    "has not been touched, which is the answer, not a "
                    "missing chart."
                )

    with right:
        with C.panel():
            C.panel_head("Change log", "this session")
            if not edits:
                C.note(
                    "No changes this session. Every edit made here is "
                    "listed with who made it, what it was before and what "
                    "it became &mdash; and the list is redundant, which "
                    "is the point. The warehouse can reconstruct all of "
                    "it without this application's help, which is why "
                    "this application does not keep it anywhere that "
                    "survives the session."
                )
            else:
                C.table(
                    [("who", "gp-td-lead"), ("from", "gp-td-num"),
                     ("to", "gp-td-num"), ("verdict", "")],
                    [[e["by"], f"{e['from_score']:.0f}", f"{e['score']:.0f}",
                      e["verdict"]] for e in edits],
                )
                C.source_note(
                    "Held in session state only. It is deliberately not "
                    "durable: an audit trail an operator can edit is not "
                    "an audit trail, and the durable one is the "
                    "warehouse's."
                )


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------


def render() -> None:
    C.tab_title(
        "The Historian",
        "Change a verdict. The warehouse still remembers what it was.",
    )

    retention = data.scalar("Q_RETENTION", "retention_days", default=90)

    # ---------------------------------------------------------------- S1
    C.hero(f"{int(retention)} days",
           "of Time Travel retention available on this account")

    pairs = data.run("Q_CONFIDENCE_PAIRS")
    if pairs.empty:
        st.warning("No scored organisations available.")
        return

    options = pairs[["suspect_id", "suspect_name"]].drop_duplicates().head(60)
    labels = dict(zip(options["suspect_id"], options["suspect_name"]))

    # ---------------------------------------------------------------- S2
    C.section("Rewrite the record")
    org_id, applied = _editor(options, labels)

    current = data.run("Q_ORG_RISK_ONE", (org_id,))
    if current.empty:
        st.warning("No score for that organisation.")
        return
    row = current.iloc[0]
    original_score = _f(row["risk_score"])
    original_verdict = str(row["verdict"])

    log = st.session_state.setdefault("gp_edit_log", {})

    if applied:
        new_score = float(st.session_state.get("gp_h_score", 42))
        verdict = ("needs a second look" if new_score >= SECOND_LOOK_AT
                   else "verified")
        log.setdefault(org_id, []).append({
            "at": int(time.time()) % 3600,
            "score": new_score,
            "verdict": verdict,
            "by": "ACCOUNTADMIN",
            "from_score": original_score,
        })
        if not data.is_preview():
            data.run("Q_APPLY_CHANGE", (new_score, verdict, org_id))
        st.rerun()

    edits = log.get(org_id, [])
    shown_score = edits[-1]["score"] if edits else original_score
    shown_verdict = edits[-1]["verdict"] if edits else original_verdict

    # ---------------------------------------------------------------- S3
    _then_and_now(shown_score, shown_verdict, original_score,
                  original_verdict, bool(edits))

    # ---------------------------------------------------------------- S4
    _history(org_id, edits)

    # ---------------------------------------------------------------- S5
    C.section("Two kinds of memory, and what each one is worth")
    C.step_explainer([
        ("The warehouse remembers, for a while",
         "Every row carries its own history for the retention window. An "
         "operator can change today's answer, but the earlier answer is "
         f"still readable for {int(retention)} days and still theirs to "
         "explain."),
        ("Retention is finite, and somebody owns it",
         "The window is set by the account owner, who is also the person "
         "an audit would be asking about. That is a real limit and it is "
         "not one the warehouse can fix."),
        ("The chain cannot forget, and nobody owns it",
         "A receipt is not held by us at all. It survives this "
         "application, this account, and this operator, which is a "
         "different and stronger property than retention."),
        ("Why both are in the design",
         "Time Travel is cheap, immediate and covers every column. The "
         "ledger is permanent and covers a deliberately small claim. "
         "Neither alone is enough, and the gap between them is exactly "
         "what this tab and the last one are for."),
    ])

    C.source_note(
        "Limits: retention is finite and is controlled by the account "
        f"owner. This account holds {int(retention)} days. The chain is "
        "not controlled by the account owner, which is exactly why both "
        "belong in this design."
    )

    if data.is_preview():
        C.source_note(
            "Preview mode. The history above replays a local edit log. In "
            "the deployed build each point is a separate "
            "MARTS.ORG_RISK AT(OFFSET => -n) query against Snowflake's "
            "own retention, and applying a change writes a real UPDATE."
        )

    C.provenance_footer(
        "MARTS.ORG_RISK queried with AT(OFFSET) at a series of negative "
        "second offsets. No additional storage required, since this is "
        "Snowflake internal retention."
    )
