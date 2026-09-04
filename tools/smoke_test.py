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
    print(f"tabs             {len(at.tabs)}")
    print(f"charts           {_charts(at)}")
    print(f"dataframes       {len(at.dataframe)}")
    print(f"markdown blocks  {len(at.markdown)}")

    # ------------------------------------------------------------------
    # Interactive paths. First render only exercises about half the code:
    # the Tab 01 reveal and the Tab 05 release are where the charts that
    # carry the argument actually live.
    # ------------------------------------------------------------------

    picks = [b for b in at.button if "give to this one" in b.label]
    if not picks:
        print("\n  MISSING   Tab 01 has no pick control")
        problems += 1
    else:
        picks[0].click().run()
        problems += _problems(at, "tab 01 reveal")
        print(f"\nafter reveal     charts {_charts(at)}")
        if not any("evasion gap" in m.value for m in at.markdown):
            print("  MISSING   the evasion gap is not reported after the reveal")
            problems += 1

    release = [b for b in at.button if b.label == "release the answer"]
    if not release:
        print("  MISSING   Tab 05 has no release control")
        problems += 1
    else:
        release[0].click().run()
        problems += _problems(at, "tab 05 release")
        print(f"after release    charts {_charts(at)}")

    repeat = [b for b in at.button if b.label == "run this ten times"]
    if repeat:
        repeat[0].click().run()
        problems += _problems(at, "tab 05 repeated queries")
        print(f"after repeat     charts {_charts(at)}")

    apply_change = [b for b in at.button if b.label == "apply"]
    if apply_change:
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
