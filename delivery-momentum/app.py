"""
app.py — Streamlit UI for the delivery-momentum scan.

Run locally:
    streamlit run app.py

Deploy free:
    Push to GitHub, then connect the repo at https://share.streamlit.io
    (main file path: delivery-momentum/app.py)

The app reads the snapshot in data/panel.csv.gz — it never calls NSE at page
load. refresh.py rebuilds that file on a schedule.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import nse_data
import scan

st.set_page_config(
    page_title="Delivery Momentum — NSE",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Sequential blue ramp (light→dark) for magnitude. Direction is carried by
# x-position and by the signed number in the table, so colour is free to encode
# something that isn't already on screen — here, the delivery surge.
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#2a78d6", "#1c5cab", "#104281"]
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e5e4e0"

st.markdown(
    """
    <style>
      .block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1400px; }
      [data-testid="stMetricValue"] { font-variant-numeric: tabular-nums;
          font-feature-settings: "tnum"; font-size: 1.55rem; }
      [data-testid="stMetricLabel"] { text-transform: uppercase; letter-spacing: .06em;
          font-size: .7rem; opacity: .7; }
      div[data-testid="stDataFrame"] { font-variant-numeric: tabular-nums; }
      .dm-tag { display:inline-block; font-size:.72rem; letter-spacing:.08em;
          text-transform:uppercase; color:#2a78d6; border:1px solid #2a78d633;
          background:#2a78d614; padding:2px 9px; border-radius:999px; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Optional password gate ────────────────────────────────────────────────────
# Streamlit Community Cloud apps are public by default. Set `app_password` in
# the app's Secrets to put a shared password in front of it; leave it unset and
# the app stays open.
def _secret(key: str):
    """
    Read a secret without tripping Streamlit's "No secrets found" error box.

    Touching st.secrets when no secrets.toml exists renders a red error to the
    page before it raises, which a family-facing app should never show. So
    check the standard locations first — Streamlit Cloud writes dashboard
    secrets to one of these too, and the gate works there unchanged.
    """
    from pathlib import Path

    paths = [Path.home() / ".streamlit" / "secrets.toml",
             Path(__file__).parent / ".streamlit" / "secrets.toml"]
    if not any(p.exists() for p in paths):
        return None
    try:
        return st.secrets[key]
    except Exception:
        return None


def _gate() -> bool:
    pw = _secret("app_password")
    if not pw:
        return True
    if st.session_state.get("dm_auth"):
        return True

    st.title("📦 Delivery Momentum")
    entered = st.text_input("Password", type="password")
    if entered:
        if entered == pw:
            st.session_state["dm_auth"] = True
            st.rerun()
        else:
            st.error("Wrong password.")
    return False


if not _gate():
    st.stop()


# ── Data ──────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=1800, show_spinner="Loading NSE delivery data …")
def get_panel() -> pd.DataFrame | None:
    return nse_data.load_panel()


panel = get_panel()

if panel is None or panel.empty:
    st.title("📦 Delivery Momentum")
    st.error(
        "**No data snapshot found.**\n\n"
        "Run `python refresh.py` in this folder to build `data/panel.csv.gz`, "
        "then commit it."
    )
    st.stop()

n_days = panel["DATE"].nunique()
last_date = pd.Timestamp(panel["DATE"].max())

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown('<span class="dm-tag">NSE Delivery Scan</span>', unsafe_allow_html=True)
st.title("📦 Delivery Momentum")
st.caption(
    "Stocks that moved sharply **and** had real delivery behind the move — "
    "shares that actually changed hands, not intraday churn. "
    f"Data through **{last_date:%d %b %Y}** ({n_days} trading days on file)."
)

# ── Controls ──────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns([1, 1, 1, 1])

with c1:
    window = st.selectbox(
        "Window", [5, 10, 15, 20],
        format_func=lambda d: {5: "1 week", 10: "2 weeks",
                               15: "3 weeks", 20: "1 month"}[d],
        index=0,
    )
with c2:
    min_move = st.slider("Min price move %", 0.0, 25.0, 5.0, 0.5)
with c3:
    direction = st.selectbox(
        "Direction", ["both", "up", "down"],
        format_func={"both": "Up or down", "up": "Gainers only",
                     "down": "Losers only"}.get,
    )
with c4:
    rank_by = st.selectbox(
        "Rank by",
        ["DELIV_VAL_CR", "SURGE", "DELIV_PCT", "DELIV_QTY", "MOVE_PCT"],
        format_func={
            "DELIV_VAL_CR": "Delivery value (₹ cr)",
            "SURGE": "Delivery surge (×)",
            "DELIV_PCT": "Delivery %",
            "DELIV_QTY": "Delivery quantity",
            "MOVE_PCT": "Price move %",
        }.get,
    )

with st.expander("Filters — liquidity, price, segment"):
    f1, f2, f3 = st.columns(3)
    min_turnover = f1.number_input("Min weekly turnover (₹ cr)", 0.0, 5000.0, 5.0, 5.0)
    min_price = f2.number_input("Min share price (₹)", 0.0, 5000.0, 20.0, 10.0)
    include_be = f3.checkbox(
        "Include BE (trade-to-trade) series", value=False,
        help="BE scrips settle at 100% delivery by rule, so their delivery % "
             "is not a conviction signal.",
    )
    st.caption(
        f"Baseline for surge: the {max(n_days - window, 0)} trading days before "
        "the window. Turnover and price filters strip out illiquid and penny scrips."
    )

max_baseline = max(n_days - window, 0)
series = ("EQ", "BE") if include_be else ("EQ",)

try:
    res = scan.build_scan(
        panel, window=window, baseline=max_baseline, min_move=min_move,
        direction=direction, min_turnover_cr=min_turnover,
        min_price=min_price, series=series,
    )
except ValueError as e:
    st.error(str(e))
    st.stop()

# Ranking "by price move" means biggest move of the kind you asked for: most
# negative when hunting losers, most positive otherwise.
ascending = rank_by == "MOVE_PCT" and direction == "down"
res = res.sort_values(rank_by, ascending=ascending,
                      na_position="last").reset_index(drop=True)

first_d, last_d = scan.window_dates(panel, window)

# ── Summary ───────────────────────────────────────────────────────────────────
st.markdown(f"**Window:** {first_d} → {last_d}")

if res.empty:
    st.warning("No stocks cleared these filters. Try lowering the minimum move.")
    st.stop()

m1, m2, m3, m4 = st.columns(4)
m1.metric("Stocks found", f"{len(res):,}")
m2.metric("Gainers / Losers",
          f"{(res['MOVE_PCT'] > 0).sum()} / {(res['MOVE_PCT'] < 0).sum()}")
m3.metric("Total delivery value", f"₹{res['DELIV_VAL_CR'].sum():,.0f} cr")
m4.metric("Median delivery %", f"{res['DELIV_PCT'].median():.1f}%")

st.divider()

# ── Table ─────────────────────────────────────────────────────────────────────
show_n = st.slider("Rows to show", 10, min(300, len(res)),
                   min(50, len(res)), 10) if len(res) > 10 else len(res)
view = res.head(show_n)

st.dataframe(
    view,
    use_container_width=True,
    hide_index=False,
    height=min(620, 60 + 35 * len(view)),
    column_config={
        "SYMBOL": st.column_config.TextColumn("Symbol", width="medium"),
        "MOVE_PCT": st.column_config.NumberColumn(
            "Move %", format="%+.2f%%",
            help="Close on the last day vs the close before the window started."),
        "DELIV_VAL_CR": st.column_config.NumberColumn(
            "Deliv ₹cr", format="%.0f",
            help="Rupee value of shares delivered during the window."),
        "DELIV_PCT": st.column_config.ProgressColumn(
            "Deliv %", format="%.1f%%", min_value=0, max_value=100,
            help="Delivered quantity as a share of total traded quantity."),
        "SURGE": st.column_config.NumberColumn(
            "Surge ×", format="%.2f",
            help="Daily delivery this window vs the prior baseline. "
                 "1.0 = normal. Blank = no baseline (recent listing)."),
        "DELIV_QTY": st.column_config.NumberColumn("Deliv qty", format="%d"),
        "TURNOVER_CR": st.column_config.NumberColumn("Turnover ₹cr", format="%.0f"),
        "CLOSE": st.column_config.NumberColumn("Close", format="%.2f"),
        "PREV_CLOSE": st.column_config.NumberColumn("Start", format="%.2f"),
        "SERIES": st.column_config.TextColumn("Ser", width="small"),
    },
)

st.download_button(
    "⬇️  Download this scan as CSV",
    res.to_csv(index=False).encode(),
    file_name=f"delivery_momentum_{last_date:%Y%m%d}_{window}d.csv",
    mime="text/csv",
)

# ── Scatter — move vs delivery value, coloured by surge ────────────────────────
st.subheader("Move vs delivery value")
st.caption(
    "Each dot is a stock. Right of centre gained, left of centre fell — so "
    "colour is free to show the **surge**: how far this window's delivery runs "
    "above the stock's own baseline. Dark dots are the unusual ones."
)

plot = view.copy()
plot["SURGE_C"] = pd.to_numeric(plot["SURGE"], errors="coerce").fillna(1.0).clip(0, 6)

fig = go.Figure(
    go.Scatter(
        x=plot["MOVE_PCT"],
        y=plot["DELIV_VAL_CR"],
        mode="markers",
        marker=dict(
            size=11,
            color=plot["SURGE_C"],
            colorscale=[[i / (len(SEQ) - 1), c] for i, c in enumerate(SEQ)],
            cmin=0, cmax=6,
            line=dict(width=2, color="#fcfcfb"),  # 2px surface ring on overlap
            colorbar=dict(
                title=dict(text="Surge ×", font=dict(size=11)),
                thickness=12, len=0.7, outlinewidth=0,
                tickfont=dict(size=10, color=MUTED),
            ),
        ),
        customdata=plot[["SYMBOL", "DELIV_PCT", "SURGE", "CLOSE"]].values,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Move %{x:+.2f}%<br>"
            "Delivery ₹%{y:,.0f} cr<br>"
            "Delivery %{customdata[1]:.1f}% of volume<br>"
            "Surge %{customdata[2]:.2f}×<br>"
            "Close ₹%{customdata[3]:,.2f}<extra></extra>"
        ),
    )
)

# Direct-label only the extremes — never a label on every point.
top_lab = pd.concat([
    plot.nlargest(5, "DELIV_VAL_CR"),
    plot.nlargest(3, "MOVE_PCT"),
    plot.nsmallest(3, "MOVE_PCT"),
]).drop_duplicates("SYMBOL")
for _, r in top_lab.iterrows():
    fig.add_annotation(
        x=r["MOVE_PCT"], y=r["DELIV_VAL_CR"], text=r["SYMBOL"],
        showarrow=False, yshift=14, font=dict(size=10, color=INK),
    )

fig.add_vline(x=0, line_width=1, line_color=GRID)
fig.update_layout(
    height=520,
    margin=dict(l=10, r=10, t=10, b=10),
    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(title="Price move over window (%)", gridcolor=GRID, zeroline=False,
               tickfont=dict(color=MUTED), ticksuffix="%"),
    yaxis=dict(title="Delivery value (₹ cr, log)", type="log", gridcolor=GRID,
               zeroline=False, tickfont=dict(color=MUTED)),
    hoverlabel=dict(bgcolor="#fcfcfb", bordercolor=GRID,
                    font=dict(color=INK, size=12)),
)
st.plotly_chart(fig, use_container_width=True)

# ── Drill-down ────────────────────────────────────────────────────────────────
st.subheader("Day-by-day detail")
pick = st.selectbox("Stock", view["SYMBOL"].tolist(), index=0)

hist = panel[panel["SYMBOL"] == pick].sort_values("DATE").tail(max(window * 3, 20)).copy()
hist["DELIV_VAL_CR"] = hist["DELIV_QTY"] * hist["AVG_PRICE"] / 1e7
hist["DELIV_PCT"] = hist["DELIV_QTY"] / hist["TTL_TRD_QNTY"].replace(0, pd.NA) * 100
win_start = pd.Timestamp(sorted(panel["DATE"].unique())[-window])

# Two measures, two charts — never a second y-axis.
d1, d2 = st.columns(2)

with d1:
    bar = go.Figure(
        go.Bar(
            x=hist["DATE"], y=hist["DELIV_VAL_CR"],
            marker=dict(color=SEQ[4], line=dict(width=0)),
            hovertemplate="%{x|%d %b}<br>₹%{y:,.1f} cr delivered<extra></extra>",
        )
    )
    bar.add_vline(x=win_start, line_width=1, line_dash="dot", line_color=MUTED)
    bar.update_layout(
        title=dict(text=f"{pick} — daily delivery value (₹ cr)",
                   font=dict(size=13, color=INK)),
        height=300, margin=dict(l=10, r=10, t=40, b=10), bargap=0.35,
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor=GRID, tickfont=dict(color=MUTED)),
        yaxis=dict(gridcolor=GRID, tickfont=dict(color=MUTED)),
        hoverlabel=dict(bgcolor="#fcfcfb", bordercolor=GRID, font=dict(color=INK)),
    )
    st.plotly_chart(bar, use_container_width=True)

with d2:
    line = go.Figure(
        go.Scatter(
            x=hist["DATE"], y=hist["CLOSE_PRICE"], mode="lines",
            line=dict(color=SEQ[5], width=2),
            hovertemplate="%{x|%d %b}<br>₹%{y:,.2f}<extra></extra>",
        )
    )
    line.add_vline(x=win_start, line_width=1, line_dash="dot", line_color=MUTED)
    line.update_layout(
        title=dict(text=f"{pick} — closing price (₹)",
                   font=dict(size=13, color=INK)),
        height=300, margin=dict(l=10, r=10, t=40, b=10),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor=GRID, tickfont=dict(color=MUTED)),
        yaxis=dict(gridcolor=GRID, tickfont=dict(color=MUTED)),
        hoverlabel=dict(bgcolor="#fcfcfb", bordercolor=GRID, font=dict(color=INK)),
    )
    st.plotly_chart(line, use_container_width=True)

st.caption("Dotted line marks where the scan window begins.")

with st.expander("What the numbers mean"):
    st.markdown(
        """
**Delivery quantity** is the slice of a day's traded volume that actually
settled into someone's demat account. The rest was intraday — bought and sold
the same day. A big price move on low delivery is usually traders passing stock
around; the same move on high delivery means someone took a position and kept it.

| Column | Meaning |
|---|---|
| **Move %** | Close on the last day of the window vs the close just before it started. |
| **Deliv ₹cr** | Rupee value delivered across the window. This is the default ranking — raw quantity flatters cheap stocks, since 40 lakh shares of a ₹12 stock is a smaller commitment than 50,000 shares of a ₹3,000 one. |
| **Deliv %** | Delivered ÷ total traded. Above ~60% is genuine accumulation; under ~25% is mostly churn. |
| **Surge ×** | This window's daily delivery against the stock's own earlier baseline. **1.0 is business as usual; 3× or more means something changed.** Blank for recent listings with no baseline. |
| **Turnover ₹cr** | Total traded value — a liquidity check, so thin scrips don't top the list on a single odd trade. |

A very high surge with very high delivery % is often a **block or bulk deal** —
one large holder moving a stake in a single print. Worth checking the news
before reading it as broad accumulation.

*Source: NSE Security-wise Price Volume & Deliverable Position (official daily
bhavcopy). Information only — not investment advice.*
        """
    )
