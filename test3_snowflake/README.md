# Test 3 — Snowflake ETL Process

Two parts, per the brief: **(1)** design how to keep production Postgres aligned with
Snowflake, and **(2)** a simple procedure to ingest data into Snowflake.

> **Verified on a live Snowflake account:** `ingest.py` loaded all 15 rows into
> `CRITERION_DB.pipeline.flow_006_raw`, idempotent on re-run (stays 15) — see
> `outputs/snowflake_run.txt` + `outputs/snowflake_demo.png`.

---

## 1) Design — keeping AWS Postgres aligned with Snowflake

Production data lives in **AWS Postgres** (RDS/Aurora); Snowflake serves it (speed +
per-customer secure sharing) and must follow every insert/update/delete.

### The native Postgres CDC connector

Snowflake's **Openflow Connector for PostgreSQL** is the production sync — connect it and
watch it behave:

- Reads the Postgres **WAL** via logical replication, continuously replicating
  **INSERT / UPDATE / DELETE** (true CDC — no manual sync to maintain).
- **BYOC**: runs in our own AWS account/VPC; data stays in our boundary until Snowflake.
- Works with **AWS RDS / Aurora**; pair with **Dynamic Tables** for the modeled layer.

```
 AWS RDS/Aurora Postgres ─ your VPC (BYOC) ─       Snowflake
 ┌──────────────┐ WAL (I/U/D) ┌──────────────────┐ CDC ┌──────────────────────┐
 │  Actual DB   ├────────────►│Openflow Connector├────►│ raw → Dynamic Tables │
 └──────────────┘             └──────────────────┘     └──────────────────────┘
```

### Modules to use
- **AI (Cortex)** — `AI_EXTRACT` (metadata), `AI_CLASSIFY`/`AI_FILTER` (data-quality), and **Cortex Analyst** ("talk to your data"). Demoed live in Snowsight: an English question generated the SQL and the correct answer over `flow_006_raw` (`outputs/AI_funcitons_demo.png`) — used as a reviewed assistant, not the source of truth.
- **Monitoring** — AI Observability (GA 2025), resource monitors, alerts.
- **Audit / governance** — `ACCESS_HISTORY`/`QUERY_HISTORY`, Trust Center, masking / row-access policies (per-customer sharing).

### Backbone
- **Sync key `flow_uuid`** (PK) — CDC keys on it, so updates upsert and re-syncs never duplicate (why `flow_uuid` was kept clean in Tests 1–2).
- **Type mapping** (`snowflake_schema.sql`): `uuid→VARCHAR(36)`, `double precision→FLOAT`, `timestamp→TIMESTAMP_NTZ`, `gen_random_uuid()→UUID_STRING()`.
- **Reconciliation** — row counts / checksums per `eff_gas_day` (we ran this: 0 value differences, below).
- **Customer-secure storage** — Secure Data Sharing / reader accounts / per-customer DBs with RBAC.

### Improvement — AI agentic pipeline monitor
A **Cortex Agent + AI Observability** loop that watches load failures, schema drift and
data-quality anomalies (e.g. a numeric column turning non-numeric — Test 1's type-guard
case), narrates the issue and proposes a fix for a human to approve — assistant, not
auto-applier (matches the brief's "be skeptical of AI").

### Hybrid LLM metadata extractor
On a prior project I built this pattern: a cloud orchestrator triggered a Python middleware
on a **standalone internal AI workstation** that ran the OCR/LLM metadata extraction and
wrote results back. Same can be done on AWS:

> **AWS orchestrator** (Step Functions / Lambda / Glue, or Snowflake Tasks + External
> Functions) → **standalone workstation** (local *or* cloud LLM) → writes back to Snowflake.

Cortex (in-Snowflake) is the default; the hybrid workstation wins when you need a
**local/controlled LLM** (cost, data residency, custom models, on-prem GPU).

---

## 2) The simple ingest procedure

`ingest.py` — a self-contained, dependency-light loader (the brief's part 2), verified live
(15 rows, idempotent), handy for backfills / one-off loads. Single-purpose modules:

| Module | Role |
|---|---|
| `connection.py` | Snowflake connection from `.env` |
| `create_db.py` | create the warehouse + `CRITERION_DB` |
| `export.py` | export `flow_006_raw` from Postgres → `sample_export.csv` |
| `ingest.py` | load the CSV: **stage → `COPY` → `MERGE` on `flow_uuid`** |

```bash
cd test3_snowflake
pip install -r requirements.txt
cp .env.example .env        # Snowflake creds (.env gitignored)
python ingest.py            # ensures warehouse+DB, then stage -> COPY -> MERGE
```

Re-running is safe (MERGE on `flow_uuid` → stays 15, not 30). Creds live only in `.env`.

## Round-trip check

Input (`sample_export.csv`) vs the rows read back from Snowflake
(`outputs/Results_2026-06-17-1859.csv`), across all 15 rows × 51 columns: **0 value
differences** — the sync is faithful. The same 15 also match the brief's `INSERT`s, and
Test 2's `test_results` are 15/15 correct. The only differences are cosmetic Snowflake
conventions:

- **Header case** — unquoted identifiers come back UPPERCASE (`FLOW_UUID`).
- **Timestamp precision** — `TIMESTAMP_NTZ` pads whole seconds to `.000`
  (`20:15:40` → `20:15:40.000`); same instant. The `.577` estimate rows are byte-identical.

## Files

- `connection.py` / `create_db.py` / `export.py` / `ingest.py` — the modules above.
- `snowflake_schema.sql` — `flow_006_raw` in Snowflake (type-mapped from Test 2's `schema.sql`).
- `sample_export.csv` — committed Postgres export (15 records).
- `outputs/` — `snowflake_run.txt` (run log), `snowflake_demo.png` (loaded rows), `AI_funcitons_demo.png` (Cortex Analyst: question → SQL → answer).
- `requirements.txt`, `.env.example`.

## Problems encountered & fixed

Two real failures while running `ingest.py` live:

1. **`;` inside a SQL comment** broke `sql.split(";")` → `Empty SQL statement`. Fix: use
   the connector's `execute_string()` (ignores `;` in comments).
2. **`MATCH_BY_COLUMN_NAME` needs `PARSE_HEADER = TRUE`** in the CSV file format. Fix: added
   it so the CSV header drives column matching.
