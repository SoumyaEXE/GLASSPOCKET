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

#MainMenu, footer { visibility: hidden; }
/* The header stays, because it carries the control that collapses the
   rail, but it is made transparent so it reads as empty space rather
   than as chrome. Collapsing it to zero height leaves the collapse
   button's icon ligature stranded on the page. */
header[data-testid="stHeader"] {
  background: transparent !important;
  border: none !important;
}

.block-container {
  padding-top: 1.6rem;
  padding-bottom: 4rem;
  /* Centred column beside the rail. Wide enough for a hex map and a pair
     of side-by-side charts, narrow enough that body text stays readable.
     Streamlit's own 6rem side padding is removed and replaced with 28px,
     because with the rail already taking 288px the default leaves a
     dead margin on both edges wide enough to read as a layout mistake.
     Prose blocks carry their own max-width instead, which is where the
     readability limit actually belongs. */
  max-width: 1360px;
  padding-left: 28px;
  padding-right: 28px;
  margin-left: auto;
  margin-right: auto;
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
  /* Two lines' worth, always. One card whose caption wraps must not end
     up taller than the four beside it. */
  min-height: 33px;
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
/* A file path is not a label token. It keeps its own casing, because
   sql/07_clone_detection.sql upper-cased is no longer a path. */
.gp-chip-file {
  background: #F7F8FA; color: #4B5563; border-color: #E4E7EB;
  text-transform: none; letter-spacing: 0; font-weight: 500;
  font-size: 11px; font-feature-settings: 'tnum' 1;
}

/* A chart legend rendered on the panel head rather than inside the
   figure. Plotly's own legend sits above the plot and pushes it down by
   its own height; this one sits on a line that already exists, so two
   panels in a row still end level with one another. */
.gp-swatch {
  display: inline-flex; align-items: center; gap: 6px; margin-left: 12px;
  font-size: 11px; font-weight: 600; letter-spacing: 0.06em;
  text-transform: uppercase; color: #6B7280; white-space: nowrap;
}
.gp-swatch i { width: 8px; height: 8px; border-radius: 2px; display: inline-block; }

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
/* One grid rather than a row of Streamlit columns. Grid items stretch
   to the tallest in their row for free, which is the whole reason the
   explainer is not laid out with st.columns any more, and auto-fit wraps
   five cards onto two lines instead of crushing them. */
.gp-steps {
  display: grid; gap: 12px; align-items: stretch;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
}
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


/* =====================================================================
   THE LEFT RAIL
   Carries the eleven moves in order, so the shape of the argument is
   always visible and a viewer can see how far through it they are. A
   horizontal tab strip cannot do that once it starts scrolling.
   ===================================================================== */
section[data-testid="stSidebar"] {
  background: #FFFFFF;
  border-right: 1px solid #E4E7EB;
  width: 288px !important;
}
section[data-testid="stSidebar"] > div {
  padding: 24px 18px 32px 18px;
}

.gp-rail-brand { margin-bottom: 28px; }
.gp-rail-mark {
  font-size: 17px; font-weight: 700; letter-spacing: -0.02em; color: #08090B;
}
.gp-rail-sub {
  font-size: 11px; font-weight: 500; color: #6B7280;
  margin-top: 4px; line-height: 1.5;
}
.gp-rail-eyebrow {
  font-size: 10px; font-weight: 600; letter-spacing: 0.11em;
  text-transform: uppercase; color: #9CA3AF;
  margin: 22px 0 10px 0;
}
/* The one-line description of the section being read. It is a caption,
   not a control, so it must not wear a box that makes it look like a
   text field sitting in the navigation. */
.gp-rail-move {
  font-size: 12px; color: #9CA3AF; line-height: 1.5;
  margin: 14px 2px 4px 2px; font-style: normal;
}
.gp-rail-state { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 2px; }
.gp-rail-state .gp-chip { margin: 0; }
.gp-rail-foot {
  font-size: 11px; color: #9CA3AF; line-height: 1.6; margin-top: 24px;
  padding-top: 16px; border-top: 1px solid #E4E7EB;
}
/* The rail scrolls independently, so its last line is not stranded
   under the viewport edge. */
section[data-testid="stSidebar"] > div { padding-bottom: 48px; }

/* The rail is a stack of buttons, not a radio.
   Streamlit's radio renders through baseweb, whose internal structure
   differs between versions, so styling it depends on selectors that can
   silently stop matching. That is a bad trade for the one control the
   whole application is navigated with, and worse inside Snowflake where
   the version is not ours to pick and a broken selector cannot be
   iterated on. A button is a button in every version. */
section[data-testid="stSidebar"] .stButton > button {
  width: 100%;
  text-align: left;
  justify-content: flex-start;
  padding: 8px 11px;
  margin: 0 0 1px 0;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: #4B5563;
  font-size: 13px;
  font-weight: 500;
  font-feature-settings: 'tnum' 1;
  box-shadow: none;
  min-height: 0;
  line-height: 1.4;
}
section[data-testid="stSidebar"] .stButton > button:hover {
  background: #F7F8FA; color: #16181D; border-color: transparent;
}
section[data-testid="stSidebar"] .stButton > button:focus {
  box-shadow: none; outline: none;
}
/* The section being read. Snowflake Blue, because that is what active
   means everywhere else in this interface. */
section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
  background: #EAF7FD; border-color: #BEE5F6; color: #0E7FA8;
  font-weight: 650;
}
section[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
  background: #DFF2FC; color: #0E7FA8;
}
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0; }
/* Streamlit centres a button's label in an inner element, so aligning
   the button alone leaves the text in the middle of the row. */
section[data-testid="stSidebar"] .stButton > button > div,
section[data-testid="stSidebar"] .stButton > button p {
  text-align: left !important;
  width: 100%;
  justify-content: flex-start;
}

/* The deploy button and toolbar are local-development chrome. They do
   not appear in Streamlit in Snowflake, and they should not appear in a
   screenshot either. */
[data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"] { display: none !important; }

/* =====================================================================
   MATERIAL SYMBOLS LIGATURES
   Streamlit draws its icons with the Material Symbols font and the icon
   NAME as the element text, relying on the font's ligatures to turn
   "keyboard_arrow_down" into a glyph. Inside Snowflake that font cannot
   be fetched, because the Content Security Policy blocks external font
   hosts (Trap 03, the same rule that forces Geist to be inlined here).
   The ligature never resolves, so the raw name renders as words, and
   every expander header reads "keyboard_double_arrow_right" on top of
   its own label.

   There is nothing to restyle: the glyph does not exist. So the icon
   elements are removed and the controls are given affordances that do
   not depend on a font arriving. */
[data-testid="stIconMaterial"],
.material-icons, .material-icons-outlined, .material-symbols-outlined,
[data-testid="stExpanderToggleIcon"] { display: none !important; }

[data-testid="stSidebarCollapseButton"],
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapsedControl"] { display: none !important; }

/* An expander needs to look openable without an icon font. A caret drawn
   in CSS costs nothing and cannot fail to load. */
[data-testid="stExpander"] summary,
[data-testid="stExpander"] details > div:first-child {
  position: relative; padding-right: 26px;
}
[data-testid="stExpander"] summary::after {
  content: ""; position: absolute; right: 12px; top: 50%;
  width: 7px; height: 7px; margin-top: -5px;
  border-right: 1.5px solid #6B7280; border-bottom: 1.5px solid #6B7280;
  transform: rotate(45deg); transition: transform 120ms ease;
}
[data-testid="stExpander"] details[open] summary::after {
  transform: rotate(-135deg); margin-top: -2px;
}

/* --------------------------- streamlit chrome --------------------- */
/* Native tabs are still used inside a section here and there, so they
   keep their styling even though navigation moved to the rail. */
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

/* =====================================================================
   PANELS, DIAGRAMS AND THE STAGE INSPECTOR
   ===================================================================== */

/* A hand-authored SVG renders inline rather than as a data URI, so it
   inherits the embedded Geist. See components.svg for why the markup is
   collapsed to a single line before it gets here. */
.gp-svg { display: block; width: 100%; line-height: 0; }
.gp-svg svg { display: block; width: 100%; height: auto; overflow: visible; }
.gp-visually-hidden {
  position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
  overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0;
}

/* A bordered surface a chart or a diagram sits inside. Two columns
   holding different kinds of content still read as one row when both
   wear the same frame. */
.gp-panel {
  border: 1px solid #E4E7EB; border-radius: 8px;
  padding: 18px 20px 16px 20px; background: #FFFFFF; height: 100%;
}
.gp-panel-tight { padding: 16px 18px 8px 18px; }
.gp-panel-head {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; margin-bottom: 14px;
  /* A chip is taller than a label token. Reserving the chip's height on
     every head keeps two side-by-side panels on the same internal grid
     whether or not either of them carries one. */
  min-height: 26px;
}
.gp-panel-note-slot { display: flex; align-items: center; }
.gp-panel-title {
  font-size: 13px; font-weight: 650; letter-spacing: -0.01em; color: #08090B;
}
.gp-panel-note {
  font-size: 10px; font-weight: 600; letter-spacing: 0.11em;
  text-transform: uppercase; color: #9CA3AF; white-space: nowrap;
}

/* Key/value rows. Used by the stage inspector under the system map. */
.gp-kv {
  display: flex; align-items: baseline; justify-content: space-between;
  gap: 16px; padding: 9px 0; border-bottom: 1px solid #F0F2F4;
  font-size: 13px; line-height: 1.45;
}
.gp-kv:last-child { border-bottom: none; }
.gp-kv-k { color: #6B7280; }
.gp-kv-v {
  color: #08090B; font-weight: 600; text-align: right;
  font-feature-settings: 'tnum' 1;
}
.gp-kv-list { margin-top: 2px; }

/* The prose that explains a stage. Held to a readable measure even
   though the column it sits in is wide. */
.gp-note { font-size: 13px; color: #4B5563; line-height: 1.65; max-width: 68ch; }
.gp-note strong { color: #08090B; font-weight: 650; }

/* The stage selector. Streamlit's segmented control ships with a pill
   look that does not match anything else here, so it is flattened onto
   the same 1px-border language as every other surface. */
div[data-testid="stSegmentedControl"] button {
  border-radius: 6px !important; border: 1px solid #E4E7EB !important;
  background: #FFFFFF !important; color: #4B5563 !important;
  font-size: 12px !important; font-weight: 600 !important;
  letter-spacing: 0.06em; text-transform: uppercase;
  padding: 7px 14px !important; box-shadow: none !important;
}
div[data-testid="stSegmentedControl"] button[aria-checked="true"],
div[data-testid="stSegmentedControl"] button[kind="segmented_controlActive"] {
  background: #EAF7FD !important; border-color: #BEE5F6 !important;
  color: #0E7FA8 !important;
}

/* Streamlit stacks 1rem between every element in a column. Inside a
   panel that reads as a hole, so blocks tagged as compact close it. */
.gp-compact + div [data-testid="stVerticalBlock"] { gap: 0.4rem; }

/* ------------------------------ static table ---------------------- */
/* st.dataframe truncates any cell it cannot fit. On a tab whose entire
   argument is that the figures are quotable, a truncated quotation is
   the one thing that cannot be allowed, so the cited-source list is a
   plain table that wraps instead. */
.gp-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.gp-table th {
  text-align: left; font-size: 10px; font-weight: 600; letter-spacing: 0.11em;
  text-transform: uppercase; color: #9CA3AF; padding: 0 14px 8px 14px;
  border-bottom: 1px solid #E4E7EB; vertical-align: bottom;
}
.gp-table td {
  padding: 13px 14px; border-bottom: 1px solid #F0F2F4;
  vertical-align: top; line-height: 1.55; color: #16181D;
}
/* A row that is shaded needs its text to clear the shading, and the
   marker rule on a differing row has to be part of the box rather than
   painted over it: an inset shadow sat on top of the first cell's own
   text. The transparent border on every other row keeps the first
   column on one vertical line whether the row is marked or not. */
.gp-table th:first-child,
.gp-table td:first-child {
  border-left: 3px solid transparent; padding-left: 11px;
}
.gp-table tr:last-child td { border-bottom: none; }
.gp-table td.gp-td-muted { color: #6B7280; }
.gp-table td.gp-td-nowrap { white-space: nowrap; color: #6B7280; }
.gp-table a { color: #0E7FA8; text-decoration: underline; }
.gp-table-scroll { overflow-x: auto; }
/* The record diff on Tab 01. A field that matches is muted so the eye
   goes straight to the two that do not, which is the whole finding. */
/* Not qualified with td: the caller wraps a cell value in a span so the
   shading and the emphasis can sit on the value rather than the cell. */
.gp-table .gp-td-field {
  display: inline-block; padding-top: 2px;
  font-size: 11px; font-weight: 600; letter-spacing: 0.09em;
  text-transform: uppercase; color: #9CA3AF; white-space: nowrap;
}
.gp-table .gp-td-same { color: #9CA3AF; }
.gp-table .gp-td-diff { color: #08090B; font-weight: 600; }
.gp-table tr.gp-tr-diff td { background: #FDF4F4; }
.gp-table tr.gp-tr-diff td:first-child { border-left-color: #E5484D; }

/* ======================================================================
   TAB 01 / the choice
   ================================================================== */

/* Both comparison cards must be exactly the same height whatever the
   mission line says, or the taller one reads as the important one and
   the test is over before it starts. */
.gp-card-choice { min-height: 156px; }

/* The action slot under each card. It holds a button before the reveal
   and a verdict after it, and it reserves its own height either way so
   the two columns never shift relative to one another. */
.gp-slot { min-height: 34px; display: flex; align-items: center; gap: 8px;
           margin: 10px 0 2px 0; }
.gp-slot-pick {
  font-size: 11px; font-weight: 600; letter-spacing: 0.09em;
  text-transform: uppercase; color: #08090B;
}

/* The result callout. One line, full width, stated plainly. */
.gp-verdict {
  border: 1px solid #E4E7EB; border-left: 3px solid #6B7280;
  border-radius: 6px; padding: 14px 18px; background: #FFFFFF;
}
.gp-verdict-right { border-left-color: #17A34A; background: #F7FCF8; }
.gp-verdict-wrong { border-left-color: #E5484D; background: #FEF8F8; }
.gp-verdict-title {
  font-size: 15px; font-weight: 650; letter-spacing: -0.015em; color: #08090B;
}
.gp-verdict-body {
  font-size: 13px; color: #4B5563; line-height: 1.6; margin-top: 5px;
  max-width: 76ch;
}

/* A figure and its label, sitting under a chart inside a panel. */
/* The bottom margin is not decoration. A readout is followed by a
   paragraph often enough that without it the label tokens and the
   first line of prose sit on top of one another. */
.gp-readout {
  display: flex; gap: 28px; flex-wrap: wrap;
  margin-top: 4px; margin-bottom: 12px;
}
.gp-readout-item { min-width: 96px; }
.gp-readout-v {
  font-size: 20px; font-weight: 700; letter-spacing: -0.03em; color: #08090B;
  font-feature-settings: 'tnum' 1;
}
.gp-readout-v-flag { color: #B02427; }
.gp-readout-k {
  font-size: 10px; font-weight: 600; letter-spacing: 0.11em;
  text-transform: uppercase; color: #9CA3AF; margin-top: 3px;
}

/* ------------------------------------------------------------------
   Tab 02. Ranked tables of figures, and the trust bands.
   ------------------------------------------------------------------ */

/* Figures right-align on a tabular rail. The class sits on the heading
   as well as on the cell, or the column reads as two columns. */
.gp-table th.gp-td-num,
.gp-table td.gp-td-num {
  text-align: right; white-space: nowrap;
  font-feature-settings: 'tnum' 1;
}
.gp-table td.gp-td-num { color: #08090B; font-weight: 600; }
.gp-table .gp-td-rank {
  display: inline-block; min-width: 20px;
  font-size: 11px; font-weight: 700; color: #9CA3AF;
  font-feature-settings: 'tnum' 1;
}
.gp-table .gp-td-where {
  display: block; font-size: 11px; color: #9CA3AF; margin-top: 3px;
}
.gp-table .gp-td-lead { color: #08090B; font-weight: 600; }

/* A row of controls that has to sit on the panel's own baseline. */
.gp-control-label {
  font-size: 10px; font-weight: 600; letter-spacing: 0.11em;
  text-transform: uppercase; color: #9CA3AF; margin: 0 0 6px 0;
}
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
