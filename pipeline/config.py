"""Paths and settings shared by every pipeline step.

Business thresholds (what counts as an "impossible" price, minimum sample
sizes for a KPI to be shown, etc.) are NOT defined here: they live once, in
`dbt_project.yml` under `vars:`, and are read from there by both dbt and the
lightweight SQLite runner, so the two can never disagree.
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SALES_DIR = DATA_DIR / "sales"            # one or more DLD transaction CSV exports (.csv or .csv.gz)
RENTS_DIR = DATA_DIR / "rents"            # one or more DLD rent-contract CSV exports (.csv or .csv.gz)
ARCHIVE_2023_CSV = DATA_DIR / "archive_2023" / "dubai_residential_transactions.csv.gz"  # v1's source file
SEEDS_DIR = ROOT / "seeds"
MODELS_DIR = ROOT / "models"
REPORTS_DIR = ROOT / "reports"
DOCS_DIR = ROOT / "docs"

DB_PATH = DATA_DIR / "dubai_real_estate.db"

DBT_PROJECT = ROOT / "dbt_project.yml"


def dbt_vars() -> dict:
    """Thresholds and settings, read from dbt_project.yml (single source of truth)."""
    with open(DBT_PROJECT) as f:
        return yaml.safe_load(f).get("vars", {})
