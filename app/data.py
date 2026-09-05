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


@dataclass
class PrivacyLedger:
    """Query accounting for the preview mechanism.

    Retained because Tab 05 still reports how many questions have been
    asked and how many were refused. It is NOT a differential privacy
    budget: the shipped guarantee has no budget, which is one of the
    things the tab says out loud.
    """

    spend: list[dict] = field(default_factory=list)


    def record(self, *, refused: bool, cohort: int) -> None:
        """Log one question and whether the policy refused it.

        There is no budget to draw down under a minimum-cohort guarantee,
        so this is a query log rather than an accounting ledger. Tab 05
        says as much: a floor that never depletes is exactly what leaves
        the differencing attack open.
        """
        self.spend.append({
            "query_n": len(self.spend) + 1,
            "cohort": int(cohort),
            "refused": bool(refused),
        })

    @property
    def asked(self) -> int:
        return len(self.spend)

    @property
    def refused(self) -> int:
        return sum(1 for e in self.spend if e["refused"])

    def reset(self) -> None:
        self.spend.clear()

    def log(self) -> pd.DataFrame:
        if not self.spend:
            return pd.DataFrame(columns=["query_n", "cohort", "refused"])
        return pd.DataFrame(self.spend)


def true_answer(filters: dict) -> dict:
    """The counterfactual: the answer that would be released with no policy.

    In warehouse mode this reads PRIVILEGED.V_BENEFICIARY_OUTCOMES_TRUE under a
    privileged role. GP_ANALYST cannot read it, which is what stops Tab 05
    from being theatre.

    THE COHORT IS COUNTED IN PEOPLE, NOT IN ROWS.

        This used to be COUNT(*), and the tab underneath it claimed the
        floor was counted "by beneficiary rather than by row, so one
        person contributing many rows does not satisfy it alone". On this
        corpus COUNT(*) is 8,545 against 7,275 actual beneficiaries, so
        the headline overstated the group by 1,270 people and the claim
        printed under the chart was false about the number above it.

        The policy in the warehouse is defined on an ENTITY KEY over
        beneficiary_id, so Snowflake was already counting people. Only
        the display and the preview's own floor were counting rows. The
        protected view answers COUNT(DISTINCT beneficiary_id) perfectly
        well, so both sides now count the thing the guarantee is about.
    """
    where, params = _beneficiary_where(filters)
    if mode() == WAREHOUSE:
        _, session = get_backend()
        sql = (
            "SELECT COUNT(DISTINCT beneficiary_id) AS cohort, "
            "COUNT(*) AS records, SUM(amount_usd) AS total_usd, "
            "AVG(delivered_flag) AS delivery_rate "
            "FROM PRIVILEGED.V_BENEFICIARY_OUTCOMES_TRUE " + where
        )
        df = normalise(session.sql(sql, params=params).to_pandas())
    else:
        df = run_sql_preview(
            "SELECT COUNT(DISTINCT beneficiary_id) AS cohort, "
            "COUNT(*) AS records, SUM(amount_usd) AS total_usd, "
            "AVG(delivered_flag) AS delivery_rate FROM beneficiary_facts " + where,
            tuple(params),
        )
    row = df.iloc[0] if len(df) else {}
    return {
        "cohort": int(row.get("cohort", 0) or 0),
        "records": int(row.get("records", 0) or 0),
        "total_usd": float(row.get("total_usd", 0) or 0),
        "delivery_rate": float(row.get("delivery_rate", 0) or 0),
    }


def released_answer(filters: dict, ledger: "PrivacyLedger",
                    rng=None) -> dict:
    """The answer that is actually released.

    Warehouse mode: the query runs as GP_ANALYST against the view the
    aggregation policy is attached to. If the group falls below the floor
    Snowflake raises, and that refusal IS the guarantee working. It is
    reported as a refusal rather than quietly replaced with something
    friendlier.

    Preview mode: the same floor, applied here, so both backends agree.

    Note what does not happen: nothing is perturbed. Above the floor the
    released value is exact. That is the honest difference between a
    minimum-cohort guarantee and a differential privacy one.
    """
    truth = true_answer(filters)
    floor = cohort_floor()
    below_floor = truth["cohort"] < floor

    ledger.record(refused=below_floor, cohort=truth["cohort"])

    if mode() == WAREHOUSE:
        where, params = _beneficiary_where(filters)
        _, session = get_backend()
        try:
            session.sql(f"USE ROLE {Q.ANALYST_ROLE}").collect()
            # Secondary roles default to ALL, which would keep
            # ACCOUNTADMIN active and quietly exempt this query
            # from the policy it is meant to be testing.
            session.sql("USE SECONDARY ROLES NONE").collect()
            df = session.sql(
                "SELECT COUNT(DISTINCT beneficiary_id) AS cohort, "
                "SUM(amount_usd) AS total_usd, "
                "AVG(delivered_flag) AS delivery_rate "
                "FROM SERVING.V_BENEFICIARY_OUTCOMES " + where,
                params=params,
            ).to_pandas()
            df.columns = [c.lower() for c in df.columns]
            row = df.iloc[0]

            # Snowflake does not raise when a group falls below the floor.
            # It returns NULL for the aggregate, which is the same refusal
            # wearing different clothes. Treating a NULL as a zero here
            # would turn a withheld answer into a confident wrong one,
            # which is the single worst thing this tab could do.
            if pd.isna(row["cohort"]) or pd.isna(row["total_usd"]):
                return {
                    "refused": True,
                    "reason": (f"the aggregation policy withheld this answer: "
                               f"the group holds fewer than {floor} beneficiaries"),
                    "cohort": None, "total_usd": None, "delivery_rate": None,
                    "floor": floor, "exact": False,
                }

            return {
                "refused": False,
                "cohort": float(row["cohort"]),
                "total_usd": float(row["total_usd"] or 0),
                "delivery_rate": float(row["delivery_rate"] or 0),
                "floor": floor,
                "exact": True,
            }
        except Exception as exc:              # noqa: BLE001
            return {
                "refused": True,
                "reason": _refusal_reason(exc, floor),
                "cohort": None, "total_usd": None, "delivery_rate": None,
                "floor": floor, "exact": False,
            }
        finally:
            session.sql("USE ROLE ACCOUNTADMIN").collect()
            session.sql("USE SECONDARY ROLES ALL").collect()

    if below_floor:
        return {
            "refused": True,
            "reason": (f"the aggregation policy refused this query: the group "
                       f"holds fewer than {floor} beneficiaries"),
            "cohort": None, "total_usd": None, "delivery_rate": None,
            "floor": floor, "exact": False,
        }

    return {
        "refused": False,
        "cohort": float(truth["cohort"]),
        "total_usd": float(truth["total_usd"]),
        "delivery_rate": float(truth["delivery_rate"]),
        "floor": floor,
        "exact": True,
    }


def _refusal_reason(exc: Exception, floor: int) -> str:
    text = " ".join(str(exc).split())
    lowered = text.lower()
    if "aggregation" in lowered or "group" in lowered or "policy" in lowered:
        return (f"Snowflake refused this query: the group holds fewer than "
                f"{floor} beneficiaries")
    return f"Snowflake refused this query: {text[:160]}"


def cohort_floor() -> int:
    """The minimum group size the policy enforces, read from the object."""
    try:
        return int(scalar("Q_COHORT_FLOOR", "min_group_size", default=50))
    except Exception:                         # noqa: BLE001
        return 50


def cohort_landscape() -> pd.DataFrame:
    """Every question this tab can be asked, and whether it gets answered.

    THIS REPLACED A CHART THAT WAS DRAWN RATHER THAN MEASURED.

        floor_curve built a log range of imaginary cohort sizes, multiplied
        each one by a hard-coded 780 dollars per person, and drew the
        result as "value against cohort size". It ignored the filters it
        was passed, it plotted a straight line on a log-log axis because
        a constant times x is a straight line on a log-log axis, and the
        780 was not measured from anything. In an application that spends
        eleven tabs arguing that a number should be traceable to a query,
        the centrepiece was illustrating its own rule with invented data.

        What is actually available is better. The three filters make 613
        distinct questions, and every one of them has a real cohort. The
        landscape returns all of them with the number of filters applied,
        so the chart can show where the wall falls across the whole
        space of questions rather than across a made-up one.

    Read from the privileged twin on purpose: the point is to show the
    refused questions as well as the permitted ones, and the protected
    view by definition cannot report the refused ones.
    """
    return run("Q_COHORT_LANDSCAPE")


def differencing_demo(filters: dict) -> dict | None:
    """The attack a cohort floor does not stop.

    Two groups that both clear the floor, one contained in the other, are
    each answerable. Their difference can be far smaller than the floor.
    This is the honest limitation of k-anonymity and the reason
    differential privacy exists, so the tab demonstrates it rather than
    claiming a guarantee the build does not have.
    """
    floor = cohort_floor()
    base = {k: v for k, v in filters.items() if k != "amount_band"}
    where, params = _beneficiary_where(base)
    joiner = " AND " if where else " WHERE "

    def agg(threshold: float) -> dict | None:
        sql = ("SELECT COUNT(DISTINCT beneficiary_id) AS cohort, "
               "SUM(amount_usd) AS total_usd "
               "FROM {obj} " + where + joiner + "amount_usd >= ?")
        try:
            if mode() == WAREHOUSE:
                _, session = get_backend()
                df = normalise(session.sql(
                    sql.format(obj="PRIVILEGED.V_BENEFICIARY_OUTCOMES_TRUE"),
                    params=params + [threshold],
                ).to_pandas())
            else:
                df = run_sql_preview(sql.format(obj="beneficiary_facts"),
                                     tuple(params + [threshold]))
            df.columns = [c.lower() for c in df.columns]
            row = df.iloc[0]
            return {"cohort": int(row["cohort"] or 0),
                    "total_usd": float(row["total_usd"] or 0)}
        except Exception:                     # noqa: BLE001
            return None

    group_a = agg(0.0)
    if not group_a or group_a["cohort"] < floor * 2:
        return None

    # Walk the threshold up until the two groups differ by fewer people
    # than the floor while both still clear it.
    #
    # THE FIRST RUNG IS A DOLLAR, AND IT USED NOT TO BE THERE.
    #
    #     The ladder started at 250 and the section it feeds was dead:
    #     differencing_demo returned None on every scope the tab could
    #     reach, so the most important argument on the centrepiece tab
    #     rendered as "widen the filters to see the differencing attack
    #     this floor cannot prevent" and never showed it.
    #
    #     The reason is in the corpus rather than in the attack. Amounts
    #     cluster, so moving a threshold from nothing to 250 dollars
    #     drops 348 people at once, and 348 is well above the floor: the
    #     two groups were never close enough together. What is close
    #     together is "everyone" against "everyone who received anything
    #     at all", because the people between them are exactly the ones
    #     who received nothing. Within a single district that is between
    #     thirteen and thirty-five people, which is below the floor on
    #     every district in the corpus.
    #
    #     A dollar is also a better rung on its own terms. It is not an
    #     arbitrary cut chosen to make the attack work; it is the
    #     boundary between having been helped and not having been, and
    #     the group it isolates is the group an attacker would want.
    for threshold in (1.0, 100.0, 250.0, 500.0, 750.0, 1000.0, 1500.0):
        group_b = agg(threshold)
        if not group_b or group_b["cohort"] < floor:
            continue
        gap = group_a["cohort"] - group_b["cohort"]
        if 0 < gap < floor:
            return {
                "floor": floor,
                "threshold": threshold,
                "group_a": group_a,
                "group_b": group_b,
                "difference_people": gap,
                "difference_usd": group_a["total_usd"] - group_b["total_usd"],
            }
    return None


@st.cache_data(ttl=60, show_spinner=False)
def differencing_scopes(filters: dict, limit: int = 6) -> list[dict]:
    """Scopes where the attack lands, most specific first.

    The gap between "everyone here" and "everyone here who received
    anything" scales with the size of the scope, so on the whole corpus
    it is 348 people and comfortably above the floor, while inside any
    one district it is between thirteen and thirty-five and comfortably
    below it. Which scopes work is therefore a property of the data, and
    the tab reports the ones that do rather than asking the reader to
    hunt for them with the filter controls.

    Cached, and it needs to be. Probing a district costs two aggregates,
    so an uncached search over sixteen of them would put thirty-two round
    trips on a render path in warehouse mode. The limit stops the walk as
    soon as enough scopes have been found to make the point.
    """
    found = []
    demo = differencing_demo(filters)
    if demo is not None:
        demo["scope"] = _scope_label(filters)
        found.append(demo)

    if filters.get("district") in (None, "any"):
        try:
            options = run("Q_FILTER_OPTIONS")
            districts = sorted(options["district"].dropna().unique().tolist())
        except Exception:                     # noqa: BLE001
            districts = []
        for district in districts:
            if len(found) >= limit:
                break
            probe = dict(filters, district=district, amount_band="any")
            demo = differencing_demo(probe)
            if demo is not None:
                demo["scope"] = _scope_label(probe)
                found.append(demo)
    return found


def _scope_label(filters: dict) -> str:
    parts = [str(filters[k]) for k in ("district", "programme_code", "month_key")
             if filters.get(k) and filters.get(k) != "any"]
    return " · ".join(parts) if parts else "the whole corpus"


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
