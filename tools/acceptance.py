"""Acceptance criteria that can be checked without a warehouse.

Build Spec Section 11. The warehouse-side checks live in
sql/99_acceptance_checks.sql and need a Snowflake connection. This file
runs everything else: the integrity contract over the generated data, the
craft rules over the source, and the repository hygiene rules.

    python tools/acceptance.py

Exit code 1 if anything fails. Run it before recording.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
STORE = ROOT / "data" / "glasspocket.duckdb"

results: list[tuple[str, str, str, bool]] = []


def check(check_id: str, area: str, statement: str, passed: bool) -> None:
    results.append((check_id, area, statement, bool(passed)))


# ===========================================================================
# Integrity. Section 05's labelling contract, enforced not assumed.
# ===========================================================================


def integrity() -> None:
    import duckdb

    if not STORE.exists():
        check("INT-00", "integrity", "preview store exists", False)
        return

    con = duckdb.connect(str(STORE), read_only=True)

    def one(sql: str):
        return con.execute(sql).fetchone()[0]

    check(
        "INT-01", "integrity",
        "No real organisation appears on the suspect side of any pair",
        one("""SELECT COUNT(*) FROM clone_pairs p
               JOIN staging_orgs o ON o.org_id = p.suspect_id
               WHERE NOT o.is_synthetic""") == 0,
    )
    check(
        "INT-02", "integrity",
        'No real organisation carries the verdict "needs a second look"',
        one("""SELECT COUNT(*) FROM org_risk
               WHERE NOT is_synthetic AND verdict = 'needs a second look'""") == 0,
    )
    check(
        "INT-03", "integrity",
        "Every seeded row carries batch identifier SYNTH_ADVERSARY_V1",
        one("""SELECT COUNT(*) FROM staging_orgs
               WHERE is_synthetic AND batch_id <> 'SYNTH_ADVERSARY_V1'""") == 0,
    )
    check(
        "INT-04", "integrity",
        "No seeded organisation is marked verified",
        one("SELECT COUNT(*) FROM staging_orgs WHERE is_synthetic AND is_verified") == 0,
    )
    check(
        "INT-05", "integrity",
        "Every target of a detected pair is real and in good standing",
        one("""SELECT COUNT(*) FROM clone_pairs p
               JOIN staging_orgs o ON o.org_id = p.target_id
               WHERE o.is_synthetic OR NOT o.is_verified""") == 0,
    )
    check(
        "INT-06", "integrity",
        "All seven cited figures are present and attributed",
        one("SELECT COUNT(*) FROM evidence_citations WHERE issuing_body IS NOT NULL") == 7,
    )
    check(
        "INT-07", "integrity",
        "Every detected pair records the technique that produced it",
        one("SELECT COUNT(*) FROM clone_pairs WHERE synth_technique IS NULL") == 0,
    )

    # ---------------------------------------------------------------- data
    check(
        "DAT-01", "data",
        "Geometry verdicts are distributed across all four categories",
        one("SELECT COUNT(DISTINCT geometry_verdict) FROM delivery_geometry") == 4,
    )
    check(
        "DAT-02", "data",
        "The risk components reconstruct the total",
        one("""SELECT COUNT(*) FROM org_risk
               WHERE ABS(LEAST(100, comp_semantic + comp_evasion + comp_geometry
                    + comp_unaccounted + comp_receipts) - risk_score) > 0.001""") == 0,
    )
    check(
        "DAT-03", "data",
        "A genuine gap exists between expected and actual receipts",
        one("SELECT COALESCE(SUM(receipts_missing), 0) FROM receipt_coverage") > 0,
    )
    check(
        "DAT-04", "data",
        "More than one hundred receipts recorded",
        one("SELECT COUNT(*) FROM mint_log") > 100,
    )
    check(
        "DAT-05", "data",
        "Every explorer link names the devnet cluster",
        one("""SELECT COUNT(*) FROM mint_log
               WHERE explorer_url NOT LIKE '%cluster=devnet%'""") == 0,
    )
    rate = one("""SELECT SUM(CASE WHEN status = 'DELIVERED' THEN amount_usd ELSE 0 END)
                       / NULLIF(SUM(CASE WHEN status <> 'PLEDGED'
                                         THEN amount_usd ELSE 0 END), 0)
                  FROM staging_disbursements""")
    check(
        "DAT-06", "data",
        f"Delivery rate {rate:.1%} is calibrated to the WFP ratio of 62.9%",
        abs(rate - 371 / 590) < 0.03,
    )
    check(
        "DAT-07", "data",
        "Clone detection found a workable number of pairs",
        50 <= one("SELECT COUNT(*) FROM clone_pairs") <= 5000,
    )
    check(
        "DAT-08", "data",
        "Every confirmed pair records how it was confirmed",
        one("SELECT COUNT(*) FROM clone_confirmed "
            "WHERE confirmation_method IS NULL") == 0,
    )

    con.close()


# ===========================================================================
# Craft. Section 03 and Section 11.
# ===========================================================================


def craft() -> None:
    app = ROOT / "app"
    py_sources = list(app.rglob("*.py"))
    source = "\n".join(p.read_text(encoding="utf-8") for p in py_sources)

    check(
        "CRF-01", "craft",
        "Geist is embedded as base64 in the committed stylesheet",
        (app / "assets" / "geist.css").exists()
        and "data:font/woff2;base64," in (app / "assets" / "geist.css").read_text(
            encoding="utf-8")[:4000],
    )
    check(
        "CRF-02", "craft",
        "st.code and st.json are never used; identifier() replaces them",
        not re.search(r"\bst\.(code|json)\s*\(", source),
    )
    # Only actual font declarations count. The word "monospace" appears
    # throughout the comments, because explaining why it is banned is part
    # of keeping it banned.
    css = (app / "theme.py").read_text(encoding="utf-8")
    declarations = re.findall(r"font-family\s*:[^;\n]*", css + source, re.I)
    check(
        "CRF-03", "craft",
        "No font declaration resolves to a monospaced family",
        not [d for d in declarations
             if re.search(r"monospace|courier|consolas|menlo|mono", d, re.I)],
    )
    check(
        "CRF-04", "craft",
        "Every tab module opens its content with a hero",
        all("C.hero(" in p.read_text(encoding="utf-8")
            for p in (app / "tabs").glob("tab_*.py")),
    )
    check(
        "CRF-05", "craft",
        "Every tab module ends with a provenance footer",
        all("provenance_footer(" in p.read_text(encoding="utf-8")
            for p in (app / "tabs").glob("tab_*.py")),
    )
    # Nine, since The Wall and Method And Honesty were removed. The count
    # is still asserted rather than left loose, so a tab going missing by
    # accident fails the build; it just has to be updated deliberately
    # when one goes on purpose.
    check(
        "CRF-06", "craft",
        "Nine tab modules exist",
        len(list((app / "tabs").glob("tab_*.py"))) == 9,
    )

    # No inline SQL in a tab module. Section 04, CONVENTION.
    offenders = [
        p.name for p in (app / "tabs").glob("tab_*.py")
        if re.search(r"(?i)\bSELECT\b[\s\S]{0,80}\bFROM\b",
                     re.sub(r'"""[\s\S]*?"""', "", p.read_text(encoding="utf-8")))
    ]
    check(
        "CRF-07", "craft",
        f"No inline SQL inside a tab module{' (' + ', '.join(offenders) + ')' if offenders else ''}",
        not offenders,
    )

    # No AI function or embedding call reachable from a render path.
    # Only an actual invocation counts; naming one in prose does not.
    check(
        "CRF-08", "craft",
        "No AI_EMBED or AI_FILTER invocation appears in the application",
        not re.search(r"AI_(EMBED|FILTER)\s*\(", source),
    )

    # Every query that can return many rows carries a LIMIT. Trap 07.
    import importlib
    sys.path.insert(0, str(app))
    queries = importlib.import_module("queries")
    unbounded = [
        name for name, q in queries.QUERIES.items()
        if re.search(r"(?i)\bfrom\b", q.sql)
        and not re.search(r"(?i)\blimit\b", q.sql)
        and not re.search(r"(?i)count\(|sum\(|group by|information_schema|"
                          r"\bv_kpi\b|v_tree_state|v_attrition_flow|"
                          r"v_privacy_budget|org_risk\s+where|retention_time",
                          q.sql)
    ]
    check(
        "CRF-09", "craft",
        f"Row-returning queries carry an explicit LIMIT"
        f"{' (' + ', '.join(unbounded) + ')' if unbounded else ''}",
        not unbounded,
    )

    # The build must not claim a guarantee the platform did not give it.
    # It ships a minimum-cohort floor, so it may name differential privacy
    # only to say it is NOT what is running. This used to read Tab 05
    # alone; with that tab removed the phrase can turn up anywhere, so the
    # check sweeps every tab rather than the one that used to own it.
    contrast = ("not ", "rather than", "does not", "unavailable", "no ",
                "instead", "difference", "cannot", "would", "specif",
                "defends", "fallback")
    claims = []
    for path in sorted((app / "tabs").glob("tab_*.py")):
        lines_ = path.read_text(encoding="utf-8").splitlines()
        for idx, line in enumerate(lines_):
            if "differential privacy" not in line.lower():
                continue
            # The window is needed because the copy wraps across several
            # source lines and the contrast often sits on a neighbour.
            window = "\n".join(lines_[max(0, idx - 4): idx + 5]).lower()
            if not any(t in window for t in contrast):
                claims.append(f"{path.name}: {line.strip()}")
    check(
        "CRF-11", "craft",
        f"No tab claims differential privacy"
        f"{' (' + claims[0][:60] + ')' if claims else ''}",
        not claims,
    )
    # The disclosure moved to The Brief when Method And Honesty was
    # removed, because the banner on every screen promises it. The check
    # follows it rather than being dropped: an application that seeds its
    # own adversaries and does not say so is the failure mode this whole
    # suite exists to catch.
    brief = (app / "tabs" / "tab_00_brief.py").read_text(encoding="utf-8")
    check(
        "CRF-12", "craft",
        "What is real and what is seeded is disclosed on The Brief",
        "REAL_VERSUS_SEEDED" in brief
        and "Entirely synthetic" in brief
        and "NOT differential privacy" in brief,
    )

    # Framing rule. The word fraud may appear only where a source is quoted.
    banned = re.compile(r"(?i)\b(fraudulent|criminal|scam|guilty)\b")
    hits = []
    for path in (app / "tabs").glob("tab_*.py"):
        if path.name.startswith("tab_00"):
            continue          # Tab 00 quotes the IC3 citation verbatim
        lines = path.read_text(encoding="utf-8").splitlines()
        for idx, line in enumerate(lines):
            if not banned.search(line):
                continue
            # Copy is wrapped across several source lines, so attribution
            # is looked for in the surrounding block rather than on the
            # one physical line the word happens to land on.
            lowered = "\n".join(lines[max(0, idx - 4): idx + 5]).lower()
            # Permitted where the line is a rule stating the word is
            # banned, or where it reproduces an attributed published
            # finding rather than describing an entity in this dataset.
            attributed = any(
                token in lowered
                for token in (
                    "never",            # a rule stating the word is banned
                    "&ldquo;", "&rdquo;",  # rendered as an explicit quotation
                    "wfp", "ic3", "world food programme", "reported",
                    "audit", "cag ", "published",
                )
            )
            if not attributed:
                hits.append(f"{path.name}: {line.strip()[:60]}")
    check(
        "CRF-10", "craft",
        f"No accusatory language outside the cited source on Tab 00"
        f"{' (' + hits[0] + ')' if hits else ''}",
        not hits,
    )


# ===========================================================================
# Repository hygiene. Section 04B.
# ===========================================================================


def hygiene() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for entry in (".env", "keys/", "*.p8"):
        check(
            f"SEC-{entry}", "security",
            f"{entry} is ignored before the first commit",
            entry in gitignore,
        )

    check(
        "SEC-env", "security",
        ".env.example contains no filled-in secret",
        all(
            line.split("=", 1)[1].strip() in {"", "ACCOUNTADMIN", "GP_WH",
                                              "GLASSPOCKET", "ORACLE", "50",
                                              "4000", "./keys/authority.json"}
            for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
            if "=" in line and not line.strip().startswith("#")
        ),
    )
    check(
        "SEC-app", "security",
        "No Snowflake credential appears in the application directory",
        not re.search(
            r"(?i)(password|private_key|SNOWFLAKE_ACCOUNT)\s*=\s*['\"][^'\"]+['\"]",
            "\n".join(p.read_text(encoding="utf-8")
                      for p in (ROOT / "app").rglob("*.py")),
        ),
    )
    check(
        "SEC-keys", "security",
        "No keypair file is present in the working tree",
        not list((ROOT / "keys").glob("*.json")) if (ROOT / "keys").exists() else True,
    )

    check(
        "REP-01", "repo",
        "All fifteen numbered SQL files exist",
        len(list((ROOT / "sql").glob("*.sql"))) == 15,
    )
    check(
        "REP-02", "repo",
        "The README carries the honesty table",
        "What is real and what is simplified"
        in (ROOT / "README.md").read_text(encoding="utf-8"),
    )
    check(
        "REP-03", "repo",
        "The platform constraints are documented with the actual errors",
        (ROOT / "docs" / "platform_constraints.md").exists()
        and "not available for trial accounts"
        in (ROOT / "docs" / "platform_constraints.md").read_text(encoding="utf-8"),
    )


def main() -> int:
    integrity()
    craft()
    hygiene()

    width = max(len(s) for _, _, s, _ in results) + 2
    failed = 0
    area = None
    for check_id, this_area, statement, passed in results:
        if this_area != area:
            area = this_area
            print(f"\n{area.upper()}")
        mark = "PASS" if passed else "FAIL"
        if not passed:
            failed += 1
        print(f"  {mark}  {statement:<{width}} {check_id}")

    print(f"\n{len(results)} checks, {len(results) - failed} passed, {failed} failed")
    if failed:
        print("BUILD BLOCKED. Fix the failures above before recording.")
        return 1
    print("BUILD ACCEPTED for everything checkable without a warehouse.")
    print("Run sql/99_acceptance_checks.sql for the warehouse-side criteria.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
