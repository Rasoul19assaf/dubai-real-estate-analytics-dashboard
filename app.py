"""
Dubai Property Acquisition Screening & Data Operations
======================================================
Streamlit front end over the governed data layer built by `python -m pipeline.build`
(DLD sales + Ejari rents -> dbt-style models -> data-quality checks).

Run locally:
    pip install -r requirements.txt
    streamlit run app.py          # builds data/dubai_real_estate.db on first run

Author: Rasoul Abouassaf
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from pipeline import config  # noqa: E402
from pipeline.build import build, input_fingerprint  # noqa: E402

# ---------------------------------------------------------------------------
# Palette: fixed categorical order, single-hue sequential ramp, reserved status
# colours (always shown with an icon + label, never colour alone).
# ---------------------------------------------------------------------------
BLUE, ORANGE = "#2a78d6", "#eb6834"
SEQUENTIAL_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#898781", "#e1e0d9", "#fcfcfb"
STATUS = {"FAIL": "🔴 FAIL", "WARN": "🟡 WARN", "PASS": "🟢 PASS"}
LAYOUT = dict(
    font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", color=INK),
    plot_bgcolor=SURFACE, paper_bgcolor=SURFACE,
    xaxis=dict(gridcolor=GRID, zerolinecolor=GRID, linecolor="#c3c2b7"),
    yaxis=dict(gridcolor=GRID, zerolinecolor=GRID, linecolor="#c3c2b7"),
    legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=1.08, x=0),
    margin=dict(l=10, r=10, t=40, b=10), hoverlabel=dict(bgcolor="white"),
)

st.set_page_config(page_title="Dubai Acquisition Screening", layout="wide", page_icon="🏙️")


# ---------------------------------------------------------------------------
# Data: rebuild the database whenever its inputs change (new export, new rule)
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner="Building the data layer and running quality checks…")
def ensure_db(fingerprint: str) -> str:
    try:
        with sqlite3.connect(config.DB_PATH) as conn:
            built = conn.execute("select fingerprint from build_meta").fetchone()[0]
        if built == fingerprint:
            return built
    except Exception:
        pass
    build(verbose=False)
    return fingerprint


@st.cache_data
def q(sql: str, _fp: str) -> pd.DataFrame:
    with sqlite3.connect(config.DB_PATH) as conn:
        return pd.read_sql(sql, conn)


FP = ensure_db(input_fingerprint())
sales = q("select * from fct_sales where is_valid = 1", FP)
units = q("select * from mart_area_unit_kpis", FP)
seg = q("select * from mart_area_segment_kpis", FP)
monthly = q("select * from mart_monthly_market order by transaction_month", FP)
dq = q("select * from dq_results", FP)
recon = q("select * from kpi_reconciliation", FP)
has_rents = int(units["rent_contracts"].sum()) > 0
n_rents = int(q("select count(*) n from fct_rent_contracts where is_valid = 1", FP)["n"].iat[0])
v = config.dbt_vars()

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("🏙️ Dubai Acquisition Screening & Data Operations")
n_fail, n_warn = (dq["status"] == "FAIL").sum(), (dq["status"] == "WARN").sum()
st.caption(
    f"Dubai Land Department open data: {len(sales):,} residential freehold sales"
    f"{f' and {n_rents:,} Ejari rent contracts' if has_rents else ''}, {v['period_start']} to {v['period_end']}. "
    "One governed data layer feeds every number here. "
    f"Latest refresh: {dq['run_at'].iat[0]} · Data health: {n_fail} {STATUS['FAIL']} · {n_warn} {STATUS['WARN']}"
)

tab_screen, tab_market, tab_health, tab_kpis, tab_ask = st.tabs(
    ["Acquisition screening", "Market overview", "Data health", "KPI definitions", "Ask the data (AI)"]
)

# ---------------------------------------------------------------------------
# Tab 1: Acquisition screening
# ---------------------------------------------------------------------------
with tab_screen:
    st.markdown("**Where should we buy?** Price, gross rental yield and resale liquidity for every area and unit "
                "type, with a confidence label on each yield.")
    if not has_rents:
        st.warning(f"{STATUS['FAIL']} Rent data not loaded (check R01 in Data health), so the yield columns are "
                   "blank. Price and liquidity are live. Add DLD rent exports to `data/rents/` to switch yields on.")

    f1, f2, f3, f4 = st.columns(4)
    classes = sorted(units["unit_class"].dropna().unique())
    unit = f1.selectbox("Unit class", classes, index=classes.index("Apartment") if "Apartment" in classes else 0)
    budget = f2.number_input("Max median ready price (AED)", min_value=0, value=2_500_000, step=250_000)
    min_liq = f3.number_input("Min ready sales / month", min_value=0.0, value=5.0, step=1.0,
                              help="Resale liquidity: how many ready units changed hands per month.")
    conf = f4.multiselect("Yield confidence", ["Reliable", "Indicative", "Insufficient data"],
                          default=["Reliable", "Indicative"] if has_rents else ["Reliable", "Indicative", "Insufficient data"])

    view = units[(units["unit_class"] == unit)
                 & (units["median_ready_price_aed"].fillna(units["median_price_aed"]) <= budget)
                 & (units["ready_sales_per_month"] >= min_liq)
                 & (units["yield_confidence"].isin(conf))].copy()
    sort_col = "gross_yield" if has_rents else "ready_sales_per_month"
    view = view.sort_values(sort_col, ascending=False, na_position="last")

    m1, m2, m3 = st.columns(3)
    m1.metric("Areas matching", f"{len(view):,}")
    m2.metric("Median ready price / sqm", f"AED {view['median_ready_price_per_sqm'].median():,.0f}" if len(view) else "–")
    rel = view.dropna(subset=["gross_yield"])
    m3.metric("Median gross yield", f"{rel['gross_yield'].median():.1%}" if len(rel) else "–",
              help="Median across the matching areas. Gross: before service charges, vacancy and fees.")

    if has_rents and len(rel):
        fig = px.scatter(
            rel, x="median_ready_price_per_sqm", y="gross_yield", size="ready_sales_per_month",
            color="yield_confidence", color_discrete_map={"Reliable": BLUE, "Indicative": ORANGE},
            hover_name="area_name",
            hover_data={"median_ready_price_aed": ":,.0f", "median_annual_rent_aed": ":,.0f",
                        "ready_sales_count": ":,", "rent_contracts": ":,", "gross_yield": ":.1%",
                        "gross_yield_new_leases": ":.1%", "median_ready_price_per_sqm": ":,.0f",
                        "ready_sales_per_month": ":.1f"},
            labels={"median_ready_price_per_sqm": "Ready price per sqm (AED)", "gross_yield": "Gross yield",
                    "yield_confidence": "Confidence", "ready_sales_per_month": "Ready sales / month",
                    "gross_yield_new_leases": "Yield, new leases only", "median_ready_price_aed": "Median ready price",
                    "median_annual_rent_aed": "Median annual rent", "ready_sales_count": "Ready sales",
                    "rent_contracts": "Rent contracts"},
            height=440)
        fig.update_traces(marker=dict(line=dict(width=2, color=SURFACE)))
        fig.update_layout(**LAYOUT, yaxis_tickformat=".0%")
        st.subheader("Yield vs. entry price (bubble size = resale liquidity)")
        st.plotly_chart(fig, width="stretch")

    cols = {"area_name": "Area", "median_ready_price_aed": "Median ready price (AED)",
            "median_ready_price_per_sqm": "Ready AED/sqm", "ready_sales_per_month": "Ready sales/mo",
            "sales_per_month": "All sales/mo", "off_plan_share": "Off-plan share"}
    if has_rents:
        cols.update({"median_annual_rent_aed": "Median rent (AED/yr)", "rent_contracts": "Rent contracts",
                     "gross_yield": "Gross yield", "gross_yield_new_leases": "Yield (new leases)",
                     "yield_confidence": "Confidence"})
    st.dataframe(
        view[list(cols)].rename(columns=cols), width="stretch", hide_index=True,
        column_config={
            "Median ready price (AED)": st.column_config.NumberColumn(format="%,.0f"),
            "Ready AED/sqm": st.column_config.NumberColumn(format="%,.0f"),
            "Ready sales/mo": st.column_config.NumberColumn(format="%.1f"),
            "All sales/mo": st.column_config.NumberColumn(format="%.1f"),
            "Off-plan share": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
            "Median rent (AED/yr)": st.column_config.NumberColumn(format="%,.0f"),
            "Rent contracts": st.column_config.NumberColumn(format="%,d"),
            "Gross yield": st.column_config.NumberColumn(format="percent"),
            "Yield (new leases)": st.column_config.NumberColumn(format="percent"),
        })
    st.caption("Gross yield = median rent per sqm ÷ median READY sale price per sqm for the same area and unit class "
               "(off-plan units can't be rented yet). Per area, not per bedroom: the Ejari export has no room count for "
               "most flats. Before service charges, vacancy and fees. Area names are DLD land areas with the communities "
               f"they contain in brackets. 'Reliable' needs ≥{v['min_sample_reliable']} ready sales and rent contracts; "
               f"'Indicative' ≥{v['min_sample_indicative']}.")

    if len(view):
        st.subheader("Price and liquidity by bedrooms")
        pick = st.selectbox("Area", view["area_name"].tolist())
        b = seg[(seg["area_name"] == pick) & (seg["unit_class"] == unit)].copy()
        order = {k: i for i, k in enumerate(["Studio", "1", "2", "3", "4", "5+"])}
        b = b.sort_values("bedrooms_band", key=lambda s: s.map(order))
        st.dataframe(
            b[["bedrooms_band", "median_ready_price_aed", "median_price_aed", "ready_sales_per_month", "sales_per_month",
               "off_plan_share"]].rename(columns={
                "bedrooms_band": "Bedrooms", "median_ready_price_aed": "Median ready price (AED)",
                "median_price_aed": "Median price, all (AED)", "ready_sales_per_month": "Ready sales/mo",
                "sales_per_month": "All sales/mo", "off_plan_share": "Off-plan share"}),
            width="stretch", hide_index=True,
            column_config={
                "Median ready price (AED)": st.column_config.NumberColumn(format="%,.0f"),
                "Median price, all (AED)": st.column_config.NumberColumn(format="%,.0f"),
                "Ready sales/mo": st.column_config.NumberColumn(format="%.1f"),
                "All sales/mo": st.column_config.NumberColumn(format="%.1f"),
                "Off-plan share": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1)})

# ---------------------------------------------------------------------------
# Tab 2: Market overview (governed numbers)
# ---------------------------------------------------------------------------
with tab_market:
    areas = ["All areas"] + sorted(sales["area_name"].unique())
    a1, a2 = st.columns([1, 3])
    area_pick = a1.selectbox("Area", areas)
    msales = sales if area_pick == "All areas" else sales[sales["area_name"] == area_pick]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Valid sales", f"{len(msales):,}")
    k2.metric("Sales value", f"AED {msales['amount_aed'].sum()/1e9:,.2f}B")
    k3.metric("Median price / sqm", f"AED {msales['price_per_sqm'].median():,.0f}" if len(msales) else "–")
    op, rd = (msales.loc[msales["is_off_plan"] == i, "price_per_sqm"].median() for i in (1, 0))
    k4.metric("Off-plan premium / sqm", f"{op/rd-1:.0%}" if pd.notna(op) and pd.notna(rd) and rd else "–",
              help="Median off-plan ÷ median ready price per sqm − 1. Mixes projects; not like-for-like.")

    c1, c2 = st.columns([2, 1])
    with c1:
        st.subheader("Valid sales per month")
        mm = msales.assign(type=msales["is_off_plan"].map({1: "Off-plan", 0: "Ready"})) \
                   .groupby(["transaction_month", "type"]).size().reset_index(name="sales")
        fig = px.line(mm, x="transaction_month", y="sales", color="type", markers=True,
                      color_discrete_map={"Off-plan": BLUE, "Ready": ORANGE},
                      labels={"transaction_month": "", "sales": "Sales", "type": ""})
        fig.update_traces(line=dict(width=2), marker=dict(size=8))
        fig.update_layout(**LAYOUT, hovermode="x unified")
        st.plotly_chart(fig, width="stretch")
    with c2:
        st.subheader("Source rows vs. real sales")
        st.caption("Each month the DLD extract holds more rows than real sales: mortgages, gifts, "
                   "lease-to-own and duplicates. Counting rows overstates activity.")
        gap = monthly.assign(gap=monthly["source_rows"] - monthly["sales_count"])
        st.dataframe(gap[["transaction_month", "source_rows", "sales_count", "gap"]]
                     .rename(columns={"transaction_month": "Month", "source_rows": "Source rows",
                                      "sales_count": "Valid sales", "gap": "Not sales"}),
                     hide_index=True, width="stretch")

    c3, c4 = st.columns(2)
    by_area = sales.groupby("area_name").agg(sales=("transaction_number", "size"),
                                              psqm=("price_per_sqm", "median")).reset_index()
    with c3:
        st.subheader("Top 10 areas by valid sales")
        top = by_area.nlargest(10, "sales").sort_values("sales")
        fig = px.bar(top, x="sales", y="area_name", orientation="h", color_discrete_sequence=[BLUE],
                     labels={"sales": "Valid sales", "area_name": ""}, text="sales")
        fig.update_traces(texttemplate="%{text:,}", textposition="outside", marker_cornerradius=4)
        fig.update_layout(**LAYOUT)
        st.plotly_chart(fig, width="stretch")
    with c4:
        st.subheader(f"Top 10 areas by median price / sqm (min. {v['min_sample_reliable']} sales)")
        top = by_area[by_area["sales"] >= v["min_sample_reliable"]].nlargest(10, "psqm").sort_values("psqm")
        fig = px.bar(top, x="psqm", y="area_name", orientation="h", color_discrete_sequence=[BLUE],
                     labels={"psqm": "AED / sqm", "area_name": ""}, text="psqm")
        fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside", marker_cornerradius=4)
        fig.update_layout(**LAYOUT)
        st.plotly_chart(fig, width="stretch")

    proj = (msales.dropna(subset=["latitude", "longitude"])
            .groupby(["project", "latitude", "longitude"])
            .agg(sales=("project", "size"), psqm=("price_per_sqm", "median")).reset_index())
    proj = proj[proj["sales"] >= 5]
    if len(proj):
        st.subheader("Where sales happen (median price / sqm by project, 5+ sales)")
        fig = px.scatter_map(proj, lat="latitude", lon="longitude", size="sales", color="psqm",
                             color_continuous_scale=SEQUENTIAL_BLUE, hover_name="project",
                             hover_data={"sales": True, "psqm": ":,.0f", "latitude": False, "longitude": False},
                             zoom=9, height=480)
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), coloraxis_colorbar_title="AED/sqm")
        st.plotly_chart(fig, width="stretch")
    # (the dubailand.gov.ae export has no project coordinates, so the map only appears for sources that do)

# ---------------------------------------------------------------------------
# Tab 3: Data health (the monitoring that surfaces problems when they happen)
# ---------------------------------------------------------------------------
with tab_health:
    st.markdown("Every refresh runs these checks before any number is shown. **FAIL** = a KPI is wrong or "
                "missing until someone acts. **WARN** = handled by a rule, but someone should know or review.")
    h1, h2, h3 = st.columns(3)
    h1.metric(STATUS["FAIL"], int((dq["status"] == "FAIL").sum()))
    h2.metric(STATUS["WARN"], int((dq["status"] == "WARN").sum()))
    h3.metric(STATUS["PASS"], int((dq["status"] == "PASS").sum()))

    order = {"FAIL": 0, "WARN": 1, "PASS": 2}
    for _, r in dq.sort_values(by="status", key=lambda s: s.map(order)).iterrows():
        with st.expander(f"{STATUS[r['status']]} · {r['check_id']} · {r['check_name']}  ({r['failing_rows']:,} rows)",
                         expanded=r["status"] == "FAIL"):
            st.markdown(f"**What we found:** {r['detail']}\n\n**Next step:** {r['action']}  \n**Owner:** {r['owner']}")
            if r["examples"]:
                st.code(r["examples"], language=None)

    st.subheader("What the data rules change in the headline numbers")
    st.caption("Same source files, two methods. Naive = how the first version of this project worked (every row, "
               "percentile clip, means). Governed = residential freehold sales only, de-duplicated, rule-based "
               "validity, medians. The original 2023 comparison is in docs/V1_RETROSPECTIVE_2023.md.")
    st.dataframe(recon.rename(columns={"kpi": "KPI", "v1": "Naive (v1 method)", "v2": "Governed", "why": "Why it differs"}),
                 hide_index=True, width="stretch")

# ---------------------------------------------------------------------------
# Tab 4: KPI definitions (generated from the same YAML as docs/KPI_CATALOGUE.md)
# ---------------------------------------------------------------------------
with tab_kpis:
    with open(config.DOCS_DIR / "kpi_definitions.yml") as f:
        kdefs = yaml.safe_load(f)
    st.markdown(f"One definition per KPI, kept in `docs/kpi_definitions.yml`. Refresh: {kdefs['defaults']['refresh']}. "
                "Business owners are proposed roles.")
    kt = pd.DataFrame(kdefs["kpis"])[["id", "name", "question", "definition", "formula", "model",
                                      "business_owner", "caveats"]]
    st.dataframe(kt.rename(columns=str.capitalize), hide_index=True, width="stretch")

# ---------------------------------------------------------------------------
# Tab 5: Ask the data (AI assistant)
# Fully isolated: its libraries are imported only here, inside try/except, and it runs as a
# fragment. No API key, a missing library or a provider outage only affects this tab.
# ---------------------------------------------------------------------------
SAMPLE_QUESTIONS = [
    "Which 5 areas have the highest reliable gross yield for apartments?",
    "Compare Jumeirah Village Circle and Dubai Marina apartments: price, yield and liquidity.",
    "How is gross yield calculated, and what are its limits?",
    "What data-quality problems were found in the rent data?",
]
MAX_QUESTIONS_PER_SESSION = 10
MAX_QUESTIONS_PER_DAY = 300      # across all visitors; keeps usage inside the free API tier


def _secret(name: str, default: str = "") -> str:
    import os
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return os.environ.get(name, default)


@st.cache_resource
def _daily_counter() -> dict:
    return {"day": "", "n": 0}


def _assistant_code_version() -> str:
    """Hash of the assistant's source, so a code update never reuses a stale cached assistant."""
    import hashlib
    h = hashlib.sha256()
    for f in sorted((ROOT / "assistant").glob("*.py")):
        h.update(f.read_bytes())
    return h.hexdigest()[:12]


@st.cache_resource(show_spinner="Starting the assistant…")
def _assistant(api_key: str, fp: str):
    from assistant.agent import DataAssistant, candidate_models, gemini_chat_model
    from assistant.retrieval import DEFAULT_EMBEDDING_MODEL, Retriever, gemini_embeddings

    models = candidate_models(api_key, _secret("GEMINI_MODEL"))
    retriever = Retriever(embeddings=gemini_embeddings(api_key, _secret("GEMINI_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)))
    return DataAssistant([gemini_chat_model(api_key, m) for m in models], retriever), models


@st.fragment
def ask_the_data():
    st.markdown("**Ask a question in plain language.** The assistant writes SQL against the same governed tables "
                "as the dashboard and looks up definitions in the KPI catalogue. Every answer shows the SQL it ran, "
                "so it can be checked.")
    api_key = _secret("GEMINI_API_KEY")
    if not api_key:
        st.info("The assistant is not switched on in this deployment (no API key configured). "
                "Everything else in the dashboard works without it.")
        st.caption("Example questions it answers: " + " · ".join(SAMPLE_QUESTIONS))
        return

    import datetime as _dt
    st.session_state.setdefault("ask_history", [])
    picked = st.pills("Try one", SAMPLE_QUESTIONS, key="ask_pick")
    with st.form("ask_form", clear_on_submit=True):
        typed = st.text_input("Your question", max_chars=400, placeholder="e.g. Where can I buy a liquid apartment under AED 1M with a yield above 7%?")
        go = st.form_submit_button("Ask")
    question = typed.strip() if go and typed.strip() else (picked if picked and picked != st.session_state.get("ask_last_pick") else "")
    if picked:
        st.session_state["ask_last_pick"] = picked

    if question:
        counter, today = _daily_counter(), _dt.date.today().isoformat()
        if counter["day"] != today:
            counter.update(day=today, n=0)
        if len(st.session_state["ask_history"]) >= MAX_QUESTIONS_PER_SESSION:
            st.warning(f"Limit of {MAX_QUESTIONS_PER_SESSION} questions per visit reached (this demo runs on a free API tier).")
        elif counter["n"] >= MAX_QUESTIONS_PER_DAY:
            st.warning("The demo's daily question limit has been reached. Please try again tomorrow.")
        else:
            counter["n"] += 1
            assistant, _models = _assistant(api_key, FP + _assistant_code_version())
            with st.spinner("Querying the governed tables…"):
                answer = assistant.ask(question)
            st.session_state["ask_history"].insert(0, (question, answer, assistant.last_model, assistant.retriever.mode))

    for qtext, answer, model, mode in st.session_state["ask_history"]:
        with st.container(border=True):
            st.markdown(f"**Q: {qtext}**")
            if answer.error:
                st.warning(answer.error)
                if getattr(answer, "detail", ""):
                    with st.expander("Technical detail"):
                        st.code(answer.detail, language=None)
            else:
                st.markdown(answer.text)
            for i, res in enumerate(answer.sql, 1):
                with st.expander(f"SQL {i} of {len(answer.sql)}" + (" (failed, retried)" if res.error else f" · {len(res.rows)} rows")):
                    st.code(res.query, language="sql")
                    if res.error:
                        st.caption(res.error)
                    elif res.rows:
                        st.dataframe(pd.DataFrame(res.rows, columns=res.columns), hide_index=True, width="stretch")
            if answer.docs:
                with st.expander("Definitions and findings used: " + ", ".join(d.doc_id for d in answer.docs)):
                    for d in answer.docs:
                        st.markdown(f"**{d.doc_id} · {d.title}**  \n{d.text}")
            st.caption(f"Model: {model} · Retrieval: {mode} · AI-generated: check the SQL before relying on a number. "
                       "Not investment advice.")


with tab_ask:
    try:
        ask_the_data()
    except Exception as e:  # the assistant must never take the dashboard down
        st.warning(f"The assistant is unavailable right now ({type(e).__name__}). The other tabs are unaffected.")

st.sidebar.markdown("### About")
st.sidebar.caption(
    "Data: Dubai Land Department open data (transactions and Ejari rents exported from dubailand.gov.ae). "
    "Pipeline: Python load → dbt SQL models → automated data-quality checks → Streamlit. "
    "See the README for the case study."
)
st.sidebar.caption(
    f"Runtime: Python {sys.version_info.major}.{sys.version_info.minor} · Streamlit {st.__version__}"
)
