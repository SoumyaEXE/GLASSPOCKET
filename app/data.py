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

    Used by the Tab 05 privacy simulator and the Tab 07 history
    simulator, both of which model warehouse behaviour DuckDB has no
    equivalent for. Never used in warehouse mode.
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
# Tab 05 / the privacy layer
# ===========================================================================
#
# THREE OBJECTS, ONE SET OF FACTS, THREE ANSWERS.
#
#   PRIVILEGED.V_BENEFICIARY_OUTCOMES_TRUE   no policy
#   SERVING.V_BENEFICIARY_OUTCOMES           aggregation policy, k = 50
#   SERVING.V_BENEFICIARY_DP                 privacy policy, epsilon 0.1
#
# The build shipped for a weekend with only the first two, on the
# recorded finding that the differential privacy DDL was absent from
# this deployment. That finding was a syntax error in the probe rather
# than a capability report: there is no CREATE PRIVACY BUDGET statement
# in Snowflake for the account to be missing, and the attach clause is
# ADD PRIVACY POLICY rather than SET. Written correctly it works, and
# sql/11b_differential_privacy.sql is the deployed proof.
#
# EVERYTHING HERE COUNTS PEOPLE, NEVER ROWS, and that is now enforced
# from two directions. The aggregation policy has an ENTITY KEY on
# beneficiary_id, so Snowflake was already counting entities. The
# privacy engine goes further and refuses COUNT(*) outright with
#
#     210007 ... have an infinite multiplier
#
# because a beneficiary holds up to five rows here and the query must
# deduplicate on the entity key itself. COUNT(DISTINCT beneficiary_id)
# is the only shape that passes, which happens to be the only shape
# that was ever the right question.


#: MEASURED AGAINST THE WAREHOUSE, NEVER DERIVED.
#:
#:   25 repeats, unfiltered count, true 8,113
#:       mean 8,115.4, sd 9.3, range 8,096 to 8,136
#:   25 repeats, one district, true 393
#:       mean 388.6, sd 11.1
#:   30 repeats of the differencing pair, true gap 12
#:       mean 14.8, sd 18.2, range -27 to +51
#:
#: The noise is additive and roughly constant in absolute terms, which
#: is what makes it negligible on a large group and ruinous on a small
#: one. A cohort of four comes back as anything between zero and thirty.
#:
#: THE PAIR FIGURE IS MEASURED RATHER THAN COMPUTED FROM THE SINGLE ONE.
#:   Two independent draws would give 9.3 times root two, or 13.2. The
#:   observed 18.2 is larger, because the filtered side of the pair is
#:   noisier than the unfiltered one and the sensitivity is not identical
#:   across the two queries. Using the measurement rather than the
#:   textbook composition keeps the attack arithmetic on the tab honest,
#:   and it moves the answer against this build rather than for it.
#:
#: The preview simulator uses the single-query figure to shape its
#: Laplace draw so the two backends behave alike. Snowflake does not
#: publish its calibration, so none of this is back-solved into a
#: claimed epsilon.
DP_MEASURED_SD = 9.3
DP_MEASURED_PAIR_SD = 18.2

#: Per-query epsilon and total budget, as declared in the policy body.
DP_EPSILON = 0.1
DP_BUDGET_LIMIT = 300


@dataclass
class PrivacyLedger:
    """Query accounting, kept per session.

    Under the aggregation policy this is a query LOG and nothing more:
    nothing is drawn down, so a refused query costs an attacker a retry
    and a permitted one costs nothing at all. Under the privacy policy
    the same list is a real ledger, because Snowflake charges epsilon
    for every aggregate whether or not the answer was useful.

    The tab shows both readings of the same list side by side, which is
    the cheapest honest way to say what a budget is for.
    """

    spend: list[dict] = field(default_factory=list)

    def record(self, *, refused: bool, cohort: int, mechanism: str) -> None:
        self.spend.append({
            "query_n": len(self.spend) + 1,
            "cohort": int(cohort),
            "refused": bool(refused),
            "mechanism": mechanism,
        })

    @property
    def asked(self) -> int:
        return len(self.spend)

    @property
    def refused(self) -> int:
        return sum(1 for e in self.spend if e["refused"])

    @property
    def epsilon_spent(self) -> float:
        """What the same questions would have cost under the budget."""
        return sum(DP_EPSILON for e in self.spend
                   if e["mechanism"] != "true")

    def reset(self) -> None:
        self.spend.clear()

    def log(self) -> pd.DataFrame:
        if not self.spend:
            return pd.DataFrame(
                columns=["query_n", "cohort", "refused", "mechanism"])
        return pd.DataFrame(self.spend)


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


def cohort_floor() -> int:
    """The minimum group size the aggregation policy enforces."""
    try:
        return int(scalar("Q_COHORT_FLOOR", "min_group_size", default=50))
    except Exception:                         # noqa: BLE001
        return 50


def true_answer(filters: dict) -> dict:
    """The counterfactual: what would be released with no policy at all.

    Warehouse mode reads PRIVILEGED.V_BENEFICIARY_OUTCOMES_TRUE under a
    privileged role. GP_ANALYST has no USAGE on that schema, which is
    what stops this column from being a second query the analyst could
    have run for themselves.

    THE COHORT IS COUNTED IN PEOPLE, NOT IN ROWS. It used to be
    COUNT(*), which read 8,545 against 7,275 actual beneficiaries while
    the caption underneath claimed the floor counted people. Both sides
    count DISTINCT beneficiary_id now, which is the thing all three
    guarantees are actually about.
    """
    where, params = _beneficiary_where(filters)
    if mode() == WAREHOUSE:
        _, session = get_backend()
        df = normalise(session.sql(
            "SELECT COUNT(DISTINCT beneficiary_id) AS cohort, "
            "COUNT(*) AS records, SUM(amount_usd) AS total_usd, "
            "AVG(delivered_flag) AS delivery_rate "
            "FROM PRIVILEGED.V_BENEFICIARY_OUTCOMES_TRUE " + where,
            params=params,
        ).to_pandas())
    else:
        df = run_sql_preview(
            "SELECT COUNT(DISTINCT beneficiary_id) AS cohort, "
            "COUNT(*) AS records, SUM(amount_usd) AS total_usd, "
            "AVG(delivered_flag) AS delivery_rate FROM beneficiary_facts "
            + where, tuple(params))
    row = df.iloc[0] if len(df) else {}
    return {
        "cohort": int(row.get("cohort", 0) or 0),
        "records": int(row.get("records", 0) or 0),
        "total_usd": float(row.get("total_usd", 0) or 0),
        "delivery_rate": float(row.get("delivery_rate", 0) or 0),
    }


def _as_analyst(session, sql: str, params: list):
    """Run one statement as the analyst persona and restore the session.

    USE ROLE is not enough. Snowflake users default to
    DEFAULT_SECONDARY_ROLES = ('ALL'), so after switching primary role
    the session still carries ACCOUNTADMIN underneath and privilege
    checks are evaluated against the union. The policy would still see
    GP_ANALYST in CURRENT_ROLE() and apply correctly, while everything
    the policy exists to protect stayed readable. Both guarantees on
    this tab are tested through this function for that reason.
    """
    try:
        session.sql(f"USE ROLE {Q.ANALYST_ROLE}").collect()
        session.sql("USE SECONDARY ROLES NONE").collect()
        df = session.sql(sql, params=params).to_pandas()
        df.columns = [c.lower() for c in df.columns]
        return df
    finally:
        session.sql("USE ROLE ACCOUNTADMIN").collect()
        session.sql("USE SECONDARY ROLES ALL").collect()


def released_answer(filters: dict, ledger: "PrivacyLedger") -> dict:
    """The answer the AGGREGATION POLICY releases.

    Above the floor it is the true value to the cent. Below it,
    Snowflake withholds. Note the shape of the withholding: it does not
    raise, it returns NULL for the aggregate, which is the same refusal
    wearing different clothes. Reading that NULL as a zero would turn a
    withheld answer into a confident wrong one, which is the single
    worst thing this tab could do.
    """
    truth = true_answer(filters)
    floor = cohort_floor()
    below = truth["cohort"] < floor
    ledger.record(refused=below, cohort=truth["cohort"], mechanism="cohort")

    if mode() == WAREHOUSE:
        where, params = _beneficiary_where(filters)
        _, session = get_backend()
        try:
            df = _as_analyst(
                session,
                "SELECT COUNT(DISTINCT beneficiary_id) AS cohort, "
                "SUM(amount_usd) AS total_usd, "
                "AVG(delivered_flag) AS delivery_rate "
                "FROM SERVING.V_BENEFICIARY_OUTCOMES " + where,
                params)
            row = df.iloc[0]
            if pd.isna(row["cohort"]) or pd.isna(row["total_usd"]):
                return {"refused": True, "exact": False, "floor": floor,
                        "cohort": None, "total_usd": None,
                        "reason": ("the aggregation policy withheld this "
                                   f"answer: fewer than {floor} beneficiaries")}
            return {"refused": False, "exact": True, "floor": floor,
                    "cohort": float(row["cohort"]),
                    "total_usd": float(row["total_usd"] or 0)}
        except Exception as exc:              # noqa: BLE001
            return {"refused": True, "exact": False, "floor": floor,
                    "cohort": None, "total_usd": None,
                    "reason": _refusal_reason(exc, floor)}

    if below:
        return {"refused": True, "exact": False, "floor": floor,
                "cohort": None, "total_usd": None,
                "reason": (f"the aggregation policy refused this query: "
                           f"the group holds fewer than {floor} beneficiaries")}
    return {"refused": False, "exact": True, "floor": floor,
            "cohort": float(truth["cohort"]),
            "total_usd": float(truth["total_usd"])}


def dp_answer(filters: dict, ledger: "PrivacyLedger | None" = None,
              seed: int | None = None) -> dict:
    """The answer the PRIVACY POLICY releases.

    It never refuses and it is never exact. Warehouse mode runs the one
    query shape the privacy engine accepts, as GP_ANALYST, against
    SERVING.V_BENEFICIARY_DP. Preview mode draws Laplace noise shaped to
    the standard deviation measured from the warehouse, and every
    caption that renders a preview figure says so.

    NOT CACHED, DELIBERATELY. Every other read in this module is cached
    for sixty seconds. Caching this one would hide the entire point: ask
    the same question twice and the answer moves, because a second
    sample is a second draw and a second charge against the budget.
    """
    truth_cohort = None
    if mode() == WAREHOUSE:
        where, params = _beneficiary_where(filters)
        _, session = get_backend()
        try:
            df = _as_analyst(
                session,
                "SELECT COUNT(DISTINCT beneficiary_id) AS cohort "
                "FROM SERVING.V_BENEFICIARY_DP " + where,
                params)
            cohort = float(df.iloc[0]["cohort"] or 0)
            out = {"refused": False, "exact": False, "cohort": cohort,
                   "simulated": False}
        except Exception as exc:              # noqa: BLE001
            return {"refused": True, "exact": False, "cohort": None,
                    "simulated": False,
                    "reason": " ".join(str(exc).split())[:200]}
    else:
        import numpy as np

        truth_cohort = true_answer(filters)["cohort"]
        rng = np.random.default_rng(seed)
        # Laplace scale from the measured standard deviation: for
        # Laplace(b) the variance is 2b squared, so b = sd / sqrt(2).
        draw = rng.laplace(0.0, DP_MEASURED_SD / (2 ** 0.5))
        out = {"refused": False, "exact": False, "simulated": True,
               "cohort": max(0.0, round(truth_cohort + draw))}

    if ledger is not None:
        ledger.record(refused=False, cohort=int(out["cohort"] or 0),
                      mechanism="dp")
    out["epsilon"] = DP_EPSILON
    return out


def _refusal_reason(exc: Exception, floor: int) -> str:
    text = " ".join(str(exc).split())
    lowered = text.lower()
    if "aggregation" in lowered or "group" in lowered or "policy" in lowered:
        return (f"Snowflake refused this query: the group holds fewer than "
                f"{floor} beneficiaries")
    return f"Snowflake refused this query: {text[:160]}"


def cohort_landscape() -> pd.DataFrame:
    """Every question the three filters can ask, at its real cohort."""
    return run("Q_COHORT_LANDSCAPE")


def qi_cells() -> pd.DataFrame:
    """Cell sizes over the quasi-identifier, smallest first."""
    return run("Q_QI_CELLS")


@st.cache_data(ttl=60, show_spinner=False)
def qi_profile() -> dict:
    """How identifying the microdata is, before any policy touches it.

    District, programme and month name nobody individually. The three
    together are a quasi-identifier, and this measures how well they
    single people out: the k of k-anonymity, counted from the corpus
    rather than asserted by a policy.

    The result is the argument for the floor being as blunt as it is.
    It is not that fifty is a cautious number; it is that the data is
    sparse enough that almost nothing clears it.
    """
    cells = qi_cells()
    if cells.empty:
        return {}
    total_people = int(true_answer({})["cohort"])
    out = {
        "cells": int(len(cells)),
        "people": total_people,
        "median_k": float(cells["k"].median()),
        "max_k": int(cells["k"].max()),
        "singletons": int((cells["k"] == 1).sum()),
        "under_5": int((cells["k"] < 5).sum()),
        "under_floor": int((cells["k"] < cohort_floor()).sum()),
    }
    out["singleton_share"] = (out["singletons"] / out["cells"]
                              if out["cells"] else 0.0)
    return out


@st.cache_data(ttl=120, show_spinner=False)
def differencing_sweep(limit_scopes: int = 60) -> pd.DataFrame:
    """Every pair of permitted questions whose difference is a group
    the floor would never have answered about.

    THIS REPLACED A SECTION THAT WAS DEAD ON EVERY PATH.

        The old version computed one demonstration against whatever the
        live filters happened to be, and printed "widen the filters to
        see the attack" whenever it came back empty. On this corpus it
        always came back empty, because the whole-corpus gap is hundreds
        of people, well above the floor. So the most important argument
        on the centrepiece tab never rendered.

        The gap scales with the scope. Across the whole corpus it is far
        above the floor; inside a single district it is between twelve
        and forty-eight, which is below it on every district that leaks.
        Which scopes work is a property of the data, so the sweep finds
        them rather than asking a reader to hunt with filter controls.

    The threshold ladder starts at a dollar, and the first rung matters.
    It is not an arbitrary cut picked to make the attack work: it is the
    boundary between having been helped and not having been, so the
    group it isolates is exactly the group an attacker would want.
    """
    floor = cohort_floor()
    thresholds = (1.0, 100.0, 250.0, 500.0, 750.0, 1000.0, 1500.0, 2000.0)

    if mode() == WAREHOUSE:
        _, session = get_backend()

        def counts(column: str | None):
            select = f"{column} AS scope, " if column else "'the whole corpus' AS scope, "
            group = f"GROUP BY {column}" if column else ""
            cases = ", ".join(
                f"COUNT(DISTINCT CASE WHEN amount_usd >= {t} "
                f"THEN beneficiary_id END) AS t{i}"
                for i, t in enumerate(thresholds))
            return normalise(session.sql(
                f"SELECT {select} COUNT(DISTINCT beneficiary_id) AS base, "
                f"{cases} FROM PRIVILEGED.V_BENEFICIARY_OUTCOMES_TRUE {group}"
            ).to_pandas())
    else:
        def counts(column: str | None):
            select = f"{column} AS scope, " if column else "'the whole corpus' AS scope, "
            group = f"GROUP BY {column}" if column else ""
            cases = ", ".join(
                f"COUNT(DISTINCT CASE WHEN amount_usd >= {t} "
                f"THEN beneficiary_id END) AS t{i}"
                for i, t in enumerate(thresholds))
            return run_sql_preview(
                f"SELECT {select} COUNT(DISTINCT beneficiary_id) AS base, "
                f"{cases} FROM beneficiary_facts {group}")

    # One statement per dimension rather than two per scope. The naive
    # version issued a round trip for every scope and every rung, which
    # on forty districts and eight thresholds is 656 queries on a render
    # path. Conditional aggregation collapses each dimension to one.
    frames = []
    for column, dim in ((None, "whole corpus"), ("district", "district"),
                        ("programme_code", "programme"),
                        ("month_key", "month")):
        try:
            df = counts(column)
        except Exception:                     # noqa: BLE001
            continue
        df["dimension"] = dim
        frames.append(df)
    if not frames:
        return pd.DataFrame()

    wide = pd.concat(frames, ignore_index=True)
    rows = []
    for _, r in wide.iterrows():
        base = int(r["base"] or 0)
        if base < floor:
            continue
        for i, t in enumerate(thresholds):
            narrowed = int(r.get(f"t{i}", 0) or 0)
            gap = base - narrowed
            if narrowed >= floor and 0 < gap < floor:
                rows.append({
                    "scope": str(r["scope"]), "dimension": r["dimension"],
                    "threshold": t, "everyone": base,
                    "received_something": narrowed, "learned_about": gap,
                })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    # One row per scope, at the rung that isolates the smallest group,
    # because a reader wants the worst case rather than eight variations
    # of the same one.
    out = (out.sort_values(["scope", "learned_about"])
              .drop_duplicates("scope", keep="first")
              .sort_values("learned_about")
              .head(limit_scopes)
              .reset_index(drop=True))
    return out


def dp_attack_trial(filters: dict, threshold: float = 1.0,
                    trials: int = 8) -> pd.DataFrame:
    """Run the differencing attack repeatedly through the privacy policy.

    Each trial issues the same two permitted queries the aggregation
    policy answers exactly, and subtracts them. Under the floor the
    recovered gap is the same number every time. Under the budget it is
    a different number every time, and the tab plots both against the
    truth.

    Kept small by default. Every trial is two warehouse round trips
    through the privacy engine, which is slower than an ordinary
    aggregate because it is doing real work.
    """
    wide = dict(filters, amount_band="any")
    narrow = dict(wide)
    rows = []
    for n in range(trials):
        a = dp_answer(wide, seed=None if mode() == WAREHOUSE else 1000 + n * 2)
        b = dp_answer(dict(narrow, amount_band=(threshold, 10 ** 9)),
                      seed=None if mode() == WAREHOUSE else 1001 + n * 2)
        if a.get("cohort") is None or b.get("cohort") is None:
            continue
        rows.append({"trial": n + 1,
                     "everyone": float(a["cohort"]),
                     "received_something": float(b["cohort"]),
                     "recovered": float(a["cohort"]) - float(b["cohort"])})
    return pd.DataFrame(rows)


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
