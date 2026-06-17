"""Snowflake connection module.

Credentials come from a local .env (copy .env.example -> .env; .env is
gitignored, so no credentials live in this repo). Shared by create_db.py and
ingest.py.
"""
from __future__ import annotations

import os
from pathlib import Path

ENV_FILE = Path(__file__).parent / ".env"


def load_env(path: Path = ENV_FILE) -> None:
    """Minimal .env loader (KEY=VALUE lines -> os.environ); no extra dependency."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


load_env()  # load .env on import so the constants below can pick it up
WAREHOUSE = os.getenv("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH")
DATABASE = os.getenv("SNOWFLAKE_DATABASE", "CRITERION_DB")


def connect(*, use_warehouse: str | None = None, use_database: str | None = None):
    """Open a Snowflake connection from the .env credentials, optionally
    selecting a warehouse/database for the session."""
    import snowflake.connector  # imported lazily (only needed when actually connecting)

    conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        role=os.getenv("SNOWFLAKE_ROLE"),
    )
    cur = conn.cursor()
    if use_warehouse:
        cur.execute(f"USE WAREHOUSE {use_warehouse}")
    if use_database:
        cur.execute(f"USE DATABASE {use_database}")
    return conn
