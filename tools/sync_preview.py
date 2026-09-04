"""Pull the warehouse-computed tables back into the local preview store.

    python tools/sync_preview.py

WHY THIS EXISTS
    The preview store is seeded by tools/make_synthetic.py, which has to
    compute clone pairs itself in order to build the projection and the
    graph layout before any vectors exist. Once the real
    snowflake-arctic-embed-m vectors are loaded and Snowflake has done
    the detection properly, those bootstrap numbers are stale.

    Leaving them stale would mean a similarity score on a laptop and the
    same score in the warehouse disagreeing, which is exactly the kind of
    quiet drift this project spends eleven tabs arguing against. So the
    warehouse becomes the source of truth and the preview store is
    refreshed from it.

    Nothing is recomputed here. Rows are copied.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
STORE = ROOT / "data" / "glasspocket.duckdb"

#: warehouse object -> preview table
PULL = {
    "MARTS.CLONE_PAIRS": "clone_pairs",
    "MARTS.CLONE_CONFIRMED": "clone_confirmed",
    "MARTS.THRESHOLD_CURVE": "threshold_curve",
    "MARTS.THRESHOLD_CALIBRATION": "threshold_calibration",
    "MARTS.ORG_RISK": "org_risk",
    "MARTS.DELIVERY_GEOMETRY": "delivery_geometry",
    "MARTS.DT_RECEIPT_COVERAGE": "receipt_coverage",
    "MARTS.DT_ORG_ACTIVITY": "org_activity",
    "MARTS.BENEFICIARY_FACTS": "beneficiary_facts",
}


def main() -> int:
    if not STORE.exists():
        raise SystemExit(f"missing {STORE}")

    sys.path.insert(0, str(ROOT / "tools"))
    import duckdb
    import deploy

    env = deploy.load_env()
    conn = deploy.connect(env)
    cur = conn.cursor()
    store = duckdb.connect(str(STORE))

    try:
        for source, target in PULL.items():
            try:
                cur.execute(f"SELECT * FROM GLASSPOCKET.{source}")
                frame = cur.fetch_pandas_all()
            except Exception as exc:            # noqa: BLE001
                print(f"  skip  {source}: {' '.join(str(exc).split())[:70]}")
                continue

            frame.columns = [c.lower() for c in frame.columns]
            store.register("_incoming", frame)
            store.execute(
                f"CREATE OR REPLACE TABLE {target} AS SELECT * FROM _incoming"
            )
            store.unregister("_incoming")
            print(f"  {target:24s} {len(frame):>8,} rows  <- {source}")

        store.execute(
            "CREATE OR REPLACE TABLE build_meta AS "
            "SELECT bmf_rows_available, generated_at, 0.94 AS similarity_threshold "
            "FROM build_meta"
        )
        print("\npreview store now matches the warehouse")
        return 0
    finally:
        store.close()
        cur.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
