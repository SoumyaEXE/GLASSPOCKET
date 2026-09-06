"""Offline preparation. Build Spec Sections 04C, 05, 06.2 and 07.

This is the largest single piece of preparation work in the build. Budget
properly for it, because the quality of the adversaries determines whether
the detection looks impressive or trivial.

It does four jobs:

  1. Normalises the IRS Business Master File and the Auto-Revocation List
     into the real side of STAGING.ORGS.
  2. Generates roughly 400 adversarial organisations by sampling real BMF
     entries and applying the five documented impersonation techniques.
  3. Generates disbursements, delivery events and beneficiary records,
     with attrition calibrated against the published WFP truck figures.
  4. Computes the geometry that does not belong in a render path: the PCA
     projection for Tab 01, the spring layout for Tab 02, and the
     threshold sweep for Tab 02 section S7.

Outputs land in two places:

  data/synthetic/*.csv   staged into Snowflake by sql/04_seed_adversaries.sql
  data/glasspocket.duckdb  the local preview store, see app/data.py

Usage
    python tools/make_synthetic.py --all
    python tools/make_synthetic.py --orgs --disbursements
    python tools/make_synthetic.py --project     # PCA and graph layout only

THE LABELLING CONTRACT
    Every row this file writes carries batch_id 'SYNTH_ADVERSARY_V1' and
    is_synthetic = TRUE. Nothing generated here is ever marked verified.
    The generator also records WHICH technique produced each row, because
    Tab 02 reports the technique breakdown and that reporting is only
    honest if the tactic is known by construction.
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import random
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
IRS = DATA / "irs"
GEO = DATA / "geo"
OUT = DATA / "synthetic"
DUCKDB_PATH = DATA / "glasspocket.duckdb"

SEED = 20260907          # the contest deadline, so runs are reproducible
BATCH_SYNTH = "SYNTH_ADVERSARY_V1"
BATCH_BMF = "IRS_BMF_2026"
BATCH_IATI = "IATI_2026"

SIMILARITY_THRESHOLD = 0.86
VECTOR_DIM = 768

#: WFP State of Palestine External Situation Report 55, 6 June 2025.
#: 590 trucks moved from Ashdod to Kerem Shalom, 371 collected inside Gaza.
#: The synthetic attrition is tuned so the aggregate delivery share sits
#: close to this ratio. The individual events are not real, and neither
#: the interface nor this file implies otherwise.
WFP_TRUCKS_MOVED = 590
WFP_TRUCKS_COLLECTED = 371
TARGET_DELIVERY_RATE = WFP_TRUCKS_COLLECTED / WFP_TRUCKS_MOVED   # 0.6288

rng = np.random.default_rng(SEED)
pyrng = random.Random(SEED)


# ===========================================================================
# 1. The real side
# ===========================================================================

BMF_COLUMNS = [
    "EIN", "NAME", "ICO", "STREET", "CITY", "STATE", "ZIP", "GROUP",
    "SUBSECTION", "AFFILIATION", "CLASSIFICATION", "RULING", "DEDUCTIBILITY",
    "FOUNDATION", "ACTIVITY", "ORGANIZATION", "STATUS", "TAX_PERIOD",
    "ASSET_CD", "INCOME_CD", "FILING_REQ_CD", "PF_FILING_REQ_CD", "ACCT_PD",
    "ASSET_AMT", "INCOME_AMT", "REVENUE_AMT", "NTEE_CD", "SORT_NAME",
]

NTEE_CAUSE = {
    "A": "arts and culture", "B": "education", "C": "environment",
    "D": "animals", "E": "medical", "F": "mental health",
    "G": "disease research", "H": "medical research", "I": "public safety",
    "J": "employment", "K": "food and agriculture", "L": "housing",
    "M": "disaster relief", "N": "recreation and sport",
    "O": "youth development", "P": "human services",
    "Q": "international development", "R": "civil rights",
    "S": "community development", "T": "philanthropy", "U": "science",
    "V": "social science", "W": "public benefit", "X": "religion",
    "Y": "mutual benefit",
}

#: Causes an impersonator actually targets. Disaster relief leads because
#: that is the documented post-wildfire pattern (BforeAI, January 2025).
TARGET_CAUSES = [
    "disaster relief", "human services", "medical", "youth development",
    "international development", "food and agriculture", "housing",
    "education", "civil rights", "environment",
]


def ntee_cause(code) -> str:
    if not isinstance(code, str) or not code:
        return "unclassified"
    return NTEE_CAUSE.get(code.strip().upper()[:1], "unclassified")


def load_zip_centroids() -> pd.DataFrame:
    """Census ZCTA gazetteer. Official, free, and it joins on ZIP."""
    path = next(GEO.glob("*Gaz_zcta_national.txt"), None)
    if path is None:
        raise SystemExit(
            "Missing the Census ZCTA gazetteer. Download it into data/geo/:\n"
            "  https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
            "2023_Gazetteer/2023_Gaz_zcta_national.zip"
        )
    df = pd.read_csv(path, sep="\t", dtype={"GEOID": str})
    df.columns = [c.strip() for c in df.columns]
    return pd.DataFrame({
        "zip": df["GEOID"].str.zfill(5),
        "lat": df["INTPTLAT"].astype(float),
        "lon": df["INTPTLONG"].astype(float),
        "source": "US Census 2023 ZCTA Gazetteer",
    })


def load_revocation() -> set[str]:
    """The Auto-Revocation List.

    BE PRECISE. This is overwhelmingly a record of organisations that
    failed to file for three consecutive years. It is not a fraud list.
    It is used here only to withhold the "in good standing" flag, and
    every surface that renders it says "no longer in good standing".
    """
    candidates = [
        p for p in IRS.glob("*")
        if "revocation" in p.name.lower() and p.suffix.lower() in {".csv", ".dat", ".txt"}
    ]
    for path in candidates:
        # The published file is pipe-delimited with no header row and a
        # couple of blank leading lines. EIN is the first field.
        # Pipe-delimited, no header, twelve fields, two blank leading lines.
        #   0 EIN  ... 9 revocation date  10 posting date  11 reinstatement date
        for sep in ("|", ","):
            try:
                df = pd.read_csv(
                    path, sep=sep, header=None, dtype=str,
                    names=[f"c{i}" for i in range(12)],
                    on_bad_lines="skip", encoding_errors="replace",
                    skip_blank_lines=True, low_memory=False,
                )
            except Exception:                   # noqa: BLE001
                continue

            if df["c11"].isna().all() and df["c9"].isna().all():
                continue

            eins = (df["c0"].astype(str)
                    .str.replace(r"\D", "", regex=True).str.zfill(9))
            # An organisation with a reinstatement date is back in good
            # standing and must not be counted. The list is cumulative
            # across many years, and treating it wholesale would
            # misdescribe hundreds of thousands of organisations, which is
            # precisely the sloppy inference this project exists to
            # criticise. See Section 05.
            reinstated = df["c11"].notna() & (df["c11"].astype(str).str.strip() != "")
            still_out = set(eins[(eins.str.len() == 9) & ~reinstated])
            if still_out:
                print(f"  revocation list: {len(still_out):,} EINs currently "
                      f"not in good standing, {int(reinstated.sum()):,} since "
                      f"reinstated ({path.name})")
                return still_out
    print("  no revocation list found; every BMF row keeps its filed status")
    return set()


def build_real_orgs(sample_size: int | None) -> pd.DataFrame:
    """Normalise the BMF into the real side of STAGING.ORGS."""
    files = sorted(IRS.glob("eo*.csv"))
    if not files:
        raise SystemExit(
            "No IRS Business Master File extracts in data/irs/.\n"
            "Download the regional files from irs.gov, Charities and "
            "Non-Profits, EO BMF extract."
        )

    frames = []
    for path in files:
        print(f"  reading {path.name}")
        df = pd.read_csv(
            path, dtype=str, usecols=lambda c: c.strip().upper() in set(BMF_COLUMNS),
            on_bad_lines="skip", encoding_errors="replace", low_memory=False,
        )
        df.columns = [c.strip().upper() for c in df.columns]
        df["SOURCE_FILE"] = path.name
        frames.append(df)

    bmf = pd.concat(frames, ignore_index=True)
    print(f"  {len(bmf):,} raw BMF rows")

    bmf["ein"] = bmf["EIN"].astype(str).str.replace(r"\D", "", regex=True)
    bmf = bmf[bmf["ein"].str.len() == 9]
    bmf = bmf[bmf["NAME"].notna()]
    bmf["revenue"] = pd.to_numeric(bmf.get("REVENUE_AMT"), errors="coerce")

    # One row per EIN, keeping the largest reported revenue.
    bmf = (bmf.sort_values("revenue", ascending=False, na_position="last")
              .drop_duplicates(subset="ein", keep="first"))

    bmf["zip5"] = (bmf["ZIP"].astype(str)
                   .str.replace(r"\D", "", regex=True).str[:5].str.zfill(5))

    zips = load_zip_centroids()
    bmf = bmf.merge(zips, left_on="zip5", right_on="zip", how="left")
    bmf = bmf[bmf["lat"].notna()]
    print(f"  {len(bmf):,} rows with a resolvable coordinate")

    revoked = load_revocation()
    bmf["cause"] = bmf["NTEE_CD"].map(ntee_cause)
    bmf["is_verified"] = (bmf["STATUS"].astype(str).str.strip() == "01") & (
        ~bmf["ein"].isin(revoked)
    )

    orgs = pd.DataFrame({
        "org_id": "ORG_" + bmf["ein"],
        "ein": bmf["ein"],
        "name": bmf["NAME"].str.strip().str.title(),
        "city": bmf["CITY"].astype(str).str.strip().str.title(),
        "state": bmf["STATE"].astype(str).str.strip().str.upper(),
        "ntee_code": bmf["NTEE_CD"].astype(str).str.strip().str.upper(),
        "cause": bmf["cause"],
        "lat": bmf["lat"].astype(float),
        "lon": bmf["lon"].astype(float),
        "revenue": bmf["revenue"],
        "is_verified": bmf["is_verified"],
    })
    orgs["blurb"] = (
        orgs["cause"] + " organisation serving "
        + orgs["city"].fillna("its community") + ", " + orgs["state"].fillna("US")
    )
    orgs["max_hops"] = np.select(
        [orgs["revenue"] >= 50_000_000, orgs["revenue"] >= 5_000_000,
         orgs["revenue"] >= 500_000, orgs["revenue"] >= 50_000],
        [40, 24, 14, 8], default=5,
    ).astype(int)
    orgs["is_synthetic"] = False
    orgs["batch_id"] = BATCH_BMF
    orgs["synth_technique"] = None
    orgs["synth_target_id"] = None

    total_real = len(orgs)

    if sample_size and len(orgs) > sample_size:
        # Concentrate the vector corpus on the causes an impersonator
        # actually targets, which mirrors the region-and-cause pre-filter
        # the detection query uses. Real row counts are reported in full
        # on The Brief regardless of this sampling.
        weights = np.where(orgs["cause"].isin(TARGET_CAUSES), 6.0, 1.0)
        weights = weights / weights.sum()
        keep = rng.choice(len(orgs), size=sample_size, replace=False, p=weights)
        orgs = orgs.iloc[np.sort(keep)].reset_index(drop=True)
        print(f"  vector corpus sampled to {len(orgs):,} of {total_real:,}")

    orgs.attrs["total_real_rows"] = total_real
    return orgs.reset_index(drop=True)


# ===========================================================================
# 2. The adversaries
# ===========================================================================

#: Synonym pairs. Meaning preserved, spelling changed. This is the whole
#: thesis: a name that means the same thing but spells differently.
SYNONYMS = {
    "relief": "aid", "aid": "relief", "foundation": "trust",
    "trust": "foundation", "children": "kids", "kids": "children",
    "fund": "appeal", "appeal": "fund", "society": "association",
    "association": "society", "center": "centre", "centre": "hub",
    "institute": "academy", "academy": "institute", "council": "board",
    "board": "council", "alliance": "coalition", "coalition": "alliance",
    "network": "partnership", "partnership": "network",
    "services": "support", "support": "services", "care": "welfare",
    "welfare": "care", "family": "families", "families": "family",
    "community": "neighborhood", "neighborhood": "community",
    "health": "wellness", "wellness": "health", "food": "nutrition",
    "nutrition": "food", "housing": "shelter", "shelter": "housing",
    "education": "learning", "learning": "education", "youth": "young",
    "hope": "promise", "promise": "hope", "mission": "outreach",
    "outreach": "mission", "rescue": "recovery", "recovery": "rescue",
    "international": "global", "global": "international",
}

FILLERS = ["National", "United", "American", "Regional", "Greater", "Central"]

#: Documented post-disaster keywords. BforeAI recorded 119 domains
#: registered between 8 and 13 January 2025 using exactly this vocabulary.
DISASTER_KEYWORDS = [
    "Wildfire Relief", "Fire Recovery", "Disaster Response", "Rebuild Fund",
    "Emergency Appeal", "Storm Relief", "Flood Recovery", "Crisis Fund",
]

TECHNIQUES = [
    "semantic clone",
    "token reorder",
    "homoglyph and spacing",
    "disaster attachment",
    "geographic implausibility",
]


def technique_semantic_clone(name: str) -> str | None:
    """Replace one word with a synonym while preserving meaning."""
    tokens = name.split()
    swappable = [i for i, t in enumerate(tokens) if t.lower().strip(",.") in SYNONYMS]
    if not swappable:
        return None
    idx = pyrng.choice(swappable)
    original = tokens[idx].lower().strip(",.")
    tokens[idx] = SYNONYMS[original].title()
    return " ".join(tokens)


STOPWORDS = {"the", "of", "for", "and", "a", "an", "in", "at", "to", "inc"}


def is_plausible_base_name(name: str) -> bool:
    """Reject base names that cannot produce a convincing imitation.

    The Business Master File is full of abbreviations, chapter codes and
    fragments: "Sc For Ed", "Pta Fl Cong", "Iam Dist Lodge 141". Cloning
    one of those produces a name no donor could plausibly be fooled by,
    and a demo built on it argues against itself. The detector is not made
    weaker by this filter, because the filter is applied when choosing
    which organisations to imitate, never when deciding what to flag.
    """
    tokens = [t for t in name.split() if t.lower() not in STOPWORDS]
    if len(tokens) < 3 or len(name) < 20:
        return False
    # Every meaningful token must read as a word, not an abbreviation.
    if any(len(t) < 4 or not t.isalpha() for t in tokens):
        return False
    # At least one token must be recognisable charity vocabulary, so the
    # pair reads as two organisations doing the same thing.
    vocabulary = set(SYNONYMS) | {
        "association", "committee", "council", "church", "school",
        "hospital", "college", "league", "project", "coalition",
    }
    return any(t.lower() in vocabulary for t in tokens)


SUFFIXES = {"inc", "incorporated", "corp", "llc", "ltd", "co"}


def technique_token_reorder(name: str) -> str | None:
    """Same words, different order, plus an optional filler word.

    Reordering has to produce something a donor could actually confuse. A
    blind rotation gives "American Enrichment Inc Brooklyn Youth", which
    nobody would fall for and which therefore proves nothing. Real
    impersonators invert around a preposition, so this does too:

        Brooklyn Youth Enrichment Inc  ->  Youth Enrichment of Brooklyn Inc
        Great Valley Senior Center     ->  Senior Center of Great Valley
    """
    tokens = name.split()
    suffix = ""
    if tokens and tokens[-1].lower().strip(".") in SUFFIXES:
        suffix = " " + tokens[-1]
        tokens = tokens[:-1]

    if len(tokens) < 3:
        return None

    # Never split so the second half opens on a stopword, or the result
    # reads "Of Math Leagues of Maine Association" and fools nobody.
    split = len(tokens) // 2
    while split < len(tokens) - 1 and tokens[split].lower() in STOPWORDS:
        split += 1
    while split > 1 and tokens[split - 1].lower() in STOPWORDS:
        split -= 1

    head, tail = tokens[:split], tokens[split:]
    if not head or not tail or tail[0].lower() in STOPWORDS:
        return None

    reordered = " ".join(tail) + " of " + " ".join(head)
    if pyrng.random() < 0.4:
        reordered = f"{pyrng.choice(FILLERS)} {reordered}"
    return reordered + suffix


def technique_homoglyph(name: str) -> str | None:
    """A doubled letter, a hyphen inserted, an abbreviation expanded."""
    tokens = name.split()
    if not tokens:
        return None
    choice = pyrng.randint(0, 2)
    if choice == 0 and len(tokens) >= 2:
        return " ".join(tokens[:1]) + "-" + " ".join(tokens[1:])
    if choice == 1:
        idx = pyrng.randrange(len(tokens))
        word = tokens[idx]
        if len(word) > 3:
            pos = pyrng.randrange(1, len(word) - 1)
            tokens[idx] = word[:pos] + word[pos] + word[pos:]
            return " ".join(tokens)
        return None
    return name.replace(" And ", " & ").replace(" Of ", " ")


def technique_disaster_attachment(name: str) -> str | None:
    """Append a current disaster keyword to a legitimate base name."""
    base = " ".join(name.split()[:3])
    return f"{base} {pyrng.choice(DISASTER_KEYWORDS)}"


def build_adversaries(real: pd.DataFrame, count: int) -> pd.DataFrame:
    """Roughly 400 adversarial organisations.

    Every one is derived from a real BMF entry that is in good standing,
    so the detection has a genuine target to match against. The technique
    is recorded on the row.
    """
    pool = real[real["is_verified"] & real["cause"].isin(TARGET_CAUSES)]
    if pool.empty:
        pool = real[real["is_verified"]]

    # Only imitate organisations whose names could plausibly be imitated.
    plausible = pool[pool["name"].map(is_plausible_base_name)]
    print(f"  {len(plausible):,} of {len(pool):,} candidate targets have a "
          f"name worth imitating")
    if len(plausible) < 200:
        raise SystemExit(
            "Too few plausible base names. Loosen is_plausible_base_name or "
            "widen TARGET_CAUSES before continuing."
        )
    pool = plausible

    builders = {
        "semantic clone": technique_semantic_clone,
        "token reorder": technique_token_reorder,
        "homoglyph and spacing": technique_homoglyph,
        "disaster attachment": technique_disaster_attachment,
        "geographic implausibility": lambda n: n,   # name kept, geography moved
    }

    rows, attempts = [], 0
    seen_names: set[str] = set()
    while len(rows) < count and attempts < count * 60:
        attempts += 1
        target = pool.iloc[pyrng.randrange(len(pool))]
        technique = pyrng.choice(TECHNIQUES)
        new_name = builders[technique](str(target["name"]))
        if not new_name or new_name == target["name"] or new_name in seen_names:
            continue
        seen_names.add(new_name)

        # Geography. Most impersonators register near their target so the
        # city line looks right. The geographic-implausibility technique
        # instead places the registration far outside any plausible
        # operating radius, which is what Tab 03 is built to catch.
        if technique == "geographic implausibility":
            lat = float(target["lat"]) + rng.normal(0, 12)
            lon = float(target["lon"]) + rng.normal(0, 26)
        else:
            lat = float(target["lat"]) + rng.normal(0, 0.05)
            lon = float(target["lon"]) + rng.normal(0, 0.05)

        digest = hashlib.sha256(
            f"{new_name}|{target['ein']}|{technique}".encode()
        ).hexdigest()
        fake_ein = "9" + str(int(digest[:12], 16))[:8].zfill(8)

        rows.append({
            "org_id": f"ORG_{fake_ein}",
            "ein": fake_ein,
            "name": new_name,
            "blurb": (f"{target['cause']} organisation serving "
                      f"{target['city']}, {target['state']}"),
            "city": target["city"],
            "state": target["state"],
            "ntee_code": target["ntee_code"],
            "cause": target["cause"],
            "lat": float(np.clip(lat, -84, 84)),
            "lon": float(np.clip(lon, -179, 179)),
            "max_hops": int(min(int(target["max_hops"]), 10)),
            "synth_technique": technique,
            "synth_target_id": target["org_id"],
            "is_verified": False,        # never, by construction
            "is_synthetic": True,
            "batch_id": BATCH_SYNTH,
            "revenue": np.nan,
        })

    print(f"  {len(rows)} adversaries across {len(TECHNIQUES)} techniques")
    return pd.DataFrame(rows)


# ===========================================================================
# 3. Embeddings, similarity and geography
# ===========================================================================


def concept_signature(text: str) -> list[str]:
    """Reduce a name to canonical concepts.

    Synonyms collapse onto a single token, so two names that mean the same
    thing produce the same signature even when they share few characters.
    """
    out = []
    for raw in text.lower().replace("-", " ").replace("&", "and").split():
        token = raw.strip(",.'\"()")
        if not token or token in {"the", "of", "for", "and", "inc", "a"}:
            continue
        canonical = min(token, SYNONYMS.get(token, token))
        out.append(canonical)
    return out


def embed_local(names: pd.Series, causes: pd.Series) -> np.ndarray:
    """LOCAL PREVIEW STAND-IN for AI_EMBED.

    In Snowflake the vectors come from AI_EMBED('snowflake-arctic-embed-m')
    in sql/06_embeddings.sql, which is the real pipeline and the one the
    write-up describes. This function exists only so the application can
    be developed and reviewed without a warehouse attached.

    It projects a bag-of-canonical-concepts through a fixed random matrix.
    That reproduces the property the tab depends on, which is that meaning
    survives a spelling change, but it is NOT a language model and the
    preview interface says so.
    """
    vocab: dict[str, int] = {}
    docs = []
    for name, cause in zip(names, causes):
        tokens = concept_signature(f"{name} {cause}")
        docs.append(tokens)
        for token in tokens:
            vocab.setdefault(token, len(vocab))

    counts = np.zeros((len(docs), len(vocab)), dtype=np.float32)
    for row, tokens in enumerate(docs):
        for token in tokens:
            counts[row, vocab[token]] += 1.0

    # Inverse document frequency, so common words carry less weight.
    df = (counts > 0).sum(axis=0)
    idf = np.log((len(docs) + 1) / (df + 1)).astype(np.float32) + 1.0
    counts *= idf

    projection = np.random.default_rng(SEED).normal(
        0, 1 / np.sqrt(VECTOR_DIM), size=(len(vocab), VECTOR_DIM)
    ).astype(np.float32)
    vectors = counts @ projection

    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


def jaro_winkler(s1: str, s2: str) -> float:
    """Jaro-Winkler, matching Snowflake's JAROWINKLER_SIMILARITY / 100."""
    s1, s2 = s1.lower(), s2.lower()
    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0

    window = max(len1, len2) // 2 - 1
    window = max(window, 0)
    f1 = [False] * len1
    f2 = [False] * len2

    matches = 0
    for i in range(len1):
        for j in range(max(0, i - window), min(len2, i + window + 1)):
            if not f2[j] and s1[i] == s2[j]:
                f1[i] = f2[j] = True
                matches += 1
                break
    if matches == 0:
        return 0.0

    transpositions, k = 0, 0
    for i in range(len1):
        if f1[i]:
            while not f2[k]:
                k += 1
            if s1[i] != s2[k]:
                transpositions += 1
            k += 1
    transpositions //= 2

    jaro = (matches / len1 + matches / len2
            + (matches - transpositions) / matches) / 3.0

    prefix = 0
    for a, b in zip(s1[:4], s2[:4]):
        if a != b:
            break
        prefix += 1
    return jaro + prefix * 0.1 * (1 - jaro)


def h3_index(lat: float, lon: float, resolution: int) -> str:
    import h3
    return h3.latlng_to_cell(float(lat), float(lon), resolution)


def h3_grid_distance(a: str, b: str) -> int:
    import h3
    try:
        return int(h3.grid_distance(a, b))
    except Exception:                       # noqa: BLE001
        return 999          # different base cell: unreachable, so implausible


def haversine_km(lat1, lon1, lat2, lon2) -> np.ndarray:
    r = 6371.0088
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def index_orgs(orgs: pd.DataFrame) -> pd.DataFrame:
    """Add the H3 columns. Resolution 5 for footprint, 3 for the pre-filter."""
    orgs = orgs.copy()
    orgs["home_h3"] = [h3_index(a, b, 5) for a, b in zip(orgs["lat"], orgs["lon"])]
    orgs["region_h3"] = [h3_index(a, b, 3) for a, b in zip(orgs["lat"], orgs["lon"])]
    return orgs


def detect_clones(orgs: pd.DataFrame, vectors: np.ndarray) -> pd.DataFrame:
    """Clone pairs, with the mandatory region-and-cause pre-filter.

    TRAP 06. The pre-filter is not an optimisation, it is the difference
    between a bounded query and a full cross product. It is applied here
    exactly as it is in sql/07_clone_detection.sql.
    """
    index = {org_id: i for i, org_id in enumerate(orgs["org_id"])}
    suspects = orgs[orgs["is_synthetic"]]
    real_by_key: dict[tuple, list] = {}
    for row in orgs[~orgs["is_synthetic"] & orgs["is_verified"]].itertuples():
        real_by_key.setdefault((row.region_h3, row.cause), []).append(row)

    rows = []
    for suspect in suspects.itertuples():
        candidates = real_by_key.get((suspect.region_h3, suspect.cause), [])
        if not candidates:
            continue
        sv = vectors[index[suspect.org_id]]
        cand_idx = [index[c.org_id] for c in candidates]
        sims = vectors[cand_idx] @ sv          # both sides are unit-normalised

        for candidate, semantic in zip(candidates, sims):
            if semantic < SIMILARITY_THRESHOLD or candidate.ein == suspect.ein:
                continue
            string_sim = jaro_winkler(suspect.name, candidate.name)
            rows.append({
                "suspect_id": suspect.org_id,
                "suspect_name": suspect.name,
                "target_id": candidate.org_id,
                "target_name": candidate.name,
                "city": suspect.city,
                "state": suspect.state,
                "cause": suspect.cause,
                "synth_technique": suspect.synth_technique,
                "semantic_sim": float(semantic),
                "string_sim": float(string_sim),
                "evasion_gap": float(semantic - string_sim),
            })

    pairs = pd.DataFrame(rows)
    print(f"  {len(pairs)} clone pairs at threshold {SIMILARITY_THRESHOLD}")
    return pairs


def threshold_sweep(orgs: pd.DataFrame, vectors: np.ndarray,
                    confirmed: pd.DataFrame) -> pd.DataFrame:
    """Sweep the cosine cut-off from 0.70 to 0.99 and store the counts.

    Precomputed so the Tab 02 slider responds instantly with no query
    behind it.
    """
    index = {org_id: i for i, org_id in enumerate(orgs["org_id"])}
    real_by_key: dict[tuple, list] = {}
    for row in orgs[~orgs["is_synthetic"] & orgs["is_verified"]].itertuples():
        real_by_key.setdefault((row.region_h3, row.cause), []).append(row)

    sims, keys = [], []
    for suspect in orgs[orgs["is_synthetic"]].itertuples():
        candidates = real_by_key.get((suspect.region_h3, suspect.cause), [])
        if not candidates:
            continue
        sv = vectors[index[suspect.org_id]]
        cand_idx = [index[c.org_id] for c in candidates]
        for candidate, sim in zip(candidates, vectors[cand_idx] @ sv):
            sims.append(float(sim))
            keys.append((suspect.org_id, candidate.org_id))

    sims_arr = np.asarray(sims)
    confirmed_keys = set(zip(confirmed["suspect_id"], confirmed["target_id"])) \
        if len(confirmed) else set()
    is_confirmed = np.array([k in confirmed_keys for k in keys], dtype=bool)

    out = []
    for threshold in np.round(np.arange(0.70, 1.00, 0.01), 2):
        mask = sims_arr >= threshold
        out.append({
            "threshold": float(threshold),
            "pairs_detected": int(mask.sum()),
            "pairs_ai_confirmed": int((mask & is_confirmed).sum()),
            "is_production_value": bool(abs(threshold - SIMILARITY_THRESHOLD) < 1e-9),
        })
    return pd.DataFrame(out)


# ===========================================================================
# 4. Disbursements, deliveries and beneficiaries
# ===========================================================================

# Real places where humanitarian aid is actually coordinated, across six
# continents. The spread is not decoration: the geometry test in sql/08
# asks whether a delivery landed inside the footprint an organisation
# declared, and that question is only interesting when footprints are far
# enough apart for the answer to vary. Sixteen districts inside one band
# of latitude made every stray delivery look alike.
#
# NOTE ON ORDER. Appending rather than reordering is deliberate. Events
# are assigned by drawing an index from this list, so inserting a row in
# the middle would move every existing delivery to a different district
# on the next regeneration, and the 285 compressed-NFT receipts already
# on devnet reference those events by id. Add to the end. Never reorder.
DISTRICTS = [
    # Middle East and North Africa
    ("Rafah", "PS", 31.2870, 34.2500), ("Khan Yunis", "PS", 31.3400, 34.3060),
    ("Deir al-Balah", "PS", 31.4180, 34.3510), ("Gaza North", "PS", 31.5490, 34.5060),
    ("Wad Madani", "SD", 14.4010, 33.5190), ("El Obeid", "SD", 13.1840, 30.2170),
    ("Kassala", "SD", 15.4510, 36.4000), ("Nyala", "SD", 12.0500, 24.8820),
    ("Sitapur", "IN", 27.5680, 80.6820), ("Barabanki", "IN", 26.9250, 81.1940),
    ("Chitrakoot", "IN", 25.2000, 80.9000), ("Balrampur", "IN", 27.4300, 82.1800),
    ("Cox's Bazar", "BD", 21.4270, 92.0050), ("Kutupalong", "BD", 21.2130, 92.1620),
    ("Maradi", "NE", 13.5000, 7.1000), ("Diffa", "NE", 13.3150, 12.6110),
    # Sub-Saharan Africa
    ("Goma", "CD", -1.6790, 29.2280), ("Juba", "SS", 4.8590, 31.5710),
    ("Maiduguri", "NG", 11.8330, 13.1500), ("Dollo Ado", "ET", 4.1700, 42.0700),
    ("Dadaab", "KE", 0.0500, 40.3100), ("Mopti", "ML", 14.4890, -4.1830),
    ("Cabo Delgado", "MZ", -12.9740, 40.5170), ("Zinder", "NE", 13.8060, 8.9880),
    # Western Asia
    ("Aleppo", "SY", 36.2020, 37.1340), ("Zaatari", "JO", 32.2940, 36.3250),
    ("Sanaa", "YE", 15.3690, 44.1910), ("Erbil", "IQ", 36.1900, 43.9930),
    # South and South-East Asia
    ("Kabul", "AF", 34.5550, 69.2075), ("Sittwe", "MM", 20.1450, 92.8990),
    ("Kathmandu", "NP", 27.7170, 85.3240), ("Tacloban", "PH", 11.2440, 125.0030),
    ("Quetta", "PK", 30.1800, 66.9750),
    # Europe
    ("Lviv", "UA", 49.8400, 24.0300), ("Chisinau", "MD", 47.0100, 28.8600),
    # Latin America and the Caribbean
    ("Port-au-Prince", "HT", 18.5940, -72.3070), ("Cucuta", "CO", 7.8940, -72.5040),
    ("Tapachula", "MX", 14.9060, -92.2670), ("La Guajira", "VE", 11.5480, -72.0000),
    # Oceania
    ("Port Vila", "VU", -17.7340, 168.3220),
]

PROGRAMMES = [
    "AID-2026-DR-114", "AID-2026-FS-207", "AID-2026-HL-330",
    "AID-2026-SH-455", "AID-2026-ED-512", "AID-2026-WS-618",
]


def assign_operating_bases(orgs: pd.DataFrame, n_real: int = 420) -> pd.DataFrame:
    """Give the programme-running organisations a declared operating base.

    WHY THIS EXISTS, AND WHY IT IS NOT THE REGISTERED ADDRESS.

    An organisation registered in Delaware that delivers food in Kassala
    is not suspicious, it is an international NGO doing exactly what it
    said it would do. Measuring grid distance from a US postal address to
    a Sudanese delivery point would therefore flag every single event, and
    a detector that flags everything has detected nothing.

    The meaningful question is whether a delivery landed inside the
    footprint the organisation DECLARED it operates in. So each programme
    organisation carries a declared operating base, taken from its
    activity locations, and the geometry test in sql/08 measures from
    there. The registered address stays on the row untouched as home_h3,
    because Tabs 01 and 02 pre-filter on it.
    """
    orgs = orgs.copy()
    orgs["base_lat"] = orgs["lat"]
    orgs["base_lon"] = orgs["lon"]
    orgs["base_district"] = None
    orgs["runs_programme"] = False

    real_pool = orgs.index[~orgs["is_synthetic"] & orgs["is_verified"]]
    chosen_real = rng.choice(real_pool, size=min(n_real, len(real_pool)),
                             replace=False)
    active_idx = list(orgs.index[orgs["is_synthetic"]]) + list(chosen_real)

    for idx in active_idx:
        district, _country, dlat, dlon = DISTRICTS[pyrng.randrange(len(DISTRICTS))]
        orgs.at[idx, "base_district"] = district
        orgs.at[idx, "base_lat"] = float(dlat + rng.normal(0, 0.12))
        orgs.at[idx, "base_lon"] = float(dlon + rng.normal(0, 0.12))
        orgs.at[idx, "runs_programme"] = True
        # An organisation running a field programme operates region-wide,
        # not city-wide: its footprint is the operating region rather than
        # the block around a registered office. Thirty resolution-5 grid
        # steps is roughly five hundred kilometres.
        orgs.at[idx, "max_hops"] = int(max(int(orgs.at[idx, "max_hops"]), 30))

    orgs["base_h3"] = [
        h3_index(a, b, 5) for a, b in zip(orgs["base_lat"], orgs["base_lon"])
    ]
    print(f"  {int(orgs['runs_programme'].sum()):,} organisations run a "
          f"field programme with a declared operating base")
    return orgs


def build_disbursements(orgs: pd.DataFrame, per_org: int) -> pd.DataFrame:
    """Delivery events, with attrition calibrated to the WFP ratio.

    Real geography, synthetic movement. Section 05 and Tab 04 section S6
    both state this, and The Brief states it again.

    Status mix is tuned so that delivered value over dispatched value
    lands close to 371/590, the WFP State of Palestine figure.
    """
    active = orgs[orgs["runs_programme"]]
    by_district = {d[0]: d for d in DISTRICTS}

    start = datetime(2026, 5, 1)
    rows = []
    for org in active.itertuples():
        n_events = pyrng.randint(max(3, per_org // 2), per_org)
        # A seeded organisation diverts more often, and sends aid outside
        # its declared footprint more often. These are the two signals the
        # geometry layer exists to surface.
        divert_bias = 0.055 if org.is_synthetic else 0.0
        stray_rate = 0.20 if org.is_synthetic else 0.012

        home = by_district[org.base_district]

        for _ in range(n_events):
            pledged = float(np.round(rng.uniform(400, 9500), 2))

            roll = rng.random()
            # Mix tuned so delivered value over dispatched value lands on
            # 371/590, the WFP State of Palestine ratio.
            if roll < 0.06:
                status = "PLEDGED"
            elif roll < 0.06 + 0.082 + divert_bias:
                status = "UNACCOUNTED"
            elif roll < 0.06 + 0.082 + divert_bias + 0.225:
                status = "DISPATCHED"
            else:
                status = "DELIVERED"

            amount = 0.0 if status == "PLEDGED" else float(
                np.round(pledged * rng.uniform(0.88, 1.0), 2))

            dispatched = start + timedelta(
                days=int(rng.integers(0, 120)), hours=int(rng.integers(0, 24)))

            # Where the delivery claims to have landed.
            hub_run = rng.random() < 0.022
            if hub_run:
                # A regional hub run: inside the declared footprint, but
                # four hundred kilometres away. Paired below with a
                # transit time under an hour, which is what makes it
                # IMPOSSIBLE_TRANSIT rather than merely distant. A truck
                # cannot do this, so the record is wrong even though the
                # destination is legitimate.
                district, country = home[0], home[1]
                lat = home[2] + float(rng.choice([-1, 1])) * rng.uniform(3.9, 4.3)
                lon = home[3] + rng.normal(0, 0.15)
            elif rng.random() < stray_rate:
                # Outside the declared footprint entirely: another
                # country, another continent. This is what
                # OUTSIDE_FOOTPRINT is built to catch.
                stray = DISTRICTS[pyrng.randrange(len(DISTRICTS))]
                district, country = stray[0], stray[1]
                lat = stray[2] + rng.normal(0, 0.6)
                lon = stray[3] + rng.normal(0, 0.6)
            else:
                district, country = home[0], home[1]
                lat = home[2] + rng.normal(0, 0.22)
                lon = home[3] + rng.normal(0, 0.22)

            if status in {"PLEDGED", "UNACCOUNTED"}:
                delivered = None
            elif hub_run or (org.is_synthetic and rng.random() < 0.04):
                # Physically impossible: a long distance covered in under
                # an hour. Seeded deliberately so Tab 04's feasibility
                # boundary has something real to reject.
                delivered = dispatched + timedelta(minutes=int(rng.integers(10, 55)))
            else:
                delivered = dispatched + timedelta(
                    hours=float(np.round(rng.uniform(6, 96), 1)))

            rows.append({
                "disbursement_id": f"DSB-{len(rows):07d}",
                "org_id": org.org_id,
                "programme_code": PROGRAMMES[pyrng.randrange(len(PROGRAMMES))],
                "beneficiary_id": f"BEN-{rng.integers(1, 26000):06d}",
                "amount_usd": amount,
                "pledged_usd": pledged,
                "district": district,
                "country": country,
                "lat": float(np.clip(lat, -84, 84)),
                "lon": float(np.clip(lon, -179, 179)),
                "dispatched_at": dispatched,
                "delivered_at": delivered,
                "status": status,
                "is_synthetic": True,
                "batch_id": BATCH_SYNTH,
            })

    disb = pd.DataFrame(rows)
    disb["delivery_h3"] = [h3_index(a, b, 7) for a, b in zip(disb["lat"], disb["lon"])]

    moved = disb.loc[disb["status"] != "PLEDGED", "amount_usd"].sum()
    delivered = disb.loc[disb["status"] == "DELIVERED", "amount_usd"].sum()
    rate = delivered / moved if moved else 0
    print(f"  {len(disb):,} delivery events, delivery rate {rate:.1%} "
          f"(WFP calibration target {TARGET_DELIVERY_RATE:.1%})")
    return disb


def build_geometry(orgs: pd.DataFrame, disb: pd.DataFrame) -> pd.DataFrame:
    """MARTS.DELIVERY_GEOMETRY, computed exactly as sql/08 computes it."""
    import h3

    org_cols = orgs.set_index("org_id")[
        ["name", "home_h3", "base_h3", "max_hops", "base_lat", "base_lon",
         "is_synthetic"]
    ]
    df = disb.join(org_cols, on="org_id", rsuffix="_org")

    # Distance is measured from the DECLARED OPERATING BASE, not from the
    # registered postal address. See assign_operating_bases for why.
    parent5 = [h3.cell_to_parent(c, 5) for c in df["delivery_h3"]]
    df["hops"] = [h3_grid_distance(b, p) for b, p in zip(df["base_h3"], parent5)]
    df["km_from_base"] = haversine_km(
        df["base_lat"].to_numpy(), df["base_lon"].to_numpy(),
        df["lat"].to_numpy(), df["lon"].to_numpy(),
    )
    df["transit_hours"] = (
        (df["delivered_at"] - df["dispatched_at"]).dt.total_seconds() / 3600.0
    )

    df["geometry_verdict"] = np.select(
        [
            df["status"] == "UNACCOUNTED",
            df["hops"] > df["max_hops"],
            (df["transit_hours"] < 1) & (df["km_from_base"] > 400),
        ],
        ["NEVER_ARRIVED", "OUTSIDE_FOOTPRINT", "IMPOSSIBLE_TRANSIT"],
        default="PLAUSIBLE",
    )
    df = df.rename(columns={"name": "org_name"})

    share = (df["geometry_verdict"] != "PLAUSIBLE").mean()
    print(f"  implausible geometry share {share:.1%}")
    print("  " + df["geometry_verdict"].value_counts().to_dict().__repr__())
    return df


def build_beneficiaries(disb: pd.DataFrame) -> pd.DataFrame:
    """Entirely synthetic beneficiary records.

    No real personal data enters this project at any point, which is
    itself the correct engineering decision and is stated in the
    interface. Section 07.
    """
    bens = disb[["beneficiary_id", "district", "programme_code"]].drop_duplicates(
        subset="beneficiary_id"
    ).copy()
    bens["cause"] = rng.choice(TARGET_CAUSES, size=len(bens))
    bens["cohort_band"] = rng.choice(
        ["household", "individual", "group"], size=len(bens), p=[0.55, 0.30, 0.15]
    )
    bens["is_synthetic"] = True
    bens["batch_id"] = BATCH_SYNTH
    print(f"  {len(bens):,} synthetic beneficiary records")
    return bens.reset_index(drop=True)


# ===========================================================================
# 5. Offline geometry: PCA and the spring layout
# ===========================================================================


def build_projection(orgs: pd.DataFrame, vectors: np.ndarray,
                     pairs: pd.DataFrame, limit: int = 900) -> pd.DataFrame:
    """Plain PCA to two components, stored on MARTS.ORG_PROJECTION.

    Do not attempt UMAP in the warehouse runtime. Section 07, C01-3. The
    tab then runs a simple SELECT and renders instantly.
    """
    from sklearn.decomposition import PCA

    keep = set(pairs["suspect_id"]) | set(pairs["target_id"])
    others = orgs[~orgs["org_id"].isin(keep)]
    if len(others) > limit:
        others = others.sample(n=limit, random_state=SEED)
    subset = orgs[orgs["org_id"].isin(keep | set(others["org_id"]))]

    index = {org_id: i for i, org_id in enumerate(orgs["org_id"])}
    rows = [index[o] for o in subset["org_id"]]
    coords = PCA(n_components=2, random_state=SEED).fit_transform(vectors[rows])

    print(f"  projected {len(subset):,} organisations to two dimensions")
    return pd.DataFrame({
        "org_id": subset["org_id"].to_numpy(),
        "pc1": coords[:, 0],
        "pc2": coords[:, 1],
    })


def build_graph(pairs: pd.DataFrame, orgs: pd.DataFrame):
    """networkx spring layout, written to MARTS.GRAPH_NODES and _EDGES.

    Third-party network components cannot load under the Content Security
    Policy, so the graph is drawn from Plotly primitives and the positions
    are computed here, once, offline.
    """
    import networkx as nx

    graph = nx.Graph()
    for row in pairs.itertuples():
        graph.add_edge(row.suspect_id, row.target_id, weight=float(row.semantic_sim))

    if graph.number_of_nodes() == 0:
        return pd.DataFrame(columns=["org_id", "name", "x", "y", "node_kind",
                                     "degree"]), pd.DataFrame(
            columns=["source_id", "target_id", "similarity"])

    layout = nx.spring_layout(graph, seed=SEED, k=0.42, iterations=90)
    meta = orgs.set_index("org_id")[["name", "is_synthetic"]]

    nodes = pd.DataFrame([
        {
            "org_id": node,
            "name": meta.loc[node, "name"] if node in meta.index else node,
            "x": float(pos[0]),
            "y": float(pos[1]),
            "node_kind": ("imitation"
                          if node in meta.index and meta.loc[node, "is_synthetic"]
                          else "verified"),
            "degree": int(graph.degree(node)),
        }
        for node, pos in layout.items()
    ])
    edges = pairs[["suspect_id", "target_id", "semantic_sim"]].rename(
        columns={"suspect_id": "source_id", "target_id": "target_id",
                 "semantic_sim": "similarity"}
    )
    print(f"  graph: {len(nodes)} nodes, {len(edges)} edges")
    return nodes, edges


# ===========================================================================
# 6. Risk score, receipts, and the local preview store
# ===========================================================================


def build_risk(orgs, pairs, geometry, receipts) -> pd.DataFrame:
    """MARTS.ORG_RISK, using the same weights as MARTS.F_RISK.

    The five components are stored alongside the total so the Tab 01
    waterfall reads them rather than recomputing them. If they ever
    disagree, the waterfall would be lying, which is worse than having no
    waterfall, so 99_acceptance_checks verifies the reconstruction.
    """
    clone = (pairs.groupby("suspect_id")
             .agg(semantic_sim=("semantic_sim", "max"),
                  evasion_gap=("evasion_gap", "max"),
                  pair_count=("target_id", "count"),
                  nearest_target_id=("target_id", "first"),
                  nearest_target_name=("target_name", "first"))
             .reset_index().rename(columns={"suspect_id": "org_id"})
             ) if len(pairs) else pd.DataFrame(
        columns=["org_id", "semantic_sim", "evasion_gap", "pair_count",
                 "nearest_target_id", "nearest_target_name"])

    geom = (geometry.assign(flag=(geometry["geometry_verdict"] != "PLAUSIBLE"))
            .groupby("org_id")
            .agg(geom_flags=("flag", "sum"))
            .reset_index())

    activity = (geometry.groupby("org_id").apply(
        lambda g: pd.Series({
            "unaccounted_ratio": (
                g.loc[g["status"] == "UNACCOUNTED", "amount_usd"].sum()
                / max(g["amount_usd"].sum(), 1)
            ),
            "delivery_rate": (
                g.loc[g["status"] == "DELIVERED", "amount_usd"].sum()
                / max(g["amount_usd"].sum(), 1)
            ),
            "moved_usd": g["amount_usd"].sum(),
            "disbursements": len(g),
        }), include_groups=False).reset_index())

    df = (orgs[["org_id", "name", "ein", "city", "state", "cause",
                "is_synthetic", "is_verified", "batch_id", "synth_technique"]]
          .merge(clone, on="org_id", how="left")
          .merge(geom, on="org_id", how="left")
          .merge(activity, on="org_id", how="left")
          .merge(receipts, on="org_id", how="left"))

    for col, default in (("semantic_sim", 0.0), ("evasion_gap", 0.0),
                         ("geom_flags", 0), ("unaccounted_ratio", 0.0),
                         ("receipts_missing", 0), ("delivery_rate", 0.0),
                         ("moved_usd", 0.0), ("disbursements", 0),
                         ("receipt_coverage", 0.0)):
        if col not in df.columns:
            df[col] = default
        df[col] = df[col].fillna(default)

    df["missing_receipts"] = df["receipts_missing"].astype(int)
    df["comp_semantic"] = 35 * np.clip((df["semantic_sim"] - 0.86) / 0.14, 0, None)
    df["comp_evasion"] = 25 * np.clip(df["evasion_gap"] / 0.45, None, 1)
    df["comp_geometry"] = 20 * np.clip(df["geom_flags"] / 5.0, None, 1)
    df["comp_unaccounted"] = 12 * np.clip(df["unaccounted_ratio"], None, 1)
    df["comp_receipts"] = 8 * np.clip(df["missing_receipts"] / 10.0, None, 1)
    df["risk_score"] = np.minimum(100, (
        df["comp_semantic"] + df["comp_evasion"] + df["comp_geometry"]
        + df["comp_unaccounted"] + df["comp_receipts"]))

    # Framing rule, Section 07. Never fraud, criminal, scam or guilty.
    df["verdict"] = np.select(
        [df["risk_score"] >= 55, df["is_verified"]],
        ["needs a second look", "verified"], default="unverified")
    df["scored_at"] = datetime.now()

    flagged_real = int(((~df["is_synthetic"]) &
                        (df["verdict"] == "needs a second look")).sum())
    if flagged_real:
        raise SystemExit(
            f"CONTRACT VIOLATION: {flagged_real} real organisations carry "
            "'needs a second look'. Section 05 forbids this. Do not proceed."
        )
    return df


def build_receipts(geometry: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame,
                                                    pd.DataFrame]:
    """Mint queue and a local mirror of the mint log.

    In the real build the log is written by bridge/src/index.ts after each
    compressed NFT is minted on devnet. The rows produced here are a local
    preview stand-in so the tab can be developed without the chain, and
    the interface labels them as such.

    THE DELIBERATE GAP. Roughly one in thirty eligible disbursements is
    withheld, so the missing-receipt finding on Tab 06 is genuine rather
    than staged. The Brief discloses it.
    """
    eligible = geometry[
        (geometry["status"] == "DELIVERED")
        & (geometry["geometry_verdict"] == "PLAUSIBLE")
    ].copy()

    if eligible.empty:
        raise SystemExit(
            "No disbursement is both delivered and geometrically plausible, so "
            "there is nothing to mint. The geometry model is mis-calibrated: "
            "check assign_operating_bases and the stray_rate in "
            "build_disbursements before continuing."
        )

    salt = "PREVIEW_SALT_NOT_A_SECRET"
    eligible["org_hash"] = [
        hashlib.sha256(f"{o}{salt}".encode()).hexdigest()
        for o in eligible["org_id"]
    ]
    eligible["amount_band"] = pd.cut(
        eligible["amount_usd"], bins=[-1, 500, 2000, 10000, np.inf],
        labels=["0-500", "500-2K", "2K-10K", "10K+"],
    ).astype(str)
    eligible["window_key"] = eligible["dispatched_at"].dt.strftime("%Y-%m")

    keep = eligible["disbursement_id"].apply(
        lambda d: int(hashlib.sha256(d.encode()).hexdigest(), 16) % 30 != 0
    )
    queue = eligible[keep].copy()

    mint_queue = pd.DataFrame({
        "queue_id": [f"Q-{i:07d}" for i in range(len(queue))],
        "disbursement_id": queue["disbursement_id"].to_numpy(),
        "programme_code": queue["programme_code"].to_numpy(),
        "amount_band": queue["amount_band"].to_numpy(),
        "window_key": queue["window_key"].to_numpy(),
        "org_hash": queue["org_hash"].to_numpy(),
        "status": "MINTED",
    })

    tree = "GPtree" + hashlib.sha256(b"glasspocket-devnet-tree").hexdigest()[:38]
    mint_log = pd.DataFrame({
        "disbursement_id": queue["disbursement_id"].to_numpy(),
        "asset_id": [
            "GPa" + hashlib.sha256(d.encode()).hexdigest()[:41]
            for d in queue["disbursement_id"]
        ],
        "signature": [
            hashlib.sha256(("sig" + d).encode()).hexdigest()
            + hashlib.sha256(("sig2" + d).encode()).hexdigest()[:24]
            for d in queue["disbursement_id"]
        ],
        "tree_address": tree,
        "leaf_index": np.arange(len(queue)),
        "minted_at": (queue["dispatched_at"]
                      + pd.to_timedelta(rng.integers(2, 72, len(queue)), unit="h")
                      ).to_numpy(),
        "amount_band": queue["amount_band"].to_numpy(),
    })
    mint_log["explorer_url"] = (
        "https://explorer.solana.com/address/" + mint_log["asset_id"]
        + "?cluster=devnet"
    )

    coverage = (geometry[geometry["status"].isin(["DELIVERED", "UNACCOUNTED"])]
                .groupby("org_id").size().rename("eligible_disbursements")
                .reset_index())
    minted = (mint_log.merge(
        geometry[["disbursement_id", "org_id"]], on="disbursement_id")
        .groupby("org_id").size().rename("receipts_on_chain").reset_index())
    coverage = coverage.merge(minted, on="org_id", how="left")
    coverage["receipts_on_chain"] = coverage["receipts_on_chain"].fillna(0).astype(int)
    coverage["receipts_missing"] = (
        coverage["eligible_disbursements"] - coverage["receipts_on_chain"]).clip(lower=0)
    coverage["receipt_coverage"] = (
        coverage["receipts_on_chain"] / coverage["eligible_disbursements"].clip(lower=1))

    print(f"  {len(mint_log):,} receipts, "
          f"{int(coverage['receipts_missing'].sum()):,} deliberately missing")
    return mint_queue, mint_log, coverage


# ===========================================================================
# entrypoint
# ===========================================================================


def write_outputs(tables: dict[str, pd.DataFrame], total_real_rows: int) -> None:
    """Write the staging CSVs and the local preview store."""
    OUT.mkdir(parents=True, exist_ok=True)

    synth_orgs = tables["staging_orgs"]
    synth_orgs = synth_orgs[synth_orgs["is_synthetic"]]
    synth_orgs[[
        "org_id", "ein", "name", "blurb", "city", "state", "ntee_code", "cause",
        "lat", "lon", "max_hops", "synth_technique", "synth_target_id",
    ]].to_csv(OUT / "synth_orgs.csv", index=False)

    tables["staging_disbursements"][[
        "disbursement_id", "org_id", "programme_code", "beneficiary_id",
        "amount_usd", "pledged_usd", "district", "lat", "lon",
        "dispatched_at", "delivered_at", "status",
    ]].to_csv(OUT / "synth_disbursements.csv", index=False)

    tables["staging_beneficiaries"][[
        "beneficiary_id", "district", "programme_code", "cause", "cohort_band",
    ]].to_csv(OUT / "synth_beneficiaries.csv", index=False)

    print(f"  staging CSVs written to {OUT.relative_to(ROOT)}")

    import duckdb

    if DUCKDB_PATH.exists():
        DUCKDB_PATH.unlink()
    con = duckdb.connect(str(DUCKDB_PATH))
    for name, df in tables.items():
        con.register("_tmp", df)
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _tmp")
        con.unregister("_tmp")

    con.execute(
        "CREATE OR REPLACE TABLE build_meta AS "
        "SELECT ? AS bmf_rows_available, ? AS generated_at, "
        "? AS similarity_threshold",
        [total_real_rows, datetime.now().isoformat(timespec="seconds"),
         SIMILARITY_THRESHOLD],
    )
    con.close()
    size_mb = DUCKDB_PATH.stat().st_size / 1e6
    print(f"  local preview store: {DUCKDB_PATH.relative_to(ROOT)} ({size_mb:.1f} MB)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="run every stage")
    parser.add_argument("--sample", type=int, default=45_000,
                        help="size of the vector corpus (default 45000)")
    parser.add_argument("--adversaries", type=int, default=400,
                        help="number of impersonators to generate")
    parser.add_argument("--events", type=int, default=14,
                        help="maximum delivery events per active organisation")
    args = parser.parse_args(argv)

    print("GLASSPOCKET / offline preparation")
    print("=" * 62)

    print("\n[1/8] real organisations, IRS Business Master File")
    real = build_real_orgs(args.sample)
    total_real = real.attrs["total_real_rows"]

    print("\n[2/8] adversaries")
    fake = build_adversaries(real, args.adversaries)

    orgs = pd.concat([real, fake], ignore_index=True)
    orgs = index_orgs(orgs)

    # The labelling contract, asserted before anything downstream runs.
    assert not orgs.loc[orgs["is_synthetic"], "is_verified"].any(), \
        "a seeded organisation is marked verified"
    assert (orgs.loc[orgs["is_synthetic"], "batch_id"] == BATCH_SYNTH).all(), \
        "a seeded row is missing its batch identifier"

    print("\n[3/8] embeddings and clone detection")
    vectors = embed_local(orgs["name"], orgs["cause"])
    pairs = detect_clones(orgs, vectors)
    if pairs.empty:
        raise SystemExit(
            "No clone pairs detected. The adversaries are not landing in the "
            "same region and cause as their targets. Check TARGET_CAUSES and "
            "the coordinate jitter before continuing."
        )
    confirmed = pairs[pairs["semantic_sim"] >= 0.88].copy()
    confirmed["ai_confirmed"] = True
    confirmed["confirmation_method"] = "PREVIEW_HEURISTIC"

    print("\n[4/8] threshold sweep")
    curve = threshold_sweep(orgs, vectors, confirmed)

    print("\n[5/8] disbursements and geometry")
    orgs = assign_operating_bases(orgs)
    disb = build_disbursements(orgs, args.events)
    geometry = build_geometry(orgs, disb)
    beneficiaries = build_beneficiaries(disb)

    print("\n[6/8] receipts")
    mint_queue, mint_log, coverage = build_receipts(geometry)

    print("\n[7/8] risk score")
    risk = build_risk(orgs, pairs, geometry, coverage)

    print("\n[8/8] projection and graph layout")
    projection = build_projection(orgs, vectors, pairs)
    nodes, edges = build_graph(pairs, orgs)

    # The seven cited figures. The authoritative copy for Snowflake is the
    # hand-entered INSERT in sql/04_seed_adversaries.sql; this CSV is the
    # same seven rows for the local preview store. If you change one, change
    # both. They must never drift, which is why neither is computed.
    citations = pd.read_csv(DATA / "evidence_citations.csv")
    citations["published_on"] = pd.to_datetime(citations["published_on"])
    if len(citations) != 7:
        raise SystemExit(
            f"evidence_citations.csv has {len(citations)} rows, expected 7. "
            "Section 01 defines exactly seven cited figures."
        )

    # Beneficiary facts, the object the privacy policy protects in Snowflake.
    beneficiary_facts = (
        disb[disb["status"].isin(["DELIVERED", "UNACCOUNTED"])]
        .merge(beneficiaries[["beneficiary_id", "cause"]], on="beneficiary_id",
               how="left")
        .assign(
            delivered_flag=lambda d: (d["status"] == "DELIVERED").astype(int),
            month_key=lambda d: d["dispatched_at"].dt.strftime("%Y-%m"),
        )[["beneficiary_id", "district", "programme_code", "cause",
           "amount_usd", "delivered_flag", "month_key"]]
    )

    tables = {
        "evidence_citations": citations,
        "beneficiary_facts": beneficiary_facts,
        "staging_orgs": orgs.drop(columns=["revenue"], errors="ignore"),
        "staging_disbursements": disb,
        "staging_beneficiaries": beneficiaries,
        "delivery_geometry": geometry,
        "clone_pairs": pairs,
        "clone_confirmed": confirmed,
        "threshold_curve": curve,
        "org_risk": risk,
        "org_projection": projection,
        "graph_nodes": nodes,
        "graph_edges": edges,
        "mint_queue": mint_queue,
        "mint_log": mint_log,
        "receipt_coverage": coverage,
    }

    print("\nwriting outputs")
    write_outputs(tables, total_real)

    print("\n" + "=" * 62)
    print(f"real rows   {total_real:,}")
    print(f"seeded rows {int(orgs['is_synthetic'].sum()) + len(disb) + len(beneficiaries):,}")
    print("every seeded row carries batch_id " + BATCH_SYNTH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
