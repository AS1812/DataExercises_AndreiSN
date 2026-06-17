"""Create the Snowflake compute warehouse + database the ingest loads into.

A fresh trial account often has no usable warehouse and only the system
SNOWFLAKE database, so we create our own (CRITERION_DB) plus a small warehouse.
Idempotent (CREATE ... IF NOT EXISTS) — safe to re-run. ingest.py also calls
`ensure()` so it works standalone, but this module is where that creation lives.

Run:
    python create_db.py
"""
from __future__ import annotations

from connection import connect, WAREHOUSE, DATABASE


def ensure(cur) -> None:
    """Create the warehouse + database if missing and select them for the session."""
    cur.execute(f"CREATE WAREHOUSE IF NOT EXISTS {WAREHOUSE} "
                "WITH WAREHOUSE_SIZE='XSMALL' AUTO_SUSPEND=60 "
                "AUTO_RESUME=TRUE INITIALLY_SUSPENDED=FALSE")
    cur.execute(f"USE WAREHOUSE {WAREHOUSE}")
    cur.execute(f"CREATE DATABASE IF NOT EXISTS {DATABASE}")
    cur.execute(f"USE DATABASE {DATABASE}")


def main() -> None:
    conn = connect()
    try:
        cur = conn.cursor()
        ensure(cur)
        cur.execute("SELECT current_version()")
        print(f"connected — Snowflake {cur.fetchone()[0]}")
        print(f"warehouse {WAREHOUSE} + database {DATABASE} ready")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
