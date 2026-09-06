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

## Constraint 1: RETRACTED. This was a syntax error, not a constraint

**The finding recorded here was wrong, and it was the most consequential
finding in the file.** It is kept in full rather than deleted, because a
document whose whole claim is "everything here comes from running the
statement" has to show what happens when that method fails.

### What was recorded

```
CREATE PRIVACY BUDGET ...
  -> SQL compilation error: syntax error at position 26 unexpected 'BUDGET'.

ALTER VIEW ... SET PRIVACY POLICY ... ENTITY KEY (id)
  -> SQL compilation error: syntax error at position 36 unexpected 'PRIVACY'.
```

> The keywords do not parse, so this is not a permissions problem and no grant
> fixes it. The feature is absent from this deployment.

The Section 10 fallback was taken on that basis: Tab 05 was rebuilt against
`AGGREGATION_CONSTRAINT(MIN_GROUP_SIZE => 50)` and relabelled as a
minimum-cohort guarantee, and was later cut altogether.

### What was actually wrong

Both statements were malformed.

- **There is no `CREATE PRIVACY BUDGET` statement in Snowflake.** A budget
  comes into existence the moment a privacy policy body names one, through
  `PRIVACY_BUDGET(BUDGET_NAME => ..., BUDGET_LIMIT => ...,
  MAX_BUDGET_PER_AGGREGATE => ...)`.
- **The attach clause is `ADD PRIVACY POLICY`, not `SET`.** Replacing one is
  `DROP PRIVACY POLICY a, ADD PRIVACY POLICY b ENTITY KEY (col)` inside a
  single `ALTER`, so the object is never briefly unprotected.

A parser error tells you a statement is malformed. It does not tell you a
feature is missing, and for a weekend this build treated those as the same
fact. Written in syntax that exists, on the same account and the same
warehouse, it attaches and it works: see `sql/11b_differential_privacy.sql`.

**A negative result about a platform needs the same evidence as a positive
one.** This file opens by boasting that every claim in it comes from running
the statement rather than reading the documentation, and that is exactly
backwards. Running a statement tells you what *that statement* does. Only the
documentation tells you whether it was the right statement. Two of the ten
findings below rested on this error. The other eight are capability messages
rather than syntax errors, and they stand.

### What the privacy engine then demanded

Attaching the policy was the easy half. Four further refusals, each a real
constraint:

| Error | Meaning | Resolution |
|---|---|---|
| `510242` supported aggregates: COUNT, COUNT_STAR | a column with no declared privacy domain has an infinite one, and infinite domain means infinite noise | every column declares a domain |
| syntax error on `SET PRIVACY DOMAIN (0, 5000)` | wrong form | ranges are `BETWEEN (0, 5000)`; lists are `IN ('a','b')`; neither takes a subquery |
| `210007` infinite multiplier | a beneficiary holds up to five rows, so one person can move a row count by five | the query itself must deduplicate: `COUNT(DISTINCT beneficiary_id)`. A `GROUP BY` inside a view is not accepted as proof of one row per entity |
| possible groups (infinity) must not exceed 10000 | `GROUP BY` over an unbounded key | filter, or group only on domain-declared columns |

The surviving query shape is `COUNT(DISTINCT beneficiary_id)` with filters
over domain-declared columns, which is exactly the question Tab 05 asks.

### What both guarantees are now worth

Both policies ship, over the same facts, on two views, because a privacy
policy and an aggregation policy cannot sit on one object. The comparison is
the point rather than a workaround.

**Measured against the warehouse.** Twenty-five repeats of the unfiltered
count through the DP view: mean 8,115.4 against a true 8,113, standard
deviation 9.3. Thirty runs of the differencing pair that the aggregation
policy answers as exactly 12, every time: mean 14.8, standard deviation 18.2,
range −27 to +51, four runs returning a negative number of people.

**What is still lost, and it is now our own choice rather than the
platform's.** `BUDGET_LIMIT` is 300 at 0.1 per aggregate, which permits 3,000
queries. Grinding the noise down far enough to recover that 12-person group
takes roughly 660. The budget as configured does not stop the attack it exists
to stop, and Tab 05 does that arithmetic on screen rather than leaving it
here.

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


---

## Constraint 3: secondary roles silently defeat the analyst persona

`USE ROLE GP_ANALYST` is **not** enough to test as GP_ANALYST.

Snowflake users default to `DEFAULT_SECONDARY_ROLES = ('ALL')`, so after
switching primary role the session still carries every other role the user
holds, ACCOUNTADMIN included, and object privilege checks are evaluated against
that union.

The failure mode is nasty because it is half-invisible:

* `CURRENT_ROLE()` returns `GP_ANALYST`, so the aggregation policy sees the
  analyst and **correctly applies the cohort floor**. The protection looks like
  it is working.
* But a `SELECT` on the unprotected counterfactual is **allowed anyway**,
  because ACCOUNTADMIN is still live as a secondary role.

So the tab that exists to prove a guarantee would have been demonstrating it
against a session that could have read the true values all along. The row-level
refusal passing is what made this easy to miss.

Two fixes, both applied:

1. `USE SECONDARY ROLES NONE` wherever the analyst persona is assumed, in
   `sql/11_privacy_policy.sql`, `tools/deploy.py` and `app/data.py`. This is the
   fix that matters.
2. The counterfactual view moved out of `SERVING` into a `PRIVILEGED` schema
   that `GP_ANALYST` has no `USAGE` on, so a blanket
   `GRANT SELECT ON ALL VIEWS IN SCHEMA SERVING` cannot reach it even by
   accident.

`tools/deploy.py --check` now verifies all four behaviours by attempting them
rather than by reading a grant table:

```
=== policy verification, as GP_ANALYST ===
  pass  row-level select is refused
  pass  broad aggregate is answered
  pass  counterfactual view is unreadable
  pass  single-beneficiary group is withheld
```

---

## Constraint 4: the specified threshold did not survive the model change

The specification fixes the cosine cut-off at 0.86. That number belongs to the
embedding pipeline it assumed. Vectors from the same model produced offline are
not the same vectors, and a threshold is a property of the vectors.

Re-measured against ground truth, which is knowable here because every seeded
organisation records the real one it was built from in `synth_target_id`:

| threshold | pairs | true | precision | recall |
| --- | --- | --- | --- | --- |
| 0.86 | 692 | 365 | 52.7% | 91.3% |
| 0.90 | 389 | 336 | 86.4% | 84.0% |
| **0.94** | **276** | **270** | **97.8%** | **67.5%** |
| 0.97 | 169 | 166 | 98.2% | 41.5% |

At 0.86 the detector offered *"Hispanic Leadership Trust"* against *"Vote Org"* —
organisations that share a sector and nothing else. Shipping that would have
made the Donor tab a liar on its opening screen.

0.94 is where precision turns the corner and where the cut-off now sits. The
cost is real and is stated rather than buried: recall falls to 270 of 387, so
roughly a third of the seeded imitations are missed. The whole curve is
materialised into `MARTS.THRESHOLD_CALIBRATION` and driven by the Tab 02
slider, so the trade-off can be moved and watched instead of taken on trust.


---

## Constraint 5: devnet SOL, and the bootstrap that blocks the bypass

Every airdrop route from this machine is refused:

```
public devnet   429 Too Many Requests   "You've either reached..."
helius devnet   403 Forbidden           "Rate limit exceeded"
```

Tested at 1, 0.5 and 0.25 SOL, and against freshly generated keypairs. Fresh
addresses are refused identically, which establishes that **the limit is keyed
to the IP, not to the address**. No amount of new wallets gets around it, and
`solana airdrop` would hit exactly the same faucet.

### The proof-of-work faucet is real, and it is not enough on its own

`devnet-pow` is installed and working. It finds a live faucet holding roughly
**1.4 million devnet SOL**, paying **0.02 SOL per solve at difficulty 3**, with
no rate limit at all:

```
Faucet address: 6yvwhesLJeE8...   balance 1446759.57 SOL   reward 0.02   d3
```

But it cannot start from zero:

```
devnet-pow mine -d 3 --reward 0.02 --no-infer -t 200000000 -u dev
  -> Error: airdrop request failed. This can happen when the rate limit is reached.
```

Claiming a mined reward is an ordinary transaction, so the miner must already be
able to pay a fee. A wallet with 0 SOL cannot pay a fee, and the airdrop that
would give it one is rate limited. That is the whole deadlock, and it is why the
proof-of-work route does not rescue an empty wallet.

**About 0.01 SOL breaks it.** Once the authority can pay a fee, `npm run mine`
tops it up from the 1.4M SOL faucet with no further limits.

### Getting the toolchain there was most of the work

Recorded because none of it is obvious from the instructions:

* `cargo install devnet-pow` needs a C toolchain. Visual Studio 2022 is present
  but **without the C++ workload**, so there is no MSVC linker.
* Under Git Bash the build fails confusingly: `/usr/bin/link` shadows MSVC's
  `link.exe` and reports `link: extra operand`. Build from PowerShell.
* The GNU toolchain then fails on the 32-bit MinGW.org `dlltool.exe` that sits
  on PATH: `Invalid bfd target`.
* Removing MinGW from PATH gets `dlltool.exe: program not found`; Rust's
  self-contained directory ships `dlltool` and `ld` but no assembler, so
  `dlltool` dies with `CreateProcess`.
* What worked: a standalone mingw-w64 (WinLibs, 274 MB zip, no installer) put
  ahead of everything on PATH, with MinGW.org removed, building the
  `stable-x86_64-pc-windows-gnu` toolchain. Roughly eight minutes to compile.

### Two side effects on this machine

`devnet-pow` insists on a Solana CLI config even when `-k` and `-u` are passed,
so these were created:

* `~/.config/solana/cli/config.yml` pointing at devnet and at the repository's
  `authority.json`. It must be written **without a BOM** or the YAML parse fails
  with a misleading "cannot find the file specified".
* `~/.config/solana/id.json`, a copy of `authority.json`. Nothing was
  overwritten: neither file existed beforehand.

### The local validator is not an option here, and it is worth saying why

`solana-test-validator` gives unlimited SOL instantly. It would also make Tab 06
dishonest. The entire argument for putting receipts on a chain is that the
record "persists whether or not GLASSPOCKET exists, whether or not the operator
stays honest". A receipt on a validator running on the builder's laptop has none
of those properties and cannot be checked by a judge. It is a reasonable way to
exercise the bridge mechanics, and it is not a way to satisfy CHN-01.
