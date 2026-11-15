"""Extract & load: copy source files into the database exactly as delivered.

The loader deliberately does almost no cleaning. Every business rule lives in
SQL models (models/) and every problem is reported by quality_checks.py, so a
reviewer can see what the source said and what we decided about it.

What the loader does do:
  * accept any number of export files per source (.csv or .csv.gz), so a new
    month is just a new file in data/sales/ or data/rents/
  * map the two column layouts DLD has used (the dubailand.gov.ae export, e.g.
    AREA_EN / TRANS_VALUE, and the older Kaggle mirror, e.g. "Area" / "Amount")
    onto one set of snake_case names
  * write dates as ISO text (SQLite and DuckDB parse other formats differently)
  * add a row fingerprint (row_hash) so exact duplicate rows can be detected even
    when the source has no unique id (DLD rent exports have no contract number)
"""
from __future__ import annotations

import re

import pandas as pd

from pipeline import config

SALES_COLUMNS = [
    "transaction_number", "transaction_date", "transaction_type", "transaction_sub_type",
    "registration_type", "is_free_hold", "usage", "area", "property_type", "property_sub_type",
    "amount", "transaction_size_sqm", "property_size_sqm", "rooms", "parking", "nearest_metro",
    "nearest_mall", "nearest_landmark", "no_of_buyer", "no_of_seller", "master_project", "project",
    "latitude_project", "longitude_project",
]
RENT_COLUMNS = [
    "ejari_contract_number", "registration_date", "start_date", "end_date", "version",
    "area", "contract_amount", "annual_amount", "is_free_hold", "property_size_sqm",
    "property_type", "property_sub_type", "number_of_rooms", "usage", "nearest_metro",
    "nearest_mall", "nearest_landmark", "parking", "no_of_units", "master_project", "project",
]

# dubailand.gov.ae export headers -> our names (older mirror headers are handled by snake())
ALIASES = {
    # transactions
    "instance_date": "transaction_date", "group_en": "transaction_type", "procedure_en": "transaction_sub_type",
    "is_offplan_en": "registration_type", "is_free_hold_en": "is_free_hold", "usage_en": "usage",
    "area_en": "area", "prop_type_en": "property_type", "prop_sb_type_en": "property_sub_type",
    "trans_value": "amount", "procedure_area": "transaction_size_sqm", "actual_area": "property_size_sqm",
    "rooms_en": "rooms", "nearest_metro_en": "nearest_metro", "nearest_mall_en": "nearest_mall",
    "nearest_landmark_en": "nearest_landmark", "total_buyer": "no_of_buyer", "total_seller": "no_of_seller",
    "master_project_en": "master_project", "project_en": "project",
    # rents (actual_area -> property_size_sqm and the shared names above also apply)
    "version_en": "version", "prop_sub_type_en": "property_sub_type", "total_properties": "no_of_units",
    "no_of_units": "no_of_units",
}
RENT_ONLY = {"rooms": "number_of_rooms"}


def snake(col: str) -> str:
    c = col.replace("﻿", "").strip().lower().replace("(sq.m)", "sqm").replace("room(s)", "rooms")
    c = re.sub(r"[?.()]", "", c)
    c = re.sub(r"[\s/\-]+", "_", c)
    return c.strip("_")


def _iso_dates(s: pd.Series, dayfirst: bool) -> pd.Series:
    vals = s.dropna().astype(str)
    if not vals.empty and vals.str.match(r"^\d{4}-\d{2}-\d{2}").all():
        parsed = pd.to_datetime(s, errors="coerce", format="ISO8601")
    else:
        parsed = pd.to_datetime(s, errors="coerce", dayfirst=dayfirst, format="mixed")
    out = parsed.dt.strftime("%Y-%m-%d %H:%M:%S")
    return out.where(parsed.notna(), None)


def _guess_dayfirst(s: pd.Series) -> bool:
    """ISO (yyyy-mm-dd) -> False. dd-mm-yyyy vs m/d/yyyy: if any first part > 12 it must be the day."""
    vals = s.dropna().astype(str)
    if vals.empty or vals.str.match(r"^\d{4}-").all():
        return False
    first = vals.str.extract(r"^(\d{1,2})[/\-.]")[0].dropna().astype(int)
    second = vals.str.extract(r"^\d{1,2}[/\-.](\d{1,2})")[0].dropna().astype(int)
    if (first > 12).any():
        return True
    if (second > 12).any():
        return False
    return "-" in vals.iloc[0]


def _read(path, aliases: dict) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""], encoding="utf-8-sig")
    df.columns = [aliases.get(snake(c), snake(c)) for c in df.columns]
    # fingerprint of the row as delivered (before we add any columns)
    df["row_hash"] = pd.util.hash_pandas_object(df.fillna(""), index=False).astype(str)
    df["source_file"] = path.name
    df["source_row"] = range(1, len(df) + 1)
    return df


def _files(folder):
    return sorted(p for p in folder.glob("*.csv*")) if folder.exists() else []


def read_sales(files=None) -> pd.DataFrame:
    files = files or _files(config.SALES_DIR)
    frames = [_read(f, ALIASES) for f in files]
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=SALES_COLUMNS)
    for c in SALES_COLUMNS:
        if c not in df.columns:
            df[c] = None
    df["transaction_date"] = _iso_dates(df["transaction_date"], _guess_dayfirst(df["transaction_date"]))
    return df


def read_rents(files=None) -> pd.DataFrame:
    files = files or _files(config.RENTS_DIR)
    frames = [_read(f, {**ALIASES, **RENT_ONLY}) for f in files]
    if not frames:
        return pd.DataFrame(columns=RENT_COLUMNS + ["row_hash", "source_file", "source_row"])
    df = pd.concat(frames, ignore_index=True)
    for c in RENT_COLUMNS:
        if c not in df.columns:
            df[c] = None
    for c in ("registration_date", "start_date", "end_date"):
        df[c] = _iso_dates(df[c], _guess_dayfirst(df[c]))
    return df


def read_seeds() -> dict[str, pd.DataFrame]:
    return {p.stem: pd.read_csv(p, dtype=str, keep_default_na=False) for p in config.SEEDS_DIR.glob("*.csv")}


def write_table(conn, name: str, df: pd.DataFrame) -> None:
    """Works for both sqlite3 and duckdb connections."""
    if "duckdb" in type(conn).__module__:
        conn.register("_tmp_df", df)
        conn.execute(f'CREATE OR REPLACE TABLE "{name}" AS SELECT * FROM _tmp_df')
        conn.unregister("_tmp_df")
    else:
        df.to_sql(name, conn, if_exists="replace", index=False, chunksize=20000)


def load_all(conn, include_seeds: bool = True) -> dict[str, int]:
    tables = {"raw_dld_transactions": read_sales(), "raw_dld_rents": read_rents()}
    if include_seeds:
        tables.update(read_seeds())
    for name, df in tables.items():
        write_table(conn, name, df)
    return {k: len(v) for k, v in tables.items()}
