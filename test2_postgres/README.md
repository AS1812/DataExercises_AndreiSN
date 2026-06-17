# Test 2 — Postgres Data Manipulation (`pipeline.flow_006_raw`)

Loads the brief's 15 records into a Postgres `flow_006_raw` table, then per the brief:

1. loops every record and prints its `flow_uuid` (row-by-row cursor);
2. adds a `test_results` column = `operating_capacity / scheduled_quantity`, per row, with error handling;
3. exports the augmented table.

Runs against a **dockerized Postgres** — nothing to install locally.

## Run

```bash
cd test2_postgres
cp .env.example .env        # connection params (gitignored; drives compose + run.py)
docker compose up -d        # Postgres 16, host port 5433
pip install -r requirements.txt
python run.py               # load -> print uuids -> compute -> export
docker compose down
```

`run.py` is idempotent (drops/recreates from `schema.sql`, re-seeds from `seed_data.sql`). Connection details live **only in `.env`** — one file feeds both `docker-compose.yml` and `run.py`, with no hardcoded fallbacks.

## Error handling (the point of the exercise)

Every Receipt row (`RPQ`) has `scheduled_quantity = 0`, so `operating / scheduled` divides by zero. The per-row `try/except` stores `NULL` instead of aborting:

```
[compute] 7 computed, 8 errors handled (-> NULL)
```

**8 `ZeroDivisionError`s → NULL; 7 Delivery rows compute** (e.g. `1000000 / 312328 = 3.20`); 0 crashes. It also guards `TypeError` (NULL operand). Full trace: [`outputs/run_log.txt`](outputs/run_log.txt).

> The brief specifies `operating ÷ scheduled` — unusual (utilisation is normally `scheduled ÷ operating`), but followed literally; flagged here.

## Outputs (committed evidence)

| Path | Contents |
|---|---|
| `outputs/uuids.txt` | every `flow_uuid` (deliverable 1) |
| `outputs/flow_006_raw_test_results.csv` | table + `test_results` (deliverable 3) |
| `outputs/run_log.txt` | console trace |

No `pg_dump` — the DB is fully reproducible from `schema.sql` + `seed_data.sql`.

## Files

- `docker-compose.yml` — Postgres 16 (ephemeral, host port 5433).
- `schema.sql` — the `flow_006_raw` DDL, verbatim from the brief (dropped the SQL-Server `GO`). It's the schema's source of truth; Test 1's `schema.py` is its Python validation projection, kept independent (different runtimes).
- `seed_data.sql` — the 15 `INSERT`s, verbatim (only the placeholder filled).
- `run.py` — load → loop/print uuid → `ALTER ADD COLUMN` → per-row `try/except` compute → `COPY` export.

## On the loop

The brief says *"create a loop … and perform an action on each record"*, so the compute is a **row-by-row Python loop** (`SELECT` → compute → `UPDATE`), not one set-based statement. The set-based equivalent would be:

```sql
UPDATE pipeline.flow_006_raw
   SET test_results = operating_capacity / NULLIF(scheduled_quantity, 0);
```

`NULLIF(…, 0)` makes the divisor `NULL` instead of erroring — the SQL-native way to handle it.
