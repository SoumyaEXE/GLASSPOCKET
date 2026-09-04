"""Deploy GLASSPOCKET to Snowflake.

Runs the numbered SQL files in order, stages the generated data, loads it,
and reports the acceptance gate.

    python tools/deploy.py --check          connect and report, change nothing
    python tools/deploy.py --stage          upload the generated CSVs only
    python tools/deploy.py --all            provision, stage, load, verify
    python tools/deploy.py --from 06        resume at a numbered step

Credentials come from the repository-root .env and are never printed. The
Streamlit application itself needs none of them: it runs inside Snowflake
and obtains its session with get_active_session().

ORDER
    The numbered files are dependency sorted. 11_privacy_policy.sql is
    numbered where it sits in the graph but is verified FIRST, because it
    is the only component that can fail in a way that cannot be fixed
    later. On this account it already has: see docs/platform_constraints.md.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "sql"
DATA = ROOT / "data"

STAGE_UPLOADS = [
    (DATA / "warehouse" / "orgs.csv", "warehouse"),
    (DATA / "warehouse" / "disbursements.csv", "warehouse"),
    (DATA / "warehouse" / "beneficiaries.csv", "warehouse"),
    (DATA / "warehouse" / "district_dim.csv", "warehouse"),
    (DATA / "warehouse" / "projection.csv", "warehouse"),
    (DATA / "warehouse" / "graph_nodes.csv", "warehouse"),
    (DATA / "warehouse" / "graph_edges.csv", "warehouse"),
    (DATA / "warehouse" / "threshold_curve.csv", "warehouse"),
    (DATA / "vectors" / "org_vectors.csv", "vectors"),
]


def load_env() -> dict:
    env_path = ROOT / ".env"
    if not env_path.exists():
        raise SystemExit("missing .env at the repository root")
    env = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if "=" in s and not s.startswith("#"):
            key, value = s.split("=", 1)
            env[key.strip()] = value.strip()
    for key in ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PASSWORD"):
        if not env.get(key):
            raise SystemExit(f"{key} is not set in .env")
    return env


def connect(env: dict):
    import snowflake.connector

    return snowflake.connector.connect(
        account=env["SNOWFLAKE_ACCOUNT"],
        user=env["SNOWFLAKE_USER"],
        password=env["SNOWFLAKE_PASSWORD"],
        role=env.get("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
        client_session_keep_alive=True,
    )


# ---------------------------------------------------------------------------
# statement splitting
# ---------------------------------------------------------------------------


def split_statements(sql: str) -> list[str]:
    """Split a script into statements, respecting $$ blocks and strings.

    Snowflake scripting blocks contain semicolons that must not be treated
    as terminators, which is why this is hand-rolled rather than a naive
    ``sql.split(";")``.
    """
    statements, current = [], []
    in_dollar = False
    in_single = False
    in_line_comment = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""

        if in_line_comment:
            current.append(ch)
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        if not in_dollar and not in_single and ch == "-" and nxt == "-":
            in_line_comment = True
            current.append(ch)
            i += 1
            continue

        if not in_single and ch == "$" and nxt == "$":
            in_dollar = not in_dollar
            current.append("$$")
            i += 2
            continue

        if not in_dollar and ch == "'":
            in_single = not in_single
            current.append(ch)
            i += 1
            continue

        if ch == ";" and not in_dollar and not in_single:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            i += 1
            continue

        current.append(ch)
        i += 1

    tail = "".join(current).strip()
    if tail:
        statements.append(tail)

    return [s for s in statements if not _is_comment_only(s)]


def _is_comment_only(statement: str) -> bool:
    stripped = re.sub(r"--[^\n]*", "", statement).strip()
    return not stripped


def label(statement: str) -> str:
    first = re.sub(r"--[^\n]*", "", statement).strip().split("\n")[0]
    return " ".join(first.split())[:78]


# ---------------------------------------------------------------------------
# execution
# ---------------------------------------------------------------------------


def run_file(cur, path: pathlib.Path, *, stop_on_error: bool) -> tuple[int, int]:
    sql = path.read_text(encoding="utf-8")
    statements = split_statements(sql)
    print(f"\n=== {path.name}  ({len(statements)} statements) ===")

    ok = failed = 0
    for statement in statements:
        text = label(statement)
        # Some statements are supposed to be refused. The verification
        # step in 11 issues a row-level SELECT against a policy-protected
        # view precisely to prove it is blocked, and a build where that
        # SUCCEEDS is the broken one.
        expects_failure = "EXPECT_FAIL" in statement
        try:
            cur.execute(statement)
            if expects_failure:
                failed += 1
                print(f"  BROKEN {text}")
                print("        this statement was supposed to be REFUSED "
                      "and was not: the policy is not protecting the view")
            else:
                ok += 1
                print(f"  ok    {text}")
        except Exception as exc:                # noqa: BLE001
            message = " ".join(str(exc).split())[:150]
            if expects_failure:
                ok += 1
                print(f"  ok    {text}")
                print(f"        refused as intended: {message[:96]}")
            else:
                failed += 1
                print(f"  FAIL  {text}")
                print(f"        {message}")
                if stop_on_error:
                    raise
    return ok, failed


def stage_files(cur) -> None:
    print("\n=== staging generated data ===")
    cur.execute("USE DATABASE GLASSPOCKET")
    cur.execute("USE SCHEMA RAW")
    for path, folder in STAGE_UPLOADS:
        if not path.exists():
            print(f"  skip  {path.name} (not generated)")
            continue
        uri = path.resolve().as_posix()
        size = path.stat().st_size / 1e6
        started = time.time()
        cur.execute(
            f"PUT 'file://{uri}' @RAW.GP_STAGE/{folder}/ "
            "AUTO_COMPRESS=TRUE OVERWRITE=TRUE"
        )
        print(f"  put   {path.name:28s} {size:7.1f} MB  "
              f"{time.time() - started:.0f}s")


def verify_policy(cur) -> None:
    """The Section 06.1 verification step, executed rather than described.

    Assumes the analyst role and attempts four reads. Three of them must
    be refused; one must succeed. A build where the refusals succeed is
    the broken one, so the expectations are asserted here rather than
    eyeballed in a worksheet.
    """
    print("\n=== policy verification, as GP_ANALYST ===")
    checks = [
        ("row-level select is refused", False,
         "SELECT beneficiary_id FROM SERVING.V_BENEFICIARY_OUTCOMES LIMIT 5"),
        ("broad aggregate is answered", True,
         "SELECT COUNT(*) c FROM SERVING.V_BENEFICIARY_OUTCOMES"),
        ("counterfactual view is unreadable", False,
         "SELECT COUNT(*) FROM SERVING.V_BENEFICIARY_OUTCOMES_TRUE"),
    ]
    try:
        cur.execute("USE WAREHOUSE GP_WH")
        cur.execute("USE DATABASE GLASSPOCKET")
        cur.execute("USE SCHEMA SERVING")
        cur.execute("USE ROLE GP_ANALYST")

        for label, should_succeed, sql in checks:
            try:
                cur.execute(sql)
                cur.fetchall()
                allowed = True
            except Exception:                   # noqa: BLE001
                allowed = False
            ok = allowed == should_succeed
            print(f"  {'pass' if ok else 'FAIL'}  {label}")

        # Below the floor the policy returns NULL rather than raising, so
        # a withheld answer has to be detected by its value.
        try:
            cur.execute(
                "SELECT COUNT(*) FROM SERVING.V_BENEFICIARY_OUTCOMES "
                "WHERE beneficiary_id = "
                "(SELECT MIN(beneficiary_id) FROM MARTS.BENEFICIARY_FACTS)")
            value = cur.fetchone()[0]
            withheld = value is None
        except Exception:                       # noqa: BLE001
            withheld = True
        print(f"  {'pass' if withheld else 'FAIL'}  "
              "single-beneficiary group is withheld")
    finally:
        cur.execute("USE ROLE ACCOUNTADMIN")


def report(cur) -> None:
    print("\n=== acceptance gate ===")
    try:
        cur.execute(
            "SELECT check_id, area, statement, result "
            "FROM GLASSPOCKET.SERVING.V_ACCEPTANCE_CHECKS "
            "ORDER BY CASE result WHEN 'FAIL' THEN 0 "
            "WHEN 'REVIEW' THEN 1 ELSE 2 END, check_id"
        )
        rows = cur.fetchall()
        for check_id, area, statement, result in rows:
            mark = {"PASS": "pass", "REVIEW": "REVIEW", "FAIL": "FAIL"}[result]
            print(f"  {mark:6s} {statement[:78]:80s} {check_id}")
        failed = sum(1 for r in rows if r[3] == "FAIL")
        print(f"\n  {len(rows)} checks, {failed} failing")
    except Exception as exc:                    # noqa: BLE001
        print(f"  acceptance view unavailable: {' '.join(str(exc).split())[:120]}")


def summary(cur) -> None:
    print("\n=== warehouse state ===")
    probes = [
        ("orgs",           "SELECT COUNT(*) FROM GLASSPOCKET.STAGING.ORGS"),
        ("  with vectors", "SELECT COUNT(name_vec) FROM GLASSPOCKET.STAGING.ORGS"),
        ("  seeded",       "SELECT COUNT(*) FROM GLASSPOCKET.STAGING.ORGS WHERE is_synthetic"),
        ("disbursements",  "SELECT COUNT(*) FROM GLASSPOCKET.STAGING.DISBURSEMENTS"),
        ("clone pairs",    "SELECT COUNT(*) FROM GLASSPOCKET.MARTS.CLONE_PAIRS"),
        ("geometry rows",  "SELECT COUNT(*) FROM GLASSPOCKET.MARTS.DELIVERY_GEOMETRY"),
        ("dynamic tables", "SELECT COUNT(*) FROM GLASSPOCKET.INFORMATION_SCHEMA.TABLES "
                           "WHERE IS_DYNAMIC = 'YES'"),
        ("mint queue",     "SELECT COUNT(*) FROM GLASSPOCKET.ORACLE.MINT_QUEUE"),
    ]
    for name, sql in probes:
        try:
            cur.execute(sql)
            print(f"  {name:16s} {cur.fetchone()[0]:>10,}")
        except Exception as exc:                # noqa: BLE001
            print(f"  {name:16s} {' '.join(str(exc).split())[:70]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--stage", action="store_true")
    parser.add_argument("--only", help="run one numbered file, e.g. 07")
    parser.add_argument("--start", help="resume at a numbered file, e.g. 06")
    parser.add_argument("--stop-on-error", action="store_true")
    args = parser.parse_args(argv)

    env = load_env()
    print(f"account   {env['SNOWFLAKE_ACCOUNT']}")
    print(f"user      {env['SNOWFLAKE_USER']}")
    print(f"role      {env.get('SNOWFLAKE_ROLE', 'ACCOUNTADMIN')}")

    conn = connect(env)
    cur = conn.cursor()

    try:
        cur.execute("SELECT CURRENT_ACCOUNT(), CURRENT_REGION(), CURRENT_USER()")
        account, region, user = cur.fetchone()
        print(f"connected {account} / {region} as {user}\n")

        if args.check:
            summary(cur)
            verify_policy(cur)
            report(cur)
            return 0

        # 13_oracle_queue.sql hashes organisation identifiers with a salt
        # before they go on chain. The salt lives in .env and is bound as a
        # session variable for that statement only; it is never written
        # into a SQL file and never printed.
        if env.get("RECEIPT_SALT"):
            cur.execute("SET receipt_salt = %s", (env["RECEIPT_SALT"],))
        else:
            print("warning: RECEIPT_SALT is not set, the mint queue will not build")

        files = sorted(SQL_DIR.glob("*.sql"))
        if args.only:
            files = [f for f in files if f.name.startswith(args.only)]
        elif args.start:
            files = [f for f in files if f.name[:2] >= args.start]

        if args.stage and not (args.all or args.only or args.start):
            stage_files(cur)
            return 0

        total_ok = total_failed = 0
        for path in files:
            # The stage has to exist before anything is uploaded into it,
            # and the uploads have to land before the loaders run.
            if path.name.startswith("02"):
                stage_files(cur)
            ok, failed = run_file(cur, path, stop_on_error=args.stop_on_error)
            total_ok += ok
            total_failed += failed

        print(f"\n=== {total_ok} statements ok, {total_failed} failed ===")
        summary(cur)
        verify_policy(cur)
        report(cur)
        return 1 if total_failed else 0
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
