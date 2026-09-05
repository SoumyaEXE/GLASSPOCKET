"""Infographic components. Built once, reused across all eleven tabs.

Build Spec Section 03, "Infographic components to build once and reuse".

The hero pattern is what converts a dashboard into a narrative: every tab
opens with one oversized figure, one line of context, and nothing else
above the fold.

`identifier` is the most load-bearing function in this module. It is the
replacement for st.code, which forces monospace, and it is the reason no
monospaced typeface appears anywhere in the application.
"""

from __future__ import annotations

import base64
import contextlib
import html
from typing import Iterable, Sequence

import streamlit as st

from theme import MAX_WIDTH  # noqa: F401  (re-exported for tab modules)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _esc(value) -> str:
    return html.escape(str(value), quote=True)


#: Public alias. A tab that composes its own cell markup for C.table
#: still has to escape the values it puts inside it.
escape = _esc


def usd(value: float, *, precise: bool = False) -> str:
    """Format dollars for display. Never rounds a cited figure."""
    if value is None:
        return "n/a"
    value = float(value)
    if precise:
        return f"${value:,.0f}"
    for cutoff, suffix, div in (
        (1_000_000_000, "B", 1_000_000_000),
        (1_000_000, "M", 1_000_000),
        (1_000, "K", 1_000),
    ):
        if abs(value) >= cutoff:
            return f"${value / div:,.1f}{suffix}".replace(".0", "")
    return f"${value:,.0f}"


def pct(value: float, digits: int = 1) -> str:
    if value is None:
        return "n/a"
    return f"{float(value) * 100:.{digits}f}%"


# ---------------------------------------------------------------------------
# shell
# ---------------------------------------------------------------------------


def shell_header(*, cluster: str = "solana devnet") -> None:
    """Wordmark and the two persistent state chips."""
    st.markdown(
        f"""
        <div class="gp-shell">
          <div class="gp-wordmark">GLASSPOCKET</div>
          <div class="gp-shell-chips">
            <span class="gp-chip gp-chip-seeded">seeded data is labelled</span>
            <span class="gp-chip gp-chip-chain">{_esc(cluster)}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def disclosure_banner() -> None:
    """The persistent banner. Required on all eleven tabs, Section 11.

    Copy is verbatim from the Section 12 copy deck.
    """
    st.markdown(
        """
        <div class="gp-banner">
          Real organisation data from public filings. Impersonators and
          beneficiary records are seeded and labelled. See the Method tab.
        </div>
        """,
        unsafe_allow_html=True,
    )


def tab_title(title: str, standfirst: str) -> None:
    st.markdown(
        f'<div class="gp-tab-title">{_esc(title)}</div>'
        f'<div class="gp-tab-standfirst">{_esc(standfirst)}</div>',
        unsafe_allow_html=True,
    )


def section(label: str) -> None:
    st.markdown(f'<div class="gp-section">{_esc(label)}</div>', unsafe_allow_html=True)


def eyebrow(label: str) -> None:
    st.markdown(f'<div class="gp-eyebrow">{_esc(label)}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# hero, stat band
# ---------------------------------------------------------------------------


def hero(value: str, caption: str) -> None:
    """Oversized figure with a label-token caption beneath.

    Opens every tab without exception. Nothing else goes above the fold.
    """
    st.markdown(
        f"""
        <div class="gp-hero">
          <div class="gp-hero-value">{_esc(value)}</div>
          <div class="gp-hero-caption">{_esc(caption)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def stat_band(items: Sequence[tuple[str, str]]) -> None:
    """Row of three to five bordered cards, each a figure plus caption.

    No shadows, 1 px borders, equal widths.
    """
    items = list(items)
    if not items:
        return
    for col, (value, caption) in zip(st.columns(len(items), gap="small"), items):
        with col:
            st.markdown(
                f"""
                <div class="gp-stat">
                  <div class="gp-stat-value">{_esc(value)}</div>
                  <div class="gp-stat-caption">{_esc(caption)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# identifier, chip
# ---------------------------------------------------------------------------


def identifier(text: str, label: str | None = None, *, copyable: bool = True) -> None:
    """Render a hash, EIN, asset ID or SQL fragment.

    Geist with tabular figures on a sunken background. This is the
    replacement for st.code and it is why no monospace appears in the
    application. Section 03, absolute rule.
    """
    if label:
        st.markdown(f'<div class="gp-identifier-label">{_esc(label)}</div>',
                    unsafe_allow_html=True)
    if copyable:
        # A selectable field is the copy control, and it is the ONLY
        # element rendered. It used to sit underneath a styled div
        # carrying the same string, so every copyable identifier printed
        # its own value twice in two boxes that looked almost alike; on
        # The Receipt that put the tree address on screen three times
        # between the stat band and the field. The field is styled to
        # match .gp-identifier in theme.py, so nothing is lost by
        # dropping the div. st.code is never used, because it would
        # force monospace.
        st.text_input(
            label or "identifier",
            value=str(text),
            key=f"copy_{abs(hash((label, text)))}",
            label_visibility="collapsed",
        )
    else:
        st.markdown(f'<div class="gp-identifier">{_esc(text)}</div>',
                    unsafe_allow_html=True)


def sql_block(sql: str, label: str | None = None) -> None:
    """Show SQL in Geist. The interface never hides the query it ran.

    An accountability tool that hides its own query contradicts itself.
    """
    if label:
        st.markdown(f'<div class="gp-identifier-label">{_esc(label)}</div>',
                    unsafe_allow_html=True)
    st.markdown(f'<div class="gp-sql">{_esc(sql.strip())}</div>',
                unsafe_allow_html=True)


def chip(text: str, tone: str = "neutral") -> str:
    """Pill in one of five tones: verified, seeded, flagged, chain, neutral.

    Returns markup so a caller can compose several chips on one line.
    """
    tone = tone if tone in {
        "verified", "seeded", "flagged", "chain", "confirmed", "neutral"
    } else "neutral"
    return f'<span class="gp-chip gp-chip-{tone}">{_esc(text)}</span>'


def file_chip(path: str) -> str:
    """A repository path as a chip, in its own casing.

    ``chip`` upper-cases its text, which is right for a label token and
    wrong for sql/07_clone_detection.sql: upper-cased it is no longer a
    path.
    """
    return f'<span class="gp-chip gp-chip-file">{_esc(path)}</span>'


def chips(items: Iterable[tuple[str, str]]) -> None:
    st.markdown(
        " ".join(chip(text, tone) for text, tone in items), unsafe_allow_html=True
    )


# ---------------------------------------------------------------------------
# explainer, compare columns, source note
# ---------------------------------------------------------------------------


def step_explainer(steps: Sequence[tuple[str, str]]) -> None:
    """Three to five numbered blocks in a horizontal row.

    Used at the foot of most tabs to explain the mechanism in plain
    language. This is what makes the application legible to a
    non-technical judge, so the copy carries no jargon.

    ONE GRID, NOT A ROW OF STREAMLIT COLUMNS.

        The cards used to be one per st.column. ``.gp-step`` asks for
        ``height: 100%``, but a column's own vertical block is only as
        tall as what is inside it, so the percentage resolved against
        auto and every card was exactly its own copy tall. Five of them
        with unequal copy came out as five different boxes on a ragged
        baseline, which is what the row looked like at the foot of The
        Last Mile.

        A CSS grid stretches its items to the tallest in the row without
        being asked, and ``auto-fit`` wraps five cards onto two lines on
        a narrow viewport rather than crushing them to 180 pixels each.
        The markup is emitted as one line: a blank line inside a block of
        HTML ends the block as far as the markdown parser is concerned.
        See ``table`` for the same trap.
    """
    cards = "".join(
        '<div class="gp-step">'
        f'<div class="gp-step-n">{idx:02d}</div>'
        f'<div class="gp-step-title">{_esc(title)}</div>'
        f'<div class="gp-step-body">{_esc(body)}</div>'
        "</div>"
        for idx, (title, body) in enumerate(steps, start=1)
    )
    st.markdown(f'<div class="gp-steps">{cards}</div>', unsafe_allow_html=True)


def compare_columns(
    left: dict,
    right: dict,
    *,
    left_tone: str = "truth",
    right_tone: str = "noise",
) -> None:
    """Two-column layout with a divider.

    Used for true against private on Tab 05, and before against after on
    Tab 07. Each side takes ``label``, ``value`` and optional ``sub``.
    """
    lcol, rcol = st.columns(2, gap="medium")
    for col, side, tone in ((lcol, left, left_tone), (rcol, right, right_tone)):
        value_class = "gp-compare-value"
        if tone == "noise":
            value_class += " gp-compare-value-noise"
        with col:
            sub = side.get("sub", "")
            sub_html = f'<div class="gp-compare-sub">{_esc(sub)}</div>' if sub else ""
            st.markdown(
                f"""
                <div class="gp-compare gp-compare-{tone}">
                  <div class="gp-compare-label">{_esc(side.get('label', ''))}</div>
                  <div class="{value_class}">{_esc(side.get('value', ''))}</div>
                  {sub_html}
                </div>
                """,
                unsafe_allow_html=True,
            )


def source_note(text: str, url: str | None = None) -> None:
    """Small muted line with a link, placed under any cited figure.

    Every cited number in the interface carries one. Where a citation has
    no URL it renders as attributed text rather than as a dead link,
    because inventing a source would defeat the point of the project.
    """
    if url:
        body = f'{_esc(text)} <a href="{_esc(url)}" target="_blank">source</a>'
    else:
        body = _esc(text)
    st.markdown(f'<div class="gp-source">{body}</div>', unsafe_allow_html=True)


def provenance_footer(text: str) -> None:
    """Muted line naming the data behind this tab, with a pointer to Tab 10."""
    st.markdown(
        f'<div class="gp-provenance">{_esc(text)} '
        f'Every figure on this tab is reproducible from the numbered SQL files. '
        f'See Method and Honesty.</div>',
        unsafe_allow_html=True,
    )


def meter(share: float, *, blue: bool = False) -> None:
    """Thin horizontal meter. Used for the privacy budget on Tab 05."""
    share = max(0.0, min(1.0, float(share or 0)))
    fill = "gp-meter-fill gp-meter-fill-blue" if blue else "gp-meter-fill"
    st.markdown(
        f'<div class="gp-meter"><div class="{fill}" '
        f'style="width:{share * 100:.1f}%"></div></div>',
        unsafe_allow_html=True,
    )


def org_card(
    *,
    name: str,
    cause: str,
    city: str,
    state: str,
    blurb: str,
    reveal: str | None = None,
    equal_height: bool = False,
) -> None:
    """Comparison card for Tab 01.

    Identical typography, identical field order, no visual tell whatsoever
    before the reveal. Do not colour, badge or shade the seeded one at
    that stage. Resist the urge.
    """
    klass = "gp-card gp-card-choice" if equal_height else "gp-card"
    if reveal == "verified":
        klass += " gp-card-reveal-verified gp-reveal"
    elif reveal == "seeded":
        klass += " gp-card-reveal-seeded gp-reveal"

    st.markdown(
        f"""
        <div class="{klass}">
          <div class="gp-card-name">{_esc(name)}</div>
          <div class="gp-card-meta">{_esc(cause)} &middot; {_esc(city)} &middot; {_esc(state)}</div>
          <div class="gp-card-blurb">{_esc(blurb)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def svg(markup: str, *, alt: str = "") -> None:
    """Render a hand-authored SVG inline.

    THE NEWLINES ARE THE BUG. Streamlit does not strip SVG tags: a probe
    of rect, text, line, path, polygon, circle, g, defs and polyline
    showed every one of them surviving unsafe_allow_html. What it does do
    is run the string through a markdown parser first, and a markdown
    parser treats a blank line as the end of an HTML block. Everything
    after the first blank line is therefore no longer HTML, so it is
    escaped and printed as source. That is exactly what the system map
    did: the first row of boxes drew, and the arrows that followed the
    blank line landed on the page as text.

    Collapsing the document to a single line fixes it at the cause and
    keeps the SVG inline, which matters because an inline document
    inherits the page's embedded Geist. A base64 data URI in an <img>
    also renders, but it is a separate document with no access to the
    font, so the labels come back in Helvetica.
    """
    one_line = " ".join(markup.split())
    label = f'<span class="gp-visually-hidden">{_esc(alt)}</span>' if alt else ""
    st.markdown(f'<div class="gp-svg">{one_line}</div>{label}',
                unsafe_allow_html=True)


def panel_head(title: str, note: str = "", *, note_html: str = "") -> None:
    """Title row for a bordered container.

    Pairs with st.container(border=True). Two columns holding different
    kinds of content only read as one row if both wear the same frame and
    label it the same way.

    ``note_html`` takes already-rendered markup, so a status chip can sit
    in the same slot as the label token. That matters for alignment: an
    extra row inside one panel and not the other puts the two panels'
    figures on different lines even when the panels themselves end
    together.
    """
    if note_html:
        note_html = f'<div class="gp-panel-note-slot">{note_html}</div>'
    else:
        note_html = f'<div class="gp-panel-note">{_esc(note)}</div>' if note else ""
    st.markdown(
        f'<div class="gp-panel-head">'
        f'<div class="gp-panel-title">{_esc(title)}</div>{note_html}</div>',
        unsafe_allow_html=True,
    )


def kv_rows(items: Sequence[tuple[str, str]]) -> None:
    """Label on the left, value right-aligned. Figures are tabular."""
    rows = "".join(
        f'<div class="gp-kv"><span class="gp-kv-k">{_esc(k)}</span>'
        f'<span class="gp-kv-v">{_esc(v)}</span></div>'
        for k, v in items
    )
    st.markdown(f'<div class="gp-kv-list">{rows}</div>', unsafe_allow_html=True)


def note(text: str) -> None:
    """A paragraph of explanation, held to a readable measure."""
    st.markdown(f'<div class="gp-note">{text}</div>', unsafe_allow_html=True)


def table(
    columns: Sequence[tuple[str, str]],
    rows: Sequence[Sequence],
    *,
    widths: Sequence[str] | None = None,
    row_classes: Sequence[str] | None = None,
) -> None:
    """A static table that wraps.

    ``columns`` is a sequence of (heading, css class) pairs; a cell whose
    value is already marked safe by the caller passes through, everything
    else is escaped. Used for the cited sources on Tab 00, where a
    truncated quotation would undercut the entire tab.

    The markup is emitted as one line on purpose. A blank line inside a
    block of HTML ends the block as far as the markdown parser is
    concerned, and everything after it comes back on the page as escaped
    source. See ``svg`` for the same trap.
    """
    cols = (
        "<colgroup>"
        + "".join(f'<col style="width:{w}"/>' for w in widths)
        + "</colgroup>"
        if widths else ""
    )
    # The column class rides on the heading too. A right-aligned figures
    # column whose heading stays left-aligned reads as two columns.
    #
    # Built by concatenation rather than by nesting a quoted attribute
    # inside an f-string expression. Backslash escapes inside f-string
    # braces are a SyntaxError before Python 3.12, and Streamlit in
    # Snowflake pins its own interpreter.
    head = "".join(
        "<th" + (' class="' + cls + '"' if cls else "") + ">"
        + _esc(name) + "</th>"
        for name, cls in columns
    )
    body = []
    classes = list(row_classes or []) + [""] * len(rows)
    for row, row_class in zip(rows, classes):
        cells = []
        for (_name, cls), value in zip(columns, row):
            klass = f' class="{cls}"' if cls else ""
            cells.append(f"<td{klass}>{value}</td>")
        tr = f'<tr class="{row_class}">' if row_class else "<tr>"
        body.append(tr + "".join(cells) + "</tr>")
    st.markdown(
        '<div class="gp-table-scroll"><table class="gp-table">'
        + cols
        + "<thead><tr>"
        + head
        + "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table></div>",
        unsafe_allow_html=True,
    )


def link(url: str, text: str = "source") -> str:
    """An external link, or a muted dash when the URL is not recorded.

    Six of the seven citations have no canonical URL in the warehouse.
    They render as an explicit absence rather than as a dead link,
    because inventing one would defeat the point of the tab.
    """
    if not url:
        return '<span style="color:#9CA3AF">not recorded</span>'
    return f'<a href="{_esc(url)}" target="_blank" rel="noopener">{_esc(text)}</a>'


@contextlib.contextmanager
def panel():
    """A bordered container, or a plain one where border is unsupported.

    st.container gained ``border`` in Streamlit 1.29. Streamlit in
    Snowflake pins its own version and it is not ours to choose, so the
    keyword is offered and the plain container is taken if it is
    refused. Losing a border degrades the layout; raising a TypeError
    takes the whole tab down, and this build has already spent a day on
    that class of failure.
    """
    try:
        box = st.container(border=True)
    except TypeError:                        # pragma: no cover
        box = st.container()
    with box:
        yield


def readout(items: Sequence[tuple[str, str]], *, flag: str | None = None) -> None:
    """A row of figures with label tokens beneath, no border.

    Sits under a chart inside a panel, where a stat_band's own frame
    would be a second box drawn inside the first one. ``flag`` names the
    one label that should be rendered in Flag Red.
    """
    cells = "".join(
        f'<div class="gp-readout-item">'
        f'<div class="gp-readout-v{" gp-readout-v-flag" if k == flag else ""}">'
        f"{_esc(v)}</div>"
        f'<div class="gp-readout-k">{_esc(k)}</div></div>'
        for v, k in items
    )
    st.markdown(f'<div class="gp-readout">{cells}</div>', unsafe_allow_html=True)


def verdict(title: str, body: str, tone: str = "neutral") -> None:
    """The result callout after a choice has been made.

    Bold markdown was doing this job and it read as an afterthought
    rather than as the answer to the question the tab just asked.
    """
    klass = {
        "right": "gp-verdict gp-verdict-right",
        "wrong": "gp-verdict gp-verdict-wrong",
    }.get(tone, "gp-verdict")
    st.markdown(
        f'<div class="{klass}"><div class="gp-verdict-title">{_esc(title)}</div>'
        f'<div class="gp-verdict-body">{_esc(body)}</div></div>',
        unsafe_allow_html=True,
    )


def slot(inner_html: str = "") -> None:
    """A fixed-height row under a card.

    Holds a button before the reveal and a verdict chip after it. It
    reserves its height either way, so the two comparison columns never
    shift relative to one another when one of them changes.
    """
    st.markdown(f'<div class="gp-slot">{inner_html}</div>',
                unsafe_allow_html=True)
