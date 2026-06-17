"""Formatter: standardize raw Point Capacity downloads into flow_006_raw.

Reads each raw .txt pull listed in the manifest, maps the site's columns onto
the flow_006_raw schema, enforces column types (schema.validate_and_coerce),
and writes upload-ready output:

  outputs/per_cycle/<pull>.csv      one standardized file per cycle+direction
  outputs/flow_006_raw_TIGT.csv     combined dataset (all pulls)  [CSV]
  outputs/flow_006_raw_TIGT.txt     same, tab-delimited          [TXT]
  outputs/flow_006_raw_TIGT.html    same, HTML table             [HTML]

Run:  .venv/bin/python test1_scraper/formatter.py
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pandas as pd

import config as C
from schema import COLUMNS, DB_DEFAULT_COLUMNS, validate_and_coerce

# --- direction -> loc_purp_desc (the page's own radio label) ----------------
# The download has no Receipt/Delivery column; direction is the radio we
# selected. We record it via loc_purp_desc, which is verbatim the page's
# "Loc Purp Desc" radio text. The loc_qti_* family (RPQ/DPQ + numeric id) is
# Criterion's internal coding (taken from the sample, not shown on the page),
# so it is left NULL for the loader.
DIRECTION_FIELDS = {
    "Receipt":  dict(loc_purp_desc="Receipt Location"),
    "Delivery": dict(loc_purp_desc="Delivery Location"),
}

# Source column -> target column for the straight 1:1 mappings.
# Capacity mappings match the grid headers the brief highlights; scheduled_quantity
# uses NET_SCHD_QTY because operating - scheduled = operationally_available
# (verified against both the sample data and live TIGT rows).
COLMAP = {
    "tsp":                     "TSP_DUNS_NO",
    "tsp_name":                "TSP_NM",
    "cycle_id":                "CYCLE_ID",       # site's own cycle id (1,2,3,4,6) -- not renumbered
    "cycle_desc":              "CYCLE_NAME",     # site's label ("Timely" .. "Intra-Day 3")
    "loc":                     "LOC_ID",
    "loc_name":                "LOC_NM",
    "loc_segment":             "LOC_GRP_ID",     # grid's "Loc Segment" column
    "bidirectional":           "BI_DI",
    "design_capacity":         "CAP_QTY",
    "operating_capacity":      "OP_CAP_QTY",
    "scheduled_quantity":      "NET_SCHD_QTY",
    "operationally_available": "OPER_AVAIL_CAP_QTY",
    "unsubscribed_capacity":   "UNSUB_QTY",
    "post_time":               "POST_TM",
}


# NOTE: the scraper populates ONLY values that come from the site (download or
# page), a public-standard derivation of them, or the scrape time it owns.
# The two columns the DB fills on INSERT are OMITTED entirely (DB_DEFAULT_COLUMNS):
# flow_uuid (DEFAULT gen_random_uuid()) and load_date (DEFAULT now()) -- the
# scraper neither invents the PK nor knows the load time, and flow_uuid can't be
# shipped NULL anyway (NOT NULL). Every other column is left NULL for Criterion's
# loader -- its value exists only in Criterion's internal coding, not on the
# site. Reconstructing any of them (loc_qti_*, loc_key, file_name, metadata_id,
# flow_id, ...) would mean fabricating data from the sample.


def map_pull(raw_path, meta: dict, scrape_ts: datetime) -> pd.DataFrame:
    """Map one raw download to a typed flow_006_raw DataFrame."""
    df = pd.read_csv(raw_path, sep="\t", dtype=str, keep_default_na=False)
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)

    dirf = DIRECTION_FIELDS[meta["direction"]]
    tsp_short = str(C.PIPELINE_ID)        # the site's pipeline id (from the URL), as char(3)

    records = []
    for _, r in df.iterrows():
        gd = pd.to_datetime(r["GAS_DAY"]).date()
        rec = {col: None for col in COLUMNS}                     # NULL by default
        rec.update({src_tgt: r[src] for src_tgt, src in COLMAP.items()})  # incl. cycle_id/cycle_desc
        rec.update(dirf)                                         # loc_purp_desc
        rec.update({
            # site values, standard derivations of them, and the scrape time:
            "tsp_short":        tsp_short,             # site pipeline id
            "eff_gas_day":      gd,                    # GAS_DAY -> date
            "eff_gas_day_time": "9",                   # 09:00 CCT: on the page + NAESB gas-day start
            "end_eff_gas_day":  gd + timedelta(days=1),# gas day ends next calendar day (page "End Date")
            "post_date":        r["POST_DT"] or None,  # POST_DT -> date
            "scrape_date":      scrape_ts,             # when this scrape ran
        })
        records.append(rec)

    # Drop the DB-assigned columns (flow_uuid, load_date) so the DB fills them on
    # load; validate the rest of the columns against the schema.
    df_out = pd.DataFrame(records, columns=COLUMNS).drop(columns=DB_DEFAULT_COLUMNS)
    return validate_and_coerce(df_out, strict=True)


def main() -> None:
    C.PER_CYCLE_DIR.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(C.MANIFEST.read_text(encoding="utf-8"))
    scrape_ts = datetime.now()

    frames, skipped = [], 0
    for meta in manifest:
        if meta["n_rows"] == 0:
            skipped += 1
            continue
        raw_path = C.RAW_DIR / meta["raw_file"]
        typed = map_pull(raw_path, meta, scrape_ts)

        per_cycle = C.PER_CYCLE_DIR / (raw_path.stem + ".csv")
        typed.to_csv(per_cycle, index=False)
        print(f"  {meta['raw_file']:<22} {len(typed):>4} rows -> per_cycle/{per_cycle.name}")
        frames.append(typed)

    combined = pd.concat(frames, ignore_index=True)
    base = C.OUT_DIR / "flow_006_raw_TIGT"
    combined.to_csv(base.with_suffix(".csv"), index=False)
    combined.to_csv(base.with_suffix(".txt"), index=False, sep="\t")
    combined.to_html(base.with_suffix(".html"), index=False, na_rep="NULL")

    print(f"\n[formatter] {len(frames)} cycle-files standardized, {skipped} empty skipped.")
    print(f"[formatter] combined {len(combined)} rows -> "
          f"{base.with_suffix('.csv').name}, .txt, .html")
    print(f"[formatter] {len(combined.columns)}/51 columns written "
          f"(flow_uuid + load_date omitted -> DB fills on load), types enforced.")


if __name__ == "__main__":
    main()
