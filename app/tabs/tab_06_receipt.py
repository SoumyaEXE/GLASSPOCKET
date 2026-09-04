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
"""

from __future__ import annotations

import streamlit as st

import charts
import components as C
import data


def render() -> None:
    C.tab_title(
        "The Receipt",
        "Do not trust this application. Check the ledger yourself.",
    )

    kpi = data.run("Q_RECEIPT_KPI")
    on_chain = int(kpi.iloc[0]["receipts_on_chain"] or 0) if len(kpi) else 0
    missing = int(kpi.iloc[0]["receipts_missing"] or 0) if len(kpi) else 0

    # ---------------------------------------------------------------- S1
    # Two figures side by side. The second number is the interesting one.
    C.hero(f"{on_chain:,}", "receipts on chain")
    st.markdown(
        f"and {missing:,} expected receipts missing. "
        "**No receipt was written for those disbursements. "
        "That absence is the finding.**"
    )
    st.markdown(
        "You should not have to trust this application. "
        "Take an identifier and check it yourself."
    )

    # ---------------------------------------------------------------- S2
    tree = data.run("Q_TREE_STATE")
    if len(tree):
        t = tree.iloc[0]
        C.stat_band([
            (str(t["tree_address"])[:10] + "…", "merkle tree"),
            (f"{int(t['leaves_used'] or 0):,}", "leaves used"),
            (f"{int(t['capacity_remaining'] or 0):,}", "capacity remaining"),
            (str(t["cluster"]), "cluster"),
        ])
        C.identifier(str(t["tree_address"]), "tree address")

    # ---------------------------------------------------------------- S3
    # Lookup and receipt card.
    C.section("Look it up")

    sample = data.run("Q_SAMPLE_ASSET")
    placeholder = str(sample.iloc[0]["asset_id"]) if len(sample) else ""

    icol, bcol = st.columns([4, 1], gap="small")
    with icol:
        asset_id = st.text_input(
            "asset identifier", value=placeholder,
            key="gp_r_asset", label_visibility="collapsed",
            placeholder="paste an asset identifier",
        )
    with bcol:
        verify = st.button("verify", type="primary", key="gp_r_verify",
                           use_container_width=True)

    if verify or asset_id:
        found = data.run("Q_RECEIPT_LOOKUP", (asset_id.strip(),))
        if found.empty:
            st.markdown(
                C.chip("no receipt found for that identifier", "flagged"),
                unsafe_allow_html=True,
            )
        else:
            r = found.iloc[0]
            st.markdown(C.chip("receipt found", "confirmed"),
                        unsafe_allow_html=True)
            f1, f2 = st.columns(2, gap="medium")
            with f1:
                C.identifier(str(r["programme_code"]), "programme", copyable=False)
                C.identifier(str(r["amount_band"]), "amount band", copyable=False)
                C.identifier(str(r["tree_address"])[:18] + "…", "tree",
                             copyable=False)
            with f2:
                C.identifier(str(r["window_key"]), "window", copyable=False)
                C.identifier(str(r["org_hash"])[:8] + "…" + str(r["org_hash"])[-4:],
                             "organisation hash", copyable=False)
                C.identifier(str(int(r["leaf_index"])), "leaf index",
                             copyable=False)
            st.markdown(
                f'<a href="{r["explorer_url"]}" target="_blank" '
                f'class="gp-identifier">open in solana explorer</a>',
                unsafe_allow_html=True,
            )
            C.source_note(
                "The link is the only thing on this tab that touches the "
                "network, and it does so in your browser rather than in a "
                "render path. Everything above is read from the local mirror "
                "the bridge wrote."
            )

    # ---------------------------------------------------------------- S4
    C.section("Expected against actual")
    gap = data.run("Q_RECEIPT_GAP")
    if gap.empty:
        st.markdown('<div class="gp-source">No receipts recorded yet.</div>',
                    unsafe_allow_html=True)
    else:
        st.plotly_chart(charts.receipt_gap(gap), use_container_width=True,
                        config=charts.bare_config())
        C.source_note(
            "Where the lines separate, no receipt was written. The gap is "
            "real: a deliberate subset of verified disbursements is left "
            "unminted, so the finding is genuine rather than staged. Tab 10 "
            "says so too."
        )

    # ------------------------------------------------------------ S5, S6
    left, right = st.columns(2, gap="medium")

    with left:
        C.section("Mint activity")
        activity = data.run("Q_MINT_ACTIVITY")
        if activity.empty:
            st.markdown('<div class="gp-source">No mints recorded.</div>',
                        unsafe_allow_html=True)
        else:
            st.plotly_chart(charts.mint_activity(activity),
                            use_container_width=True,
                            config=charts.bare_config())
            C.source_note(
                f"One point per compressed NFT, {len(activity):,} shown. This "
                "exists to confirm the volume is genuine rather than three "
                "hand-made tokens created for a screenshot."
            )

    with right:
        C.section("What goes on chain")
        st.markdown(
            """
            | on chain | never on chain |
            | --- | --- |
            | programme code | beneficiary identifier |
            | amount band, not the amount | the exact amount |
            | delivery window, not the timestamp | the exact timestamp |
            | salted hash of the organisation | the organisation name |
            | schema version | any coordinate |
            """
        )
        C.source_note(
            "Publish the claim, not the data. A public ledger is permanent, "
            "and permanence plus personal data is a harm that cannot be undone."
        )

    if data.is_preview():
        C.source_note(
            "Preview mode. These rows are a local stand-in for the mint log. "
            "In the deployed build every row is written by bridge/src/index.ts "
            "after a real compressed NFT is minted on Solana devnet, and the "
            "explorer link resolves."
        )

    # ---------------------------------------------------------------- S7
    C.section("Why a ledger")
    C.step_explainer([
        ("Whose record it is",
         "Not ours. The receipt sits on a public chain, so verifying it does "
         "not require trusting the charity, the platform, or us."),
        ("What survives",
         "If this application disappears tomorrow, every receipt it wrote is "
         "still there and still checkable by anybody."),
        ("What a receipt cannot prove",
         "That a claim was recorded at a point in time, and nothing more. It "
         "does not prove goods reached a person. Anyone who tells you a "
         "blockchain solves that is selling something."),
    ])

    C.provenance_footer(
        "ORACLE.MINT_LOG mirrors every successful mint with asset identifier, "
        "signature, tree address, leaf index and explorer URL. "
        "ORACLE.MINT_QUEUE supplies the expected side. SERVING.V_RECEIPT_GAP "
        "computes the difference over time. Devnet, not mainnet, and the "
        "interface says so plainly."
    )
