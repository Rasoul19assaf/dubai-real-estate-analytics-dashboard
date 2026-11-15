"""The two tools the "Ask the data" assistant may use, and the guardrails around them.

run_sql      read-only SQL against the GOVERNED tables only (marts, facts, quality results).
             Enforced by SQLite itself, not by the prompt:
               * the database is opened read-only (mode=ro) with query_only on
               * an authorizer rejects any statement that is not a SELECT and any read of a
                 table outside ALLOWED_TABLES (so raw_* tables, with duplicates and mortgages,
                 are unreachable)
               * one statement per call, at most MAX_ROWS rows returned, a time limit per query
search_docs  keyword retrieval (BM25) over the written knowledge: KPI definitions, the latest
             data-quality findings and the documented limitations. This is the RAG part: the
             assistant must use the same definitions as the dashboard, not its own.
"""
from __future__ import annotations

import math
import re
import sqlite3
import time
from dataclasses import dataclass, field

import yaml

from pipeline import config
from pipeline.run_models import register_functions

ALLOWED_TABLES = {
    "mart_area_unit_kpis", "mart_area_segment_kpis", "mart_monthly_market",
    "fct_sales", "fct_rent_contracts", "dq_results", "kpi_reconciliation", "area_name_map",
}
MAX_ROWS = 200
TIME_LIMIT_S = 3.0


@dataclass
class SqlResult:
    query: str
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    truncated: bool = False
    error: str | None = None

    def as_text(self, max_rows: int = 30) -> str:
        """Compact text the model reads back (keeps token use low)."""
        if self.error:
            return f"ERROR: {self.error}"
        if not self.rows:
            return "No rows."
        head = " | ".join(self.columns)
        body = "\n".join(" | ".join(_fmt(v) for v in r) for r in self.rows[:max_rows])
        more = len(self.rows) - max_rows
        note = f"\n... {more} more rows not shown" if more > 0 else ""
        if self.truncated:
            note += f"\n(result capped at {MAX_ROWS} rows)"
        return f"{head}\n{body}{note}"


def _fmt(v):
    if isinstance(v, float):
        return f"{v:.4f}" if abs(v) < 10 else f"{v:,.0f}"
    return "" if v is None else str(v)


def _authorizer(action, arg1, arg2, db_name, trigger):
    # Allow plain SELECTs, reads of whitelisted tables, and function calls (median, round, ...).
    if action == sqlite3.SQLITE_SELECT or action == sqlite3.SQLITE_FUNCTION:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_READ:
        # arg1 = table; CTE / subquery reads carry no table name or a sqlite_ internal one
        if arg1 is None or arg1 in ALLOWED_TABLES:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_RECURSIVE:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def _connect(db_path=None) -> sqlite3.Connection:
    path = db_path or config.DB_PATH
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
    conn.execute("PRAGMA query_only = ON")
    register_functions(conn)
    conn.set_authorizer(_authorizer)
    return conn


def run_sql(query: str, db_path=None) -> SqlResult:
    query = (query or "").strip().rstrip(";").strip()
    res = SqlResult(query=query)
    if not re.match(r"(?is)^\s*(select|with)\b", query):
        res.error = "Only a single SELECT (or WITH ... SELECT) statement is allowed."
        return res
    conn = _connect(db_path)
    deadline = time.monotonic() + TIME_LIMIT_S
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
    try:
        cur = conn.execute(query)
        res.columns = [d[0] for d in cur.description or []]
        rows = cur.fetchmany(MAX_ROWS + 1)
        res.truncated = len(rows) > MAX_ROWS
        res.rows = rows[:MAX_ROWS]
    except sqlite3.DatabaseError as e:
        msg = str(e)
        if "not authorized" in msg:
            msg = ("not authorized: only these tables can be queried: " + ", ".join(sorted(ALLOWED_TABLES))
                   + ". Statements other than SELECT are blocked.")
        elif "interrupted" in msg:
            msg = f"query took longer than {TIME_LIMIT_S:.0f}s; aggregate or filter more."
        res.error = msg
    finally:
        conn.close()
    return res


# --------------------------------------------------------------------------------------
# Retrieval (BM25) over the project's written knowledge
# --------------------------------------------------------------------------------------
@dataclass
class Doc:
    doc_id: str
    title: str
    text: str


def build_corpus(db_path=None) -> list[Doc]:
    docs: list[Doc] = []
    with open(config.DOCS_DIR / "kpi_definitions.yml") as f:
        kdefs = yaml.safe_load(f)
    for k in kdefs["kpis"]:
        docs.append(Doc(f"KPI {k['id']}", k["name"],
                        f"{k['name']}. Question: {k['question']} Definition: {k['definition']} "
                        f"Formula: {k['formula']} Source: {k['model']}. Unit: {k['unit']}. "
                        f"Owner: {k['business_owner']}. Caveats: {k.get('caveats', '')}"))
    try:
        conn = sqlite3.connect(f"file:{db_path or config.DB_PATH}?mode=ro", uri=True)
        for cid, name, status, n, detail, action in conn.execute(
                "select check_id, check_name, status, failing_rows, detail, action from dq_results"):
            docs.append(Doc(f"Check {cid}", name,
                            f"Data-quality check {cid} '{name}': status {status}, {n} rows affected. {detail} "
                            f"Next step: {action}"))
        conn.close()
    except sqlite3.Error:
        pass
    readme = (config.ROOT / "README.md").read_text()
    for section in ("Known limitations", "Refreshing the data"):
        m = re.search(rf"## {section}\n(.*?)(?=\n## |\Z)", readme, re.S)
        if m:
            docs.append(Doc(f"README: {section}", section, m.group(1).strip()))
    return docs


_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class BM25:
    def __init__(self, docs: list[Doc], k1: float = 1.5, b: float = 0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.toks = [_tokens(d.title + " " + d.text) for d in docs]
        self.avgdl = sum(map(len, self.toks)) / max(len(self.toks), 1)
        df: dict[str, int] = {}
        for t in self.toks:
            for w in set(t):
                df[w] = df.get(w, 0) + 1
        n = len(docs)
        self.idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}

    def search(self, query: str, k: int = 4) -> list[Doc]:
        q = _tokens(query)
        scores = []
        for i, t in enumerate(self.toks):
            tf: dict[str, int] = {}
            for w in t:
                tf[w] = tf.get(w, 0) + 1
            s = 0.0
            for w in q:
                if w in tf:
                    f = tf[w]
                    s += self.idf.get(w, 0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * len(t) / self.avgdl))
            scores.append((s, i))
        return [self.docs[i] for s, i in sorted(scores, reverse=True)[:k] if s > 0]


def search_docs(query: str, index: BM25 | None = None) -> list[Doc]:
    return (index or BM25(build_corpus())).search(query)


# --------------------------------------------------------------------------------------
# What the model needs to know about the tables (goes into the system prompt)
# --------------------------------------------------------------------------------------
SCHEMA_GUIDE = """
Tables you can query (SQLite; MEDIAN(x) is available). Data: Dubai Land Department open data,
residential FREEHOLD only, May-October 2026.

mart_area_unit_kpis  -- one row per area_name x unit_class. USE THIS FIRST for price / yield / liquidity questions.
  area_name, unit_class ('Apartment','Villa/Townhouse','Hotel apartment','Hotel room'),
  sales_count, ready_sales_count, sales_per_month, ready_sales_per_month (= liquidity), off_plan_share (0-1),
  median_price_aed, median_price_per_sqm, median_ready_price_aed, median_ready_price_per_sqm,
  rent_contracts, new_rent_contracts, median_annual_rent_aed, median_rent_per_sqm, median_new_rent_per_sqm,
  gross_yield (0-1, e.g. 0.072 = 7.2%), gross_yield_new_leases (0-1), yield_sample,
  yield_confidence ('Reliable','Indicative','Insufficient data')
mart_area_segment_kpis -- area_name x unit_class x bedrooms_band ('Studio','1','2','3','4','5+'): sales_count,
  ready_sales_count, sales_per_month, ready_sales_per_month, off_plan_share, median_price_aed,
  median_price_per_sqm, median_ready_price_aed, median_ready_price_per_sqm. (No rents/yield by bedroom.)
mart_monthly_market -- transaction_month ('2026-05'..'2026-10'), source_rows, sales_count, off_plan_sales,
  sales_value_aed, median_price_per_sqm, median_off_plan_price_per_sqm, median_ready_price_per_sqm
fct_sales -- one row per sale. ALWAYS filter is_valid = 1. transaction_number, transaction_date,
  transaction_month, is_off_plan (1/0), area_name, unit_class, bedrooms_band, amount_aed,
  transaction_size_sqm, price_per_sqm, project, quality_status
fct_rent_contracts -- one row per rent contract. ALWAYS filter is_valid = 1. registration_month,
  version ('New','Renewed'), area_name, unit_class, bedrooms_band (mostly NULL for flats),
  annual_rent_aed, property_size_sqm, rent_per_sqm, project
dq_results -- data-quality checks: check_id, check_name, status (PASS/WARN/FAIL), failing_rows, detail, action, owner
kpi_reconciliation -- naive method vs governed headline numbers: kpi, v1, v2, why
area_name_map -- raw_area_key (name as in the source, UPPER CASE), area_name, mapping_status, evidence

AREA NAMES: area_name is the official DLD land area followed by the communities it contains, e.g.
'Al Barsha South Fourth (Jumeirah Village Circle)', 'Marsa Dubai (Dubai Marina, Jumeirah Beach Residence)',
'Business Bay', 'Burj Khalifa' (= Downtown). When a user names a community, match with
LIKE '%Jumeirah Village Circle%' (case-insensitive) rather than '='. Downtown Dubai is area 'Burj Khalifa'.
"""
