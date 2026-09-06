# GLASSPOCKET

**A Snowflake accountability engine for charitable giving.**

Multi-tab Streamlit application, Solana compressed-NFT receipt ledger,
governed serving layer with an enforced minimum-cohort guarantee.

> Generosity fails not because people stop giving but because they cannot see
> where the money went. This is the machinery that lets them see.

The name refers to the "glass pockets" principle in philanthropy: an
organisation handling public generosity should be transparent enough that
anyone can see into its pockets.

---

## Challenge disclosure

| | |
| --- | --- |
| Event | DEV.to Weekend Challenge, Generosity Edition |
| Primary category | Best Use of Snowflake |
| Secondary category | Best Use of Solana |
| Cluster | Solana **devnet**, never mainnet |
| Synthetic data | Present, labelled in the data and in the interface |

Every impersonating organisation and every beneficiary record in this project
is **generated**. Every one carries `batch_id = 'SYNTH_ADVERSARY_V1'` and
`is_synthetic = TRUE`, renders a visible "seeded" chip, and is disclosed on the
Method and Honesty tab. Real organisations appear **only** as the legitimate
target of an impersonation, never in a flagged state. That constraint is
enforced in SQL and verified by an acceptance check, not by convention.

---

## The problem, in one paragraph

The most common charitable fraud is not an invented organisation. It is a real
organisation with the serial numbers filed off: a near-identical name, a copied
mission statement, a cloned campaign page with one extra character in the URL.
String matching cannot catch this because the strings are deliberately
different. Meanwhile, on the disbursement side, aid that is genuinely raised is
frequently diverted before it reaches a beneficiary, and the sector's answer is
a PDF annual report published nine months later. GLASSPOCKET attacks both
halves: it detects impersonation by meaning rather than spelling, it detects
diversion by geography and timing, it publishes the resulting statistics under a
governance policy that refuses to answer about small groups of people, and it
writes a public, tamper-evident receipt for every verified disbursement
so a donor can check the claim without trusting anybody.

## Evidence

| Claim | Figure | Source |
| --- | --- | --- |
| Charitable and crowdfunding fraud, US, 2024 | More than 4,500 complaints reporting approximately 96 million USD in losses | [FBI IC3 PSA I-011625](https://www.ic3.gov/PSA/2025/PSA250116), 16 Jan 2025 |
| Impersonation surges after disasters | 119 domains registered between 8 and 13 January 2025 using keywords including "LA fire", "wildfire", "relief", "fund", "rebuild" | BforeAI threat research report on the Los Angeles wildfires |
| Scale of the pool being imitated | More than 250 million USD raised for Los Angeles wildfire relief | GoFundMe public statement |
| Last-mile diversion, Gaza | 590 trucks moved from Ashdod to Kerem Shalom, of which 371 were collected inside Gaza; looting estimated at about 20 percent of cases | WFP State of Palestine External Situation Report 55, 6 Jun 2025 |
| Warehouse-scale diversion, Sudan | Looting of a Gezira State warehouse holding over 2,500 metric tons of food | WFP statement, Dec 2023 |
| Programme leakage, India | 169.75 crore rupees misappropriated, 20.93 crore recovered, a 12.33 percent recovery rate, across 125,602 cases | MGNREGA action report, as of 29 Mar 2025 |
| Diversion before delivery, India | 86.20 lakh rupees intended for 159 genuine beneficiaries diverted to other accounts | CAG audit of PMAY-Gramin, Uttar Pradesh, tabled Dec 2025 |

These seven figures are hand-entered into `MARTS.EVIDENCE_CITATIONS` and into
`data/evidence_citations.csv`. They are never computed and never templated, so
they cannot drift. Nothing here is rounded or embellished.

---

## The ten tabs

Not a dashboard. An argument in ten moves.

| | Tab | The move |
| --- | --- | --- |
| 00 | The Brief | Establish stakes with cited numbers |
| 01 | Give With Confidence | Telling real from imitation is genuinely hard |
| 02 | The Trust Graph | Imitation is a structure, not incidents |
| 03 | Follow The Money | Geography of where aid actually landed |
| 04 | The Last Mile | Where the gap between pledged and delivered opens |
| 05 | **The Wall** | Invite the viewer to attack the privacy layer |
| 06 | **The Receipt** | Verify without trusting the operator |
| 07 | The Historian | The record cannot be quietly rewritten |
| 08 | Ask The Warehouse | Plain-language questions over governed data |
| 09 | Where A Dollar Lands | Point the viewer toward giving |

Method And Honesty was removed; its disclosure moved to The Brief, where the
banner on every screen already promises it. The Wall was removed too, and came
back: the reason it was cut turned out to be a syntax error in this build's own
probe rather than a missing platform feature, and it now carries three
governance regimes over one set of facts instead of two.

Tabs 05, 01 and 06 are the submission. Everything else is amplification.

**Framing rule.** The product is a confidence layer for people who want to give,
not an accusation engine. The interface says *verified*, *unverified*, *needs a
second look*, *confidence*, *receipt found*. It never says fraud, criminal, scam
or guilty about any entity. The word "fraud" appears only on Tab 00, quoting a
cited source.

---

## Setup

### 0. Prerequisites

| Tool | Version | Used for |
| --- | --- | --- |
| Snowflake | **Enterprise Edition or higher** | Aggregation policies and 90-day Time Travel are Enterprise-gated |
| Node | 20 LTS or later | Bridge, Umi, Bubblegum |
| Solana CLI | current stable | Keypair generation, devnet airdrop |
| Python | 3.11 (matches the Streamlit warehouse runtime) | Offline preparation |

> **Trap 01, unrecoverable.** Cloud platform, region and edition are chosen at
> Snowflake signup and **cannot be changed afterwards**. Selecting Standard
> makes the centrepiece of this build permanently unavailable on that account,
> and the only remedy is a new trial.
>
> `CURRENT_EDITION()` is an unknown function on some deployments, so
> `sql/00_account_setup.sql` establishes the edition by behaviour instead: it
> creates a scratch database, sets 90-day retention and creates an aggregation
> policy, both Enterprise-gated, then drops it. It also probes for the
> differential privacy DDL and the AI functions and reports whether each is
> available, so you learn in minute one rather than at hour eleven.

> **Trap 04, do it in the first ten minutes.** Accept **External Offerings
> Terms** in Snowsight. `st.pydeck_chart` draws tiles from Carto, a third-party
> offering. Skip this and the geospatial tab renders empty with no error.

### 1. Fonts

Geist must be base64-inlined, because Streamlit in Snowflake enforces a Content
Security Policy that blocks fonts from external domains. A CDN link silently
falls back to a system font.

```bash
npm pack geist && tar -xzf geist-*.tgz
cp package/dist/fonts/geist-sans/Geist-{Regular,Medium,SemiBold,Bold,Variable}.woff2 fonts/
python tools/build_font_css.py        # writes app/assets/geist.css, committed
```

### 2. Data

```bash
# IRS Exempt Organizations Business Master File, all regional extracts
#   irs.gov > Charities and Non-Profits > EO BMF extract
curl -o data/irs/eo1.csv https://www.irs.gov/pub/irs-soi/eo1.csv     # and eo2..eo4
curl -o data/irs/revocation.zip https://apps.irs.gov/pub/epostcard/data-download-revocation.zip

# US Census ZCTA gazetteer, for coordinates
curl -o data/geo/zcta.zip https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_Gaz_zcta_national.zip

python tools/make_synthetic.py --all
```

This normalises the real corpus, generates roughly 400 adversaries using the
five documented impersonation techniques, generates disbursements calibrated
against the published WFP truck figures, computes the offline PCA projection and
the networkx graph layout, and writes both the staging CSVs and a local preview
store.

### 3. Warehouse

Run the numbered files in order.

```
sql/00_account_setup.sql          warehouse, database, schemas, edition assert
sql/01_raw_tables.sql             landing and staging schema
sql/02_load_bmf.sql               IRS BMF and the revocation list
sql/03_load_iati.sql              IATI activity and location data
sql/04_seed_adversaries.sql       synthetic clones, labelled, plus the citations
sql/05_staging_dynamic_tables.sql six Dynamic Tables at a 60 second target lag
sql/06_embeddings.sql             AI_EMBED batch, RUN ONCE
sql/07_clone_detection.sql        vector similarity and the evasion gap
sql/08_geospatial_h3.sql          H3 geometry and hex risk
sql/09_risk_score_udf.sql         the decomposable score
sql/10_semantic_view.sql          semantic layer
sql/11_privacy_policy.sql         aggregation policy  <-- BUILD THIS FIRST
sql/11b_differential_privacy.sql  privacy policy and epsilon budget
sql/12_serving_views.sql          terminal serving views
sql/13_oracle_queue.sql           mint queue and mint log
sql/99_acceptance_checks.sql      the gate
```

**Build `11_privacy_policy.sql` first in practice.** It is numbered where it
sits in the dependency graph, but it is the only component that can fail in a
way that cannot be fixed later. Build it against a minimal fabricated fact
table, verify the three behaviours below, and only then continue.

```sql
-- As GP_ANALYST:
-- 1. MUST FAIL       a row-level select on the protected view
-- 2. MUST SUCCEED    a broad aggregate, with slight noise
-- 3. MUST be noisy   or refused: an aggregate filtered to one beneficiary
```

If all three behave as described, the centrepiece works. If not, apply the
fallback (an aggregation policy with a minimum group size, relabelled honestly
as a minimum-cohort guarantee) within thirty minutes and document the attempt.

### 4. Bridge

```bash
cd bridge
cp ../.env.example .env          # fill it in; never commit it
solana-keygen new -o keys/authority.json
solana airdrop 2 --url devnet    # do this on Friday, not Saturday
npm install
npm run tree                     # creates the tree and collection, prints both addresses
# paste MERKLE_TREE_ADDRESS and COLLECTION_MINT into .env
npm run start
```

Run the full mint batch **hours before recording**. The application reads
`ORACLE.MINT_LOG`, a local mirror, so nothing on screen ever waits on an RPC.

### 5. Application

Deploy `app/` as a Streamlit app inside Snowflake. It needs **no credentials**:
it obtains its session with `get_active_session()`. If any Snowflake credential
appears in `app/`, that is a defect.

To develop locally against the preview store:

```bash
streamlit run app/glasspocket_app.py
python tools/smoke_test.py        # renders every tab and every interactive path
python tools/acceptance.py        # the Section 11 criteria checkable offline
```

### Deploying

```bash
python tools/embed_offline.py         # arctic-embed vectors, once
python tools/export_for_snowflake.py  # prepared corpus for staging
python tools/deploy.py --check        # connect and report, change nothing
python tools/deploy.py --all          # provision, stage, load, verify
python tools/deploy.py --only 07      # re-run one numbered file
```

`tools/deploy.py` reads the repository-root `.env`, never prints a credential,
and binds `RECEIPT_SALT` as a session variable for the one statement that needs
it. Statements marked `-- EXPECT_FAIL` are ones that are *supposed* to be
refused: the row-level `SELECT` in `sql/11` proves the policy is protecting the
view, and a build where it succeeds is the broken one.

---

## Architecture

```
IRS BMF ─┐
IATI ────┼─> RAW ─> STAGING ─> MARTS ─> SERVING ─> Streamlit in Snowflake
synth ───┘              │         │         │
                        │         │         └─ privacy policy (terminal only)
                        │         └─ vectors, H3 geometry, risk UDF, semantic view
                        └─ six Dynamic Tables, 60s target lag

                 ORACLE.MINT_QUEUE ──> Node bridge ──> Solana devnet
                 ORACLE.MINT_LOG   <──   (Umi + Bubblegum V1)
```

The arrow from the bridge points **into** Snowflake, not out of it. Trial
accounts have no external network access, and a signing key has no business
inside a data warehouse regardless.

### Snowflake features, and where they appear

| Feature | Where the judge sees it |
| --- | --- |
| Privacy policy with an epsilon budget, and an aggregation policy beside it | Tab 05, The Wall |
| `AI_EMBED` and `VECTOR_COSINE_SIMILARITY` | Tabs 01 and 02 |
| `AI_FILTER` as a semantic predicate | Tab 01, confirmation chip |
| H3 grid functions and `ST_DISTANCE` | Tabs 03 and 04 |
| SQL UDF, decomposable score | Tab 01, waterfall |
| Dynamic Tables with `TARGET_LAG` | Tab 00, pipeline strip |
| Semantic view | Tab 08, Ask The Warehouse |
| Time Travel | Tab 07, The Historian |

### Why Solana is load-bearing

A donor verifying a claim about a charity is verifying it against a record kept
by the charity, or by a platform the charity pays, or by an application built by
someone they have never met. Every one of those requires trust in an interested
party. A compressed NFT receipt persists whether or not GLASSPOCKET exists,
whether or not the operator stays honest, and whether or not the warehouse is
later edited. That is the only reason a chain is here, and it is a real property
rather than a decorative one.

**What goes on chain:** programme code, amount *band*, delivery *window*, a
salted hash of the organisation identifier, a schema version.
**What never does:** beneficiary identifier, coordinates, organisation name,
exact amount, exact timestamp.

Publish the claim, not the data. A public ledger is permanent, and permanence
plus personal data is a harm that cannot be undone.

---

## What is real and what is simplified

| Element | Real | Seeded or simplified |
| --- | --- | --- |
| Organisation corpus | IRS Business Master File, unmodified | Nothing |
| Standing information | IRS Auto-Revocation List, which records failure to file, not wrongdoing | Nothing |
| Activity and location data | IATI Datastore slice | Coordinates jittered where precision would be identifying |
| Imitating organisations | Nothing | All of them, `tools/make_synthetic.py`, batch `SYNTH_ADVERSARY_V1` |
| Beneficiary records | Nothing | Entirely synthetic. Handling real beneficiary data here would be unethical. |
| Attrition rates | Calibrated against published WFP truck figures | Individual delivery events are modelled |
| On-chain receipts | Genuinely minted and independently verifiable | Solana devnet, not mainnet |
| Privacy guarantee | Two real Snowflake policies over the same facts: an aggregation policy with `MIN_GROUP_SIZE => 50`, and a privacy policy on `SERVING.V_BENEFICIARY_DP` with a 0.1 epsilon budget. Both carry an entity key on `beneficiary_id` | The cohort floor is **not** differential privacy: no noise, no budget. The DP view is, and it shipped late, because this build first recorded the feature as absent on the strength of two malformed statements. |
| Embeddings | Genuine `snowflake-arctic-embed-m` vectors in a `VECTOR(FLOAT, 768)` column; all similarity search runs in Snowflake | Generated offline, because AI functions are blocked on trial accounts |
| Clone confirmation | Nothing | `AI_FILTER` is blocked on trial accounts, so confirmation is two SQL predicates; every row carries `confirmation_method = 'HEURISTIC'` |

### What the platform would not give us, and what we got wrong about it

**Differential privacy was recorded as unavailable, and that was our error.**
`CREATE PRIVACY BUDGET` and `ALTER VIEW ... SET PRIVACY POLICY` were run,
failed to parse, and were written up as a missing feature. Both statements were
malformed: there is no `CREATE PRIVACY BUDGET` statement in Snowflake at all —
a budget is created by being named inside a policy body — and the attach clause
is `ADD PRIVACY POLICY`, not `SET`. A parser error says a statement is
malformed. It does not say a feature is missing. Written correctly it attaches
and it works, in `sql/11b_differential_privacy.sql`, and The Wall renders its
output live beside the aggregation policy. The full retraction, the four
further refusals the privacy engine raised, and the measured noise are in
[`docs/platform_constraints.md`](docs/platform_constraints.md).

**Every AI function.** `AI_EMBED`, `AI_FILTER` and all `SNOWFLAKE.CORTEX.*`
return *"not available for trial accounts"*. So embeddings are generated offline
with the same model the design names, `snowflake-arctic-embed-m`, and loaded
into a real `VECTOR(FLOAT, 768)` column. **The similarity search did not move**:
every comparison still runs in Snowflake through `VECTOR_COSINE_SIMILARITY` with
the mandatory pre-filter. The `AI_FILTER` confirmation step becomes two SQL
predicates, and `confirmation_method` is carried on every row.

The intended statements are preserved, commented, in `sql/06_embeddings.sql`,
`sql/07_clone_detection.sql` and `sql/11_privacy_policy.sql`, so the difference
between what was designed and what shipped is inspectable rather than described.

### What this cannot do

- **The privacy budget is set too high to stop the attack it exists to stop.**
  Recovering the smallest group the cohort floor leaks takes roughly 660
  queries; `BUDGET_LIMIT => 300` at 0.1 per aggregate permits 3,000. The Wall
  does that arithmetic on screen.
- **The cohort floor is not differential privacy and is not presented as it.**
  It refuses to answer about fewer than fifty beneficiaries, but it adds no
  noise and has no budget, so two permitted large queries can be subtracted to
  learn about a handful of people.
- **It cannot prove intent.** A high similarity score is a reason to look
  closer, never a verdict about a person.
- **It cannot detect an imitator whose name shares no meaning with its target.**
  Detection by meaning has a blind spot for names chosen at random.
- **It cannot see money that never entered a reporting system at all**, which is
  very likely where the largest losses actually sit.
- **A receipt proves a claim was recorded at a point in time.** It does not
  prove goods reached a person. Anyone who tells you a blockchain solves that is
  selling something.

### On the Auto-Revocation List

It is overwhelmingly a record of organisations that failed to file for three
consecutive years, and organisations that were later reinstated are excluded
here. It is **not** a fraud list. This project describes it as *no longer in
good standing* and never as *fraudulent*. Mislabelling it would be exactly the
kind of sloppy inference this project exists to criticise.

### On the synthetic adversaries

The sharpest objection to this project is that the detector finds imitations its
own author generated. That objection is correct. It is why the technique
breakdown on Tab 02 exists: the tactics are known by construction, so the honest
thing is to report which ones the detector handles well and which it does not.

---

## Security

No secret is ever committed, printed to a log, pasted into a Streamlit page, or
visible in the demo recording. `.env`, `keys/` and `*.json` keypairs are in
`.gitignore` from the first commit. If a key is ever exposed, it is rotated and
the rotation is noted here rather than quietly rewritten out of history.

Rotations to date: none.

---

## Repository layout

```
sql/          15 numbered files, run in order
bridge/       Node + TypeScript, polls Snowflake, mints on devnet
app/          Streamlit in Snowflake
  theme.py        design system, Geist inlined, no monospace anywhere
  charts.py       every Plotly figure routes through one styling gate
  components.py   hero, stat band, identifier chip, compare columns
  queries.py      EVERY SQL string the app runs, one file, no inline SQL
  data.py         one query surface, warehouse or local preview
  tabs/           eleven tab modules
tools/        font builder, synthetic generator, smoke test
docs/         demo script, architecture
```

Every SQL statement the application executes lives as a named constant in
`app/queries.py`. This makes the whole query surface runnable headlessly during
acceptance testing, and it makes the write-up easy because the SQL is quotable
from one file.
