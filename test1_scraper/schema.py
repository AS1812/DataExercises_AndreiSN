"""flow_006_raw schema definition + type-safe coercion/validation.

This module is the heart of the "standardize for DB upload" requirement. The
task states: *"bad data will throw errors, i.e. uploading a string to a numeric
data type."* Rather than discover that at INSERT time, we enforce the column
types here, in Python, so a bad value fails loudly with a clear message and
never reaches the database.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional

import numpy as np
import pandas as pd


class DataTypeError(ValueError):
    """Raised when a value cannot be coerced to its target column type."""


@dataclass(frozen=True)
class Column:
    name: str
    kind: str               # uuid | int | bigint | smallint | float | numeric | str | date | ts
    nullable: bool = True
    maxlen: Optional[int] = None     # for str/char columns
    scale: Optional[int] = None      # for numeric(p,s)
    precision: Optional[int] = None
    db_default: bool = False         # DB fills it on INSERT (gen_random_uuid(), now())


# Column order + types transcribed directly from the CREATE TABLE in the brief.
SCHEMA: list[Column] = [
    Column("flow_uuid", "uuid", nullable=False, db_default=True),  # DEFAULT gen_random_uuid()
    Column("date_cycle_id", "bigint"),
    Column("nomination_id", "str", maxlen=36),
    Column("metadata_id", "str", maxlen=30),
    Column("tsp", "str", maxlen=15),
    Column("tsp_short", "str", maxlen=3),
    Column("tsp_name", "str", maxlen=100),
    Column("cycle_id", "smallint"),
    Column("hourly_cycle_id", "int"),
    Column("cycle_num", "smallint"),
    Column("cycle_desc", "str", maxlen=30),
    Column("eff_gas_day", "date"),
    Column("eff_gas_day_time", "str", maxlen=15),
    Column("end_eff_gas_day", "date"),
    Column("end_eff_gas_day_time", "str", maxlen=15),
    Column("post_date", "date"),
    Column("post_time", "str", maxlen=25),
    Column("cap_type_desc", "str", maxlen=75),
    Column("loc", "str", maxlen=15),
    Column("loc_prop", "str", maxlen=15),
    Column("loc_name", "str", maxlen=150),
    Column("loc_segment", "str", maxlen=25),
    Column("loc_zone", "str", maxlen=25),
    Column("flow_id", "smallint"),
    Column("flow_short", "str", maxlen=25),
    Column("loc_purp_desc", "str", maxlen=50),
    Column("loc_qti_id", "smallint"),
    Column("loc_qti_short", "str", maxlen=3),
    Column("loc_qti", "str", maxlen=10),
    Column("loc_qti_desc", "str", maxlen=75),
    Column("meas_basis_desc", "str", maxlen=75),
    Column("it_id", "smallint"),
    Column("it_num", "smallint"),
    Column("it_desc", "str", maxlen=75),
    Column("design_capacity", "float"),
    Column("operating_capacity", "float"),
    Column("scheduled_quantity", "float"),
    Column("operationally_available", "float"),
    Column("unsubscribed_capacity", "float"),
    Column("no_notice_quantity", "float"),
    Column("storage_capacity", "float"),
    Column("storage_quantity", "float"),
    Column("storage_pct_full", "numeric", precision=3, scale=2),
    Column("design_description", "str", maxlen=25),
    Column("bidirectional", "str", maxlen=25),
    Column("source_type_id", "int"),
    Column("scrape_date", "ts"),
    Column("loc_key", "str", maxlen=20),
    Column("file_name", "str", maxlen=255),
    Column("tsq_sign", "smallint"),
    Column("load_date", "ts", db_default=True),                    # DEFAULT now()
]

COLUMNS = [c.name for c in SCHEMA]
_BY_NAME = {c.name: c for c in SCHEMA}

# Columns the database fills on INSERT (flow_uuid via gen_random_uuid(),
# load_date via now()). The scraper omits these so the DB supplies them --
# they can't be shipped NULL (flow_uuid is NOT NULL) and we don't invent them.
DB_DEFAULT_COLUMNS = [c.name for c in SCHEMA if c.db_default]

_INT_RANGES = {  # postgres int families map exactly onto fixed-width ints
    "smallint": (int(np.iinfo(np.int16).min), int(np.iinfo(np.int16).max)),
    "int":      (int(np.iinfo(np.int32).min), int(np.iinfo(np.int32).max)),
    "bigint":   (int(np.iinfo(np.int64).min), int(np.iinfo(np.int64).max)),
}


def _is_null(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    if isinstance(v, str) and v.strip() in ("", "NULL", "null", "None"):
        return True
    return False


def coerce_value(col: Column, value: Any) -> Any:
    """Coerce one value to its column type or raise DataTypeError."""
    if _is_null(value):
        if not col.nullable:
            raise DataTypeError(f"{col.name}: NULL not allowed (NOT NULL column)")
        return None

    k = col.kind
    try:
        if k == "uuid":
            s = str(value).strip()
            # cheap structural check; the DB enforces the real uuid type
            if len(s.replace("-", "")) != 32:
                raise ValueError("not a uuid")
            return s

        if k in ("int", "smallint", "bigint"):
            # reject genuinely non-numeric strings ("abc") but accept "29520" / 29520.0
            f = float(value)
            if not f.is_integer():
                raise ValueError(f"{value!r} is not an integer")
            iv = int(f)
            lo, hi = _INT_RANGES["smallint" if k == "smallint" else ("bigint" if k == "bigint" else "int")]
            if not (lo <= iv <= hi):
                raise DataTypeError(f"{col.name}: {iv} out of range for {k}")
            return iv

        if k == "float":
            return float(value)

        if k == "numeric":
            f = float(value)
            if col.precision is not None and col.scale is not None:
                max_abs = 10 ** (col.precision - col.scale)
                if abs(f) >= max_abs:
                    raise DataTypeError(
                        f"{col.name}: {f} exceeds numeric({col.precision},{col.scale})")
                f = round(f, col.scale)
            return f

        if k == "str":
            s = str(value)
            if col.maxlen is not None and len(s) > col.maxlen:
                raise DataTypeError(
                    f"{col.name}: value length {len(s)} > varchar({col.maxlen}): {s[:40]!r}...")
            return s

        if k == "date":
            if isinstance(value, datetime):
                return value.date()
            if isinstance(value, date):
                return value
            return pd.to_datetime(value).date()

        if k == "ts":
            if isinstance(value, datetime):
                return value
            return pd.to_datetime(value).to_pydatetime()

    except DataTypeError:
        raise
    except (ValueError, TypeError) as e:
        raise DataTypeError(
            f"{col.name}: cannot coerce {value!r} to {k} ({e})") from e

    raise DataTypeError(f"{col.name}: unknown kind {k!r}")


def validate_and_coerce(df: pd.DataFrame, *, strict: bool = True) -> pd.DataFrame:
    """Return a copy of df with every column coerced to its schema type.

    Any cell that cannot be coerced raises DataTypeError (strict=True) so bad
    data is caught here instead of failing the database INSERT. With
    strict=False, errors are collected and raised together at the end.

    Columns the DB fills on INSERT (db_default, e.g. flow_uuid) may be omitted
    from df; they are simply absent from the result and the DB supplies them.
    Only columns actually present are validated and returned, in schema order.
    """
    missing = [c.name for c in SCHEMA if c.name not in df.columns and not c.db_default]
    if missing:
        raise DataTypeError(f"missing required columns: {missing}")

    out = {}
    errors: list[str] = []
    for col in SCHEMA:
        if col.name not in df.columns:          # DB-default column, omitted on purpose
            continue
        coerced = []
        for idx, raw in enumerate(df[col.name].tolist()):
            try:
                coerced.append(coerce_value(col, raw))
            except DataTypeError as e:
                if strict:
                    raise DataTypeError(f"row {idx}: {e}") from e
                errors.append(f"row {idx}: {e}")
                coerced.append(None)
        out[col.name] = coerced

    if errors:
        raise DataTypeError(f"{len(errors)} type error(s):\n  " + "\n  ".join(errors[:20]))

    present = [c.name for c in SCHEMA if c.name in df.columns]
    return pd.DataFrame(out, columns=present)
