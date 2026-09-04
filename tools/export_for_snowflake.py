"""Export the prepared corpus for loading into Snowflake.

WHAT THIS IS FOR, AND WHAT IT IS NOT

    sql/02_load_bmf.sql and sql/03_load_iati.sql are the full-scale path:
    stage the raw IRS regional extracts and an IATI slice, and let
    Snowflake do the parsing, the normalisation and the H3 indexing. That
    path is real and it stays in the repository.

    This exporter is the bounded path, and it is the one the deployment
    uses. It writes the already-normalised STAGING tables so that:

      * the warehouse and the local preview store hold exactly the same
        corpus, which means a number on screen means the same thing in
        both, and

      * the vector corpus stays at tens of thousands of rows rather than
        nine hundred thousand, so the pre-filtered similarity join stays
        inside a trial credit budget (Trap 06 and Trap 09).

    Everything DOWNSTREAM of staging is still computed in Snowflake:
    clone detection, the evasion gap, the H3 geometry, the risk UDF, the
    Dynamic Tables, the semantic view, the governance policy and the mint
    queue. The warehouse is doing the work; this file only decides which
    rows it does it over.

USAGE
    python tools/export_for_snowflake.py
"""

from __future__ import annotations

import pathlib
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
STORE = ROOT / "data" / "glasspocket.duckdb"
OUT = ROOT / "data" / "warehouse"

#: table in the preview store -> (output name, columns to keep)
EXPORTS = {
    "staging_orgs": ("orgs", [
        "org_id", "ein", "name", "blurb", "city", "state", "ntee_code",
        "cause", "lat", "lon", "home_h3", "region_h3", "base_h3", "max_hops",
        "is_verified", "is_synthetic", "batch_id", "synth_technique",
        "synth_target_id",
    ]),
    "staging_disbursements": ("disbursements", [
        "disbursement_id", "org_id", "programme_code", "beneficiary_id",
        "amount_usd", "pledged_usd", "district", "lat", "lon", "delivery_h3",
        "dispatched_at", "delivered_at", "status", "is_synthetic", "batch_id",
    ]),
    "staging_beneficiaries": ("beneficiaries", [
        "beneficiary_id", "district", "programme_code", "cause",
        "cohort_band", "is_synthetic", "batch_id",
    ]),
    "org_projection": ("projection", ["org_id", "pc1", "pc2"]),
    "graph_nodes": ("graph_nodes", [
        "org_id", "name", "x", "y", "node_kind", "degree",
    ]),
    "graph_edges": ("graph_edges", ["source_id", "target_id", "similarity"]),
    "threshold_curve": ("threshold_curve", [
        "threshold", "pairs_detected", "pairs_ai_confirmed",
        "is_production_value",
    ]),
    "evidence_citations": ("citations", [
        "citation_id", "claim", "figure", "magnitude", "unit_type", "region",
        "issuing_body", "published_on", "url",
    ]),
}


def district_dim(con) -> pd.DataFrame:
    """The district dimension, derived from where deliveries actually went.

    Normally this comes from IATI activity locations. No IATI slice was
    loaded for this build, which Section 04C explicitly permits, so the
    dimension is built from the synthetic delivery geography instead and
    Tab 10 discloses it.
    """
    return con.execute("""
        SELECT district,
               ANY_VALUE(country)                 AS country,
               ANY_VALUE(country)                 AS region,
               AVG(lat)                           AS centroid_lat,
               AVG(lon)                           AS centroid_lon,
               ANY_VALUE(delivery_h3)             AS district_h3
        FROM staging_disbursements
        WHERE district IS NOT NULL
        GROUP BY district
        ORDER BY district
    """).df()


def main() -> int:
    if not STORE.exists():
        raise SystemExit(
            f"missing {STORE}. Run: python tools/make_synthetic.py --all"
        )

    import duckdb

    con = duckdb.connect(str(STORE), read_only=True)
    OUT.mkdir(parents=True, exist_ok=True)

    total = 0
    for table, (name, columns) in EXPORTS.items():
        try:
            available = [
                r[0] for r in con.execute(
                    f"SELECT column_name FROM (DESCRIBE {table})"
                ).fetchall()
            ]
        except Exception as exc:                # noqa: BLE001
            print(f"  skip  {table}: {exc}")
            continue

        keep = [c for c in columns if c in available]
        missing = [c for c in columns if c not in available]
        df = con.execute(f"SELECT {', '.join(keep)} FROM {table}").df()

        # Booleans have to reach Snowflake as TRUE/FALSE rather than as
        # Python's True/False, which COPY INTO reads as a string.
        for column in df.columns:
            if df[column].dtype == bool:
                df[column] = df[column].map({True: "TRUE", False: "FALSE"})

        path = OUT / f"{name}.csv"
        df.to_csv(path, index=False)
        total += len(df)
        note = f"  (missing: {', '.join(missing)})" if missing else ""
        print(f"  {name:16s} {len(df):>8,} rows  "
              f"{path.stat().st_size / 1e6:6.1f} MB{note}")

    districts = district_dim(con)
    districts.to_csv(OUT / "district_dim.csv", index=False)
    print(f"  {'district_dim':16s} {len(districts):>8,} rows")

    con.close()
    print(f"\nwrote {OUT.relative_to(ROOT)}  ({total:,} rows total)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
