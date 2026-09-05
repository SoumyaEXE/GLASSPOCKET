"""Tab 06 / The Receipt. Build Spec Sections 07 and 08.

    Do not trust this application. Check the ledger yourself.

A donor verifying a claim about a charity is verifying it against a record
kept by the charity, or by a platform the charity pays, or by an
application built by someone they have never met. Every one of those
requires trust in an interested party. A compressed NFT receipt is a
record that persists whether or not GLASSPOCKET exists, whether or not the
operator stays honest, and whether or not the warehouse is later edited.
That property is the only reason a chain is here.

DEMO SAFETY
    Every receipt is minted hours before recording. The lookup reads the
    local mirror table populated by the bridge, and only the explorer link
    touches the network, in the viewer's browser. If the RPC is slow
    during the demo, nothing on screen stalls. Never call an RPC from a
    render path.

THREE THINGS ON THIS TAB WERE NOT TRUE ENOUGH TO SHIP.

    1. THE PREVIEW HANDED YOU AN IDENTIFIER THAT WAS ON NO LEDGER.

       The preview store carried 4,427 fabricated mint rows whose asset
       identifiers began "GP" and whose explorer links resolved to
       nothing, while the warehouse held 285 real devnet mints. A tab
       whose entire argument is "do not trust this application, check the
       ledger yourself" cannot hand the reader something that is not on
       the ledger. tools/sync_preview.py now pulls ORACLE.MINT_LOG and
       ORACLE.MINT_QUEUE like every other table, so the preview is a
       mirror and the link resolves.

    2. THE TWO BACKENDS DISAGREED ABOUT HOW MANY WERE MISSING.

       Q_RECEIPT_KPI read MAX(cum_gap) off the daily gap view in the
       warehouse and summed receipts_missing off the coverage table in
       the preview, and the two came back hundreds apart on the same
       corpus. Both figures are now counted off the queue and the log.

    3. THE GAP CHART READ AS FOUR MONTHS OF NEGLECT.

       Every mint in the corpus landed inside one twenty-two minute
       window on 4 September 2026, because that is when the bridge ran.
       Drawn as a cumulative daily series with only the final gap
       annotated, that looks like a record nobody bothered to write. It
       is a migration that has started and is not finished, and the date
       it started is now marked on the chart.

RECEIPTS ARE NOT DISBURSEMENTS, AND THE TAB SAYS SO.

    285 leaves cover 206 disbursements. A mint is an append and it is not
    idempotent: a retried disbursement writes a second leaf, and an
    append-only ledger has no way to take the first one back. Both
    numbers are reported.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import charts
import components as C
import data

#: What the receipt publishes, against what it deliberately never carries.
#: Section 08: publish the claim, not the data.
ON_CHAIN = [
    ("programme code", "beneficiary identifier"),
    ("amount band, never the amount", "the exact amount"),
    ("delivery window, never the timestamp", "the exact timestamp"),
    ("salted hash of the organisation", "the organisation name"),
    ("schema version", "any coordinate"),
]

GROUPINGS = ("by amount band", "by appeal")


def _f(value, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _i(value, default: int = 0) -> int:
    return int(_f(value, default))


def _when(value) -> str:
    try:
        if value is None or pd.isna(value):
            return "not recorded"
        return pd.to_datetime(value).strftime("%d %B %Y, %H:%M")
    except (TypeError, ValueError):
        return "not recorded"


def _picker(options, key: str, default: str) -> str:
    """A segmented control, or buttons where the control does not exist."""
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


# ---------------------------------------------------------------------------
# S3 / check it yourself
# ---------------------------------------------------------------------------


def _lookup() -> None:
    C.section("Check it yourself")
    sample = data.run("Q_SAMPLE_ASSET")
    placeholder = str(sample.iloc[0]["asset_id"]) if len(sample) else ""

    with C.panel():
        C.panel_head("Look up any receipt on the ledger", "oracle.mint_log")
        C.note(
            "The field opens on the most recent mint. Paste any other "
            "asset identifier and it is looked up in the local mirror the "
            "bridge wrote &mdash; never over the network, because an RPC "
            "on a render path is a demo that stalls in front of an "
            "audience. The explorer link is the one thing here that "
            "touches Solana, and it does so in your browser."
        )
        icol, bcol = st.columns([5, 1], gap="small")
        with icol:
            asset_id = st.text_input(
                "asset identifier", value=placeholder,
                key="gp_r_asset", label_visibility="collapsed",
                placeholder="paste an asset identifier",
            )
        with bcol:
            st.button("verify", key="gp_r_verify", use_container_width=True)

        if not asset_id.strip():
            C.note("Nothing to look up yet.")
            return

        found = data.run("Q_RECEIPT_LOOKUP", (asset_id.strip(),))
        if found.empty:
            st.markdown(
                C.chip("no receipt found for that identifier", "flagged"),
                unsafe_allow_html=True,
            )
            C.source_note(
                "An identifier that is not on the ledger returns nothing, "
                "which is the correct answer rather than an error. A tool "
                "that invented a plausible receipt for an unknown "
                "identifier would be worse than no tool."
            )
            return

        r = found.iloc[0]
        st.markdown(C.chip("receipt found", "confirmed"),
                    unsafe_allow_html=True)

        claim, proof = st.columns(2, gap="medium")
        with claim:
            C.eyebrow("what the receipt claims")
            C.kv_rows([
                ("programme", str(r["programme_code"])),
                ("amount band", str(r["amount_band"])),
                ("delivery window", str(r["window_key"])),
                ("organisation hash",
                 str(r["org_hash"])[:10] + "…" + str(r["org_hash"])[-6:]),
            ])
        with proof:
            C.eyebrow("where it sits on the ledger")
            C.kv_rows([
                ("tree", str(r["tree_address"])[:10] + "…"
                         + str(r["tree_address"])[-6:]),
                ("leaf index", f"{_i(r['leaf_index']):,}"),
                ("minted", _when(r["minted_at"])),
                ("cluster", "solana devnet"),
            ])

        C.identifier(str(r["asset_id"]), "asset identifier")
        C.identifier(str(r["signature"]), "transaction signature")
        st.markdown(
            f'<a href="{r["explorer_url"]}" target="_blank" '
            f'rel="noopener" class="gp-identifier">open in solana explorer '
            "&rarr;</a>",
            unsafe_allow_html=True,
        )
        C.source_note(
            "Both identifiers above are selectable so they can be pasted "
            "into any explorer, not only the one this application links "
            "to. That is the whole point: the record does not belong to "
            "us, and checking it should not require our interface."
        )


# ---------------------------------------------------------------------------
# S4 / the migration
# ---------------------------------------------------------------------------


def _migration(kpi) -> None:
    C.section("Expected against actual")
    gap = data.run("Q_RECEIPT_GAP")

    with C.panel():
        C.panel_head("Records verified, against records on the ledger",
                     "serving.v_receipt_gap")
        if gap.empty:
            C.note("No receipts recorded yet.")
            return
        st.plotly_chart(charts.receipt_gap(gap, height=336),
                        use_container_width=True, config=charts.bare_config())
        last = gap.iloc[-1]
        expected = _i(last["cum_expected"])
        actual = _i(last["cum_actual"])
        C.readout([
            (f"{expected:,}", "verified in the warehouse"),
            (f"{actual:,}", "leaves on the ledger"),
            (f"{max(expected - actual, 0):,}", "awaiting a receipt"),
            (f"{actual / expected * 100:.1f}%" if expected else "0%",
             "of the way through"),
        ], flag="awaiting a receipt")
        C.note(
            "The purple line is flat for four months and then steps up "
            f"once, on {_when(kpi['first_mint']).split(',')[0]}. That is "
            "not four months of neglect: it is the day the bridge first "
            "ran. Minting is a migration against a queue that already "
            "existed, and it stops when the devnet wallet stops, which is "
            "a funding limit, and it is stated here rather than hidden "
            "behind a smoother-looking chart."
        )
        C.source_note(
            "The red area is still the finding. A record with no receipt "
            "cannot be checked by anybody who does not trust this "
            "application, and that is true whether the reason is neglect "
            "or an unfinished migration."
        )


# ---------------------------------------------------------------------------
# S5 / how far it has got
# ---------------------------------------------------------------------------


def _progress() -> None:
    C.section("How far the migration has got")
    grouping = _picker(GROUPINGS, "gp_r_group", GROUPINGS[0])

    if grouping == "by appeal":
        frame = data.run("Q_MINT_PROGRAMME")
        label_column = "programme_code"
        where = "oracle.mint_queue · oracle.mint_log"
        lead = (
            "Six appeals, each with its own queue. The bars are close "
            "together because the bridge works the queue in order rather "
            "than by programme, which is the behaviour you want: an "
            "appeal cannot be quietly prioritised into looking better "
            "covered than the others."
        )
    else:
        frame = data.run("Q_MINT_PROGRESS")
        label_column = "amount_band"
        where = "oracle.mint_queue · oracle.mint_log"
        lead = (
            "The band is the only thing the queue publishes about value, "
            "because the band is what goes on chain. Grouping by the "
            "exact amount would mean this tab had read a number it has "
            "spent two sections explaining it never writes down."
        )

    if frame.empty:
        C.note("Nothing queued.")
        return

    queued = int(frame["queued"].sum())
    covered = int(frame["covered"].sum())
    leaves = int(frame["leaves_written"].sum())

    with C.panel():
        C.panel_head("Queued against covered", where)
        C.note(lead)
        st.plotly_chart(
            charts.mint_progress(frame, label_column,
                                 height=max(220, 46 * len(frame) + 110)),
            use_container_width=True, config=charts.bare_config(),
        )
        C.readout([
            (f"{queued:,}", "queued"),
            (f"{covered:,}", "disbursements covered"),
            (f"{leaves:,}", "leaves written"),
            (f"{max(leaves - covered, 0):,}", "written more than once"),
        ])
        C.source_note(
            "Leaves written exceeds disbursements covered because a mint "
            "is an append and it is not idempotent. A retry writes a "
            "second leaf for the same disbursement, and an append-only "
            "ledger has no way to take the first one back. Reporting the "
            "leaf count as a disbursement count would overstate coverage "
            "by exactly that difference, so both are here."
        )


# ---------------------------------------------------------------------------
# S6 / what goes on chain
# ---------------------------------------------------------------------------


def _payload() -> None:
    C.section("What goes on chain, and what never does")
    with C.panel():
        C.panel_head("The receipt schema", "bridge/src/index.ts")
        C.table(
            [("on chain", "gp-td-lead"), ("never on chain", "")],
            [[on, never] for on, never in ON_CHAIN],
            widths=["50%", "50%"],
        )
        C.source_note(
            "Publish the claim, not the data. A public ledger is "
            "permanent, and permanence plus personal data is a harm that "
            "cannot be undone by deleting a row later. The right-hand "
            "column is not a list of things we have not got round to; it "
            "is a list of things that are deliberately absent."
        )


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------


def render() -> None:
    C.tab_title(
        "The Receipt",
        "Do not trust this application. Check the ledger yourself.",
    )

    kpi_frame = data.run("Q_RECEIPT_KPI")
    if kpi_frame.empty:
        st.warning("No mint data.")
        return
    kpi = kpi_frame.iloc[0]
    on_chain = _i(kpi["receipts_on_chain"])
    covered = _i(kpi["disbursements_covered"])
    queued = _i(kpi["queued"])
    awaiting = _i(kpi["awaiting"])

    tree = data.run("Q_TREE_STATE")

    # ---------------------------------------------------------------- S1
    C.hero(f"{on_chain:,}", "receipts written to a public ledger")

    # ---------------------------------------------------------------- S2
    C.stat_band([
        (f"{covered:,}", "disbursements covered"),
        (f"{queued:,}", "queued"),
        (f"{awaiting:,}", "awaiting a receipt"),
        (f"{_i(tree.iloc[0]['capacity_remaining']):,}" if len(tree) else "—",
         "leaves left on the tree"),
        ("devnet", "cluster"),
    ])
    C.source_note(
        f"{awaiting:,} disbursements have no receipt. No receipt was "
        "written for them, and that absence is itself the finding: a "
        "record nobody can check without trusting this application is a "
        "record you are being asked to take on faith. The tree is real, "
        "on Solana devnet, and its address is below."
    )

    # ---------------------------------------------------------------- S2b
    if len(tree):
        t = tree.iloc[0]
        with C.panel():
            C.panel_head("The merkle tree", "serving.v_tree_state")
            C.identifier(str(t["tree_address"]), "tree address")
            C.kv_rows([
                ("leaves used", f"{_i(t['leaves_used']):,}"),
                ("capacity", f"{_i(t['capacity']):,}"),
                ("capacity remaining", f"{_i(t['capacity_remaining']):,}"),
                ("last mint", _when(t["last_mint_at"])),
                ("cluster", str(t["cluster"])),
            ])
            C.source_note(
                "maxDepth 14 gives 16,384 leaves. The tree parameters are "
                "immutable once it is created, so the capacity here is "
                "the capacity for the life of the tree rather than a "
                "quota anybody can raise."
            )

    # ---------------------------------------------------------------- S3
    _lookup()

    # ---------------------------------------------------------------- S4
    _migration(kpi)

    # ---------------------------------------------------------------- S5
    _progress()

    # ---------------------------------------------------------------- S6
    _payload()

    if data.is_preview():
        C.source_note(
            "Preview mode. These rows are pulled from ORACLE.MINT_LOG and "
            "ORACLE.MINT_QUEUE by tools/sync_preview.py, so they are the "
            "same real devnet mints the deployed build reads and the "
            "explorer links resolve. Every row was written by "
            "bridge/src/index.ts after a compressed NFT was minted."
        )

    # ---------------------------------------------------------------- S7
    C.section("Why a ledger")
    C.step_explainer([
        ("Whose record it is",
         "Not ours. The receipt sits on a public chain, so verifying it "
         "does not require trusting the charity, the platform, or us."),
        ("What survives",
         "If this application disappears tomorrow, every receipt it wrote "
         "is still there and still checkable by anybody."),
        ("What it deliberately omits",
         "No beneficiary, no exact amount, no timestamp, no coordinate. A "
         "band and a window are enough to check a claim, and they are the "
         "most that can safely be made permanent."),
        ("What a receipt cannot prove",
         "That a claim was recorded at a point in time, and nothing more. "
         "It does not prove goods reached a person. Anyone who tells you "
         "a blockchain solves that is selling something."),
    ])

    C.provenance_footer(
        "ORACLE.MINT_LOG mirrors every successful mint with asset "
        "identifier, signature, tree address, leaf index and explorer URL. "
        "ORACLE.MINT_QUEUE supplies the expected side and the payload "
        "fields. SERVING.V_RECEIPT_GAP computes the difference over time. "
        "Devnet, not mainnet, and the interface says so plainly."
    )
