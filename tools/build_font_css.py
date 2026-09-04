"""Base64-inline the Geist typeface into a single stylesheet.

Streamlit in Snowflake enforces a Content Security Policy that blocks fonts
from any external domain (Build Spec, Trap 03). A CDN link silently falls back
to a system font, so every face has to travel inside the stylesheet itself.

Run once. The output, app/assets/geist.css, is committed to the repository.

    python tools/build_font_css.py

Source fonts come from the npm package `geist`, subpath dist/fonts/geist-sans/.
The four static weights are the ones named in Section 03. The variable face is
carried alongside them under a distinct family so that the 650 and 800 weights
demanded by the Section 03 type scale render as real cut weights rather than as
a browser-synthesised approximation of Bold.
"""

import base64
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "fonts"
OUT = ROOT / "app" / "assets" / "geist.css"

WEIGHTS = {"Regular": 400, "Medium": 500, "SemiBold": 600, "Bold": 700}
VARIABLE = "Geist-Variable"


def _b64(path: pathlib.Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def _face(family: str, weight: str, path: pathlib.Path) -> str:
    return (
        "@font-face{"
        f"font-family:'{family}';"
        "font-style:normal;"
        f"font-weight:{weight};"
        "font-display:block;"
        f"src:url(data:font/woff2;base64,{_b64(path)}) format('woff2');"
        "}"
    )


def build() -> str:
    faces = []

    variable = FONT_DIR / f"{VARIABLE}.woff2"
    if variable.exists():
        faces.append(_face("Geist Variable", "100 900", variable))

    for name, weight in WEIGHTS.items():
        path = FONT_DIR / f"Geist-{name}.woff2"
        if not path.exists():
            raise SystemExit(
                f"missing {path}\n"
                "Obtain it from the npm package `geist`, subpath dist/fonts/geist-sans/:\n"
                "  npm pack geist && tar -xzf geist-*.tgz\n"
                "  cp package/dist/fonts/geist-sans/Geist-{Regular,Medium,SemiBold,Bold,Variable}.woff2 fonts/"
            )
        faces.append(_face("Geist", str(weight), path))

    return "".join(faces)


def main() -> int:
    css = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(css, encoding="utf-8")
    kb = len(css.encode()) / 1024
    print(f"wrote {OUT.relative_to(ROOT)}  {kb:,.0f} KB  {css.count('@font-face')} faces")
    return 0


if __name__ == "__main__":
    sys.exit(main())
