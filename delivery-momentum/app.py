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

ACCENT, INK, MUTED, GRID = "#2a78d6", "#0b0b0b", "#52514e", "#e5e4e0"

st.markdown(
    """
    <style>
      .block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1200px; }
      div[data-testid="stDataFrame"] { font-variant-numeric: tabular-nums; }
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


@st.cache_data(ttl=1800, show_spinner=False)
def get_scans(panel: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {k: scan.build_scan(panel, w) for k, w in scan.WINDOWS.items()}


panel = get_panel()

if panel is None or panel.empty:
    st.title("📦 Delivery Momentum")
    st.error("**No data snapshot found.** Run `python refresh.py` in this folder "
             "to build `data/panel.csv.gz`, then commit it.")
    st.stop()

last_date = pd.Timestamp(panel["DATE"].max())
scans = get_scans(panel)

# ── Header + the only two controls ────────────────────────────────────────────
st.title("📦 Delivery Momentum")
st.caption(
    "Stocks where **delivery** (shares bought and kept, not day-traded) has stepped "
    f"up steadily against their own last {scan.BASELINE} trading days. "
    f"Data through **{last_date:%d %b %Y}**."
)

c1, c2 = st.columns([3, 2])
tf = c1.radio("Timeframe", list(scan.WINDOWS), index=1, horizontal=True,
              help="3D is the earliest but noisiest read; 1W–1M are more reliable.")
strength = c2.radio("Delivery surge", ["2× or more", "3× or more"], horizontal=True,
                    help="2× gives more ideas; 3× is a stricter, shorter list.")
min_surge = 2.0 if strength.startswith("2") else 3.0
window = scan.WINDOWS[tf]

res = scan.signals(scans[tf], window, min_surge)

# Which other timeframes flag the same stock — agreement across timeframes
# means the build-up isn't a one-window fluke.
also = {k: set(scan.signals(scans[k], w, min_surge)["SYMBOL"])
        for k, w in scan.WINDOWS.items()}
res["ALSO"] = res["SYMBOL"].map(
    lambda s: " ".join(k for k in scan.WINDOWS if k != tf and s in also[k]))
res["HOT"] = res["HOT_DAYS"].astype(int).astype(str) + f" / {window}"

first_d, last_d = scan.window_dates(panel, window)
st.markdown(f"**{len(res)} stocks** · window {first_d} → {last_d}")

if res.empty:
    st.info("Nothing qualifies right now. Try 2× or a longer timeframe.")
    st.stop()

# ── Table ─────────────────────────────────────────────────────────────────────
st.dataframe(
    res[["SYMBOL", "SURGE", "HOT", "ALSO", "DELIV_PCT", "BASE_DELIV_PCT",
         "MOVE_PCT", "CLOSE", "TURNOVER_CR"]],
    use_container_width=True,
    hide_index=True,
    height=min(560, 40 + 35 * len(res)),
    column_config={
        "SYMBOL": st.column_config.TextColumn("Stock"),
        "SURGE": st.column_config.NumberColumn(
            "Surge ×", format="%.1f×",
            help="Avg daily delivery in the window ÷ its normal level."),
        "HOT": st.column_config.TextColumn(
            "Hot days", help="Days in the window with delivery ≥ 1.5× normal. "
                             "More = steadier accumulation."),
        "ALSO": st.column_config.TextColumn(
            "Also on", help="Other timeframes where this stock also qualifies."),
        "DELIV_PCT": st.column_config.NumberColumn(
            "Deliv % now", format="%.0f%%",
            help="Delivered ÷ traded volume in the window."),
        "BASE_DELIV_PCT": st.column_config.NumberColumn(
            "Deliv % normal", format="%.0f%%"),
        "MOVE_PCT": st.column_config.NumberColumn(
            "Price move", format="%+.1f%%", help="Price change over the window."),
        "CLOSE": st.column_config.NumberColumn("Close ₹", format="%.2f"),
        "TURNOVER_CR": st.column_config.NumberColumn(
            "Avg turnover ₹cr/day", format="%.1f"),
    },
)

# ── One stock, day by day ─────────────────────────────────────────────────────
st.subheader("Check a stock")
pick = st.selectbox("Stock", res["SYMBOL"].tolist(), label_visibility="collapsed")

hist = panel[panel["SYMBOL"] == pick].sort_values("DATE")
dates = sorted(panel["DATE"].unique())
win_start = pd.Timestamp(dates[-window])
base_rate = hist[hist["DATE"] < win_start].tail(scan.BASELINE)["DELIV_QTY"].mean()
hist = hist.tail(window + 40)

fig = go.Figure()
fig.add_bar(
    x=hist["DATE"], y=hist["DELIV_QTY"], name="Delivered qty",
    marker=dict(color=[ACCENT if d >= win_start else "#9ec5f4" for d in hist["DATE"]]),
    hovertemplate="%{x|%d %b}<br>%{y:,.0f} shares delivered<extra></extra>",
)
fig.add_hline(y=base_rate, line_dash="dash", line_color=MUTED, line_width=1,
              annotation_text="normal", annotation_position="top left",
              annotation_font=dict(size=10, color=MUTED))
fig.add_hline(y=base_rate * scan.HOT_MULT, line_dash="dot", line_color=MUTED,
              line_width=1, annotation_text="hot (1.5×)",
              annotation_position="top left",
              annotation_font=dict(size=10, color=MUTED))
fig.add_scatter(
    x=hist["DATE"], y=hist["CLOSE_PRICE"], name="Close ₹", yaxis="y2",
    mode="lines", line=dict(color=INK, width=1.5),
    hovertemplate="%{x|%d %b}<br>₹%{y:,.2f}<extra></extra>",
)
fig.update_layout(
    height=360, margin=dict(l=10, r=10, t=10, b=10), bargap=0.3,
    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    showlegend=False,
    xaxis=dict(gridcolor=GRID, tickfont=dict(color=MUTED)),
    yaxis=dict(title="Delivered shares", gridcolor=GRID, tickfont=dict(color=MUTED)),
    yaxis2=dict(title="Close ₹", overlaying="y", side="right", showgrid=False,
                tickfont=dict(color=MUTED)),
)
st.plotly_chart(fig, use_container_width=True)
st.caption("Dark bars = the scan window. Black line = closing price (right axis).")

# ── Extras, tucked away ───────────────────────────────────────────────────────
sp = scan.spikes(scans[tf])
with st.expander(f"Block-deal spikes — surge above {scan.MAX_SURGE:.0f}× ({len(sp)})"):
    st.caption("Usually one large holder moving a stake in a single day. Historically "
               "these did *not* outperform — check the news before reading them as "
               "accumulation.")
    st.dataframe(
        sp[["SYMBOL", "SURGE", "HOT_DAYS", "MOVE_PCT", "CLOSE"]],
        hide_index=True, use_container_width=True,
        column_config={
            "SYMBOL": "Stock",
            "SURGE": st.column_config.NumberColumn("Surge ×", format="%.1f×"),
            "HOT_DAYS": st.column_config.NumberColumn("Hot days"),
            "MOVE_PCT": st.column_config.NumberColumn("Price move", format="%+.1f%%"),
            "CLOSE": st.column_config.NumberColumn("Close ₹", format="%.2f"),
        },
    )

with st.expander("How to use this"):
    st.markdown(
        f"""
**What it shows.** Stocks whose average daily *delivery* in the chosen window is at
least 2× (or 3×) their normal level — normal being the {scan.BASELINE} trading days
before the window — **and** that were "hot" (≥ 1.5× normal) on at least half of the
window's days. Steadiest stocks are listed first.

**Why these rules.** Backtested on one year of NSE data (Oct 2025 – Oct 2026),
looking at how stocks did over the next 20 trading days against the median stock:

- **2–5× surge** was the useful band. Under 2× is noise; over 5× the edge vanished
  (mostly block deals).
- **Steady beats spiky.** With a 2–5× surge, stocks hot on most window days beat the
  median by about 1–1.4% with a 54–55% hit rate. One-day spikes underperformed.
- **1W to 1M** carry the signal; **3D** is the earliest but noisiest read.
- Surge that coincides with a big price move over 2W–1M (already up 15%+) tended to
  keep going — delivery confirming the move, not just predicting it.

**A simple routine.**
1. Start on **1W**. Scan for stocks that also show **2W** or **1M** in *Also on* —
   the build-up has lasted.
2. Prefer a **Deliv % now** clearly above **Deliv % normal**, and a price that hasn't
   yet run far (catching it early).
3. Use **3D** to spot fresh starts, then check back in a few days to see whether they
   graduate to 1W.
4. Open the chart: steady dark bars above the dotted line are what you want; one tall
   bar is a block deal.

Filters always applied: EQ series only, price ≥ ₹{scan.MIN_PRICE:.0f}, average turnover ≥
₹{scan.MIN_TURNOVER_CR:.0f} cr/day, ETFs removed.

*The edges are small and noisy — use this as a research shortlist, not a buy list.
Source: NSE daily delivery bhavcopy. Not investment advice.*
        """
    )
