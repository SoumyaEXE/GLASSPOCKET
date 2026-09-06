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
)

#: The narrative spine, in order: (number, name, one-line move, module).
#: Section 09 names 05, 01 and 06 as the submission: the privacy layer,
#: the detector that tells real from imitation, and the receipt that lets
#: you check a claim without trusting this application.
#:
#: The Wall was cut two days before submission and is back, because the
#: reason it was cut turned out to be a syntax error in this build's own
#: probe rather than a missing platform feature. It now carries three
#: governance regimes over one set of facts instead of two.
#:
#: The numbers are the position in the argument, not a stable identifier.
#: They renumber when a tab is added or removed, because a rail that
#: skips one invites a reader to hunt for the gap.
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
]

def _sidebar() -> int:
    """The left rail: identity, the ten moves, one status line.

    Returns the index of the selected move.

    WHAT IS NOT HERE, AND WHY
      The rail used to carry a step number on every item, a caption for
      the section being read, three state chips and a paragraph of
      disclosure. All of it was true and none of it was navigation.

      The numbers were ordinals rather than identifiers, so they invited
      a reader to hunt for a meaning they did not carry. The caption
      restated the heading the reader was about to see anyway. The
      disclosure paragraph was a duplicate: ``C.disclosure_banner()``
      renders the same sentence at the top of every tab, which is where
      Section 11 requires it and where a reader is actually looking.

      What survives is one status line, because whether the numbers on
      screen came from the warehouse or from the local preview store is
      the one fact a viewer cannot infer from anything else on the page.
    """
    with st.sidebar:
        st.markdown(
            '<div class="gp-rail-brand">'
            '<div class="gp-rail-mark">GLASSPOCKET</div>'
            '<div class="gp-rail-sub">accountability for charitable giving</div>'
            "</div>",
            unsafe_allow_html=True,
        )

        # One button per move. The active one is rendered primary, which
        # is the only state Streamlit gives a button, and it is enough.
        chosen = st.session_state.setdefault("gp_nav", 0)
        for index, (number, name, _move, _mod) in enumerate(TABS):
            if st.button(
                name,
                key=f"gp_nav_{number}",
                use_container_width=True,
                type="primary" if index == chosen else "secondary",
            ):
                st.session_state["gp_nav"] = index
                chosen = index
                st.rerun()

        live = not data.is_preview()
        st.markdown(
            '<div class="gp-rail-status">'
            f'<span class="gp-dot gp-dot-{"live" if live else "preview"}"></span>'
            f'<span>{"live warehouse" if live else "local preview"}</span>'
            '<span class="gp-rail-sep">/</span>'
            "<span>solana devnet</span>"
            "</div>",
            unsafe_allow_html=True,
        )

    return chosen


def main() -> None:
    chosen = _sidebar()
    _number, name, _move, module = TABS[chosen]

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
            f"**{name}** could not render.\n\n"
            f"`{type(exc).__name__}: {exc}`\n\n"
            "Every other section is unaffected. If this says a column is "
            "missing, the query and the tab disagree about a name; "
            "run `python tools/verify_queries.py` to see what the "
            "warehouse actually returns."
        )


if __name__ == "__main__":
    main()
