# Criterion Research — Data Test Projects

Solutions to the three test projects. Each is self-contained and runnable; the
three together form one data pipeline:

> **scrape → standardize → load Postgres → transform → sync to Snowflake**

| Test | Folder | Status |
|---|---|---|
| 1 — ETL & Web Scraping (TIGT Operationally Available → Point Capacity) | [`test1_scraper/`](test1_scraper/) | ✅ Built & run against the live site |
| 2 — Postgres data manipulation | [`test2_postgres/`](test2_postgres/) | ✅ Built & run (dockerized Postgres) |
| 3 — Snowflake ETL process | [`test3_snowflake/`](test3_snowflake/) | ✅ CDC-connector design + ingest procedure; verified live on Snowflake demo account + AI Demo playground (15 rows, idempotent) |

See [`docs/architecture.md`](docs/architecture.md) for the end-to-end picture.

## Quick start (Test 1)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r test1_scraper/requirements.txt
playwright install chromium
python test1_scraper/scraper.py && python test1_scraper/formatter.py
```

Committed output snapshots are included under each test's `outputs/` so results
can be reviewed without re-running. See per-test READMEs for details.
