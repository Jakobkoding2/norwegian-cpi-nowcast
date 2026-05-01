"""Streamlit dashboard — Norwegian CPI Nowcasting Engine.

Charts:
  1. Smoothed daily index (blue) vs SSB official monthly prints (red dots)
  2. Nowcast prediction with 95% CI shaded band
  3. COICOP breakdown bar chart for the most recent date
"""
from __future__ import annotations

import os
from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Norwegian CPI Nowcast",
    page_icon="📈",
    layout="wide",
)

st.title("Norwegian Food CPI Nowcasting Engine")
st.caption("Real-time Laspeyres index from grocery retailers vs SSB official releases")


# ── Data fetchers (cached 30 min) ─────────────────────────────────────────────

@st.cache_data(ttl=1800)
def fetch_daily_index(from_date: str) -> pd.DataFrame:
    r = requests.get(f"{API_URL}/index", params={"from_date": from_date}, timeout=10)
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    if not df.empty:
        df["price_date"] = pd.to_datetime(df["price_date"])
    return df


@st.cache_data(ttl=1800)
def fetch_ssb() -> pd.DataFrame:
    r = requests.get(f"{API_URL}/ssb", timeout=10)
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    if not df.empty:
        df["reference_month"] = pd.to_datetime(df["reference_month"])
    return df


@st.cache_data(ttl=1800)
def fetch_nowcast() -> dict | None:
    r = requests.get(f"{API_URL}/nowcast/latest", timeout=10)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=1800)
def fetch_breakdown(price_date: str) -> pd.DataFrame:
    r = requests.get(f"{API_URL}/breakdown/{price_date}", timeout=10)
    if r.status_code == 404:
        return pd.DataFrame()
    r.raise_for_status()
    return pd.DataFrame(r.json())


# ── Load data ─────────────────────────────────────────────────────────────────

from_date = str(date.today() - timedelta(days=365))

with st.spinner("Loading data…"):
    try:
        daily_df = fetch_daily_index(from_date)
        ssb_df = fetch_ssb()
        nowcast = fetch_nowcast()
        breakdown_date = str(date.today())
        breakdown_df = fetch_breakdown(breakdown_date)
    except Exception as e:
        st.error(f"API unavailable: {e}")
        st.stop()

# Aggregate index across all COICOP groups for chart 1 (simple mean)
if not daily_df.empty:
    agg_daily = (
        daily_df.groupby("price_date")["index_value"].mean().reset_index()
    )
else:
    agg_daily = pd.DataFrame(columns=["price_date", "index_value"])


# ── Chart 1: Daily Index vs SSB Prints ────────────────────────────────────────

st.subheader("Daily Smoothed Index vs SSB Official")
fig1 = go.Figure()

if not agg_daily.empty:
    fig1.add_trace(
        go.Scatter(
            x=agg_daily["price_date"],
            y=agg_daily["index_value"],
            mode="lines",
            name="Daily Index (smoothed)",
            line=dict(color="#2563EB", width=2),
        )
    )

if not ssb_df.empty:
    fig1.add_trace(
        go.Scatter(
            x=ssb_df["reference_month"],
            y=ssb_df["mom_pct"],
            mode="markers",
            name="SSB Official MoM %",
            marker=dict(color="#DC2626", size=10, symbol="circle"),
            yaxis="y2",
        )
    )

fig1.update_layout(
    yaxis=dict(title="Index (base=100)"),
    yaxis2=dict(title="MoM % Change", overlaying="y", side="right", showgrid=False),
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    height=380,
    margin=dict(t=30, b=0),
)
st.plotly_chart(fig1, use_container_width=True)


# ── Chart 2: Nowcast with CI ──────────────────────────────────────────────────

st.subheader("Nowcast Prediction (current month)")
if nowcast:
    col1, col2, col3 = st.columns(3)
    col1.metric("Point Estimate", f"{nowcast['point_estimate']:+.2f}%", "MoM")
    col2.metric("95% CI Lower", f"{nowcast['ci_lower_95']:+.2f}%")
    col3.metric("95% CI Upper", f"{nowcast['ci_upper_95']:+.2f}%")

    fig2 = go.Figure()
    if not agg_daily.empty:
        fig2.add_trace(
            go.Scatter(
                x=agg_daily["price_date"],
                y=agg_daily["index_value"],
                mode="lines",
                name="Historical Index",
                line=dict(color="#2563EB"),
            )
        )

    target = pd.to_datetime(nowcast["target_month"])
    ssb_release = target + pd.DateOffset(days=10)
    fig2.add_trace(
        go.Scatter(
            x=[agg_daily["price_date"].max(), ssb_release, ssb_release],
            y=[
                agg_daily["index_value"].iloc[-1] if not agg_daily.empty else 100,
                nowcast["point_estimate"] + 100,
                nowcast["point_estimate"] + 100,
            ],
            mode="lines",
            name="Nowcast",
            line=dict(color="#7C3AED", dash="dash", width=2),
        )
    )
    fig2.add_vrect(
        x0=str(target),
        x1=str(ssb_release),
        fillcolor="#7C3AED",
        opacity=0.08,
        annotation_text=f"Prediction: {nowcast['point_estimate']:+.2f}%",
    )
    fig2.update_layout(height=340, margin=dict(t=20, b=0))
    st.plotly_chart(fig2, use_container_width=True)
else:
    st.info("No nowcast available yet. Run `python -m model.predict` after training the model.")


# ── Chart 3: COICOP Breakdown ─────────────────────────────────────────────────

st.subheader(f"COICOP Breakdown — {breakdown_date}")
if not breakdown_df.empty:
    breakdown_df = breakdown_df.sort_values("mom_pct", ascending=True)
    fig3 = go.Figure(
        go.Bar(
            x=breakdown_df["mom_pct"],
            y=breakdown_df["coicop_code"],
            orientation="h",
            marker_color=[
                "#DC2626" if v > 0 else "#16A34A" for v in breakdown_df["mom_pct"].fillna(0)
            ],
            text=breakdown_df["mom_pct"].apply(lambda v: f"{v:+.2f}%" if pd.notna(v) else "N/A"),
            textposition="outside",
        )
    )
    fig3.update_layout(
        xaxis_title="MoM % Change",
        height=max(250, len(breakdown_df) * 40),
        margin=dict(t=10, b=0),
    )
    st.plotly_chart(fig3, use_container_width=True)
else:
    st.info("No breakdown data for today. Run the scraper and indexer first.")

st.divider()
st.caption("Data: Kassal.app / Oda / Meny · Index weights: SSB Table 14700 (2026) · Model: XGBoost")
