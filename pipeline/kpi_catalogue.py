"""Generate docs/KPI_CATALOGUE.md from docs/kpi_definitions.yml and check that the
definitions and the Lightdash metrics in models/schema.yml stay in sync."""
from __future__ import annotations

import yaml

from pipeline import config

DEFS = config.DOCS_DIR / "kpi_definitions.yml"
OUT = config.DOCS_DIR / "KPI_CATALOGUE.md"


def load() -> dict:
    with open(DEFS) as f:
        return yaml.safe_load(f)


def lightdash_kpi_ids() -> set[str]:
    with open(config.MODELS_DIR / "schema.yml") as f:
        schema = yaml.safe_load(f)
    ids = set()
    for model in schema.get("models", []):
        for col in model.get("columns", []) or []:
            for metric in ((col.get("meta") or {}).get("metrics") or {}).values():
                if (metric.get("meta") or {}).get("kpi_id"):
                    ids.add(metric["meta"]["kpi_id"])
    return ids


def write_markdown() -> str:
    d = load()
    kpis, defaults = d["kpis"], d["defaults"]
    defined = {k["id"] for k in kpis}
    orphan_metrics = lightdash_kpi_ids() - defined
    if orphan_metrics:
        raise ValueError(f"Lightdash metrics point to undefined KPI ids: {sorted(orphan_metrics)}")
    v = config.dbt_vars()
    lines = [
        "# KPI catalogue",
        "",
        "_Generated from `docs/kpi_definitions.yml` by `python -m pipeline.build`. Edit the YAML, not this file._",
        "",
        f"- **Refresh:** {defaults['refresh']}",
        f"- **Data owner (all KPIs):** {defaults['data_owner']}",
        "- **Business owners** are proposed roles, to be confirmed with the team.",
        f"- **Thresholds** (`dbt_project.yml` → `vars`): min sale price AED {v['min_sale_price_aed']:,}; "
        f"price/sqm floor AED {v['min_sale_price_per_sqm']:,}; review above AED {v['review_sale_price_per_sqm']:,}/sqm; "
        f"KPI shown as *Reliable* from n = {v['min_sample_reliable']}, *Indicative* from n = {v['min_sample_indicative']}.",
        "",
        "| ID | KPI | Question it answers | Unit | Business owner |",
        "|---|---|---|---|---|",
    ]
    lines += [f"| {k['id']} | {k['name']} | {k['question']} | {k['unit']} | {k['business_owner']} |" for k in kpis]
    lightdash = lightdash_kpi_ids()
    for k in kpis:
        lines += ["", f"## {k['id']} · {k['name']}", "",
                  f"**Definition.** {k['definition']}", "",
                  f"**Formula.** `{k['formula']}`", "",
                  f"**Source model.** `{k['model']}` · **Unit.** {k['unit']} · **Business owner.** {k['business_owner']} "
                  f"· **Refresh.** {k.get('refresh', 'Weekly')}"
                  + (" · **Lightdash metric:** yes" if k["id"] in lightdash else "")]
        if k.get("caveats"):
            lines += ["", f"**Watch out.** {k['caveats']}"]
    text = "\n".join(lines) + "\n"
    OUT.write_text(text)
    return text


if __name__ == "__main__":
    write_markdown()
    print(f"wrote {OUT}")
