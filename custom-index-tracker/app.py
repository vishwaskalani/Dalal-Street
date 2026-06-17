"""
app.py — Streamlit UI for the niche index tracker.

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
    fetch_prices,
    list_sectors,
    load_sector,
)

UP, DOWN, GRID = "#16a34a", "#dc2626", "#9ca3af"

st.set_page_config(
    page_title="Niche Index Tracker",
    page_icon="📊",
    layout="wide",
)

# ── Styling — clean, dense, terminal-ish for technical users ───────────────────
st.markdown(
    """
    <style>
      .block-container { padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1300px; }
      [data-testid="stMetricValue"] { font-variant-numeric: tabular-nums;
          font-feature-settings: "tnum"; }
      [data-testid="stMetricLabel"] { text-transform: uppercase; letter-spacing: .06em;
          font-size: .72rem; opacity: .7; }
      div[data-testid="stDataFrame"] { font-variant-numeric: tabular-nums; }
      .nit-tag { display:inline-block; font-size:.72rem; letter-spacing:.08em;
          text-transform:uppercase; color:#16a34a; border:1px solid #16a34a33;
          background:#16a34a14; padding:2px 9px; border-radius:999px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown('<span class="nit-tag">Niche Index Tracker</span>', unsafe_allow_html=True)
st.title("📊 Niche Index Tracker")
st.caption(
    "Custom **FairBlend-weighted** indices for under-the-radar NSE themes — "
    "auto ancillaries, pumps, refractories, capital markets, ports, wind, solar & more. "
    "Total-return (split/dividend-adjusted), rebased to 100 at the start of each window."
)

with st.expander("ℹ️  How weighting works — FairBlend (50 / 50)"):
    st.markdown(
        """
**The problem with pure market-cap weighting.** In a niche basket one giant
can swallow the index — e.g. a Ports index that is ~86% Adani Ports really just
tracks Adani Ports, and the smaller names you actually wanted exposure to become
invisible.

**FairBlend.** Each constituent's weight is a 50/50 blend of *equal* weight and
*market-cap* weight:

$$w_i \\;=\\; 0.5 \\cdot \\underbrace{\\tfrac{1}{N}}_{\\text{equal}} \\;+\\; 0.5 \\cdot \\underbrace{\\tfrac{\\text{mcap}_i}{\\sum_j \\text{mcap}_j}}_{\\text{market cap}}$$

- **Equal half** gives every company in the niche a real, comparable voice.
- **Market-cap half** keeps economic size honest, so a ₹2,000 Cr minnow doesn't
  move the index as much as a ₹1 L Cr leader.

Weights sum to 100%, so the index always starts at 100. The index value is then
the blended-weight sum of each stock's total return:
$\\;\\text{index}(t) = 100 \\cdot \\sum_i w_i \\cdot p_i(t)/p_i(t_0)$.
The table below shows each name's **Equal**, **Cap**, and final **Blend** weight
so you can see exactly how the mix lands.
        """
    )

# ── Load sectors ───────────────────────────────────────────────────────────────
sector_paths = list_sectors()
if not sector_paths:
    st.warning(
        "No sector files found in `sectors/`. Add a `.txt` file with the "
        "index name on line 1 and one NSE symbol per line below it."
    )
    st.stop()

sectors = {load_sector(p)[0]: p for p in sector_paths}

# ── Controls ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Settings")
    selected_name = st.selectbox("Index", list(sectors.keys()))
    selected_tf = st.radio(
        "Timeframe",
        TIMEFRAMES,
        index=TIMEFRAMES.index("1y"),
        horizontal=False,
    )
    st.markdown("---")
    st.caption(
        "Each index is defined by a file in `sectors/` — first line is the "
        "index name, then one NSE symbol per line. Data via yfinance, cached "
        "for 15 min."
    )

sector_name, tickers = load_sector(sectors[selected_name])

# ── Compute (cached) ───────────────────────────────────────────────────────────
@st.cache_data(ttl=900, show_spinner="Fetching prices & shares from yfinance…")
def _get_index(tickers_t: tuple[str, ...], tf: str):
    return fetch_index(list(tickers_t), tf)


@st.cache_data(ttl=900, show_spinner=False)
def _get_prices(ticker: str, tf: str) -> pd.Series:
    return fetch_prices(ticker, tf)


index_series, constituents, excluded = _get_index(tuple(tickers), selected_tf)

if index_series.empty:
    st.error(
        "Could not build the index — no usable data for any constituent. "
        "Check the ticker symbols in the sector file."
    )
    st.stop()

# ── Header metrics ─────────────────────────────────────────────────────────────
current = float(index_series.iloc[-1])
ret_pct = current - float(index_series.iloc[0])  # start == 100

col1, col2, col3, col4 = st.columns(4)
col1.metric("Index", sector_name)
col2.metric("Value", f"{current:,.2f}", f"{ret_pct:+.2f}%")
col3.metric("Window", selected_tf.upper())
col4.metric("Constituents", len(constituents))

if excluded:
    st.info("Excluded (no data for this window): " + ", ".join(excluded))

# ── Index chart ────────────────────────────────────────────────────────────────
line_color = UP if ret_pct >= 0 else DOWN
fill_color = "rgba(22,163,74,0.10)" if ret_pct >= 0 else "rgba(220,38,38,0.10)"

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
fig.add_hline(y=100, line_dash="dot", line_color=GRID, opacity=0.6)
fig.update_layout(
    height=460,
    yaxis_title="Index value (base = 100)",
    xaxis_title=None,
    template="plotly_white",
    margin=dict(l=10, r=10, t=20, b=10),
    showlegend=False,
)
fig.update_yaxes(rangemode="tozero" if ret_pct < 0 else "normal")
st.plotly_chart(fig, use_container_width=True)

# ── Constituents table (click a row to inspect) ────────────────────────────────
st.subheader("Constituents")
st.caption("Select a row to chart an individual constituent and compare it to the index.")

table = (
    pd.DataFrame(
        [
            {
                "Ticker": sym,
                "Price (₹)": round(d["price"], 2),
                "Market Cap (Cr)": round(d["mcap_cr"], 0),
                "Equal (%)": round(d["eq_wt"], 2),
                "Cap (%)": round(d["cap_wt"], 2),
                "Blend (%)": round(d["weight_pct"], 2),
            }
            for sym, d in constituents.items()
        ]
    )
    .sort_values("Blend (%)", ascending=False)
    .reset_index(drop=True)
)

event = st.dataframe(
    table,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "Ticker": st.column_config.TextColumn(width="small"),
        "Price (₹)": st.column_config.NumberColumn(format="₹ %.2f"),
        "Market Cap (Cr)": st.column_config.NumberColumn(format="%.0f"),
        "Equal (%)": st.column_config.NumberColumn(format="%.2f%%", help="1 / N — every name equal"),
        "Cap (%)": st.column_config.NumberColumn(format="%.2f%%", help="Pure market-cap share"),
        "Blend (%)": st.column_config.ProgressColumn(
            format="%.2f%%",
            help="FairBlend weight = 50% Equal + 50% Cap",
            min_value=0.0,
            max_value=float(table["Blend (%)"].max()),
        ),
    },
)

# ── Constituent detail ─────────────────────────────────────────────────────────
selected_rows = event.selection.rows if event and event.selection else []
if selected_rows:
    row = table.iloc[selected_rows[0]]
    sym = row["Ticker"]
    meta = constituents[sym]

    st.markdown("---")
    st.subheader(f"🔍 {sym}")

    prices = _get_prices(sym, selected_tf)
    if prices.empty:
        st.warning(f"No price history available for {sym} in this window.")
    else:
        c_ret = (float(prices.iloc[-1]) / float(prices.iloc[0]) - 1.0) * 100.0
        rel = c_ret - ret_pct  # constituent return minus index return

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Price", f"₹ {meta['price']:,.2f}")
        m2.metric(f"Return ({selected_tf.upper()})", f"{c_ret:+.2f}%")
        m3.metric("vs Index", f"{rel:+.2f}%")
        m4.metric("FairBlend weight", f"{meta['weight_pct']:.2f}%")

        # Rebase both to 100 to compare relative performance over the window.
        c_rebased = prices / float(prices.iloc[0]) * 100.0
        c_color = UP if c_ret >= 0 else DOWN

        cfig = go.Figure()
        cfig.add_trace(
            go.Scatter(
                x=index_series.index,
                y=index_series.values,
                mode="lines",
                name=f"{sector_name} index",
                line=dict(color=GRID, width=1.6, dash="dot"),
                hovertemplate="Index: %{y:,.2f}<extra></extra>",
            )
        )
        cfig.add_trace(
            go.Scatter(
                x=c_rebased.index,
                y=c_rebased.values,
                mode="lines",
                name=sym,
                line=dict(color=c_color, width=2.2),
                hovertemplate=f"<b>%{{x|%d %b %Y}}</b><br>{sym}: %{{y:,.2f}}<extra></extra>",
            )
        )
        cfig.add_hline(y=100, line_dash="dot", line_color=GRID, opacity=0.4)
        cfig.update_layout(
            height=420,
            yaxis_title="Rebased to 100 at window start",
            xaxis_title=None,
            template="plotly_white",
            margin=dict(l=10, r=10, t=20, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0),
        )
        st.plotly_chart(cfig, use_container_width=True)
        st.caption(
            f"{sym} rebased to 100 vs the {sector_name} index over {selected_tf.upper()} — "
            "lets you see whether the name led or lagged its niche."
        )
