"""Data-quality checks that run on every refresh.

Each check answers one question about the data, returns how many rows fail,
shows examples, and says what should happen next and who should act.
Results go to:
  * table  dq_results               (read by the dashboard's "Data health" tab)
  * file   reports/data_quality_report.md   (the incident report for this run)
  * file   reports/dq_run_history.csv       (one line per check per run, so trends show)

Status meaning:
  PASS - nothing to do
  WARN - handled by a rule in the models, but someone should know / review
  FAIL - a KPI is wrong or missing until someone acts (e.g. a new area name
         appeared that isn't in the area map)
"""
from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone

from pipeline import config

OWNER_DATA = "Ops Excellence (data owner)"
OWNER_BIZ = "Acquisitions (business owner)"


@dataclass
class Result:
    check_id: str
    dataset: str
    check: str
    status: str            # PASS / WARN / FAIL
    failing_rows: int
    detail: str
    action: str
    owner: str
    examples: list[str] = field(default_factory=list)


def _one(conn, sql):
    return conn.execute(sql).fetchone()[0]


def _rows(conn, sql):
    return conn.execute(sql).fetchall()


def _fmt_aed(x):
    return f"AED {x/1e9:,.2f}B" if x and x >= 1e9 else f"AED {x/1e6:,.1f}M" if x else "AED 0"


def run_checks(conn: sqlite3.Connection) -> list[Result]:
    v = config.dbt_vars()
    R: list[Result] = []

    # ---------------- Sales source --------------------------------------------------
    n_raw = _one(conn, "select count(*) from stg_dld_transactions")
    months = [r[0] for r in _rows(conn, "select distinct transaction_month from stg_dld_transactions order by 1")]
    expected = [f"{v['period_start'][:4]}-{m:02d}" for m in range(int(v['period_start'][5:7]), int(v['period_end'][5:7]) + 1)]
    missing = [m for m in expected if m not in months]
    extra = [m for m in months if m not in expected]
    R.append(Result("S01", "sales", "Every month of the period is present",
                    "FAIL" if missing or n_raw == 0 else "PASS", len(missing),
                    f"{n_raw:,} source rows; all {len(expected)} months present" if not missing else
                    f"{n_raw:,} source rows; missing months: {', '.join(missing)}",
                    "Re-download the missing months before publishing KPIs.", OWNER_DATA))

    n = _one(conn, """select count(*) from stg_dld_transactions
                      where transaction_number is null or transaction_date is null
                         or amount_aed is null or raw_area_name is null""")
    R.append(Result("S02", "sales", "Required fields (number, date, amount, area) are filled",
                    "FAIL" if n else "PASS", n, f"{n:,} rows missing a required field",
                    "Rows can't be used; check the export settings.", OWNER_DATA))

    n = _one(conn, "select count(*) from stg_dld_transactions where transaction_date not between "
                   f"'{v['period_start']}' and '{v['period_end']} 23:59:59'")
    ex = [f"{r[0]}: {r[1]:,} rows" for r in _rows(conn, f"""select substr(transaction_date, 1, 10), count(*) from stg_dld_transactions
            where transaction_date not between '{v['period_start']}' and '{v['period_end']} 23:59:59' group by 1 order by 2 desc limit 3""")]
    R.append(Result("S03", "sales", "Dates fall inside the reporting window",
                    "WARN" if n else "PASS", n,
                    f"{n:,} rows dated outside {v['period_start']} to {v['period_end']} although the export was requested "
                    "for exactly that window (the website's date filter and the recorded timestamp disagree). "
                    "Handled: marked out of scope, so each month's KPIs only contain that month.",
                    "Check how the export filters dates; don't trust the filter for month-end totals.", OWNER_DATA, ex))

    # duplicates, classified
    dup_rows = _one(conn, """select count(*) from stg_dld_transactions where transaction_number in
                             (select transaction_number from stg_dld_transactions group by 1 having count(*) > 1)""")
    dup_numbers = _one(conn, "select count(*) from (select transaction_number from stg_dld_transactions group by 1 having count(*) > 1)")
    dual_logged = _one(conn, """select count(*) from (select transaction_number from stg_dld_transactions
                                 group by 1 having count(*) = 2 and count(distinct transaction_type) = 2)""")
    dup_sales = _one(conn, """select count(*) from (select transaction_number from stg_dld_transactions
                               where transaction_type = 'Sales' group by 1 having count(*) > 1)""")
    exact_dupes = _one(conn, """select coalesce(sum(c - 1), 0) from (select count(*) c from stg_dld_transactions
                                  group by row_hash having count(*) > 1)""")
    ex = [f"{r[0]}: {r[1]}, same amount AED {r[2]:,.0f}" for r in _rows(conn, """
            select transaction_number, group_concat(transaction_type || ': ' || transaction_sub_type, ' + '), max(amount_aed)
            from stg_dld_transactions group by 1
            having count(*) = 2 and count(distinct transaction_type) = 2 and count(distinct amount_aed) = 1 limit 3""")]
    R.append(Result("S04", "sales", "Transaction numbers are unique",
                    "WARN" if dup_rows else "PASS", dup_rows,
                    f"{dup_rows:,} rows share {dup_numbers:,} transaction numbers. {dual_logged:,} numbers are one deal "
                    f"(mostly lease-to-own) logged twice, once as Sales and once as Mortgage; {dup_sales:,} numbers repeat "
                    f"within Sales ({exact_dupes:,} rows are exact copies); the rest are portfolio mortgages (see S05). "
                    "Handled: these sub-types are not market sales, and one row per number reaches the KPIs.",
                    "No action while the rule holds; counting raw rows overstates market activity.", OWNER_DATA, ex))

    # portfolio mortgages repeating the whole portfolio value on each unit
    rows_ = _rows(conn, """select transaction_number, count(*) c, max(amount_aed) a, min(project)
                           from stg_dld_transactions where transaction_sub_type like 'Portfolio Mortgage%'
                           group by 1 having count(*) > 1 and count(distinct amount_aed) = 1 order by c desc""")
    n_rows = sum(r[1] for r in rows_)
    overstated = sum(r[2] * (r[1] - 1) for r in rows_)
    R.append(Result("S05", "sales", "Portfolio mortgage amounts aren't repeated per unit",
                    "WARN" if rows_ else "PASS", n_rows,
                    f"{len(rows_):,} portfolio mortgages repeat the same total amount on every unit ({n_rows:,} rows). "
                    f"Summing raw amounts would add {_fmt_aed(overstated)} that never changed hands. "
                    "Handled: mortgages are excluded from sales KPIs by rule.",
                    "Never sum the raw Amount column across transaction types.", OWNER_DATA,
                    [f"{r[0]} ({r[3]}): {r[1]} rows x AED {r[2]:,.0f}" for r in rows_[:3]]))

    n = _one(conn, "select count(*) from int_transactions_conformed where is_unmapped_type = 1")
    ex = [r[0] for r in _rows(conn, """select distinct transaction_type || ' / ' || transaction_sub_type
                                       from int_transactions_conformed where is_unmapped_type = 1 limit 5""")]
    R.append(Result("S06", "sales", "Every transaction sub-type has a sale/not-sale rule",
                    "FAIL" if n else "PASS", n,
                    f"{n:,} rows have a sub-type not in seeds/transaction_type_rules.csv (counted as NOT a sale until reviewed)",
                    "Add the sub-type to the rules seed with a decision and rationale.", OWNER_DATA, ex))

    by_reason = _rows(conn, "select quality_status, count(*) from fct_sales where quality_status like 'excluded%' group by 1 order by 2 desc")
    n = sum(r[1] for r in by_reason)
    ex = [f"{r[0]} | {r[1]} | {r[2]} | AED {r[3]:,.0f} | {r[4] if r[4] is not None else 'no'} sqm" for r in _rows(conn, """
            select * from (select transaction_number, area_name, quality_status, amount_aed, transaction_size_sqm,
                   row_number() over (partition by quality_status order by amount_aed) rn
                   from fct_sales where is_valid = 0) where rn <= 2""")]
    tiny = _one(conn, "select count(*) from fct_sales where transaction_size_sqm > 0 and transaction_size_sqm < 5")
    R.append(Result("S07", "sales", "Sale prices and sizes are physically possible",
                    "WARN" if n else "PASS", n,
                    ("; ".join(f"{c:,} {s.replace('excluded: ', '')}" for s, c in by_reason) or "none")
                    + (f". {tiny} 'sales' are under 5 sqm at low prices (e.g. a 2-bed flat at 3 sqm): possibly a share of a "
                       "unit changing hands rather than a whole unit. Hypothesis, to confirm with DLD." if tiny else ""),
                    "Excluded from KPIs automatically; spot-check examples against the DLD site.", OWNER_DATA, ex))

    hi = _rows(conn, """select transaction_number, area_name, project, amount_aed, round(price_per_sqm)
                        from fct_sales where quality_status like 'kept%' order by price_per_sqm desc""")
    R.append(Result("S08", "sales", f"Price per sqm above AED {v['review_sale_price_per_sqm']:,} reviewed",
                    "WARN" if hi else "PASS", len(hi),
                    f"{len(hi):,} sales between AED {v['review_sale_price_per_sqm']:,} and {v['max_sale_price_per_sqm']:,} per sqm: "
                    "kept (real ultra-prime sales exist) but listed for review. Above the maximum they are excluded (S07)",
                    "Confirm or correct; medians keep a few outliers from moving area KPIs.", OWNER_BIZ,
                    [f"{r[0]} | {r[1]} | {r[2]} | AED {r[3]:,.0f} ({r[4]:,.0f}/sqm)" for r in hi[:4]]))

    studios = _one(conn, "select count(*) from fct_sales where bedrooms_band = 'Studio'")
    n_sales = _one(conn, "select count(*) from fct_sales")
    R.append(Result("S09", "sales", "Studios are recorded as a separate category",
                    "WARN" if studios == 0 else "PASS", 0 if studios else n_sales,
                    f"{studios:,} studio sales out of {n_sales:,}"
                    + (". Zero studios is unlikely for Dubai; the extract may code studios as 1-bedroom." if not studios else ""),
                    "Verify against a fresh DLD export before reporting 1-bed KPIs separately.", OWNER_DATA))

    blank_usage = _one(conn, "select count(*) from stg_dld_transactions where usage is null or usage = ''")
    scope = _rows(conn, """select quality_status, count(*) from fct_sales where quality_status like 'out of scope%'
                           group by 1 order by 2 desc""")
    non_res = _rows(conn, """select coalesce(property_type, '?') || ' / ' || coalesce(property_sub_type, '(blank)'), count(*)
                             from fct_sales where quality_status = 'out of scope: land or non-residential'
                             group by 1 order by 2 desc limit 5""")
    R.append(Result("S10", "sales", "Export filter 'Usage = Residential' can be trusted",
                    "WARN" if blank_usage or scope else "PASS", sum(c for _, c in scope),
                    f"The Usage column is blank on {blank_usage:,} of {n_raw:,} rows, and sales of land, offices and shops "
                    "are present although the export was filtered to Residential. "
                    + "; ".join(f"{c:,} {st.replace('out of scope: ', '')}" for st, c in scope)
                    + ". Handled: scope is decided by property type and unit-class rules, not by the export filter.",
                    "Don't rely on the website filter; keep the unit-type rules current.", OWNER_DATA,
                    [f"{t}: {c:,} sales" for t, c in non_res]))

    # ---------------- Area names (the shared dimension) ------------------------------
    unm = _rows(conn, """select raw_area_name, count(*) from int_transactions_conformed
                         where area_mapping_status = 'unmapped' group by 1 order by 2 desc""")
    R.append(Result("A01", "areas", "Every area name in sales is in the area map",
                    "FAIL" if unm else "PASS", sum(r[1] for r in unm),
                    f"{len(unm)} new area names not in seeds/area_name_map.csv",
                    "Add each name to the area map (as-is, case fix or alias) and rebuild.", OWNER_DATA,
                    [f"{r[0]} ({r[1]} rows)" for r in unm[:5]]))

    by_status = dict(_rows(conn, "select area_mapping_status, count(*) from fct_sales where is_valid = 1 group by 1"))
    n_valid = sum(by_status.values()) or 1
    bridged = by_status.get("project_crosswalk", 0)
    joinable = by_status.get("land_area", 0) + bridged
    n_bridged_names = _one(conn, "select count(*) from area_name_map where mapping_status = 'project_crosswalk'")
    R.append(Result("A02", "areas", "Sales areas line up with rent areas",
                    "PASS" if joinable / n_valid >= 0.8 else "WARN", n_valid - joinable,
                    f"Sales use community names (e.g. Jumeirah Village Circle); rents use DLD land areas (e.g. Al Barsha "
                    f"South Fourth). On name alone only {by_status.get('land_area', 0) / n_valid:.0%} of valid sales match a rent "
                    f"area. {n_bridged_names} communities are bridged to their land area by shared projects "
                    f"(seeds/area_name_map.csv), bringing coverage to {joinable / n_valid:.0%}.",
                    "Re-run pipeline/propose_area_map.py when new names appear; review its proposals.", OWNER_DATA,
                    [f"{r[0]} -> {r[1]} ({r[2]})" for r in _rows(conn, """select raw_area_key, area_name, evidence from area_name_map
                        where mapping_status = 'project_crosswalk' order by cast(sales_rows_at_review as integer) desc limit 4""")]))

    pend = _rows(conn, """select raw_area_key, evidence, cast(sales_rows_at_review as integer) from area_name_map
                          where mapping_status = 'alias_pending_review' order by 3 desc""")
    R.append(Result("A03", "areas", "Weakly-evidenced area links decided by an owner",
                    "WARN" if pend else "PASS", sum(p[2] for p in pend),
                    f"{len(pend)} communities share only a few projects with a rent land area, so they are NOT linked "
                    f"automatically ({sum(p[2] for p in pend):,} sales rows). A wrong link silently changes that area's yield.",
                    "Owner confirms or rejects each link in seeds/area_name_map.csv.", OWNER_BIZ,
                    [f"{p[0]} ({p[2]:,} sales): {p[1]}" for p in pend[:5]]))

    no_match = _rows(conn, """select raw_area_key, cast(sales_rows_at_review as integer) from area_name_map
                              where mapping_status = 'no_rent_match' order by 2 desc""")
    R.append(Result("A04", "areas", "Sales areas with no rent evidence at all",
                    "WARN" if no_match else "PASS", sum(n for _, n in no_match),
                    f"{len(no_match)} sales area names share no project with any rent contract (often new off-plan "
                    "communities with nothing rented yet). They get price and liquidity, but no yield.",
                    "Expected for pre-handover areas; recheck after each refresh.", OWNER_DATA,
                    [f"{a} ({n:,} sales rows)" for a, n in no_match[:5]]))

    # ---------------- Rents ------------------------------------------------------------
    n_rent = _one(conn, "select count(*) from stg_dld_rents")
    R.append(Result("R01", "rents", "Rent contracts are loaded",
                    "FAIL" if n_rent == 0 else "PASS", 0 if n_rent else 1,
                    f"{n_rent:,} rent contract rows loaded from data/rents/" if n_rent else
                    "No rent file in data/rents/: rent and yield KPIs are blank",
                    "Export DLD rent contracts for the same period into data/rents/.", OWNER_DATA))
    if n_rent:
        months_r = [r[0] for r in _rows(conn, "select distinct registration_month from stg_dld_rents order by 1")]
        missing_r = [m for m in expected if m not in months_r]
        R.append(Result("R02", "rents", "Every month of the period is present (rents)",
                        "FAIL" if missing_r else "PASS", len(missing_r),
                        f"{n_rent:,} rows covering {len(months_r)} months; missing: {', '.join(missing_r) or 'none'}",
                        "Re-download the missing months.", OWNER_DATA))
        dups = _one(conn, """select coalesce(sum(c - 1), 0) from (select count(*) c from stg_dld_rents
                             group by row_hash having count(*) > 1)""")
        R.append(Result("R03", "rents", "Rent rows are not duplicated",
                        "WARN" if dups else "PASS", dups,
                        f"{dups:,} of {n_rent:,} rent rows ({dups / n_rent:.1%}) are exact copies of another row. The DLD rent "
                        "export has no contract number, so a full-row fingerprint is the only way to catch them. Kept once.",
                        "Report to the data provider; never count raw rows as contracts.", OWNER_DATA))
        out_win = _one(conn, "select count(*) from stg_dld_rents where registration_date not between "
                             f"'{v['period_start']}' and '{v['period_end']} 23:59:59'")
        R.append(Result("R08", "rents", "Registration dates fall inside the reporting window",
                        "WARN" if out_win else "PASS", out_win, f"{out_win:,} rent rows dated outside the window",
                        "Check the export date filter.", OWNER_DATA))
        by_reason = _rows(conn, "select quality_status, count(*) from fct_rent_contracts where quality_status like 'excluded%' or quality_status like 'out of scope%' group by 1 order by 2 desc")
        R.append(Result("R04", "rents", "Rents are single residential units with plausible values",
                        "WARN" if by_reason else "PASS", sum(r[1] for r in by_reason),
                        "; ".join(f"{c:,} {s.replace('excluded: ', '').replace('out of scope: ', '')}" for s, c in by_reason) or "none",
                        "Excluded from KPIs automatically (labour camps, whole-building leases, data-entry errors).", OWNER_DATA))
        unm_r = _rows(conn, """select raw_area_name, count(*) from fct_rent_contracts
                               where area_mapping_status = 'unmapped' group by 1 order by 2 desc""")
        R.append(Result("R05", "rents", "Every rent area name is in the area map",
                        "FAIL" if unm_r else "PASS", sum(r[1] for r in unm_r),
                        f"{len(unm_r)} rent area names not in the area map",
                        "Map them so rents join to sales by area.", OWNER_DATA,
                        [f"{r[0]} ({r[1]} rows)" for r in unm_r[:5]]))
        unm_u = _rows(conn, """select coalesce(property_sub_type, '(blank)'), count(*) from fct_rent_contracts
                               where unit_class is null group by 1 order by 2 desc""")
        R.append(Result("R06", "rents", "Every rent unit type maps to a unit class",
                        "WARN" if unm_u else "PASS", sum(r[1] for r in unm_u),
                        f"{len(unm_u)} rent property sub-types without a unit class (can't join to sales)",
                        "Add to seeds/unit_type_map.csv or confirm they are out of scope.", OWNER_DATA,
                        [f"{r[0]} ({r[1]} rows)" for r in unm_u[:5]]))
        no_bed = _one(conn, "select count(*) from fct_rent_contracts where bedrooms_band is null and is_valid = 1")
        n_valid_r = _one(conn, "select count(*) from fct_rent_contracts where is_valid = 1")
        R.append(Result("R07", "rents", "Bedrooms are known for rent contracts",
                        "WARN" if no_bed else "PASS", no_bed,
                        f"{no_bed:,} of {n_valid_r:,} valid contracts ({no_bed / max(n_valid_r, 1):.0%}) have no room count: "
                        "the Ejari export leaves it blank for flats. Handled: yield is computed per area and unit class using "
                        "rent and price per sqm, not per bedroom.",
                        "Revisit if a richer rent source (e.g. Dubai Pulse API) becomes available.", OWNER_DATA))

    # ---------------- Cross-source coverage ---------------------------------------------
    segs = _one(conn, "select count(*) from mart_area_unit_kpis")
    with_yield = _one(conn, "select count(*) from mart_area_unit_kpis where gross_yield is not null")
    sales_cov = _one(conn, "select coalesce(sum(sales_count), 0) from mart_area_unit_kpis where gross_yield is not null")
    sales_all = _one(conn, "select coalesce(sum(sales_count), 0) from mart_area_unit_kpis")
    R.append(Result("X01", "kpis", "Yield can be computed where buying happens",
                    "WARN" if not segs or with_yield / segs < 0.5 else "PASS", segs - with_yield,
                    f"Yield available for {with_yield} of {segs} area/unit-class segments, covering "
                    f"{(sales_cov / sales_all if sales_all else 0):.0%} of valid sales "
                    f"(needs at least {v['min_sample_indicative']} ready sales and rent contracts per segment)",
                    "Segments without yield show 'Insufficient data' rather than a guess.", OWNER_BIZ))
    return R


def write_outputs(conn, results: list[Result], recon: list[dict]) -> str:
    run_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    conn.execute("drop table if exists dq_results")
    conn.execute("""create table dq_results (run_at text, check_id text, dataset text, check_name text, status text,
                    failing_rows integer, detail text, action text, owner text, examples text)""")
    conn.executemany("insert into dq_results values (?,?,?,?,?,?,?,?,?,?)",
                     [(run_at, r.check_id, r.dataset, r.check, r.status, r.failing_rows, r.detail, r.action,
                       r.owner, "\n".join(r.examples)) for r in results])
    conn.commit()

    config.REPORTS_DIR.mkdir(exist_ok=True)
    hist = config.REPORTS_DIR / "dq_run_history.csv"
    new = not hist.exists()
    with open(hist, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["run_at", "check_id", "status", "failing_rows"])
        w.writerows([[run_at, r.check_id, r.status, r.failing_rows] for r in results])

    counts = {s: sum(r.status == s for r in results) for s in ("FAIL", "WARN", "PASS")}
    icon = {"FAIL": "🔴 FAIL", "WARN": "🟡 WARN", "PASS": "🟢 PASS"}
    lines = [
        "# Data quality report",
        "",
        f"_Generated automatically by `python -m pipeline.build` on {run_at}. Do not edit by hand._",
        "",
        f"**{counts['FAIL']} fail · {counts['WARN']} warn · {counts['PASS']} pass**",
        "",
        "FAIL = a KPI is wrong or missing until someone acts. WARN = handled by a rule, but someone should "
        "know or review. Thresholds live in `dbt_project.yml` → `vars`.",
        "",
        "## Open incidents",
        "",
    ]
    order = {"FAIL": 0, "WARN": 1, "PASS": 2}
    for r in sorted(results, key=lambda r: (order[r.status], r.check_id)):
        if r.status == "PASS":
            continue
        lines += [f"### {icon[r.status]} {r.check_id} · {r.check}", "",
                  f"- **Dataset:** {r.dataset}  ·  **Rows affected:** {r.failing_rows:,}  ·  **Owner:** {r.owner}",
                  f"- **What we found:** {r.detail}", f"- **Next step:** {r.action}"]
        if r.examples:
            lines.append("- **Examples:**")
            lines += [f"  - `{e}`" for e in r.examples]
        lines.append("")
    lines += ["## Passing checks", "", "| Check | Dataset | Result |", "|---|---|---|"]
    lines += [f"| {r.check_id} {r.check} | {r.dataset} | {r.detail} |" for r in results if r.status == "PASS"]
    lines += ["", "## Impact of the data rules on headline KPIs", "",
              "Same source files, computed two ways: the naive v1 method (every row, 0.5/99.5 percentile clip, means) "
              "vs governed (residential freehold sales only, de-duplicated, rule-based validity, medians). "
              "What v1 actually published on the 2023 file: docs/V1_RETROSPECTIVE_2023.md.", "",
              "| KPI | Naive (v1 method) | Governed | Why it differs |", "|---|---|---|---|"]
    lines += [f"| {d['kpi']} | {d['v1']} | {d['v2']} | {d['why']} |" for d in recon]
    text = "\n".join(lines) + "\n"
    (config.REPORTS_DIR / "data_quality_report.md").write_text(text)
    return text
