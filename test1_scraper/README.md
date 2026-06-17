# Test 1 — ETL & Web Scraping (TIGT Operationally Available → Point Capacity)

Scrapes the **last 3 gas days × every cycle × Receipt and Delivery** from Tallgrass
Interstate Gas Transmission, saves each pull separately, and standardizes it into the
`flow_006_raw` schema (CSV / TXT / HTML).

Target: `…/Pages/Point.aspx?pipeline=302&type=OA` (via *TIGT → Capacity → Operationally
Available → Point Capacity*).

## Why Playwright (not `requests`)

The site is behind **Imperva/Incapsula** — a plain `curl`/`requests` gets a ~200-byte
JavaScript *challenge* page, not data. Only a real browser executes that challenge to earn
the session cookies, so the scraper drives **Chromium**, then uses the site's own
**Download** button (a tab-delimited `PointCapacity.txt`). Navigation is stateful ASP.NET
WebForms (gas-day field, cycle dropdown, Receipt/Delivery radio), which the browser handles.

## Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r test1_scraper/requirements.txt
playwright install chromium

python test1_scraper/scraper.py     # pull raw downloads (live site)
python test1_scraper/formatter.py   # standardize -> flow_006_raw outputs
```

## Outputs

| Path | Contents |
|---|---|
| `raw_downloads/*.txt` | exact site downloads, one per gas-day × cycle × direction |
| `raw_downloads/manifest.json` | index of every pull |
| `outputs/per_cycle/*.csv` | upload-ready CSV per cycle+direction |
| `outputs/flow_006_raw_TIGT.{csv,txt,html}` | combined dataset, the 3 requested formats |

A committed snapshot (captured **2026-06-17**, gas days 6/14–6/16) lets a reviewer check it
without re-running — the site only exposes the most recent gas days.

## Key design decisions

- **Gas day** = 24h, 09:00→09:00 Central, every calendar day incl. weekends. The scraper
  reads the site's *current* gas day from the page (not the local clock) and walks back 3.
- **Cycles discovered live** from the dropdown (`discover_cycles`) — no hardcoded list —
  scraped with the site's own `CYCLE_ID`/`CYCLE_NAME`. **"Best Available" is excluded**:
  not a cycle, just the latest posted one, and verified **100% redundant** (every row
  reproduced by the real cycles). Cycles not yet posted (e.g. today's ID2/ID3) are skipped.
- **Direction** isn't a column in the download — it's the Receipt/Delivery radio (verified
  it changes the data: 73 vs 246 rows). Recorded via `loc_purp_desc` (the page's label);
  the `loc_qti_*` codes are Criterion-internal, so left NULL.
- **Type safety** (`schema.py`): every `flow_006_raw` column type is enforced *before*
  upload, so "a string into a numeric column" fails loudly here, not at INSERT.

## Column mapping

The output writes **49 of 51** columns, **21 populated** — only what the site provides,
standard derivations of it, and the scrape time. `flow_uuid` and `load_date` are
**omitted** so the DB fills them (`gen_random_uuid()` / `now()`); the other 28 are NULL for
the loader (internal keys/codes not on the site).

→ Full per-column mapping: **[field_mapping.md](field_mapping.md)**

## Files

Separation of concerns — **contract** (`schema.py`) vs **source adapter** (`formatter.py`):

- `config.py` — URL, selectors, excluded cycles, paths (`PIPELINE_ID` targets another pipeline).
- `scraper.py` — Playwright pull → `raw_downloads/` + manifest; discovers gas days + cycles live.
- `schema.py` — the `flow_006_raw` columns/types + the type-safe `validate_and_coerce` guard (source-agnostic).
- `formatter.py` — maps the TIGT download onto the schema (`COLMAP` + direction + derived) and writes CSV/TXT/HTML.
- `field_mapping.md` — per-column mapping + NULL rationale.

`schema.py` (Python validator) and Test 2's `schema.sql` (the DDL the DB enforces, verbatim
from the brief) both describe `flow_006_raw` but are kept **independent** — different
runtimes, and generating one from the other would risk drifting from the brief's DDL.
