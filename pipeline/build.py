"""One command for the whole refresh: load -> transform -> check -> report.

    python -m pipeline.build

1. ingest.py         copy the DLD files into SQLite as delivered (raw_* tables + seeds)
2. run_models.py     run the dbt models in models/ (staging -> intermediate -> marts)
3. quality_checks.py run every data-quality check, write dq_results + the incident report
4. kpi_catalogue.py  regenerate docs/KPI_CATALOGUE.md from models/marts/schema.yml

The Streamlit app calls build() automatically if the database is missing or stale.
"""
from __future__ import annotations

import sqlite3
import time

import pandas as pd

from pipeline import config, ingest, kpi_catalogue, quality_checks, run_models


def _v1_reconciliation(conn) -> list[dict]:
    """Run v1's method (every row, 0.5/99.5 percentile clip, means) on the current data, next to
    the governed v2 numbers. The 2023 comparison v1 was built on is in docs/V1_RETROSPECTIVE_2023.md."""
    raw = ingest.read_sales()
    v1 = raw.copy()
    v1["amount_aed"] = pd.to_numeric(v1["amount"].str.replace(",", "", regex=False), errors="coerce")
    v1["size"] = pd.to_numeric(v1["transaction_size_sqm"], errors="coerce")
    v1 = v1[v1["size"].notna() & (v1["size"] > 0)]
    v1["psm"] = v1["amount_aed"] / v1["size"]
    lo, hi = v1["psm"].quantile([0.005, 0.995])
    clipped_out = v1[(v1["psm"] < lo) | (v1["psm"] > hi)]
    v1 = v1[(v1["psm"] >= lo) & (v1["psm"] <= hi)]
    v1_area = v1["area"].str.strip().str.title()
    v1_off = v1.groupby("registration_type")["psm"].mean()

    v2 = pd.read_sql("select * from fct_sales where is_valid = 1", conn)
    v2_off = v2.groupby("is_off_plan")["price_per_sqm"].median()
    big_real = clipped_out[(clipped_out["amount_aed"] >= 50e6)
                           & clipped_out["transaction_number"].isin(v2["transaction_number"])]  # valid under v2 rules
    invalid = pd.read_sql("select transaction_number from fct_sales where quality_status like 'excluded%'", conn)["transaction_number"]
    kept_bad = int(invalid.isin(v1["transaction_number"]).sum())
    n_rule = int(_one(conn, "select count(*) from fct_sales where quality_status like 'excluded%'"))
    n_scope = int(_one(conn, "select count(*) from fct_sales where quality_status like 'out of scope%'"))

    return [
        {"kpi": "Transactions", "v1": f"{len(v1):,} rows", "v2": f"{len(v2):,} sales",
         "why": "the naive count includes mortgages, gifts, lease-to-own, developer registrations, land, offices "
                "and duplicate rows"},
        {"kpi": "Total value", "v1": f"AED {v1['amount_aed'].sum()/1e9:,.1f}B",
         "v2": f"AED {v2['amount_aed'].sum()/1e9:,.1f}B",
         "why": "the naive sum adds loan amounts, repeated portfolio-mortgage totals, land and commercial deals"},
        {"kpi": "Price per sqm (all)", "v1": f"AED {v1['psm'].mean():,.0f} (mean)",
         "v2": f"AED {v2['price_per_sqm'].median():,.0f} (median)",
         "why": "residential freehold sales only; median so a few ultra-prime sales don't pull the figure"},
        {"kpi": "Off-plan premium per sqm", "v1": f"{v1_off['Off-Plan']/v1_off['Ready']-1:.0%}",
         "v2": f"{v2_off[1]/v2_off[0]-1:.0%}",
         "why": "the naive ready average mixes in mortgage, gift and land values; "
                f"on sales alone the same mean-based method gives {_sales_only_premium(v1):.0%}"},
        {"kpi": "Records removed", "v1": f"{len(clipped_out):,} (percentile clip)",
         "v2": f"{n_rule:,} invalid + {n_scope:,} out of scope (rules)",
         "why": f"the clip deletes {len(big_real):,} genuine AED 50M+ sales while keeping {kept_bad:,} records "
                "with impossible sizes or prices; rules say why each record is out"},
        {"kpi": "Distinct area names", "v1": f"{v1_area.nunique()}",
         "v2": f"{int(_one(conn, 'select count(distinct area_name) from fct_sales where is_valid = 1'))}",
         "why": "sales communities linked to their DLD land area, so they join to rents"},
    ]


def _sales_only_premium(v1: pd.DataFrame) -> float:
    m = v1[v1["transaction_type"] == "Sales"].groupby("registration_type")["psm"].mean()
    return m["Off-Plan"] / m["Ready"] - 1


def input_fingerprint() -> str:
    """Hash of everything the database is built from. The app rebuilds when it changes."""
    import hashlib
    h = hashlib.sha256()
    files = [config.DBT_PROJECT, config.DOCS_DIR / "kpi_definitions.yml"]
    files += sorted(config.SALES_DIR.glob("*.csv*")) if config.SALES_DIR.exists() else []
    files += sorted(config.SEEDS_DIR.glob("*.csv")) + sorted(config.MODELS_DIR.rglob("*.sql"))
    files += sorted(config.RENTS_DIR.glob("*.csv*")) if config.RENTS_DIR.exists() else []
    files += sorted((config.ROOT / "pipeline").glob("*.py"))
    for f in files:
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()[:16]


def _one(conn, sql):
    return conn.execute(sql).fetchone()[0]


def build(db_path=config.DB_PATH, verbose=True) -> dict:
    t0 = time.time()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = db_path.with_suffix(".building.db")
    if tmp.exists():
        tmp.unlink()
    conn = sqlite3.connect(tmp)
    run_models.register_functions(conn)
    loaded = ingest.load_all(conn)
    models = run_models.run(conn)
    results = quality_checks.run_checks(conn)
    recon = _v1_reconciliation(conn)
    pd.DataFrame(recon).to_sql("kpi_reconciliation", conn, if_exists="replace", index=False)
    quality_checks.write_outputs(conn, results, recon)
    conn.execute("drop table if exists build_meta")
    conn.execute("create table build_meta (fingerprint text, built_at text)")
    conn.execute("insert into build_meta values (?, datetime('now'))", (input_fingerprint(),))
    conn.commit()
    conn.close()
    tmp.replace(db_path)  # swap in atomically so the app never reads a half-built DB
    kpi_catalogue.write_markdown()
    summary = {
        "loaded": loaded, "models": models, "seconds": round(time.time() - t0, 1),
        "checks": {s: sum(r.status == s for r in results) for s in ("FAIL", "WARN", "PASS")},
    }
    if verbose:
        print(f"Loaded {loaded['raw_dld_transactions']:,} transaction rows and {loaded['raw_dld_rents']:,} rent rows")
        print(f"Built {len(models)} models: {', '.join(models)}")
        print(f"Data quality: {summary['checks']}  ->  reports/data_quality_report.md")
        print(f"Done in {summary['seconds']}s -> {db_path}")
    return summary


def main():
    build()


if __name__ == "__main__":
    main()
