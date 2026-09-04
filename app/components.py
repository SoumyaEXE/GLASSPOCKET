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

import html
from typing import Iterable, Sequence

import streamlit as st

from theme import MAX_WIDTH  # noqa: F401  (re-exported for tab modules)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _esc(value) -> str:
    return html.escape(str(value), quote=True)


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
    label_html = (
        f'<div class="gp-identifier-label">{_esc(label)}</div>' if label else ""
    )
    st.markdown(
        f'{label_html}<div class="gp-identifier">{_esc(text)}</div>',
        unsafe_allow_html=True,
    )
    if copyable:
        # A selectable field is the copy control. st.code would force
        # monospace, so it is never used.
        st.text_input(
            label or "identifier",
            value=str(text),
            key=f"copy_{abs(hash((label, text)))}",
            label_visibility="collapsed",
        )


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


def chips(items: Iterable[tuple[str, str]]) -> None:
    st.markdown(
        " ".join(chip(text, tone) for text, tone in items), unsafe_allow_html=True
    )


# ---------------------------------------------------------------------------
# explainer, compare columns, source note
# ---------------------------------------------------------------------------


def step_explainer(steps: Sequence[tuple[str, str]]) -> None:
    """Three or four numbered blocks in a horizontal row.

    Used at the foot of most tabs to explain the mechanism in plain
    language. This is what makes the application legible to a
    non-technical judge, so the copy carries no jargon.
    """
    steps = list(steps)
    for idx, (col, (title, body)) in enumerate(
        zip(st.columns(len(steps), gap="small"), steps), start=1
    ):
        with col:
            st.markdown(
                f"""
                <div class="gp-step">
                  <div class="gp-step-n">{idx:02d}</div>
                  <div class="gp-step-title">{_esc(title)}</div>
                  <div class="gp-step-body">{_esc(body)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


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
) -> None:
    """Comparison card for Tab 01.

    Identical typography, identical field order, no visual tell whatsoever
    before the reveal. Do not colour, badge or shade the seeded one at
    that stage. Resist the urge.
    """
    klass = "gp-card"
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
