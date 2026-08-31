"""
Dubai Residential Real Estate Analytics Dashboard
==================================================
An interactive Streamlit dashboard over Dubai Land Department residential
transaction records (Jan-Jun 2023, ~44K transactions).

Run locally:
    pip install -r requirements.txt
    python scripts/build_database.py   # builds data/dubai_real_estate.db (first run only)
    streamlit run app.py

Author: Rasoul Abouassaf
"""
import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# Palette (fixed categorical order + single-hue sequential ramp, chosen so
# adjacent series stay distinguishable under common colour-vision deficiencies)
# ---------------------------------------------------------------------------
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SEQUENTIAL_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
INK_PRIMARY = "#0b0b0b"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"

PLOTLY_TEMPLATE = dict(
    layout=dict(
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", color=INK_PRIMARY),
        plot_bgcolor=SURFACE,
        paper_bgcolor=SURFACE,
        xaxis=dict(gridcolor=GRID, zerolinecolor=GRID, linecolor="#c3c2b7"),
        yaxis=dict(gridcolor=GRID, zerolinecolor=GRID, linecolor="#c3c2b7"),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=10, r=10, t=40, b=10),
    )
)

DB_PATH = Path(__file__).resolve().parent / "data" / "dubai_real_estate.db"

st.set_page_config(page_title="Dubai Real Estate Analytics", layout="wide", page_icon="🏙️")


@st.cache_data
def load_data() -> pd.DataFrame:
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql("SELECT * FROM transactions", conn, parse_dates=["transaction_date"])
        conn.close()
        return df
    except Exception:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from scripts.build_database import main as build_database
        build_database()
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql("SELECT * FROM transactions", conn, parse_dates=["transaction_date"])
        conn.close()
        return df
df = load_data()

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
st.sidebar.title("Filters")

months = sorted(df["transaction_month"].unique())
month_range = st.sidebar.select_slider(
    "Transaction month", options=months, value=(months[0], months[-1])
)

areas = ["All areas"] + sorted(df["area"].unique().tolist())
area_pick = st.sidebar.selectbox("Area", areas)

prop_types = ["All types"] + sorted(df["property_sub_type"].dropna().unique().tolist())
prop_pick = st.sidebar.selectbox("Property sub-type", prop_types)

reg_types = ["All"] + sorted(df["registration_type"].dropna().unique().tolist())
reg_pick = st.sidebar.selectbox("Off-Plan / Ready", reg_types)

st.sidebar.markdown("---")
st.sidebar.caption(
    "Data: Dubai Land Department residential transaction records, "
    "Jan-Jun 2023 (~44K transactions after cleaning). "
    "See README for full source attribution."
)

# Apply filters
mask = df["transaction_month"].between(month_range[0], month_range[1])
if area_pick != "All areas":
    mask &= df["area"] == area_pick
if prop_pick != "All types":
    mask &= df["property_sub_type"] == prop_pick
if reg_pick != "All":
    mask &= df["registration_type"] == reg_pick

fdf = df[mask]

# ---------------------------------------------------------------------------
# Header + KPI tiles
# ---------------------------------------------------------------------------
st.title("🏙️ Dubai Residential Real Estate Analytics")
st.caption(
    "Exploring ~44,000 residential sales, mortgage, and gift transactions recorded "
    "by the Dubai Land Department between January and June 2023."
)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Transactions", f"{len(fdf):,}")
k2.metric("Total value", f"AED {fdf['amount_aed'].sum()/1e9:,.2f} B")
k3.metric("Avg price / sqm", f"AED {fdf['price_per_sqm'].mean():,.0f}")
k4.metric("Avg transaction value", f"AED {fdf['amount_aed'].mean():,.0f}")

st.markdown("---")

# ---------------------------------------------------------------------------
# Row 1: monthly trend (transactions) + off-plan vs ready split
# ---------------------------------------------------------------------------
c1, c2 = st.columns([2, 1])

with c1:
    st.subheader("Monthly transaction volume")
    monthly = fdf.groupby("transaction_month").size().reset_index(name="transactions")
    fig = px.line(monthly, x="transaction_month", y="transactions", markers=True)
    fig.update_traces(line=dict(color=CATEGORICAL[0], width=2), marker=dict(size=8))
    fig.update_layout(**PLOTLY_TEMPLATE["layout"], yaxis_title="Transactions", xaxis_title="")
    st.plotly_chart(fig, use_container_width=True)

with c2:
    st.subheader("Off-Plan vs. Ready")
    split = fdf["registration_type"].value_counts().reset_index()
    split.columns = ["registration_type", "count"]
    fig = px.bar(split, x="registration_type", y="count", color="registration_type",
                 color_discrete_sequence=CATEGORICAL)
    fig.update_layout(**PLOTLY_TEMPLATE["layout"], showlegend=False, yaxis_title="Transactions", xaxis_title="")
    st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# Row 2: top areas by volume, top areas by price/sqm
# ---------------------------------------------------------------------------
c3, c4 = st.columns(2)

with c3:
    st.subheader("Top 10 areas by transaction volume")
    top_vol = (
        fdf.groupby("area").size().reset_index(name="transactions")
        .sort_values("transactions", ascending=False).head(10)
    )
    fig = px.bar(top_vol.sort_values("transactions"), x="transactions", y="area", orientation="h",
                 color_discrete_sequence=[CATEGORICAL[0]])
    fig.update_layout(**PLOTLY_TEMPLATE["layout"], xaxis_title="Transactions", yaxis_title="")
    st.plotly_chart(fig, use_container_width=True)

with c4:
    st.subheader("Top 10 areas by avg. price / sqm (min. 50 txns)")
    by_area = fdf.groupby("area").agg(transactions=("area", "size"), avg_psqm=("price_per_sqm", "mean"))
    top_price = by_area[by_area["transactions"] >= 50].sort_values("avg_psqm", ascending=False).head(10).reset_index()
    fig = px.bar(top_price.sort_values("avg_psqm"), x="avg_psqm", y="area", orientation="h",
                 color="avg_psqm", color_continuous_scale=SEQUENTIAL_BLUE)
    fig.update_layout(**PLOTLY_TEMPLATE["layout"], xaxis_title="AED / sqm", yaxis_title="", coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# Row 3: property mix + bedroom distribution
# ---------------------------------------------------------------------------
c5, c6 = st.columns(2)

with c5:
    st.subheader("Property sub-type mix")
    mix = fdf["property_sub_type"].value_counts().reset_index()
    mix.columns = ["property_sub_type", "count"]
    fig = px.bar(mix, x="property_sub_type", y="count", color="property_sub_type",
                 color_discrete_sequence=CATEGORICAL)
    fig.update_layout(**PLOTLY_TEMPLATE["layout"], showlegend=False, yaxis_title="Transactions", xaxis_title="")
    st.plotly_chart(fig, use_container_width=True)

with c6:
    st.subheader("Bedroom-count distribution")
    rooms_order = ["Studio", "1 B/R", "2 B/R", "3 B/R", "4 B/R", "5 B/R", "6 B/R", "7 B/R", "9 B/R"]
    rooms = fdf["rooms"].value_counts().reindex(rooms_order).dropna().reset_index()
    rooms.columns = ["rooms", "count"]
    fig = px.bar(rooms, x="rooms", y="count", color_discrete_sequence=[CATEGORICAL[2]])
    fig.update_layout(**PLOTLY_TEMPLATE["layout"], yaxis_title="Transactions", xaxis_title="")
    st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# Row 4: map
# ---------------------------------------------------------------------------
st.subheader("Where transactions are happening (avg. price / sqm by project)")
proj = (
    fdf.dropna(subset=["latitude_project", "longitude_project"])
    .groupby(["project", "latitude_project", "longitude_project"])
    .agg(transactions=("project", "size"), avg_psqm=("price_per_sqm", "mean"))
    .reset_index()
)
proj = proj[proj["transactions"] >= 5]
if len(proj):
    fig = px.scatter_map(
        proj, lat="latitude_project", lon="longitude_project",
        size="transactions", color="avg_psqm", color_continuous_scale=SEQUENTIAL_BLUE,
        hover_name="project", hover_data={"transactions": True, "avg_psqm": ":.0f",
                                           "latitude_project": False, "longitude_project": False},
        zoom=9, height=520,
    )
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), coloraxis_colorbar_title="AED/sqm")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No projects with 5+ transactions match the current filters.")

# ---------------------------------------------------------------------------
# Data table
# ---------------------------------------------------------------------------
with st.expander("View filtered data"):
    st.dataframe(
        fdf[["transaction_date", "area", "project", "property_sub_type", "registration_type",
             "rooms", "transaction_size_sqm", "amount_aed", "price_per_sqm"]]
        .sort_values("transaction_date", ascending=False),
        use_container_width=True,
    )
