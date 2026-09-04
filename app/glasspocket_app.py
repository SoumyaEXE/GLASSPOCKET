"""GLASSPOCKET. Entrypoint and navigation shell.

A Snowflake accountability engine for charitable giving.

This is not a dashboard in the usual sense. It is an argument in eleven
moves, ordered so a viewer clicking straight through experiences a
beginning, a turn and a payoff:

    generosity fails not because people stop giving but because they
    cannot see where the money went, so this is the machinery that lets
    them see.

LAYOUT
    A left rail carries the eleven moves in order and the state chips
    that must be visible everywhere; the content sits in a centred column
    beside it. The rail keeps the whole argument in view, which a
    horizontal tab strip cannot do once it starts scrolling, and it means
    a viewer always knows how far through the argument they are.

FRAMING RULE, EVERY TAB
    The product is a confidence layer for people who want to give, not an
    accusation engine. Interface language reflects this throughout. We
    write verified, unverified, needs a second look, confidence, receipt
    found. We never write fraud, criminal, scam or guilty about any
    entity. The word fraud appears only on Tab 00, where it quotes a
    cited source.
"""

from __future__ import annotations

import pathlib
import sys

import streamlit as st

sys.path.insert(0, str(pathlib.Path(__file__).parent))

st.set_page_config(
    page_title="GLASSPOCKET",
    page_icon="◇",
    layout="wide",
    initial_sidebar_state="expanded",
)

from theme import inject_theme               # noqa: E402
import components as C                       # noqa: E402
import data                                  # noqa: E402

# Must be the very first Streamlit call after page configuration.
inject_theme()

from tabs import (                           # noqa: E402
    tab_00_brief,
    tab_01_confidence,
    tab_02_graph,
    tab_03_money,
    tab_04_last_mile,
    tab_05_wall,
    tab_06_receipt,
    tab_07_historian,
    tab_08_ask,
    tab_09_dollar,
    tab_10_method,
)

#: The narrative spine, in order: (number, name, one-line move, module).
#: Section 09: tabs 05, 01 and 06 are the submission. Everything else is
#: amplification. If the schedule slips, protect those three.
TABS = [
    ("00", "The Brief",            "the stakes, with sources",      tab_00_brief),
    ("01", "Give With Confidence", "telling real from imitation",   tab_01_confidence),
    ("02", "The Trust Graph",      "imitation as a structure",      tab_02_graph),
    ("03", "Follow The Money",     "where aid actually landed",     tab_03_money),
    ("04", "The Last Mile",        "where the gap opens",           tab_04_last_mile),
    ("05", "The Wall",             "attack the privacy layer",      tab_05_wall),
    ("06", "The Receipt",          "verify without trusting us",    tab_06_receipt),
    ("07", "The Historian",        "the record cannot be rewritten", tab_07_historian),
    ("08", "Ask The Warehouse",    "questions in plain language",   tab_08_ask),
    ("09", "Where A Dollar Lands", "who to give to",                tab_09_dollar),
    ("10", "Method And Honesty",   "what is real, what is seeded",  tab_10_method),
]

def _sidebar() -> int:
    """The left rail: identity, the eleven moves, and live state.

    Returns the index of the selected move.
    """
    with st.sidebar:
        st.markdown(
            '<div class="gp-rail-brand">'
            '<div class="gp-rail-mark">GLASSPOCKET</div>'
            '<div class="gp-rail-sub">accountability for charitable giving</div>'
            "</div>",
            unsafe_allow_html=True,
        )

        st.markdown('<div class="gp-rail-eyebrow">the argument</div>',
                    unsafe_allow_html=True)

        # One button per move. The active one is rendered primary, which
        # is the only state Streamlit gives a button, and it is enough.
        chosen = st.session_state.setdefault("gp_nav", 0)
        for index, (number, name, _move, _mod) in enumerate(TABS):
            if st.button(
                f"{number}   {name}",
                key=f"gp_nav_{number}",
                use_container_width=True,
                type="primary" if index == chosen else "secondary",
            ):
                st.session_state["gp_nav"] = index
                chosen = index
                st.rerun()

        number, name, move, _mod = TABS[chosen]
        st.markdown(
            f'<div class="gp-rail-move">{move}</div>', unsafe_allow_html=True
        )

        st.markdown('<div class="gp-rail-eyebrow">state</div>',
                    unsafe_allow_html=True)

        backend = "live warehouse" if not data.is_preview() else "local preview"
        tone = "verified" if not data.is_preview() else "seeded"
        st.markdown(
            '<div class="gp-rail-state">'
            + C.chip(backend, tone)
            + C.chip("solana devnet", "chain")
            + C.chip("seeded data is labelled", "seeded")
            + "</div>",
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="gp-rail-foot">'
            "Real organisation data from public filings. Impersonators and "
            "beneficiary records are seeded and labelled, and every one of "
            "them says so on screen. See Method And Honesty."
            "</div>",
            unsafe_allow_html=True,
        )

    return chosen


def main() -> None:
    chosen = _sidebar()
    number, name, _move, module = TABS[chosen]

    # The disclosure banner is required on every tab, not only the ones
    # that happen to mention synthetic data. Section 11.
    C.disclosure_banner()

    try:
        module.render()
    except Exception as exc:                  # noqa: BLE001
        # One tab failing must never take the whole thing down, but it
        # must also not fail silently: the message names the tab and the
        # error so it is fixable rather than mysterious.
        st.error(
            f"**{number} {name}** could not render.\n\n"
            f"`{type(exc).__name__}: {exc}`\n\n"
            "Every other section is unaffected. If this says a column is "
            "missing, the query and the tab disagree about a name; "
            "run `python tools/verify_queries.py` to see what the "
            "warehouse actually returns."
        )


if __name__ == "__main__":
    main()
