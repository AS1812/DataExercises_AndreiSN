"""Test 2 — Postgres data manipulation on pipeline.flow_006_raw.

Against the dockerized Postgres (docker-compose.yml):
  1. load schema.sql + seed_data.sql (the 15 records from the brief)
  2. loop through every record and print its flow_uuid
  3. add a `test_results` column = operating_capacity / scheduled_quantity,
     computed per row WITH error handling -- the Receipt rows have
     scheduled_quantity = 0, which is the division-by-zero case
  4. export the augmented table to outputs/

Run:  docker compose up -d  &&  ../.venv/bin/python run.py
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import psycopg2

ROOT = Path(__file__).parent
OUT = ROOT / "outputs"
ENV_FILE = ROOT / ".env"
TABLE = "pipeline.flow_006_raw"


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


def dsn() -> dict:
    """Postgres connection params, read only from .env (no hardcoded fallbacks)."""
    load_env()
    try:
        return dict(
            host=os.environ["PGHOST"],
            port=int(os.environ["PGPORT"]),
            user=os.environ["PGUSER"],
            password=os.environ["PGPASSWORD"],
            dbname=os.environ["PGDATABASE"],
        )
    except KeyError as e:
        raise SystemExit(f"missing {e} in environment — run: cp .env.example .env")


def connect(retries: int = 20):
    """Wait for the container's Postgres to start accepting connections."""
    params = dsn()
    last = None
    for _ in range(retries):
        try:
            return psycopg2.connect(**params)
        except psycopg2.OperationalError as e:
            last = e
            time.sleep(1)
    raise SystemExit(f"could not connect to Postgres at {params['host']}:{params['port']}: {last}")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    conn = connect()
    conn.autocommit = True
    cur = conn.cursor()

    # 1) load the table definition + the 15 seed records
    cur.execute((ROOT / "schema.sql").read_text())
    cur.execute((ROOT / "seed_data.sql").read_text())
    cur.execute(f"SELECT count(*) FROM {TABLE}")
    n = cur.fetchone()[0]
    print(f"[load] {n} records into {TABLE}")

    # 2) loop through each record and print its uuid (row-by-row cursor)
    print("\n[loop] record uuids:")
    uuids = []
    cur.execute(f"SELECT flow_uuid FROM {TABLE} ORDER BY date_cycle_id, loc_qti")
    for (flow_uuid,) in cur:
        print(f"   {flow_uuid}")
        uuids.append(str(flow_uuid))
    (OUT / "uuids.txt").write_text("\n".join(uuids) + "\n")

    # 3) add test_results and compute operating_capacity / scheduled_quantity per row
    cur.execute(f"ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS test_results double precision")
    cur.execute(f"SELECT flow_uuid, operating_capacity, scheduled_quantity FROM {TABLE}")
    rows = cur.fetchall()

    print("\n[compute] test_results = operating_capacity / scheduled_quantity:")
    ok = errs = 0
    for flow_uuid, operating, scheduled in rows:
        try:
            result = operating / scheduled          # ZeroDivisionError when scheduled == 0
        except (ZeroDivisionError, TypeError) as e:  # TypeError if either side is NULL
            result = None                            # store NULL; one bad row mustn't abort the run
            errs += 1
            print(f"   {flow_uuid}  handled {type(e).__name__} "
                  f"(operating={operating}, scheduled={scheduled}) -> NULL")
        else:
            ok += 1
        cur.execute(f"UPDATE {TABLE} SET test_results = %s WHERE flow_uuid = %s",
                    (result, flow_uuid))
    print(f"[compute] {ok} computed, {errs} errors handled (-> NULL)")

    # 4) export the augmented table (all columns incl. test_results) via COPY
    export = OUT / "flow_006_raw_test_results.csv"
    with open(export, "w", newline="") as f:
        cur.copy_expert(
            f"COPY (SELECT * FROM {TABLE} ORDER BY date_cycle_id, loc_qti) "
            f"TO STDOUT WITH CSV HEADER", f)
    print(f"\n[export] {export.relative_to(ROOT)}  ({n} rows, incl. test_results)")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
