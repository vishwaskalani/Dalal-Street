"""
app.py — Streamlit UI for the custom index tracker.

Run locally:
    streamlit run app.py

Deploy:
    Push the folder to GitHub, then connect at https://share.streamlit.io
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from index_engine import (
    TIMEFRAMES,
    fetch_index,
    list_sectors,
    load_sector,
)

st.set_page_config(
    page_title="Custom Index Tracker",
    page_icon="📈",
    layout="wide",
)

st.title("📈 Custom Index Tracker")
st.caption("Market-cap weighted indices built from your own sector files.")

# ── Load sectors ───────────────────────────────────────────────────────────────
sector_paths = list_sectors()
if not sector_paths:
    st.warning(
        "No sector files found in `sectors/`. Add a `.txt` file with the "
        "sector name on line 1 and one NSE symbol per line below it."
    )
    st.stop()

sectors = {load_sector(p)[0]: p for p in sector_paths}

# ── Controls ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Settings")
    selected_name = st.selectbox("Index", list(sectors.keys()))
    selected_tf   = st.radio(
        "Timeframe",
        TIMEFRAMES,
        index=TIMEFRAMES.index("1y"),
        horizontal=False,
    )
    st.markdown("---")
    st.caption(
        "Edit / add files in `sectors/` to change the indices. "
        "First line = sector name, then one NSE symbol per line."
    )

sector_name, tickers = load_sector(sectors[selected_name])

# ── Compute (cached) ───────────────────────────────────────────────────────────
@st.cache_data(ttl=900, show_spinner="Fetching prices & shares from yfinance…")
def _get_index(tickers_t: tuple[str, ...], tf: str):
    return fetch_index(list(tickers_t), tf)


index_series, constituents, excluded = _get_index(tuple(tickers), selected_tf)

if index_series.empty:
    st.error(
        "Could not build the index — no usable data for any constituent. "
        "Check the ticker symbols in the sector file."
    )
    st.stop()

# ── Header metrics ─────────────────────────────────────────────────────────────
current   = float(index_series.iloc[-1])
start_val = float(index_series.iloc[0])
ret_pct   = current - start_val   # because start_val == 100

col1, col2, col3, col4 = st.columns(4)
col1.metric("Sector", sector_name)
col2.metric("Current value", f"{current:,.2f}", f"{ret_pct:+.2f}%")
col3.metric("Timeframe", selected_tf.upper())
col4.metric("Constituents", len(constituents))

if excluded:
    st.info(
        "Excluded (no data for the selected window): " + ", ".join(excluded)
    )

# ── Chart ──────────────────────────────────────────────────────────────────────
line_color = "#16a34a" if ret_pct >= 0 else "#dc2626"
fill_color = "rgba(22, 163, 74, 0.10)" if ret_pct >= 0 else "rgba(220, 38, 38, 0.10)"

fig = go.Figure()
fig.add_trace(
    go.Scatter(
        x=index_series.index,
        y=index_series.values,
        mode="lines",
        name=sector_name,
        line=dict(color=line_color, width=2.2),
        fill="tozeroy",
        fillcolor=fill_color,
        hovertemplate="<b>%{x|%d %b %Y}</b><br>Index: %{y:,.2f}<extra></extra>",
    )
)
fig.add_hline(y=100, line_dash="dot", line_color="#9ca3af", opacity=0.6)
fig.update_layout(
    height=480,
    yaxis_title="Index value (base = 100)",
    xaxis_title=None,
    template="plotly_white",
    margin=dict(l=10, r=10, t=20, b=10),
    showlegend=False,
)
fig.update_yaxes(rangemode="tozero" if ret_pct < 0 else "normal")

st.plotly_chart(fig, use_container_width=True)

# ── Constituents table ─────────────────────────────────────────────────────────
st.subheader("Constituents")

table = (
    pd.DataFrame(
        [
            {
                "Ticker":           sym,
                "Price (₹)":        round(d["price"], 2),
                "Market Cap (Cr)":  round(d["mcap_cr"], 0),
                "Weight (%)":       round(d["weight_pct"], 2),
            }
            for sym, d in constituents.items()
        ]
    )
    .sort_values("Weight (%)", ascending=False)
    .reset_index(drop=True)
)
st.dataframe(table, use_container_width=True, hide_index=True)
