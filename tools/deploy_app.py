"""Deploy the Streamlit application into Snowflake.

    python tools/deploy_app.py

Uploads app/ to a named stage and creates (or replaces) the Streamlit
object that serves it. The application carries no credentials: inside
Snowflake it obtains its session with get_active_session(), which is why
app/data.py tries the warehouse first and only falls back to the local
preview store when there is no session to be had.

WHAT GETS UPLOADED
    Every .py under app/, plus app/assets/geist.css. The stylesheet is
    the load-bearing one: Streamlit in Snowflake enforces a Content
    Security Policy that blocks fonts from external domains (Trap 03), so
    Geist travels base64-inlined inside that file or the design silently
    disappears.

WHAT DOES NOT
    The local preview store, the raw extracts and the .env. None of them
    have any business in a warehouse stage.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = ROOT / "app"

DATABASE = "GLASSPOCKET"
SCHEMA = "SERVING"
STAGE = "GP_APP_STAGE"
STREAMLIT_NAME = "GLASSPOCKET_APP"
WAREHOUSE = "GP_WH"

# Streamlit in Snowflake reads this from the root location to resolve
# packages. Everything here is in the Snowflake Anaconda channel, which
# is why the build uses Plotly and pydeck rather than anything that would
# need to be fetched at runtime (Trap 03).
ENVIRONMENT_YML = """name: sf_env
channels:
  - snowflake
dependencies:
  - streamlit
  - plotly
  - pydeck
  - pandas
  - numpy
"""


def app_files() -> list[pathlib.Path]:
    files = sorted(APP.glob("*.py"))
    files += sorted((APP / "tabs").glob("*.py"))
    css = APP / "assets" / "geist.css"
    if css.exists():
        files.append(css)
    else:
        raise SystemExit(
            "app/assets/geist.css is missing. Run tools/build_font_css.py.\n"
            "Without it every element falls back to a system font and the "
            "build fails its own craft checks."
        )
    return files


def main() -> int:
    sys.path.insert(0, str(ROOT / "tools"))
    import deploy

    env = deploy.load_env()
    conn = deploy.connect(env)
    cur = conn.cursor()

    try:
        cur.execute(f"USE DATABASE {DATABASE}")
        cur.execute(f"USE SCHEMA {SCHEMA}")
        cur.execute(f"USE WAREHOUSE {WAREHOUSE}")

        cur.execute(
            f"CREATE STAGE IF NOT EXISTS {STAGE} "
            "DIRECTORY = (ENABLE = TRUE) "
            "COMMENT = 'GLASSPOCKET Streamlit application files'"
        )
        print(f"stage @{DATABASE}.{SCHEMA}.{STAGE} ready")

        env_yml = ROOT / "app" / "environment.yml"
        env_yml.write_text(ENVIRONMENT_YML, encoding="utf-8")

        uploads = app_files() + [env_yml]
        for path in uploads:
            relative = path.relative_to(APP)
            folder = f"/{relative.parent.as_posix()}" if relative.parent.name else ""
            uri = path.resolve().as_posix()
            cur.execute(
                f"PUT 'file://{uri}' @{STAGE}{folder} "
                "AUTO_COMPRESS=FALSE OVERWRITE=TRUE"
            )
            print(f"  put   {relative.as_posix()}")

        cur.execute(
            f"CREATE OR REPLACE STREAMLIT {DATABASE}.{SCHEMA}.{STREAMLIT_NAME} "
            f"ROOT_LOCATION = '@{DATABASE}.{SCHEMA}.{STAGE}' "
            "MAIN_FILE = 'glasspocket_app.py' "
            f"QUERY_WAREHOUSE = {WAREHOUSE} "
            "TITLE = 'GLASSPOCKET' "
            "COMMENT = 'Accountability engine for charitable giving.'"
        )
        print(f"\ncreated STREAMLIT {DATABASE}.{SCHEMA}.{STREAMLIT_NAME}")

        cur.execute(f"SHOW STREAMLITS LIKE '{STREAMLIT_NAME}' IN SCHEMA {SCHEMA}")
        rows = cur.fetchall()
        if rows:
            columns = [c[0].lower() for c in cur.description]
            record = dict(zip(columns, rows[0]))
            url_id = record.get("url_id")
            account = env["SNOWFLAKE_ACCOUNT"]
            print("\nOpen it from Snowsight: Projects > Streamlit > GLASSPOCKET")
            if url_id:
                print(f"  url_id {url_id}")
            print(f"  account {account}")

        cur.execute(
            "SELECT COUNT(*) FROM DIRECTORY("
            f"@{DATABASE}.{SCHEMA}.{STAGE})"
        )
        print(f"  {cur.fetchone()[0]} files staged")
        return 0
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
