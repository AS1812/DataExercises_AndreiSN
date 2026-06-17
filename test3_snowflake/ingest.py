"""Ingest a Postgres export of flow_006_raw into Snowflake.

The standard stage -> COPY -> MERGE pattern, keyed on flow_uuid so re-runs upsert
instead of duplicating:

    export CSV  ->  internal stage  ->  COPY INTO landing table  ->  MERGE into target

    python ingest.py               # load sample_export.csv into Snowflake

Modules: connection.py (auth via .env), create_db.py (warehouse + CRITERION_DB).
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).parent
SCHEMA_SQL = ROOT / "snowflake_schema.sql"
TABLE = "pipeline.flow_006_raw"
LANDING = "pipeline.flow_006_raw_landing"
KEY = "flow_uuid"


def schema_columns() -> list[str]:
    """The target column names, read from snowflake_schema.sql (single source)."""
    ddl = SCHEMA_SQL.read_text()
    body = ddl.split(f"CREATE TABLE IF NOT EXISTS {TABLE} (", 1)[1].rsplit(");", 1)[0]
    cols = []
    for line in body.splitlines():
        line = line.strip().rstrip(",")
        if not line or line.upper().startswith("CONSTRAINT"):
            continue
        cols.append(line.split()[0])
    return cols


def build_statements(csv_path: Path, columns: list[str]) -> list[tuple[str, str]]:
    """The ordered (label, SQL) steps of the ingest."""
    set_clause = ",\n        ".join(f"t.{c} = s.{c}" for c in columns if c != KEY)
    insert_cols = ", ".join(columns)
    insert_vals = ", ".join(f"s.{c}" for c in columns)

    return [
        ("ensure target table", SCHEMA_SQL.read_text().strip()),

        ("file format", """CREATE OR REPLACE FILE FORMAT pipeline.ff_csv
    TYPE = CSV
    FIELD_OPTIONALLY_ENCLOSED_BY = '"'
    NULL_IF = ('', 'NULL')
    EMPTY_FIELD_AS_NULL = TRUE
    PARSE_HEADER = TRUE;"""),  # required for MATCH_BY_COLUMN_NAME (matches CSV header)

        ("temporary stage", """CREATE OR REPLACE TEMPORARY STAGE pipeline.stg_flow_006_raw
    FILE_FORMAT = pipeline.ff_csv;"""),

        ("upload the export to the stage",
         f"PUT file://{csv_path} @pipeline.stg_flow_006_raw OVERWRITE = TRUE AUTO_COMPRESS = TRUE;"),

        ("landing table (same shape as target)",
         f"CREATE OR REPLACE TRANSIENT TABLE {LANDING} LIKE {TABLE};"),

        ("COPY into landing (match CSV header by name)", f"""COPY INTO {LANDING}
    FROM @pipeline.stg_flow_006_raw
    MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
    ON_ERROR = ABORT_STATEMENT;"""),

        (f"idempotent MERGE into target on {KEY}", f"""MERGE INTO {TABLE} AS t
USING {LANDING} AS s
   ON t.{KEY} = s.{KEY}
WHEN MATCHED THEN UPDATE SET
        {set_clause}
WHEN NOT MATCHED THEN INSERT ({insert_cols})
    VALUES ({insert_vals});"""),

        ("cleanup landing", f"DROP TABLE IF EXISTS {LANDING};"),
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(ROOT / "sample_export.csv"),
                    help="Postgres export of flow_006_raw to ingest")
    args = ap.parse_args()

    from connection import connect          # auth via .env
    import create_db                        # warehouse + CRITERION_DB lives here

    columns = schema_columns()
    steps = build_statements(Path(args.csv).resolve(), columns)

    conn = connect()
    try:
        cur = conn.cursor()
        create_db.ensure(cur)               # warehouse + database (idempotent), then USE them
        for i, (label, sql) in enumerate(steps, 1):
            print(f"[{i}/{len(steps)}] {label} ...")
            # execute_string is a proper multi-statement splitter -- unlike a
            # naive sql.split(";"), it ignores ';' inside comments and strings.
            conn.execute_string(sql)
        cur.execute(f"SELECT count(*) FROM {TABLE}")
        print(f"[done] {TABLE} now has {cur.fetchone()[0]} rows")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
