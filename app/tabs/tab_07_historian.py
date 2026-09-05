"""The Historian. Build Spec Section 07.

    Change a verdict. The warehouse still remembers what it was.

The warehouse-side counterpart to the on-chain receipt: an operator can
alter the present, but not the record of the past.

LIMITS, STATED PLAINLY
    Retention is finite and is controlled by the account owner. The chain
    is not. Saying so strengthens the argument for the chain rather than
    weakening it.

WHAT THE TAB WAS MISSING, AND IT WAS NOT STYLING.

    It had one chart, four figures and a lot of prose. Every number it
    showed was the score, and the score is one column of a row that
    carries twenty-two. MARTS.ORG_RISK already holds the five components
    that add up to the score, the similarity and evasion measurements
    underneath them, the technique that generated the imitation, and the
    timestamp the pipeline last computed the row. None of it was on
    screen, so a reader had no way to tell what they were about to
    overwrite or what the number they were overwriting was made of.

    So the row itself is now the second section: identity, verdict,
    provenance, and the waterfall that reconstructs the score from its
    own parts. The editor previews the verdict the new score would carry
    before anything is written. And the reconciliation section is new.

THE RECONCILIATION SECTION IS THE ARGUMENT, MEASURED.

    MARTS.F_RISK is decomposable, so the five component columns sum to
    the score. The demo control writes risk_score and verdict and leaves
    the components alone, because that is what an UPDATE against two
    columns does. A row whose components no longer reconstruct its own
    total is therefore a row somebody has overwritten by hand, and the
    warehouse can list those rows without anybody having kept a log.

    That is not hypothetical. A demo click during development left
    ORG_982257031, a seeded imitation, reading 43 and "verified" against
    components summing to 62.5, and it sat in the shipped corpus until
    acceptance check DAT-02 caught it in exactly this way.

TWO ALIGNMENT BUGS FIXED IN components.py AND theme.py RATHER THAN HERE.

    compare_columns drew its two cards in Streamlit columns, and
    .gp-compare asks for height: 100%, which inside a column resolves
    against auto. Two captions of different lengths gave two cards of
    different heights on a ragged baseline. It is one CSS grid now.

    .gp-verdict had no top margin, so a callout placed under those cards
    put its own top border directly on their bottom border and the two
    read as a single broken box.
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

#: The score at or above which MARTS.F_RISK's verdict flips, from
#: sql/09_risk_score_udf.sql. Matching the warehouse rather than guessing
#: at it is the whole point of the tab.
SECOND_LOOK_AT = 55

#: The five component columns, in the order the UDF adds them, with the
#: names they carry on the Give With Confidence waterfall. One score has
#: one set of labels across the build.
COMPONENTS = (
    ("comp_semantic", "semantic proximity"),
    ("comp_evasion", "evasion gap"),
    ("comp_geometry", "geometry flags"),
    ("comp_unaccounted", "unaccounted ratio"),
    ("comp_receipts", "missing receipts"),
)


def _f(value, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _i(value, default: int = 0) -> int:
    return int(_f(value, default))


def _text(value, default: str = "not recorded") -> str:
    """A string, or a default.

    ``value or default`` is wrong here: a pandas NaN is truthy and comes
    back as the literal "nan" on screen.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    text = str(value).strip()
    return text if text else default


def _when(value) -> str:
    try:
        if value is None or pd.isna(value):
            return "not recorded"
        return pd.to_datetime(value).strftime("%d %B %Y, %H:%M")
    except (TypeError, ValueError):
        return "not recorded"


def _ago(seconds: float) -> str:
    seconds = abs(float(seconds))
    if seconds < 90:
        return "now" if seconds < 5 else f"{seconds:.0f} seconds ago"
    if seconds < 3600:
        return f"{seconds / 60:.0f} minutes ago"
    return f"{seconds / 3600:.0f} hour ago"


def _verdict_for(score: float, is_verified: bool) -> str:
    """The verdict a score implies, following sql/09_risk_score_udf.sql."""
    if score >= SECOND_LOOK_AT:
        return "needs a second look"
    return "verified" if is_verified else "unverified"


# ---------------------------------------------------------------------------
# S2 / the row itself
# ---------------------------------------------------------------------------


def _the_row(row) -> None:
    C.section("The row you are about to change")
    components = {label: _f(row[column]) for column, label in COMPONENTS}
    total = _f(row["risk_score"])
    reconstructed = min(100.0, sum(components.values()))
    drifted = abs(reconstructed - total) > 0.001

    identity, breakdown = st.columns([2, 3], gap="medium")

    with identity:
        with C.panel():
            C.panel_head("Who this is", "marts.org_risk")
            st.markdown(
                f'<div class="gp-card">'
                f'<div class="gp-card-name">{_text(row["name"])}</div>'
                f'<div class="gp-card-meta">{_text(row["cause"])} &middot; '
                f'{_text(row["city"])} &middot; {_text(row["state"])}</div>'
                f"</div>",
                unsafe_allow_html=True,
            )
            C.chips([
                ("seeded imitation", "seeded") if bool(row["is_synthetic"])
                else ("real filing", "verified"),
                (_text(row["verdict"]),
                 "flagged" if str(row["verdict"]) == "needs a second look"
                 else "verified"),
            ])
            C.kv_rows([
                ("EIN", _text(row["ein"])),
                ("technique", _text(row["synth_technique"], "not seeded")),
                ("semantic similarity", f"{_f(row['semantic_sim']):.3f}"),
                ("evasion gap", f"{_f(row['evasion_gap']):.3f}"),
                ("geometry flags", f"{_i(row['geom_flags']):,}"),
                ("unaccounted share", f"{_f(row['unaccounted_ratio']):.1%}"),
                ("missing receipts", f"{_i(row['missing_receipts']):,}"),
                ("last scored by the pipeline", _when(row["scored_at"])),
            ])
            C.source_note(
                "Every field here is a column on the row the button below "
                "writes to. None of it is derived in this application, and "
                "none of it is what the edit changes: an UPDATE against "
                "risk_score and verdict leaves all eight of these alone."
            )

    with breakdown:
        with C.panel():
            C.panel_head("What the score is made of", "marts.f_risk")
            st.plotly_chart(
                charts.risk_waterfall(components, total, height=306),
                use_container_width=True, config=charts.bare_config(),
            )
            C.readout([
                (f"{total:.1f}", "stored score"),
                (f"{reconstructed:.1f}", "components add to"),
                (str(SECOND_LOOK_AT), "second-look line"),
                ("yes" if drifted else "no", "has been hand-edited"),
            ], flag="has been hand-edited" if drifted else None)
            C.source_note(
                "The score is decomposable on purpose. An accountability "
                "tool cannot hand somebody an opaque number, so the five "
                "components are stored beside it and the waterfall "
                "reconstructs the total by eye. That property is also what "
                "makes an edit detectable, which is what the last section "
                "on this tab is about."
            )


# ---------------------------------------------------------------------------
# S3 / the edit
# ---------------------------------------------------------------------------


def _editor(options, labels, row) -> bool:
    C.section("Rewrite the record")
    current = _f(row["risk_score"])
    is_verified = bool(row["is_verified"])

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

        pick, score, act = st.columns([5, 2, 2], gap="medium")
        with pick:
            C.eyebrow("organisation")
            st.selectbox(
                "organisation", options["suspect_id"].tolist(),
                format_func=lambda oid: labels.get(oid, oid),
                key="gp_h_org", label_visibility="collapsed",
            )
        with score:
            C.eyebrow("new risk score")
            st.number_input(
                "new score", min_value=0, max_value=100,
                value=int(round(current)),
                key="gp_h_score", label_visibility="collapsed",
            )
        with act:
            # A real label rather than a blank spacer. The button needs an
            # eyebrow above it to sit on the same line as the two fields,
            # and the first attempt passed "&nbsp;" to get an invisible
            # one, which printed as the literal &NBSP; because eyebrow
            # escapes its text. Saying where the write goes is more use
            # than an empty line anyway.
            C.eyebrow("writes to marts.org_risk")
            applied = st.button("apply the change", key="gp_h_apply",
                                type="primary", use_container_width=True)

        proposed = float(st.session_state.get("gp_h_score", int(round(current))))
        now_verdict = _text(row["verdict"])
        next_verdict = _verdict_for(proposed, is_verified)
        crosses = (proposed >= SECOND_LOOK_AT) != (current >= SECOND_LOOK_AT)

        # The preview sits in the same three columns as the controls, so
        # each figure lands under the field that produces it. A single
        # readout across the full width packs everything against the left
        # edge and leaves the right two thirds of the panel empty, which
        # is what it used to do.
        was, becomes, effect = st.columns([5, 2, 2], gap="medium")
        with was:
            C.readout([
                (f"{current:.0f}", "reads now"),
                (now_verdict, "verdict now"),
            ])
        with becomes:
            C.readout([
                (f"{proposed:.0f}", "would read"),
                (f"{proposed - current:+.0f}", "change"),
            ])
        with effect:
            C.readout([(next_verdict, "verdict after")],
                      flag="verdict after" if crosses else None)

        if crosses:
            C.verdict(
                f"This edit moves the row across the {SECOND_LOOK_AT} line",
                f"It currently reads {now_verdict}. At {proposed:.0f} it "
                f"would read {next_verdict}. That is the whole verdict "
                "flipping on one operator's UPDATE, which is exactly the "
                "thing the next two sections are here to make undeniable.",
                "wrong",
            )
        else:
            C.verdict(
                "This edit does not change the verdict",
                f"Both {current:.0f} and {proposed:.0f} sit on the same "
                f"side of the {SECOND_LOOK_AT} line, so the row would keep "
                f"reading {next_verdict}. Move the score across the line to "
                "see the verdict move with it.",
                "neutral",
            )

        C.source_note(
            "The verdict shown for the proposed score follows "
            "sql/09_risk_score_udf.sql: at or above 55 a row needs a "
            "second look, otherwise it takes whatever its verification "
            "status says. This preview is computed here, but the rule it "
            "applies is the warehouse's, not a second rule invented for "
            "the interface. Applying writes an UPDATE against "
            "MARTS.ORG_RISK. No audit table is written and no copy is "
            "kept, which is deliberate, because the next section reads the "
            "old value back out of the warehouse's own retention."
        )
    return applied


# ---------------------------------------------------------------------------
# S4 / then and now
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
# S5 / history and log
# ---------------------------------------------------------------------------


def _history(org_id: str, edits, row) -> None:
    C.section("The same row, read at six earlier moments")
    history = data.value_history(org_id, OFFSETS)

    with C.panel():
        C.panel_head("Value history", "marts.org_risk at(offset)")
        if history.empty:
            C.note(
                "No history for this row yet. Apply a change above and the "
                "line will step."
            )
        else:
            st.plotly_chart(charts.value_history(history, height=330),
                            use_container_width=True,
                            config=charts.bare_config())
            scores = [_f(v) for v in history["risk_score"]]
            moved = len({round(v, 6) for v in scores}) > 1
            C.readout([
                (str(len(history)), "offsets queried"),
                (f"{min(scores):.0f}", "lowest reading"),
                (f"{max(scores):.0f}", "highest reading"),
                (f"{max(scores) - min(scores):.0f}", "spread"),
                ("yes" if moved else "no", "value changed"),
            ], flag="value changed" if moved else None)
            C.source_note(
                "Six queries, no extra storage: this is Snowflake's own "
                "retention rather than an audit table we maintain. A flat "
                "line means the row has not been touched, which is the "
                "answer rather than a missing chart."
            )

    with C.panel():
        C.panel_head("Change log", "this session")
        if not edits:
            C.note(
                "No changes this session. The row as it currently stands "
                "is below; apply a change above and it will appear here "
                "with who made it, what it was before and what it became."
            )
            C.kv_rows([
                ("organisation", _text(row["name"])),
                ("score", f"{_f(row['risk_score']):.1f}"),
                ("verdict", _text(row["verdict"])),
                ("last scored by the pipeline", _when(row["scored_at"])),
                ("edits this session", "0"),
            ])
        else:
            C.table(
                [("who", "gp-td-lead"), ("from", "gp-td-num"),
                 ("to", "gp-td-num"), ("change", "gp-td-num"),
                 ("verdict after", "")],
                [[e["by"], f"{e['from_score']:.0f}", f"{e['score']:.0f}",
                  f"{e['score'] - e['from_score']:+.0f}", e["verdict"]]
                 for e in edits],
                widths=["26%", "14%", "14%", "14%", "32%"],
            )
            C.readout([
                (str(len(edits)), "edits this session"),
                (f"{edits[-1]['from_score']:.0f}", "started at"),
                (f"{edits[-1]['score']:.0f}", "now reads"),
            ])
        C.source_note(
            "Held in session state only, and deliberately not durable: an "
            "audit trail an operator can edit is not an audit trail. The "
            "durable one is the warehouse's, and the section below shows "
            "that it does not need this list to find the same edits."
        )


# ---------------------------------------------------------------------------
# S6 / reconciliation
# ---------------------------------------------------------------------------


def _reconciliation() -> None:
    C.section("Which rows have been rewritten, with no audit table at all")
    summary = data.run("Q_SCORE_RECONCILIATION")
    if summary.empty:
        C.note("No scored rows.")
        return
    s = summary.iloc[0]
    scored = _i(s["rows_scored"])
    edited = _i(s["hand_edited"])

    with C.panel():
        C.panel_head("The components have to add up", "marts.org_risk")
        C.note(
            "MARTS.F_RISK is decomposable, so the five component columns "
            "sum to the score. The control at the top of this tab writes "
            "<b>risk_score</b> and <b>verdict</b> and leaves the "
            "components alone, because that is what an UPDATE against two "
            "columns does. A row whose components no longer reconstruct "
            "its own total is therefore a row somebody has overwritten by "
            "hand, and the warehouse can name those rows without anybody "
            "having kept a log."
        )
        C.readout([
            (f"{scored:,}", "rows scored"),
            (f"{edited:,}", "components do not reconstruct"),
            (f"{_i(s['seeded_rows']):,}", "seeded rows"),
            (f"{_i(s['second_look']):,}", "need a second look"),
            (_when(s["last_scored_at"]).split(",")[0], "pipeline last ran"),
        ], flag="components do not reconstruct" if edited else None)

        rows = data.run("Q_EDITED_ROWS")
        if rows.empty:
            C.verdict(
                "Every row reconstructs from its own components",
                f"All {scored:,} of them. That is the clean state, and it "
                "is what the corpus ships in. Apply a change above and "
                "this section will find it, without this application "
                "having told it anything.",
                "right",
            )
        else:
            C.table(
                [("organisation", "gp-td-lead"), ("region", ""),
                 ("stored", "gp-td-num"), ("components add to", "gp-td-num"),
                 ("gap", "gp-td-num"), ("verdict", "")],
                [[
                    _text(r.name),
                    _text(r.state),
                    f"{_f(r.stored_score):.1f}",
                    f"{_f(r.reconstructed):.1f}",
                    f"{_f(r.reconstructed) - _f(r.stored_score):+.1f}",
                    _text(r.verdict),
                ] for r in rows.itertuples()],
                widths=["30%", "10%", "13%", "18%", "12%", "17%"],
            )
            C.verdict(
                f"{edited:,} row{'s' if edited != 1 else ''} "
                "no longer reconstructs",
                "Each one has been written to by hand. Nothing recorded "
                "that it happened; the arithmetic simply stopped working, "
                "and the arithmetic is checkable by anybody with read "
                "access to the table.",
                "wrong",
            )
        C.source_note(
            "Acceptance check DAT-02 runs exactly this comparison and "
            "fails the build when it finds a row. It has caught a real "
            "one: a demo click during development left a seeded imitation "
            "reading 43 and verified against components summing to 62.5, "
            "and it sat in the shipped corpus until the check found it."
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

    pairs = data.run("Q_CONFIDENCE_PAIRS")
    if pairs.empty:
        st.warning("No scored organisations available.")
        return
    options = pairs[["suspect_id", "suspect_name"]].drop_duplicates().head(60)
    labels = dict(zip(options["suspect_id"], options["suspect_name"]))

    org_id = st.session_state.get("gp_h_org") or options["suspect_id"].iloc[0]
    current = data.run("Q_ORG_RISK_ONE", (org_id,))
    if current.empty:
        st.warning("No score for that organisation.")
        return
    row = current.iloc[0]
    original_score = _f(row["risk_score"])
    original_verdict = _text(row["verdict"])

    log = st.session_state.setdefault("gp_edit_log", {})
    edits = log.get(org_id, [])
    shown_score = edits[-1]["score"] if edits else original_score
    shown_verdict = edits[-1]["verdict"] if edits else original_verdict

    # ---------------------------------------------------------------- S1
    C.hero(f"{int(retention)} days",
           "of Time Travel retention available on this account")
    C.stat_band([
        (f"{len(OFFSETS)}", "offsets this tab reads"),
        (f"{original_score:.0f}", "the row's score"),
        (original_verdict, "its verdict"),
        (str(len(edits)), "edits this session"),
        ("none", "audit tables kept"),
    ])
    C.source_note(
        "Time Travel is queried, never stored into. Every figure in that "
        "band is read at query time from MARTS.ORG_RISK or from the "
        "account's own retention setting; this application keeps no "
        "history of its own, which is the point it is making."
    )

    # ---------------------------------------------------------------- S2
    _the_row(row)

    # ---------------------------------------------------------------- S3
    applied = _editor(options, labels, row)
    if applied:
        new_score = float(st.session_state.get("gp_h_score", 42))
        verdict = _verdict_for(new_score, bool(row["is_verified"]))
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

    # ---------------------------------------------------------------- S4
    _then_and_now(shown_score, shown_verdict, original_score,
                  original_verdict, bool(edits))

    # ---------------------------------------------------------------- S5
    _history(org_id, edits, row)

    # ---------------------------------------------------------------- S6
    _reconciliation()

    # ---------------------------------------------------------------- S7
    C.section("Two kinds of memory, and what each one is worth")
    C.step_explainer([
        ("The warehouse remembers, for a while",
         "Every row carries its own history for the retention window. An "
         "operator can change today's answer, but the earlier answer is "
         f"still readable for {int(retention)} days and still theirs to "
         "explain."),
        ("The arithmetic remembers too",
         "A decomposable score means an edit leaves a trace even after "
         "retention expires: the components stop adding up to the total, "
         "and that is checkable forever by anybody who can read the "
         "table."),
        ("Retention is finite, and somebody owns it",
         "The window is set by the account owner, who is also the person "
         "an audit would be asking about. That is a real limit and it is "
         "not one the warehouse can fix."),
        ("The chain cannot forget, and nobody owns it",
         "A receipt is not held by us at all. It survives this "
         "application, this account, and this operator, which is a "
         "different and stronger property than retention."),
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
            "own retention, and applying a change writes a real UPDATE. "
            "The reconciliation section reads the same table either way."
        )

    C.provenance_footer(
        "MARTS.ORG_RISK queried with AT(OFFSET) at a series of negative "
        "second offsets, and read directly for the row detail, the "
        "component breakdown and the reconciliation. No additional "
        "storage required, since this is Snowflake internal retention."
    )
