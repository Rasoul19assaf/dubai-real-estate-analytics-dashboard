"""Propose seeds/area_name_map.csv: one reporting area per raw area name, across sales AND rents.

Why this exists
---------------
DLD's two exports name areas at different levels:
  * rent contracts (Ejari) use official DLD land areas, e.g. "AL BARSHA SOUTH FOURTH"
  * sales mostly use community / master-development names, e.g. "JUMEIRAH VILLAGE CIRCLE"
Joined on name, under half of sales find matching rents. They are not typos to merge;
they are two levels of one hierarchy. This script builds the bridge from evidence:
the same PROJECT appearing in both files tells us which land area a community sits in.

Rules (thresholds in dbt_project.yml vars):
  * raw name is itself a rent land area            -> mapped, status "land_area"
  * community whose shared projects point to one land area
    (>= area_map_min_projects projects and >= area_map_min_share of matched sales)
                                                    -> mapped, status "project_crosswalk"
  * weaker evidence                                 -> NOT mapped, status "alias_pending_review"
  * no shared projects at all                       -> NOT mapped, status "no_rent_match"

The output is a PROPOSAL committed to seeds/ and reviewed like any other code change.
Run it when the quality check A01 reports area names that are not in the map:

    python -m pipeline.propose_area_map
"""
from __future__ import annotations

import pandas as pd

from pipeline import config, ingest

FIX = {"Ii": "II", "Iii": "III", "Mbr": "MBR", "Me'Aisem": "Me'aisem", "Jlt": "JLT", "Ph": "Ph"}


def title(name: str) -> str:
    return " ".join(FIX.get(w, w) for w in name.strip().title().split(" "))


def propose() -> pd.DataFrame:
    v = config.dbt_vars()
    min_projects, min_share = int(v["area_map_min_projects"]), float(v["area_map_min_share"])
    sales, rents = ingest.read_sales(), ingest.read_rents()
    key = lambda s: s.fillna("").str.strip().str.upper()
    sales["k"], sales["p"] = key(sales["area"]), key(sales["project"])
    rents["k"], rents["p"] = key(rents["area"]), key(rents["project"])
    land_areas = set(rents["k"]) - {""}

    # project -> the land area most of its rent contracts are registered in
    rp = (rents[rents["p"] != ""].groupby(["p", "k"]).size().reset_index(name="n")
          .sort_values("n", ascending=False).drop_duplicates("p"))
    sp = sales[(sales["transaction_type"] == "Sales") & (sales["p"] != "")].groupby(["k", "p"]).size().reset_index(name="sales")
    m = sp.merge(rp.rename(columns={"k": "land"}), on="p", how="inner")
    cw = m.groupby(["k", "land"]).agg(projects=("p", "nunique"), sales=("sales", "sum")).reset_index()
    cw["share"] = cw["sales"] / cw.groupby("k")["sales"].transform("sum")
    best = cw.sort_values(["share", "sales"], ascending=False).drop_duplicates("k").set_index("k")

    sales_counts = sales[sales["transaction_type"] == "Sales"]["k"].value_counts()
    rows = []
    for raw in sorted((set(sales["k"]) | land_areas) - {""}):
        if raw in land_areas:
            rows.append((raw, raw, "land_area", ""))
            continue
        if raw in best.index:
            b = best.loc[raw]
            ev = f"{int(b.projects)} shared projects, {b.share:.0%} of matched sales -> {title(b.land)}"
            if b.projects >= min_projects and b.share >= min_share:
                rows.append((raw, b.land, "project_crosswalk", ev))
            else:
                rows.append((raw, raw, "alias_pending_review", ev))
        else:
            rows.append((raw, raw, "no_rent_match", "no project shared with any rent contract"))
    df = pd.DataFrame(rows, columns=["raw_area_key", "land_area_key", "mapping_status", "evidence"])

    # Display name: "Land Area (Biggest Community, Second)" so people recognise where it is
    communities = (df[df["mapping_status"] == "project_crosswalk"]
                   .assign(sales=lambda d: d["raw_area_key"].map(sales_counts).fillna(0))
                   .sort_values("sales", ascending=False)
                   .groupby("land_area_key")["raw_area_key"].apply(lambda s: [title(x) for x in s[:2]]))
    def display(k):
        c = communities.get(k, [])
        return f"{title(k)} ({', '.join(c)})" if c else title(k)
    df["area_name"] = df["land_area_key"].map(display)
    df["sales_rows_at_review"] = df["raw_area_key"].map(sales_counts).fillna(0).astype(int)
    return df[["raw_area_key", "area_name", "land_area_key", "mapping_status", "evidence", "sales_rows_at_review"]]


def main():
    df = propose()
    out = config.SEEDS_DIR / "area_name_map.csv"
    df.to_csv(out, index=False)
    print(df["mapping_status"].value_counts().to_string())
    print(f"wrote {out} ({len(df)} names)")


if __name__ == "__main__":
    main()
