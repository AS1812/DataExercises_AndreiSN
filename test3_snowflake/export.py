"""Export records from Postgres -> CSV (the 'export' half of the Postgres ->
Snowflake sync; ingest.py loads the CSV into Snowflake).

Reads the Test 2 dockerized Postgres (pipeline.flow_006_raw) and writes the
flow_006_raw columns to sample_export.csv, excluding the ad-hoc test_results
column Test 2 added. Re-generates the file ingest.py consumes.

Prerequisite: Test 2's Postgres is up and seeded:
    (cd ../test2_postgres && docker compose up -d && python run.py)

Run:
    python export.py
"""
from __future__ import annotations

import os
from pathlib import Path

import psycopg2

ROOT = Path(__file__).parent
OUT = ROOT / "sample_export.csv"
TABLE = "pipeline.flow_006_raw"

# matches test2_postgres/docker-compose.yml; overridable via standard PG* env vars
PG = dict(
    host=os.getenv("PGHOST", "localhost"),
    port=int(os.getenv("PGPORT", "5433")),
    user=os.getenv("PGUSER", "criterion"),
    password=os.getenv("PGPASSWORD", "criterion"),
    dbname=os.getenv("PGDATABASE", "criterion"),
)


def main() -> None:
    conn = psycopg2.connect(**PG)
    try:
        cur = conn.cursor()
        # the real flow_006_raw columns (skip Test 2's ad-hoc test_results), in order
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'pipeline' AND table_name = 'flow_006_raw'
              AND column_name <> 'test_results'
            ORDER BY ordinal_position""")
        cols = [r[0] for r in cur.fetchall()]
        if not cols:
            raise SystemExit("flow_006_raw not found — is Test 2's Postgres seeded?")
        collist = ", ".join(cols)

        with open(OUT, "w", newline="") as f:
            cur.copy_expert(
                f"COPY (SELECT {collist} FROM {TABLE} ORDER BY date_cycle_id, loc_qti) "
                f"TO STDOUT WITH CSV HEADER", f)
        n = sum(1 for _ in open(OUT)) - 1
        print(f"exported {n} rows, {len(cols)} columns -> {OUT.name}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
