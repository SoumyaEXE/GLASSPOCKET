"""Tab 07 / The Historian. Build Spec Section 07.

    Change a verdict. The warehouse still remembers what it was.

The warehouse-side counterpart to the on-chain receipt: an operator can
alter the present, but not the record of the past.

LIMITS, STATED PLAINLY
    Retention is finite and is controlled by the account owner. The chain
    is not. Saying so strengthens the argument for the chain rather than
    weakening it.
"""

from __future__ import annotations

import time

import streamlit as st

import charts
import components as C
import data

OFFSETS = (60, 120, 300, 600, 1800, 3600)


def render() -> None:
    C.tab_title(
        "The Historian",
        "Change a verdict. The warehouse still remembers what it was.",
    )

    retention = data.scalar("Q_RETENTION", "retention_days", default=90)

    # ---------------------------------------------------------------- S1
    C.hero(f"{int(retention)} days", "of Time Travel retention available on this account")

    # ---------------------------------------------------------------- S2
    C.section("Rewrite the record")
    st.markdown(
        C.chip("demo mode only. a production deployment would not expose this.",
               "seeded"),
        unsafe_allow_html=True,
    )

    pairs = data.run("Q_CONFIDENCE_PAIRS")
    if pairs.empty:
        st.warning("No scored organisations available.")
        return

    options = pairs[["suspect_id", "suspect_name"]].drop_duplicates().head(60)
    labels = dict(zip(options["suspect_id"], options["suspect_name"]))

    c1, c2, c3 = st.columns([3, 1, 1], gap="small")
    with c1:
        org_id = st.selectbox(
            "organisation", options["suspect_id"].tolist(),
            format_func=lambda oid: labels.get(oid, oid),
            key="gp_h_org",
        )
    with c2:
        new_score = st.number_input("new score", min_value=0, max_value=100,
                                    value=42, key="gp_h_score")
    with c3:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        applied = st.button("apply", key="gp_h_apply", use_container_width=True)

    current = data.run("Q_ORG_RISK_ONE", (org_id,))
    if current.empty:
        st.warning("No score for that organisation.")
        return
    row = current.iloc[0]
    original_score = float(row["risk_score"])
    original_verdict = str(row["verdict"])

    log = st.session_state.setdefault("gp_edit_log", {})

    if applied:
        verdict = "needs a second look" if new_score >= 55 else "verified"
        log.setdefault(org_id, []).append({
            "at": int(time.time()) % 3600,
            "score": float(new_score),
            "verdict": verdict,
            "by": "ACCOUNTADMIN",
            "from_score": original_score,
        })
        if not data.is_preview():
            data.run("Q_APPLY_CHANGE", (float(new_score), verdict, org_id))
        st.rerun()

    edits = log.get(org_id, [])
    shown_score = edits[-1]["score"] if edits else original_score
    shown_verdict = edits[-1]["verdict"] if edits else original_verdict

    # ---------------------------------------------------------------- S3
    C.section("As it stands now, and as it stood before")
    C.compare_columns(
        {
            "label": "as it stands now",
            "value": f"{shown_score:.0f}",
            "sub": f"verdict {shown_verdict}"
                   + (" · changed by ACCOUNTADMIN" if edits else ""),
        },
        {
            "label": "as it stood five minutes ago",
            "value": f"{original_score:.0f}",
            "sub": f"verdict {original_verdict} · AT(OFFSET => -300)",
        },
        left_tone="truth", right_tone="noise",
    )
    C.source_note(
        "The right-hand column is not a copy this application kept. It is the "
        "same row, read as it existed at an earlier moment, straight out of "
        "the warehouse's own retention."
    )

    # ---------------------------------------------------------------- S4
    C.section("Value history")
    history = data.value_history(org_id, OFFSETS)
    if history.empty:
        st.markdown('<div class="gp-source">No history for this row yet. '
                    'Apply a change above.</div>', unsafe_allow_html=True)
    else:
        st.plotly_chart(charts.value_history(history),
                        use_container_width=True, config=charts.bare_config())
        C.source_note(
            "Built by querying successive Time Travel offsets and unioning the "
            "results. No additional storage is required, because this is "
            "Snowflake's own retention rather than an audit table we maintain."
        )

    # ------------------------------------------------------------ S5, S6
    lcol, rcol = st.columns(2, gap="medium")

    with lcol:
        C.section("Change log")
        if not edits:
            st.markdown('<div class="gp-source">No changes this session.</div>',
                        unsafe_allow_html=True)
        else:
            import pandas as pd
            st.dataframe(
                pd.DataFrame([{
                    "who": e["by"],
                    "from": f"{e['from_score']:.0f}",
                    "to": f"{e['score']:.0f}",
                    "verdict": e["verdict"],
                } for e in edits]),
                use_container_width=True, hide_index=True,
            )

    with rcol:
        C.section("Two kinds of memory")
        C.step_explainer([
            ("The warehouse remembers",
             "Every row carries its own history for the retention window. An "
             "operator can change today's answer, but the earlier answer is "
             "still readable and still theirs to explain."),
            ("The chain cannot forget",
             "A receipt is not held by us at all. It survives this "
             "application, this account, and this operator, which is a "
             "different and stronger property."),
        ])

    # ---------------------------------------------------------------- S7
    C.source_note(
        "Limits: retention is finite and is controlled by the account owner. "
        f"This account holds {int(retention)} days. The chain is not "
        "controlled by the account owner, which is exactly why both belong in "
        "this design."
    )

    if data.is_preview():
        C.source_note(
            "Preview mode. The history above replays a local edit log. In the "
            "deployed build each point is a separate "
            "MARTS.ORG_RISK AT(OFFSET => -n) query against Snowflake's own "
            "retention."
        )

    C.provenance_footer(
        "MARTS.ORG_RISK queried with AT(OFFSET) at a series of negative second "
        "offsets. No additional storage required, since this is Snowflake "
        "internal retention."
    )
