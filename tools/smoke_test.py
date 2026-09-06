"""Headless render check for every tab.

Streamlit's AppTest runs the real script in-process, so this exercises the
actual render path rather than only proving the server answers on a port.
Any exception a tab raises shows up here instead of in front of a judge.

    python tools/smoke_test.py
"""

from __future__ import annotations

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = ROOT / "app" / "glasspocket_app.py"
sys.path.insert(0, str(ROOT / "app"))


def _problems(at, label: str) -> int:
    count = 0
    for exc in at.exception:
        count += 1
        print(f"  EXCEPTION [{label}]  {exc.value}")
    for err in at.error:
        count += 1
        print(f"  ST.ERROR  [{label}]  {err.value}")
    return count


def _charts(at) -> int:
    """Count chart elements by walking the tree.

    AppTest has no public accessor for plotly_chart or pydeck_chart, so
    they arrive as UnknownElement. Counting them is still the only way to
    know a chart was actually emitted rather than silently skipped.
    """
    seen = 0
    stack = [at._tree]
    while stack:
        node = stack.pop()
        if type(node).__name__ == "UnknownElement":
            seen += 1
        children = getattr(node, "children", None)
        if isinstance(children, dict):
            stack.extend(children.values())
        elif children:
            stack.extend(children)
    return seen


def main() -> int:
    from streamlit.testing.v1 import AppTest

    started = time.time()
    at = AppTest.from_file(str(APP), default_timeout=180)
    at.run()

    problems = _problems(at, "first render")

    print(f"first render     {time.time() - started:.1f}s")
    nav = [b for b in at.button if b.key and b.key.startswith("gp_nav_")]
    print(f"nav entries      {len(nav)}")
    print(f"charts           {_charts(at)}")
    print(f"dataframes       {len(at.dataframe)}")
    print(f"markdown blocks  {len(at.markdown)}")

    # ------------------------------------------------------------------
    # Interactive paths. First render only exercises about half the code:
    # the Give With Confidence reveal and The Historian's apply are where
    # the charts that carry the argument actually live.
    # ------------------------------------------------------------------

    # Navigation is a rail now, so each section has to be selected before
    # its controls exist. Walk every one of them and report any that
    # cannot render, which is the failure this test exists to catch.
    def goto(index: int):
        """Click the rail entry at a position and return the fresh tree."""
        entries = [b for b in at.button if b.key and b.key.startswith("gp_nav_")]
        entries[index].click().run()

    if nav:
        broken = []
        keys = [b.key for b in nav]
        for idx, key in enumerate(keys):
            goto(idx)
            errs = [e.value for e in at.error] + [e.value for e in at.exception]
            if errs:
                broken.append(f"{key}: {errs[0][:90]}")
            else:
                print(f"  ok  {key.replace('gp_nav_', 'section ')}")
        for b in broken:
            print(f"  FAIL {b}")
            problems += 1
        goto(1)   # land on Confidence for the rest

    picks = [b for b in at.button if "give to this one" in b.label]
    if not picks:
        print("\n  MISSING   Tab 01 has no pick control")
        problems += 1
    else:
        picks[0].click().run()
        problems += _problems(at, "tab 01 reveal")
        print(f"\nafter reveal     charts {_charts(at)}")
        # The reveal has to report the gap in words, not only inside the
        # chart, or a screenshot of the tab loses the whole argument.
        if not any("gap between them" in m.value for m in at.markdown):
            print("  MISSING   the gap is not reported in words after the reveal")
            problems += 1

    # The Wall is walked here, between the reveal and the tamper, which
    # is where it sits in the argument: the system refusing, between the
    # system finding and the system being checked. Positions are resolved
    # from the rail by name rather than hard-coded, so the next tab to
    # move does not silently skip its own test the way renaming the apply
    # button once did.
    def goto_named(name: str) -> bool:
        entries = [b for b in at.button if b.key and b.key.startswith("gp_nav_")]
        for index, entry in enumerate(entries):
            if name.lower() in (entry.label or "").lower():
                goto(index)
                return True
        return False

    if not goto_named("The Wall"):
        print("  MISSING   The Wall is not on the rail")
        problems += 1
    else:
        problems += _problems(at, "tab 05 wall")
        print(f"\nthe wall         charts {_charts(at)}")
        # The tab's whole argument is that three regimes answer the same
        # question differently. If any one of the three cards is absent
        # the comparison has silently become a claim.
        page = " ".join(m.value for m in at.markdown)
        for phrase in ("no policy", "aggregation policy",
                       "differential privacy"):
            if phrase not in page.lower():
                print(f"  MISSING   the wall does not show '{phrase}'")
                problems += 1

    if not goto_named("The Historian"):
        print("  MISSING   The Historian is not on the rail")
        problems += 1
    # Matched by prefix, not by the whole label. An exact match meant
    # that renaming the button to "apply the change" silently skipped the
    # tamper path and the run still reported clean, which is the worst
    # thing a smoke test can do.
    apply_change = [b for b in at.button
                    if (b.label or "").startswith("apply")]
    if not apply_change:
        print("  MISSING   The Historian has no apply control")
        problems += 1
    else:
        apply_change[0].click().run()
        problems += _problems(at, "tab 07 apply")
        print(f"after tamper     charts {_charts(at)}")

    if problems:
        print(f"\n{problems} problems")
        return 1

    print("\nevery tab and every interactive path renders clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
