"""Data access. One query surface, two backends.

WAREHOUSE MODE is the real build and the one the write-up describes. The
application runs as a Streamlit app inside Snowflake, obtains its session
with ``get_active_session()``, and therefore needs no credentials at all.
If any Snowflake credential ever appears in this directory, that is a
defect (Build Spec Section 04B).

PREVIEW MODE exists so the interface can be built, reviewed and rehearsed
without a warehouse attached. It reads the DuckDB store written by
tools/make_synthetic.py. Every figure it serves is derived from the same
generator that feeds the warehouse, but the cohort floor on Tab 05 is
enforced in Python rather than by a Snowflake aggregation policy, and the
receipts are local rows rather than devnet mints.

THE GUARANTEE ON TAB 05 IS A MINIMUM COHORT FLOOR, NOT DIFFERENTIAL
PRIVACY. The differential privacy DDL does not parse on the target
deployment, so the build takes the fallback Section 10 specifies: an
aggregation policy with MIN_GROUP_SIZE. What that does and does not
guarantee is spelled out in sql/11_privacy_policy.sql and on the tab
itself. The Laplace machinery below is retained only for the noise-curve
illustration, which is labelled as an illustration.

The interface states which mode it is in, on every tab, in the header. A
project about honest disclosure does not get to be vague about that.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field

import pandas as pd
import streamlit as st

import queries as Q

LOCAL_STORE = pathlib.Path(__file__).parent.parent / "data" / "glasspocket.duckdb"

WAREHOUSE = "warehouse"
PREVIEW = "preview"


# ---------------------------------------------------------------------------
# backend detection
# ---------------------------------------------------------------------------


@st.cache_resource(show_spinner=False)
def get_backend() -> tuple[str, object]:
    """Return (mode, handle).

    Tries Snowflake first, because that is the real deployment target.
    """
    try:
        from snowflake.snowpark.context import get_active_session

        session = get_active_session()
        session.sql("SELECT 1").collect()
        return WAREHOUSE, session
    except Exception:                        # noqa: BLE001
        pass

    if not LOCAL_STORE.exists():
        raise RuntimeError(
            "No Snowflake session and no local preview store.\n"
            "Run: python tools/make_synthetic.py --all"
        )

    import duckdb

    return PREVIEW, duckdb.connect(str(LOCAL_STORE), read_only=True)


def mode() -> str:
    return get_backend()[0]


def is_preview() -> bool:
    return mode() == PREVIEW


# ---------------------------------------------------------------------------
# the one entry point
# ---------------------------------------------------------------------------


def normalise(df: pd.DataFrame) -> pd.DataFrame:
    """Lower-case every column name.

    THIS IS NOT COSMETIC. Snowflake returns identifiers folded to upper
    case; DuckDB returns them as written, which here is lower case. The
    application is written against one spelling, so without this every
    tab that touches a column by name works locally and dies inside the
    warehouse with a bare KeyError like 'evasion_gap'. Normalising in the
    one place every result passes through is the only way to be sure a
    tab cannot forget.
    """
    df.columns = [str(c).lower() for c in df.columns]
    return df


@st.cache_data(ttl=60, show_spinner=False)
def run(query_name: str, params: tuple | None = None) -> pd.DataFrame:
    """Execute a named query from app/queries.py.

    Cached for sixty seconds, which matches the Dynamic Table target lag,
    so a demo click never waits on the warehouse twice for the same answer.
    """
    query = Q.QUERIES[query_name]
    backend_mode, handle = get_backend()
    params = tuple(params or ())

    if backend_mode == WAREHOUSE:
        if params:
            return normalise(handle.sql(query.sql, params=list(params)).to_pandas())
        return normalise(handle.sql(query.sql).to_pandas())

    local = query.local
    if local.startswith("__"):
        raise RuntimeError(
            f"{query_name} has no preview implementation; it is handled "
            "explicitly by the tab that needs it."
        )
    if params:
        return normalise(handle.execute(local, list(params)).df())
    return normalise(handle.execute(local).df())


def run_sql_preview(sql: str, params: tuple | None = None) -> pd.DataFrame:
    """Escape hatch for the preview store only.

    Used by the Tab 05 privacy simulator and the Tab 07 history simulator,
    both of which model warehouse behaviour that DuckDB has no equivalent
    for. Never used in warehouse mode.
    """
    backend_mode, handle = get_backend()
    if backend_mode != PREVIEW:
        raise RuntimeError("run_sql_preview is preview-only")
    return normalise(handle.execute(sql, list(params or ())).df())


def scalar(query_name: str, column: str, params: tuple | None = None,
           default=None):
    """First value of a column, or a default when the result is empty."""
    df = run(query_name, params)
    if df.empty or column not in df.columns:
        return default
    value = df.iloc[0][column]
    return default if pd.isna(value) else value


# ===========================================================================
# Tab 05 / the cohort floor
# ===========================================================================
#
# THE SHIPPED GUARANTEE IS K-ANONYMITY, NOT DIFFERENTIAL PRIVACY.
#
# In warehouse mode Snowflake does this. An aggregation policy with
# MIN_GROUP_SIZE => 50 is attached to SERVING.V_BENEFICIARY_OUTCOMES with
# an entity key on beneficiary_id. Snowflake refuses any aggregate whose
# group falls below the floor, and it refuses it for GP_ANALYST however
# the query is phrased.
#
# In preview mode the same rule is applied here in Python, so both
# backends behave identically.
#
# What this does NOT do, and what the tab says plainly: it adds no noise,
# it has no budget, and it does not stop a differencing attack built from
# several large overlapping queries. Differential privacy is what defends
# against that, and the target deployment does not offer it. See
# docs/platform_constraints.md.


# ===========================================================================
# Tab 07 / the history layer
# ===========================================================================


def value_history(org_id: str, offsets_seconds: tuple[int, ...]) -> pd.DataFrame:
    """The same row at successive Time Travel offsets.

    Warehouse mode issues one AT(OFFSET => -n) per point and unions the
    results. Retention is Snowflake's own, so no additional storage is
    needed.

    Preview mode replays the local edit log, which is a simulation of the
    mechanic and is labelled as one on screen.
    """
    if mode() == WAREHOUSE:
        _, session = get_backend()
        frames = []
        for offset in offsets_seconds:
            try:
                df = session.sql(
                    "SELECT ? AS offset_seconds, risk_score, verdict "
                    f"FROM MARTS.ORG_RISK AT(OFFSET => -{int(offset)}) "
                    "WHERE org_id = ?",
                    params=[offset, org_id],
                ).to_pandas()
                frames.append(df)
            except Exception:                 # noqa: BLE001
                continue
        if not frames:
            return pd.DataFrame(columns=["as_of", "risk_score", "verdict"])
        out = pd.concat(frames, ignore_index=True)
        out.columns = [c.lower() for c in out.columns]
        out["as_of"] = -out["offset_seconds"]
        return out.sort_values("as_of")

    log = st.session_state.setdefault("gp_edit_log", {})
    entries = log.get(org_id, [])
    base = run("Q_ORG_RISK_ONE", (org_id,))
    original = float(base.iloc[0]["risk_score"]) if len(base) else 0.0

    # One row per offset, exactly as the warehouse path returns. It used
    # to emit a single baseline point plus one row per edit, so before
    # any edit the chart held one dot and the readout said "1 offsets
    # queried" underneath a caption promising six. A flat line across six
    # readings is the correct picture of a row nobody has touched, and it
    # is the picture the warehouse would draw.
    rows = [
        {"as_of": -offset, "risk_score": original, "verdict": "as first scored"}
        for offset in sorted(offsets_seconds, reverse=True)
    ]
    for entry in entries:
        rows.append({"as_of": entry["at"], "risk_score": entry["score"],
                     "verdict": entry["verdict"]})
    return pd.DataFrame(rows).sort_values("as_of").reset_index(drop=True)
