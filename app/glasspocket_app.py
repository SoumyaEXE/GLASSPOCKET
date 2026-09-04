"""GLASSPOCKET. Entrypoint and tab router.

A Snowflake accountability engine for charitable giving.

This is not a dashboard. It is an argument in eleven moves, ordered so a
viewer clicking straight through experiences a beginning, a turn and a
payoff:

    generosity fails not because people stop giving but because they
    cannot see where the money went, so this is the machinery that lets
    them see.

FRAMING RULE, EVERY TAB
    The product is a confidence layer for people who want to give, not an
    accusation engine. Interface language reflects this throughout. We
    write verified, unverified, needs a second look, confidence, receipt
    found. We never write fraud, criminal, scam or guilty about any
    entity. The word fraud appears only on Tab 00, where it quotes a cited
    source.

NAMING
    Section 04's file tree lists six tab modules under an earlier
    four-role naming. Section 07 specifies eleven tabs in detail and is
    the normative one, so the modules below follow Section 07's names.
"""

from __future__ import annotations

import sys
import pathlib

import streamlit as st

sys.path.insert(0, str(pathlib.Path(__file__).parent))

st.set_page_config(
    page_title="GLASSPOCKET",
    page_icon="◇",
    layout="wide",
    initial_sidebar_state="collapsed",
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

#: The narrative spine, in order. Each entry is (label, module).
#: Section 09: tabs 05, 01 and 06 are the submission. Everything else is
#: amplification. If the schedule slips, protect those three.
TABS = [
    ("00 Brief",      tab_00_brief),
    ("01 Confidence", tab_01_confidence),
    ("02 Graph",      tab_02_graph),
    ("03 Money",      tab_03_money),
    ("04 Last Mile",  tab_04_last_mile),
    ("05 Wall",       tab_05_wall),
    ("06 Receipt",    tab_06_receipt),
    ("07 Historian",  tab_07_historian),
    ("08 Ask",        tab_08_ask),
    ("09 Dollar",     tab_09_dollar),
    ("10 Method",     tab_10_method),
]


def main() -> None:
    C.shell_header()
    C.disclosure_banner()

    if data.is_preview():
        # Honest disclosure of which backend is answering. A project about
        # accountability does not get to be vague about this.
        st.markdown(
            C.chip("preview mode: local store, not a live warehouse", "seeded"),
            unsafe_allow_html=True,
        )

    for tab_ui, (_label, module) in zip(
        st.tabs([label for label, _ in TABS]), TABS
    ):
        with tab_ui:
            try:
                module.render()
            except Exception as exc:          # noqa: BLE001
                # One tab failing must never take the demo down with it.
                st.error(
                    f"This tab could not render: {exc}\n\n"
                    "The other tabs are unaffected."
                )


if __name__ == "__main__":
    main()
