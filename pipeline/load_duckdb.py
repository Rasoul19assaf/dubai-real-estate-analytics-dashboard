"""Load the raw DLD files into DuckDB so the real dbt project can run on them:

    python -m pipeline.load_duckdb
    dbt build --profiles-dir .          # seeds, models and tests
"""
import duckdb

from pipeline import config, ingest


def main():
    conn = duckdb.connect(str(config.DATA_DIR / "dbt.duckdb"))
    counts = ingest.load_all(conn, include_seeds=False)  # dbt loads the seeds itself
    conn.close()
    print(f"Loaded into data/dbt.duckdb: {counts}")


if __name__ == "__main__":
    main()
