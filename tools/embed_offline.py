"""Generate snowflake-arctic-embed-m vectors offline.

Build Spec Section 06.2, with the Section 10 substitution forced by the
platform.

WHY THIS FILE EXISTS
    The specified statement is

        UPDATE STAGING.ORGS SET name_vec = AI_EMBED(
            'snowflake-arctic-embed-m', name || ' :: ' || blurb || ' :: ' || cause)

    On the target account that fails with

        AI function _AI_EMBED_WITH_PROMPT_768 is not available for
        trial accounts.

    Every SNOWFLAKE.CORTEX.* function is blocked identically. It is an
    account-class restriction, so no grant and no waiting fixes it.

WHAT CHANGES AND WHAT DOES NOT
    The model does not change: this loads the same
    Snowflake/snowflake-arctic-embed-m weights and produces the same 768
    dimensional vectors. The machine changes, from the warehouse to this
    laptop.

    The similarity search does NOT move. The vectors are loaded into a
    real VECTOR(FLOAT, 768) column and every comparison still runs in
    Snowflake through VECTOR_COSINE_SIMILARITY, with the mandatory
    region-and-cause pre-filter. That is the part the thesis rests on and
    it is untouched.

    Tab 10 and the write-up state this substitution plainly.

USAGE
    python tools/embed_offline.py                 # all orgs in the store
    python tools/embed_offline.py --batch 128

    Writes data/vectors/org_vectors.csv, two columns: org_id and a JSON
    array of 768 floats, ready for COPY INTO and a cast in sql/06.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
STORE = ROOT / "data" / "glasspocket.duckdb"
OUT_DIR = ROOT / "data" / "vectors"
OUT = OUT_DIR / "org_vectors.csv"

MODEL_NAME = "Snowflake/snowflake-arctic-embed-m"
DIM = 768


def build_text(row) -> str:
    """The exact concatenation the AI_EMBED statement would have used."""
    return (
        f"{row.name_} :: "
        f"{row.blurb if isinstance(row.blurb, str) else ''} :: "
        f"{row.cause if isinstance(row.cause, str) else ''}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=int, default=256)
    parser.add_argument("--limit", type=int, default=None,
                        help="embed only the first N rows, for a smoke run")
    parser.add_argument("--all-orgs", action="store_true",
                        help="embed every organisation rather than only those "
                             "that can reach the pre-filtered similarity join")
    parser.add_argument("--seq", type=int, default=64,
                        help="max sequence length. The texts are a name, a "
                             "one-line blurb and a cause, so 64 tokens covers "
                             "them and attention cost falls sharply")
    args = parser.parse_args(argv)

    if not STORE.exists():
        raise SystemExit(
            f"missing {STORE}. Run: python tools/make_synthetic.py --all"
        )

    import duckdb

    con = duckdb.connect(str(STORE), read_only=True)

    # Only organisations that can actually reach the similarity join need
    # a vector. The join is hard pre-filtered on region_h3 and cause
    # (Trap 06), so an organisation sharing neither with any adversary can
    # never be compared to one, and embedding it would be work whose
    # result is never read. Everything on the suspect side is included
    # unconditionally.
    scope = "" if args.all_orgs else """
        WHERE o.is_synthetic
           OR EXISTS (SELECT 1 FROM staging_orgs a
                       WHERE a.is_synthetic
                         AND a.region_h3 = o.region_h3
                         AND a.cause     = o.cause)
           OR o.org_id IN (SELECT org_id FROM org_projection)
    """
    orgs = con.execute(
        "SELECT o.org_id, o.name AS name_, o.blurb, o.cause "
        "FROM staging_orgs o" + scope
        + (f" LIMIT {int(args.limit)}" if args.limit else "")
    ).df()
    total = con.execute("SELECT COUNT(*) FROM staging_orgs").fetchone()[0]
    con.close()

    print(f"{len(orgs):,} organisations to embed, of {total:,} in the store")
    if not args.all_orgs:
        print("  (restricted to those reachable by the pre-filtered join;"
              " pass --all-orgs to embed everything)")
    print(f"model {MODEL_NAME}")

    from sentence_transformers import SentenceTransformer

    started = time.time()
    model = SentenceTransformer(MODEL_NAME)
    model.max_seq_length = args.seq
    print(f"model loaded in {time.time() - started:.1f}s, "
          f"max_seq_length {model.max_seq_length}")

    texts = [build_text(row) for row in orgs.itertuples()]

    started = time.time()
    vectors = model.encode(
        texts,
        batch_size=args.batch,
        show_progress_bar=True,
        normalize_embeddings=True,   # cosine similarity becomes a dot product
        convert_to_numpy=True,
    ).astype(np.float32)
    elapsed = time.time() - started

    if vectors.shape[1] != DIM:
        raise SystemExit(
            f"model returned {vectors.shape[1]} dimensions, expected {DIM}. "
            "STAGING.ORGS.name_vec is declared VECTOR(FLOAT, 768)."
        )

    print(f"embedded {len(vectors):,} rows in {elapsed:.0f}s "
          f"({len(vectors) / max(elapsed, 1):.0f}/s)")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame({
        "org_id": orgs["org_id"].to_numpy(),
        # Rounded to six places: identical cosine results, roughly a third
        # off the staged file size.
        "vec": [json.dumps([round(float(x), 6) for x in v]) for v in vectors],
    })
    frame.to_csv(OUT, index=False)

    size_mb = OUT.stat().st_size / 1e6
    print(f"wrote {OUT.relative_to(ROOT)}  {size_mb:.1f} MB")

    # Write them back into the preview store too, so the local app and the
    # warehouse agree on what a similarity score means.
    con = duckdb.connect(str(STORE))
    con.register("_vecs", pd.DataFrame({
        "org_id": orgs["org_id"].to_numpy(),
        "vec": list(vectors),
    }))
    con.execute("CREATE OR REPLACE TABLE org_vectors AS SELECT * FROM _vecs")
    con.unregister("_vecs")
    con.close()
    print("preview store updated with the same vectors")

    return 0


if __name__ == "__main__":
    sys.exit(main())
