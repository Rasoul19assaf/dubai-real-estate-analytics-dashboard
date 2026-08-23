"""
Build a clean SQLite database from the raw Dubai residential transactions CSV.

Source data: Dubai Land Department (DLD) open real estate transaction records,
Jan-Jun 2023 residential transactions, accessed via a public GitHub mirror
(see README for full attribution).
"""
import sqlite3
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "dubai_real_estate.db"

# The repo ships the raw CSV gzip-compressed (data/dubai_residential_transactions.csv.gz)
# to keep the repo small; pandas.read_csv decompresses .gz files transparently based on
# the extension, so this works whether you keep the .gz or gunzip it yourself.
_CSV_PLAIN = DATA_DIR / "dubai_residential_transactions.csv"
_CSV_GZ = DATA_DIR / "dubai_residential_transactions.csv.gz"
RAW_CSV = _CSV_PLAIN if _CSV_PLAIN.exists() else _CSV_GZ


def load_and_clean(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)

    # Normalize column names: strip whitespace, lowercase, snake_case
    df.columns = [c.strip().lower().replace(".", "").replace("(", "").replace(")", "")
                    .replace("?", "").replace("/", "_").replace(" ", "_") for c in df.columns]

    # Amount arrives as a comma-formatted string, e.g. "2,631,000"
    df["amount_aed"] = (
        df["amount"].astype(str).str.replace(",", "", regex=False).astype(float)
    )
    df = df.drop(columns=["amount"])

    # Parse transaction date/time
    df["transaction_date"] = pd.to_datetime(df["transaction_date"], errors="coerce")
    df["transaction_year"] = df["transaction_date"].dt.year
    df["transaction_month"] = df["transaction_date"].dt.to_period("M").astype(str)

    # Drop the 8 rows with no transaction size (can't compute price/sqm for them)
    df = df.dropna(subset=["transaction_size_sqm"])
    df = df[df["transaction_size_sqm"] > 0]

    # Price per square metre — the core comparability metric across property sizes
    df["price_per_sqm"] = df["amount_aed"] / df["transaction_size_sqm"]

    # Drop a small number of extreme outliers (data-entry errors: AED/sqm outside
    # a plausible Dubai residential range) so they don't distort area-level averages
    lower, upper = df["price_per_sqm"].quantile([0.005, 0.995])
    before = len(df)
    df = df[(df["price_per_sqm"] >= lower) & (df["price_per_sqm"] <= upper)]
    removed = before - len(df)

    # Tidy text fields
    df["area"] = df["area"].str.strip().str.title()
    df["property_sub_type"] = df["property_sub_type"].str.strip()
    df["registration_type"] = df["registration_type"].str.strip()

    print(f"Loaded {before:,} rows, removed {removed} price/sqm outliers "
          f"(0.5th/99.5th pct clip), kept {len(df):,} rows.")

    keep_cols = [
        "transaction_number", "transaction_date", "transaction_year", "transaction_month",
        "transaction_type", "transaction_sub_type", "registration_type", "is_free_hold",
        "area", "property_type", "property_sub_type", "amount_aed",
        "transaction_size_sqm", "property_size_sqm", "rooms", "bedrooms", "parking",
        "nearest_metro", "nearest_mall", "no_of_buyer", "no_of_seller",
        "project", "latitude_project", "longitude_project", "price_per_sqm",
    ]
    # Handle the 'room(s)' -> 'rooms' rename robustly
    if "rooms" not in df.columns and "roomss" in df.columns:
        df = df.rename(columns={"roomss": "rooms"})
    df = df.rename(columns={c: "rooms" for c in df.columns if c.startswith("rooms")})
    keep_cols = [c for c in keep_cols if c in df.columns]
    return df[keep_cols]


def main():
    df = load_and_clean(RAW_CSV)
    conn = sqlite3.connect(DB_PATH)
    df.to_sql("transactions", conn, if_exists="replace", index=False)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_area ON transactions(area)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_month ON transactions(transaction_month)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_type ON transactions(property_sub_type)")
    conn.commit()
    conn.close()
    print(f"Wrote {len(df):,} cleaned rows to {DB_PATH}")


if __name__ == "__main__":
    main()
