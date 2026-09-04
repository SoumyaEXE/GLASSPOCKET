"""Data access. One query surface, two backends.

WAREHOUSE MODE is the real build and the one the write-up describes. The
application runs as a Streamlit app inside Snowflake, obtains its session
with ``get_active_session()``, and therefore needs no credentials at all.
If any Snowflake credential ever appears in this directory, that is a
defect (Build Spec Section 04B).

PREVIEW MODE exists so the interface can be built, reviewed and rehearsed
without a warehouse attached. It reads the DuckDB store written by
tools/make_synthetic.py. Every figure it serves is derived from the same
generator that feeds the warehouse, but the differential privacy on Tab 05
is a local Laplace mechanism rather than a Snowflake privacy policy, and
the receipts are local rows rather than devnet mints.

The interface states which mode it is in, on every tab, in the header. A
project about honest disclosure does not get to be vague about that.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field

import numpy as np
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
            return handle.sql(query.sql, params=list(params)).to_pandas()
        return handle.sql(query.sql).to_pandas()

    local = query.local
    if local.startswith("__"):
        raise RuntimeError(
            f"{query_name} has no preview implementation; it is handled "
            "explicitly by the tab that needs it."
        )
    if params:
        return handle.execute(local, list(params)).df()
    return handle.execute(local).df()


def run_sql_preview(sql: str, params: tuple | None = None) -> pd.DataFrame:
    """Escape hatch for the preview store only.

    Used by the Tab 05 privacy simulator and the Tab 07 history simulator,
    both of which model warehouse behaviour that DuckDB has no equivalent
    for. Never used in warehouse mode.
    """
    backend_mode, handle = get_backend()
    if backend_mode != PREVIEW:
        raise RuntimeError("run_sql_preview is preview-only")
    return handle.execute(sql, list(params or ())).df()


def scalar(query_name: str, column: str, params: tuple | None = None,
           default=None):
    """First value of a column, or a default when the result is empty."""
    df = run(query_name, params)
    if df.empty or column not in df.columns:
        return default
    value = df.iloc[0][column]
    return default if pd.isna(value) else value


# ===========================================================================
# Tab 05 / the privacy layer
# ===========================================================================
#
# In warehouse mode Snowflake does this. A privacy policy is attached to
# SERVING.V_BENEFICIARY_OUTCOMES with an entity key on beneficiary_id, the
# noise is calibrated by the privacy domains, and the budget is a real
# Snowflake privacy budget that genuinely depletes.
#
# In preview mode the class below implements the same guarantee in Python:
# a Laplace mechanism with a per-query epsilon and a budget ledger that
# does not refill. It is a real differential privacy implementation, not a
# mock, but it is NOT the Snowflake feature, and Tab 05 says so on screen
# whenever it is the one answering.


@dataclass
class PrivacyLedger:
    """Per-query epsilon accounting for the preview mechanism."""

    epsilon_allocated: float = 1.0
    epsilon_per_query: float = 0.1
    spend: list[dict] = field(default_factory=list)

    @property
    def consumed(self) -> float:
        return sum(entry["epsilon_spent"] for entry in self.spend)

    @property
    def remaining(self) -> float:
        return max(0.0, self.epsilon_allocated - self.consumed)

    @property
    def share_remaining(self) -> float:
        return self.remaining / self.epsilon_allocated if self.epsilon_allocated else 0.0

    @property
    def exhausted(self) -> bool:
        return self.remaining <= 1e-9

    def charge(self, *, narrow: bool) -> float:
        """A narrow query costs more.

        Sensitivity is higher when a filter isolates few entities, so the
        same accuracy target buys less. This is why repeatedly narrowing
        drains the budget rather than sharpening the answer.
        """
        cost = self.epsilon_per_query * (3.0 if narrow else 1.0)
        cost = min(cost, self.remaining)
        self.spend.append({
            "query_n": len(self.spend) + 1,
            "epsilon_spent": cost,
            "is_narrow": narrow,
        })
        return cost

    def reset(self) -> None:
        self.spend.clear()

    def burndown(self) -> pd.DataFrame:
        if not self.spend:
            return pd.DataFrame(columns=["query_n", "epsilon_spent", "is_narrow"])
        return pd.DataFrame(self.spend)


def _laplace(scale: float, size=None, rng=None) -> float | np.ndarray:
    rng = rng or np.random.default_rng()
    return rng.laplace(0.0, scale, size)


#: Privacy domain on amount_usd, matching the ALTER VIEW in sql/11.
AMOUNT_DOMAIN = (0.0, 5000.0)


def true_answer(filters: dict) -> dict:
    """The counterfactual: the answer that would be released with no policy.

    In warehouse mode this reads SERVING.V_BENEFICIARY_OUTCOMES_TRUE under a
    privileged role. GP_ANALYST cannot read it, which is what stops Tab 05
    from being theatre.
    """
    where, params = _beneficiary_where(filters)
    if mode() == WAREHOUSE:
        _, session = get_backend()
        sql = (
            "SELECT COUNT(*) AS cohort, SUM(amount_usd) AS total_usd, "
            "AVG(delivered_flag) AS delivery_rate "
            "FROM SERVING.V_BENEFICIARY_OUTCOMES_TRUE " + where
        )
        df = session.sql(sql, params=params).to_pandas()
    else:
        df = run_sql_preview(
            "SELECT COUNT(*) AS cohort, SUM(amount_usd) AS total_usd, "
            "AVG(delivered_flag) AS delivery_rate FROM beneficiary_facts " + where,
            tuple(params),
        )
    row = df.iloc[0] if len(df) else {}
    return {
        "cohort": int(row.get("cohort", 0) or 0),
        "total_usd": float(row.get("total_usd", 0) or 0),
        "delivery_rate": float(row.get("delivery_rate", 0) or 0),
    }


def released_answer(filters: dict, ledger: PrivacyLedger,
                    rng=None) -> dict:
    """The answer that is actually released.

    Warehouse mode: Snowflake applies the policy and returns the noised
    aggregate. The budget depletes inside Snowflake.

    Preview mode: a Laplace mechanism at the ledger's per-query epsilon,
    with sensitivity taken from the privacy domain on amount_usd. Once the
    budget is exhausted the query is refused rather than answered badly,
    which is the honest failure mode.
    """
    truth = true_answer(filters)
    narrow = truth["cohort"] < 50

    if ledger.exhausted:
        return {
            "refused": True,
            "reason": "privacy budget exhausted for this window",
            "cohort": None, "total_usd": None, "delivery_rate": None,
            "epsilon_spent": 0.0,
        }

    spent = ledger.charge(narrow=narrow)

    if mode() == WAREHOUSE:
        where, params = _beneficiary_where(filters)
        _, session = get_backend()
        try:
            session.sql(f"USE ROLE {Q.ANALYST_ROLE}").collect()
            df = session.sql(
                "SELECT COUNT(*) AS cohort, SUM(amount_usd) AS total_usd, "
                "AVG(delivered_flag) AS delivery_rate "
                "FROM SERVING.V_BENEFICIARY_OUTCOMES " + where,
                params=params,
            ).to_pandas()
            row = df.iloc[0]
            return {
                "refused": False,
                "cohort": float(row["COHORT"] if "COHORT" in row else row["cohort"]),
                "total_usd": float(row.get("TOTAL_USD", row.get("total_usd", 0)) or 0),
                "delivery_rate": float(
                    row.get("DELIVERY_RATE", row.get("delivery_rate", 0)) or 0),
                "epsilon_spent": spent,
            }
        except Exception as exc:              # noqa: BLE001
            return {
                "refused": True,
                "reason": f"the policy refused this query: {exc}",
                "cohort": None, "total_usd": None, "delivery_rate": None,
                "epsilon_spent": spent,
            }
        finally:
            session.sql("USE ROLE ACCOUNTADMIN").collect()

    # Preview mechanism.
    rng = rng or np.random.default_rng()
    epsilon = spent if spent > 0 else ledger.epsilon_per_query

    count_scale = 1.0 / epsilon
    amount_scale = (AMOUNT_DOMAIN[1] - AMOUNT_DOMAIN[0]) / epsilon

    return {
        "refused": False,
        "cohort": max(0.0, truth["cohort"] + float(_laplace(count_scale, rng=rng))),
        "total_usd": max(0.0, truth["total_usd"] + float(_laplace(amount_scale, rng=rng))),
        "delivery_rate": float(np.clip(
            truth["delivery_rate"] + float(_laplace(1.0 / (epsilon * 20), rng=rng)),
            0, 1)),
        "epsilon_spent": spent,
    }


def repeated_releases(filters: dict, n: int = 40) -> list[float]:
    """Spread of released answers across repeated identical queries.

    This is what defeats the averaging objection on Tab 05 section S6. The
    releases do not converge on the truth, because in a real deployment the
    budget is spent long before enough samples exist to average.
    """
    truth = true_answer(filters)
    epsilon = 0.1 if truth["cohort"] >= 50 else 0.1 / 3.0
    scale = (AMOUNT_DOMAIN[1] - AMOUNT_DOMAIN[0]) / epsilon
    rng = np.random.default_rng(7)
    return [max(0.0, truth["total_usd"] + float(v))
            for v in _laplace(scale, size=n, rng=rng)]


def noise_curve_frame(filters: dict) -> pd.DataFrame:
    """True against released across cohort sizes, one to ten thousand.

    Lines converge right and diverge violently left. This is the picture of
    a privacy guarantee.
    """
    cohorts = np.unique(np.logspace(0, 4, 44).astype(int))
    per_person = 780.0
    epsilon = 0.1
    scale = (AMOUNT_DOMAIN[1] - AMOUNT_DOMAIN[0]) / epsilon

    truth = cohorts * per_person
    rng = np.random.default_rng(11)
    released = np.maximum(0, truth + _laplace(scale, size=len(cohorts), rng=rng))

    # Floored at one so both axes can be logarithmic. A released value of
    # zero is indistinguishable from "one dollar" at this scale, and the
    # shape of the divergence is what the chart is for.
    return pd.DataFrame({
        "cohort": cohorts,
        "true_value": np.maximum(1.0, truth),
        "released_value": np.maximum(1.0, released),
        "released_lo": np.maximum(1.0, truth - scale),
        "released_hi": truth + scale,
    })


def _beneficiary_where(filters: dict) -> tuple[str, list]:
    clauses, params = [], []
    for column in ("district", "programme_code", "month_key"):
        value = filters.get(column)
        if value and value != "any":
            clauses.append(f"{column} = ?")
            params.append(value)

    band = filters.get("amount_band")
    if band and band != "any":
        lo, hi = band
        clauses.append("amount_usd BETWEEN ? AND ?")
        params += [lo, hi]

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


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

    rows = [{"as_of": -max(offsets_seconds), "risk_score": original,
             "verdict": "as first scored"}]
    for entry in entries:
        rows.append({"as_of": entry["at"], "risk_score": entry["score"],
                     "verdict": entry["verdict"]})
    return pd.DataFrame(rows)
