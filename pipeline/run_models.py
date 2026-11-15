"""Minimal dbt-compatible model runner for SQLite.

The SQL in models/ is a real dbt project (run it with `dbt build`, see README).
Streamlit Community Cloud can't run dbt on startup cheaply, so this ~80-line
runner executes the same .sql files against SQLite: it resolves
{{ ref() }}, {{ source() }}, {{ var() }} and {{ config() }}, orders models by
their dependencies and materialises each as a view or table, following the
folder-level settings in dbt_project.yml.

One SQL definition, two engines: dbt+DuckDB/warehouse for the "real" stack,
SQLite for the free demo.
"""
from __future__ import annotations

import re
import sqlite3
import statistics

import yaml

from pipeline import config

REF = re.compile(r"\{\{\s*ref\(\s*['\"](\w+)['\"]\s*\)\s*\}\}")
SOURCE = re.compile(r"\{\{\s*source\(\s*['\"]\w+['\"]\s*,\s*['\"](\w+)['\"]\s*\)\s*\}\}")
VAR = re.compile(r"\{\{\s*var\(\s*['\"](\w+)['\"]\s*\)\s*\}\}")
CONFIG = re.compile(r"\{\{\s*config\((.*?)\)\s*\}\}", re.S)


class _Median:
    """SQLite has no MEDIAN(); DuckDB and most warehouses do. Register one so the
    same SQL runs on both."""

    def __init__(self):
        self.values = []

    def step(self, v):
        if v is not None:
            self.values.append(v)

    def finalize(self):
        return statistics.median(self.values) if self.values else None


def register_functions(conn: sqlite3.Connection) -> None:
    conn.create_aggregate("median", 1, _Median)


def _folder_materializations() -> dict[str, str]:
    with open(config.DBT_PROJECT) as f:
        proj = yaml.safe_load(f)
    models_cfg = proj["models"][proj["name"]]
    return {k: v.get("+materialized", "view") for k, v in models_cfg.items() if isinstance(v, dict)}


def discover() -> dict[str, dict]:
    mats = _folder_materializations()
    models = {}
    for path in sorted(config.MODELS_DIR.rglob("*.sql")):
        sql = path.read_text()
        folder = path.relative_to(config.MODELS_DIR).parts[0]
        mat = mats.get(folder, "view")
        cfg = CONFIG.search(sql)
        if cfg:
            m = re.search(r"materialized\s*=\s*['\"](\w+)['\"]", cfg.group(1))
            if m:
                mat = m.group(1)
        models[path.stem] = {"sql": sql, "deps": set(REF.findall(sql)), "materialized": mat}
    return models


def render(sql: str, variables: dict) -> str:
    sql = CONFIG.sub("", sql)
    sql = REF.sub(lambda m: m.group(1), sql)
    sql = SOURCE.sub(lambda m: m.group(1), sql)
    return VAR.sub(lambda m: str(variables[m.group(1)]), sql)


def topo_order(models: dict) -> list[str]:
    order, seen = [], set()

    def visit(name, stack=()):
        if name in seen or name not in models:
            return
        if name in stack:
            raise ValueError(f"cycle in models: {' -> '.join(stack + (name,))}")
        for d in sorted(models[name]["deps"]):
            visit(d, stack + (name,))
        seen.add(name)
        order.append(name)

    for n in sorted(models):
        visit(n)
    return order


def run(conn: sqlite3.Connection) -> list[str]:
    register_functions(conn)
    variables = config.dbt_vars()
    models = discover()
    order = topo_order(models)
    for name in reversed(order):  # drop dependants first
        conn.execute(f'DROP VIEW IF EXISTS "{name}"')
        conn.execute(f'DROP TABLE IF EXISTS "{name}"')
    for name in order:
        body = render(models[name]["sql"], variables)
        kind = "TABLE" if models[name]["materialized"] == "table" else "VIEW"
        conn.execute(f'CREATE {kind} "{name}" AS {body}')
    conn.commit()
    return order
