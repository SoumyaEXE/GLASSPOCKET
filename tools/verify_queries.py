"""Run the entire query surface against Snowflake and report what comes back.

    python tools/verify_queries.py

The application is written against lowercase column names because that is
what the local preview store returns. Snowflake returns them uppercase.
That mismatch is invisible until the app runs inside the warehouse, where
every tab fails at once on a KeyError, so this checks it directly.
"""
from __future__ import annotations
import pathlib, sys, re

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "tools"))

import queries as Q
import deploy
import snowflake.connector

snowflake.connector.paramstyle = "qmark"

PARAMS = {
    "Q_ORG_RISK_ONE": ("ORG_900000000",),
    "Q_PROJECTION": ("disaster relief",),
    "Q_NODE_DETAIL": ("ORG_900000000",),
    "Q_CELL_DRILLDOWN": ("872db6382ffffff",),
    "Q_RECEIPT_LOOKUP": ("none",),
    "Q_TIME_TRAVEL": ("ORG_900000000", "ORG_900000000"),
    "Q_CONFIDENCE_RANK": (None, None, None, None, 0.0),
    "Q_BENEFICIARY_PRIVATE": (None,) * 9,
    "Q_BENEFICIARY_TRUE": (None,) * 9,
    "Q_APPLY_CHANGE": None,   # a write, skipped
}

def main() -> int:
    env = deploy.load_env()
    conn = deploy.connect(env)
    cur = conn.cursor()
    cur.execute("USE WAREHOUSE GP_WH"); cur.execute("USE DATABASE GLASSPOCKET")
    cur.execute("USE SCHEMA SERVING")

    bad = 0
    for name in sorted(Q.QUERIES):
        query = Q.QUERIES[name]
        if name in PARAMS and PARAMS[name] is None:
            print(f"  skip  {name}")
            continue
        params = PARAMS.get(name, ())
        sql = query.sql
        n_placeholders = sql.count("?")
        if n_placeholders and len(params) != n_placeholders:
            params = tuple([None] * n_placeholders)
        try:
            cur.execute(sql, params if params else None)
            cols = [c[0] for c in cur.description]
            rows = cur.fetchmany(2)
            upper = [c for c in cols if c != c.lower()]
            flag = "UPPER" if upper else "     "
            print(f"  ok {flag} {name:28s} {len(rows)} rows  {cols[:5]}")
        except Exception as exc:
            bad += 1
            print(f"  FAIL       {name:28s} {' '.join(str(exc).split())[:95]}")
    cur.close(); conn.close()
    print(f"\n{bad} queries failing")
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main())
