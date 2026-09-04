# Platform constraints found on the target account

Probed against `hwsyjpp-sf45442` (AWS_AP_SOUTHEAST_1) on 2026-09-04 as
`DEVSOUMYA` / `ACCOUNTADMIN`. Every claim below is the result of running the
statement, not of reading documentation.

This file exists because the Build Spec asks for honesty about what is real,
and two of its headline features are unavailable on this account. Both
substitutions below are the fallbacks the spec itself specifies in Section 10.

---

## What works

| Probe | Result |
| --- | --- |
| `H3_LATLNG_TO_CELL_STRING(31.5, 34.5, 7)` | `872db6382ffffff` |
| `VECTOR_COSINE_SIMILARITY(...::VECTOR(FLOAT,3), ...)` | `1` |
| `JAROWINKLER_SIMILARITY('abc','abd')` | `82` |
| `CREATE AGGREGATION POLICY ... MIN_GROUP_SIZE` | created |
| `CREATE MASKING POLICY`, `CREATE ROW ACCESS POLICY`, `CREATE TAG` | created |
| `ALTER DATABASE SET DATA_RETENTION_TIME_IN_DAYS = 90` | accepted, reads back `90` |
| `SHOW SEMANTIC VIEWS`, `SHOW DYNAMIC TABLES` | supported |

Aggregation policies and ninety-day retention are both Enterprise-gated, so
**this account is Enterprise Edition or higher**. Trap 01 is satisfied.
(`CURRENT_EDITION()` itself is an unknown function in this deployment, which is
why the assertion in `sql/00_account_setup.sql` now probes retention instead.)

---

## Constraint 1: differential privacy DDL is not available

```
CREATE PRIVACY BUDGET ...
  -> SQL compilation error: syntax error at position 26 unexpected 'BUDGET'.

ALTER VIEW ... SET PRIVACY POLICY ... ENTITY KEY (id)
  -> SQL compilation error: syntax error at position 36 unexpected 'PRIVACY'.
```

The keywords do not parse, so this is not a permissions problem and no grant
fixes it. The feature is absent from this deployment.

**Fallback taken, Build Spec Section 10, hour 5.**

> Fallback: implement the Attacker tab against an aggregation policy with a
> minimum group size instead, which enforces a real k-anonymity floor and is
> still a genuine governance feature. Relabel the tab honestly as a
> minimum-cohort guarantee rather than a differential-privacy guarantee.
> Document the attempt and the reason in the post.

So Tab 05 ships against `AGGREGATION_CONSTRAINT(MIN_GROUP_SIZE => 50)`. The
guarantee it enforces is real and it is enforced by Snowflake, but it is
k-anonymity, not differential privacy. The tab says so on screen, in its own
words, and does not use the phrase "differential privacy" about what it is
doing. The intended differential privacy DDL stays in
`sql/11_privacy_policy.sql`, commented, so the difference is inspectable.

**What is lost.** A minimum group size stops a query that isolates a small
cohort. It does not add calibrated noise and it has no budget, so it does not
defend against a sequence of overlapping queries the way differential privacy
does. Tab 05 states this limitation rather than glossing it.

---

## Constraint 2: every AI function is blocked on trial accounts

```
AI_EMBED(...)                      -> AI function _AI_EMBED_WITH_PROMPT_768
                                      is not available for trial accounts.
AI_FILTER(...)                     -> AI function _AI_FILTER_WITH_PROMPT
                                      is not available for trial accounts.
SNOWFLAKE.CORTEX.EMBED_TEXT_768    -> not available for trial accounts.
SNOWFLAKE.CORTEX.EMBED_TEXT_1024   -> not available for trial accounts.
SNOWFLAKE.CORTEX.COMPLETE          -> not available for trial accounts.
SNOWFLAKE.CORTEX.SENTIMENT         -> not available for trial accounts.
```

This is an account-class restriction, not a credit-exhaustion one, so the
Section 10 hour-13 remedy ("embeddings are already materialised, skip
AI_FILTER") applies but has to be taken from the start rather than partway
through.

**Fallback taken.**

* **Embeddings** are computed offline with the same model the spec names,
  `snowflake-arctic-embed-m`, run locally through `sentence-transformers`, and
  loaded into the `VECTOR(FLOAT, 768)` column. The vectors are genuine
  arctic-embed vectors; only the machine that produced them changed.
* **Similarity search stays in the warehouse.** `VECTOR_COSINE_SIMILARITY` over
  a `VECTOR` column is doing the work in SQL, with the region-and-cause
  pre-filter, exactly as specified. This is unaffected.
* **`AI_FILTER` confirmation** is replaced by the heuristic the spec supplies
  as its own fallback, and every confirmed row carries
  `confirmation_method = 'HEURISTIC'` so the substitution is visible in the
  data rather than hidden in a footnote.

**What is lost.** The claim "the embedding runs inside the warehouse" is not
true on this account and is not made anywhere in the interface or the write-up.
The claim "the similarity search runs inside the warehouse in SQL" is true and
is the one that is made.

---

## Consequence for the write-up

The honest sentence is:

> On a trial account, Snowflake blocks every AI function and this region has no
> differential privacy DDL. The vector search, the H3 geometry, the semantic
> view, the Dynamic Tables and the governance policy are all doing real work in
> the warehouse. The embeddings were generated offline with the same model, and
> the privacy layer is a minimum-cohort guarantee rather than a differential
> privacy one. Both substitutions are labelled in the interface.
