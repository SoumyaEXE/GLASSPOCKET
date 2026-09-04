"""GLASSPOCKET design system. Build Spec Section 03.

The application must not look like a default Streamlit app. This module is
not decoration, it is a scored criterion.

Three rules carry everything here:

  1. One typeface, Geist, on every element without exception.
  2. No monospace anywhere. Not in tables, not in tooltips, not in chart
     axes. Any element that resolves to a monospaced font is a defect.
  3. Light mode only. White surfaces, ink text, colourful data.

Geist is base64-inlined because Streamlit in Snowflake enforces a Content
Security Policy that blocks fonts from any external domain (Trap 03). A
CDN link silently falls back to a system font, which is the worst kind of
failure: nothing errors, the design is just gone.
"""

from __future__ import annotations

import pathlib

import streamlit as st

ASSETS = pathlib.Path(__file__).parent / "assets"

# ---------------------------------------------------------------------------
# Colour. Section 03.
# ---------------------------------------------------------------------------

INK = "#08090B"
SNOWFLAKE_BLUE = "#29B5E8"
FLAG_RED = "#E5484D"
SOLANA_PURPLE = "#9945FF"
SOLANA_GREEN = "#14F195"
NOISE_AMBER = "#F5A623"

SURFACE = "#FFFFFF"
SURFACE_SUNKEN = "#F7F8FA"
BORDER = "#E4E7EB"
TEXT = "#16181D"
TEXT_MUTED = "#6B7280"
TRUTH = "#16181D"
NOISE = "#F5A623"
CONFIRMED_GREEN = "#17A34A"
DEEP_TEAL = "#0F7B8A"
ORCHID = "#B45BD6"
NEUTRAL = "#6B7280"

#: Ordered categorical palette. Use it IN ORDER, never shuffled, so the same
#: category keeps the same colour across all eleven tabs. Every value is
#: checked for legibility on white.
CATEGORICAL = [
    SNOWFLAKE_BLUE,     # 1 verified, plausible, primary series
    SOLANA_PURPLE,      # 2 on-chain, receipts
    NOISE_AMBER,        # 3 privacy noise, uncertainty, seeded data
    FLAG_RED,           # 4 needs a second look, unaccounted
    CONFIRMED_GREEN,    # 5 delivered, receipt found
    DEEP_TEAL,          # 6 fourth and later categorical series
    ORCHID,             # 7 fifth categorical series
    NEUTRAL,            # 8 baseline, context, everything unremarkable
]

#: Semantic assignments. Colour carries meaning strictly: a red bar always
#: means flagged, an amber line always means privacy noise.
TONE = {
    "verified": SNOWFLAKE_BLUE,
    "seeded": NOISE_AMBER,
    "flagged": FLAG_RED,
    "chain": SOLANA_PURPLE,
    "confirmed": CONFIRMED_GREEN,
    "neutral": NEUTRAL,
}

# ---------------------------------------------------------------------------
# Spacing, radius, type scale. No arbitrary values.
# ---------------------------------------------------------------------------

SPACE = (4, 8, 12, 16, 24, 32, 48, 64)
MAX_WIDTH = 1180

TYPE_SCALE = {
    #  token      size  weight  tracking     use
    "display": ("44px", 800, "-0.035em"),  # tab hero numbers
    "title":   ("28px", 700, "-0.03em"),   # tab titles
    "heading": ("18px", 650, "-0.02em"),   # section headings inside a tab
    "body":    ("14px", 400, "-0.005em"),  # paragraphs and table cells
    "label":   ("11px", 600, "0.09em"),    # metric captions, chart eyebrows
    "data":    ("13px", 500, "0"),         # identifiers, hashes, SQL
}


GLOBAL_CSS = """
/* ---------------------------------------------------------------------
   ABSOLUTE RULE / NO MONOSPACE
   Every selector Streamlit can produce, including the ones that force
   monospace by default (code, pre, kbd, samp, st.code, st.json), is
   pulled onto Geist. Tabular figures are on globally so numerals in
   tables and identifiers align in columns.
   --------------------------------------------------------------------- */
html, body, [class*="css"], [data-testid], button, input, textarea, select,
code, pre, kbd, samp, tt, .stMarkdown, .stDataFrame, .stTable,
.js-plotly-plot, .plotly, .stCodeBlock, .stJson, .stTooltipContent,
[data-testid="stMetricValue"], [data-testid="stMetricLabel"],
.deck-tooltip, .modebar {
  font-family: 'Geist Variable', 'Geist', -apple-system, BlinkMacSystemFont, sans-serif !important;
  font-feature-settings: 'tnum' 1, 'cv01' 1;
  font-variant-ligatures: none;
}

h1, h2, h3, h4 { letter-spacing: -0.028em; font-weight: 650; }

#MainMenu, footer, header { visibility: hidden; }

.block-container {
  padding-top: 2.4rem;
  padding-bottom: 4rem;
  max-width: 1180px;
}

/* Light mode only. A viewer with dark Snowsight still sees the intended
   design; we do not inherit their preference. Charts carry the colour,
   the page does not. */
:root, body, .stApp, [data-testid="stAppViewContainer"] {
  background: #FFFFFF !important;
  color: #16181D !important;
  color-scheme: light !important;
}

/* --------------------------------- shell -------------------------- */
.gp-shell {
  display: flex; align-items: center; justify-content: space-between;
  gap: 16px; padding: 0 0 16px 0; border-bottom: 1px solid #E4E7EB;
  margin-bottom: 8px;
}
.gp-wordmark {
  font-size: 18px; font-weight: 700; letter-spacing: -0.02em; color: #08090B;
}
.gp-shell-chips { display: flex; gap: 8px; }

/* Persistent disclosure banner. Present on all eleven tabs. */
.gp-banner {
  display: flex; align-items: center; gap: 8px;
  border: 1px solid #E4E7EB; border-left: 3px solid #F5A623;
  background: #F7F8FA; border-radius: 6px;
  padding: 10px 14px; margin: 0 0 24px 0;
  font-size: 13px; font-weight: 500; color: #16181D;
}

/* ---------------------------------- hero -------------------------- */
.gp-hero { margin: 8px 0 32px 0; }
.gp-hero-value {
  font-size: 44px; font-weight: 800; letter-spacing: -0.035em;
  line-height: 1.05; color: #08090B;
}
.gp-hero-caption {
  font-size: 11px; font-weight: 600; letter-spacing: 0.09em;
  text-transform: uppercase; color: #6B7280; margin-top: 10px;
  max-width: 720px; line-height: 1.55;
}
.gp-tab-title {
  font-size: 28px; font-weight: 700; letter-spacing: -0.03em;
  color: #08090B; margin: 0 0 4px 0;
}
.gp-tab-standfirst {
  font-size: 14px; font-weight: 400; color: #6B7280;
  margin: 0 0 24px 0; max-width: 760px; line-height: 1.6;
}
.gp-section {
  font-size: 18px; font-weight: 650; letter-spacing: -0.02em;
  color: #08090B; margin: 32px 0 12px 0;
}
.gp-eyebrow {
  font-size: 11px; font-weight: 600; letter-spacing: 0.09em;
  text-transform: uppercase; color: #6B7280; margin: 24px 0 8px 0;
}

/* ------------------------------- stat band ------------------------ */
.gp-stat {
  border: 1px solid #E4E7EB; border-radius: 6px; padding: 16px;
  background: #FFFFFF; height: 100%;
}
.gp-stat-value {
  font-size: 24px; font-weight: 700; letter-spacing: -0.03em; color: #08090B;
}
.gp-stat-caption {
  font-size: 11px; font-weight: 600; letter-spacing: 0.09em;
  text-transform: uppercase; color: #6B7280; margin-top: 6px; line-height: 1.5;
}

/* ------------------------------ identifier ------------------------ */
/* The replacement for st.code, and the reason no monospace appears. */
.gp-identifier {
  display: inline-block; background: #F7F8FA; border: 1px solid #E4E7EB;
  border-radius: 4px; padding: 6px 10px;
  font-size: 13px; font-weight: 500; letter-spacing: 0;
  font-feature-settings: 'tnum' 1; color: #16181D;
  word-break: break-all; max-width: 100%;
}
.gp-identifier-label {
  font-size: 11px; font-weight: 600; letter-spacing: 0.09em;
  text-transform: uppercase; color: #6B7280; margin-bottom: 4px;
}
.gp-sql {
  background: #F7F8FA; border: 1px solid #E4E7EB; border-radius: 6px;
  padding: 14px 16px; font-size: 13px; font-weight: 500; line-height: 1.65;
  color: #16181D; white-space: pre-wrap; overflow-x: auto;
  font-feature-settings: 'tnum' 1;
}

/* --------------------------------- chips -------------------------- */
.gp-chip {
  display: inline-flex; align-items: center; gap: 6px;
  border-radius: 999px; padding: 4px 11px;
  font-size: 11px; font-weight: 600; letter-spacing: 0.06em;
  text-transform: uppercase; border: 1px solid transparent; white-space: nowrap;
}
.gp-chip-verified  { background: #EAF7FD; color: #0E7FA8; border-color: #BEE5F6; }
.gp-chip-seeded    { background: #FEF6E7; color: #9A6410; border-color: #F8E0B0; }
.gp-chip-flagged   { background: #FDECEC; color: #B02427; border-color: #F6C6C7; }
.gp-chip-chain     { background: #F3EAFF; color: #6D25C4; border-color: #DFC9FA; }
.gp-chip-confirmed { background: #E8F6EC; color: #10702F; border-color: #BFE5CA; }
.gp-chip-neutral   { background: #F7F8FA; color: #4B5563; border-color: #E4E7EB; }

/* ---------------------------- comparison cards -------------------- */
.gp-card {
  border: 1px solid #E4E7EB; border-radius: 6px; padding: 20px;
  background: #FFFFFF; height: 100%;
}
.gp-card-reveal-verified { border: 1px solid #29B5E8; box-shadow: none; }
.gp-card-reveal-seeded   { border: 1px solid #E5484D; box-shadow: none; }
.gp-card-name {
  font-size: 18px; font-weight: 650; letter-spacing: -0.02em;
  color: #08090B; line-height: 1.35; margin-bottom: 8px;
}
.gp-card-meta {
  font-size: 11px; font-weight: 600; letter-spacing: 0.09em;
  text-transform: uppercase; color: #6B7280; margin-bottom: 12px;
}
.gp-card-blurb { font-size: 14px; color: #16181D; line-height: 1.6; }

/* Reveal animation. One of only two permitted animations, ~400 ms. */
@keyframes gpReveal {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}
.gp-reveal { animation: gpReveal 400ms cubic-bezier(0.22, 0.61, 0.36, 1) both; }

/* ------------------------------- explainer ------------------------ */
.gp-step {
  border: 1px solid #E4E7EB; border-radius: 6px; padding: 16px; height: 100%;
}
.gp-step-n {
  font-size: 11px; font-weight: 600; letter-spacing: 0.09em; color: #29B5E8;
  margin-bottom: 8px;
}
.gp-step-title {
  font-size: 14px; font-weight: 650; color: #08090B; margin-bottom: 6px;
}
.gp-step-body { font-size: 13px; color: #6B7280; line-height: 1.6; }

/* ----------------------------- source note ------------------------ */
.gp-source {
  font-size: 11px; font-weight: 500; color: #6B7280;
  margin-top: 8px; line-height: 1.6;
}
.gp-source a { color: #6B7280; text-decoration: underline; }
.gp-provenance {
  border-top: 1px solid #E4E7EB; margin-top: 48px; padding-top: 16px;
  font-size: 11px; font-weight: 500; color: #6B7280; line-height: 1.7;
}

/* ---------------------- compare columns (true vs private) --------- */
.gp-compare {
  border: 1px solid #E4E7EB; border-radius: 6px; padding: 20px; height: 100%;
}
.gp-compare-truth { border-left: 3px solid #16181D; }
.gp-compare-noise { border-left: 3px solid #F5A623; }
.gp-compare-label {
  font-size: 11px; font-weight: 600; letter-spacing: 0.09em;
  text-transform: uppercase; color: #6B7280; margin-bottom: 12px;
}
.gp-compare-value {
  font-size: 28px; font-weight: 700; letter-spacing: -0.03em; color: #08090B;
}
.gp-compare-value-noise { color: #9A6410; }
.gp-compare-sub { font-size: 13px; color: #6B7280; margin-top: 6px; }

/* --------------------------- streamlit chrome --------------------- */
/* Native tabs, restyled. No default chrome is visible anywhere. */
.stTabs [data-baseweb="tab-list"] {
  gap: 2px; border-bottom: 1px solid #E4E7EB; overflow-x: auto;
}
.stTabs [data-baseweb="tab"] {
  height: 42px; padding: 0 14px; background: transparent;
  font-size: 13px; font-weight: 500; color: #6B7280; border-radius: 0;
}
.stTabs [aria-selected="true"] {
  color: #08090B !important; font-weight: 650;
  border-bottom: 2px solid #29B5E8;
}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {
  display: none;
}

div[data-testid="stDataFrame"] { border: 1px solid #E4E7EB; border-radius: 6px; }
div[data-testid="stDataFrame"] * { font-size: 13px !important; }

.stButton > button {
  border: 1px solid #E4E7EB; border-radius: 4px; background: #FFFFFF;
  color: #16181D; font-size: 13px; font-weight: 500; padding: 6px 14px;
  box-shadow: none;
}
.stButton > button:hover { border-color: #29B5E8; color: #0E7FA8; }
.stButton > button[kind="primary"] {
  background: #29B5E8; border-color: #29B5E8; color: #FFFFFF;
}

/* Elevation: none. Separation comes from a single 1px border. */
div[data-testid="stExpander"] {
  border: 1px solid #E4E7EB; border-radius: 6px; box-shadow: none;
}
hr { border: none; border-top: 1px solid #E4E7EB; margin: 32px 0; }

/* Progress bars carry budget state, so they are amber not the theme colour. */
.gp-meter {
  height: 6px; background: #F7F8FA; border-radius: 999px;
  border: 1px solid #E4E7EB; overflow: hidden;
  margin: 12px 0 28px 0; max-width: 520px;
}
.gp-meter-fill { height: 100%; background: #F5A623; }
.gp-meter-fill-blue { background: #29B5E8; }
"""


@st.cache_data(show_spinner=False)
def _font_css() -> str:
    """Read the generated stylesheet once per session.

    Generated by tools/build_font_css.py and committed to the repository.
    If it is missing, the application still runs but every element falls
    back to a system sans-serif, which fails the Section 11 craft checks.
    """
    path = ASSETS / "geist.css"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def inject_theme() -> None:
    """Inject fonts and the global override.

    Must be the very first Streamlit call after page configuration.
    """
    font_css = _font_css()
    st.markdown(f"<style>{font_css}{GLOBAL_CSS}</style>", unsafe_allow_html=True)

    if not font_css:
        st.warning(
            "Geist is not embedded. Run `python tools/build_font_css.py` before "
            "recording. Without it the application falls back to a system font "
            "and fails the Section 11 craft checks."
        )
