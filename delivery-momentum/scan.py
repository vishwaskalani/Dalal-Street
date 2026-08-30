"""
scan.py — Rank stocks by delivery activity behind a week's price move.

The question this answers: over the last week, which stocks moved more than X%
*and* had real money changing hands behind the move?

Raw delivered quantity on its own is a trap — 40 lakh shares of a ₹12 stock is
a smaller commitment than 50,000 shares of a ₹3,000 one. So the headline rank
is delivery **value** in ₹ crore (qty × the day's average price, summed over
the window). Raw quantity is still reported alongside for anyone who wants it.

Three numbers do the actual work:

  DELIV_VAL_CR   rupees that changed hands as delivery this week — conviction size
  DELIV_PCT      delivery as % of traded volume — position-taking vs intraday churn
  SURGE          this week's daily delivery ÷ the prior baseline's daily delivery
                 — the "something changed" signal. 1.0 is normal, 3.0 is a jump.
"""

from __future__ import annotations

import pandas as pd

# Series worth scanning. EQ is normal rolling settlement; BE is the
# trade-to-trade segment (100% delivery by construction, so it flatters
# DELIV_PCT — off by default for that reason).
DEFAULT_SERIES = ("EQ",)

RESULT_COLS = [
    "SYMBOL", "MOVE_PCT", "DELIV_VAL_CR", "DELIV_PCT", "SURGE",
    "DELIV_QTY", "TURNOVER_CR", "CLOSE", "PREV_CLOSE", "SERIES",
]


def _window_split(panel: pd.DataFrame, window: int, baseline: int):
    dates = sorted(panel["DATE"].unique())
    if len(dates) < window:
        raise ValueError(
            f"Need at least {window} trading days of data, panel has {len(dates)}."
        )
    win_dates = dates[-window:]
    base_dates = dates[-(window + baseline):-window] if baseline else []
    return win_dates, base_dates


def build_scan(
    panel: pd.DataFrame,
    window: int = 5,
    baseline: int = 20,
    min_move: float = 5.0,
    direction: str = "both",          # "up" | "down" | "both"
    min_turnover_cr: float = 5.0,
    min_price: float = 20.0,
    series: tuple[str, ...] = DEFAULT_SERIES,
) -> pd.DataFrame:
    """
    Aggregate `panel` over the last `window` trading days and return the
    stocks that cleared the move and liquidity filters, ranked by delivery
    value.

    `baseline` is how many trading days *before* the window are used as the
    "normal" delivery level for SURGE. Set 0 to skip it.
    """
    panel = panel[panel["SERIES"].isin(series)]
    win_dates, base_dates = _window_split(panel, window, baseline)

    win = panel[panel["DATE"].isin(win_dates)].copy()
    win["DELIV_VAL"] = win["DELIV_QTY"] * win["AVG_PRICE"]

    first, last = win_dates[0], win_dates[-1]

    agg = win.groupby("SYMBOL").agg(
        DELIV_QTY=("DELIV_QTY", "sum"),
        DELIV_VAL=("DELIV_VAL", "sum"),
        TRD_QTY=("TTL_TRD_QNTY", "sum"),
        TURNOVER_LACS=("TURNOVER_LACS", "sum"),
        DAYS=("DATE", "nunique"),
    )

    # Anchor the move on the previous close of the window's first day, so a
    # 5-day window measures a genuine 5-day move (not 4 days of change).
    start = (win[win["DATE"] == first].set_index("SYMBOL")["PREV_CLOSE"])
    end_rows = win[win["DATE"] == last].set_index("SYMBOL")
    agg["PREV_CLOSE"] = start
    agg["CLOSE"] = end_rows["CLOSE_PRICE"]
    agg["SERIES"] = end_rows["SERIES"]

    # Only stocks present on both ends — a mid-window listing or suspension
    # has no meaningful weekly move.
    agg = agg.dropna(subset=["PREV_CLOSE", "CLOSE"])
    agg = agg[agg["PREV_CLOSE"] > 0]

    agg["MOVE_PCT"] = (agg["CLOSE"] / agg["PREV_CLOSE"] - 1) * 100
    agg["DELIV_VAL_CR"] = agg["DELIV_VAL"] / 1e7
    agg["TURNOVER_CR"] = agg["TURNOVER_LACS"] / 100
    agg["DELIV_PCT"] = (agg["DELIV_QTY"] / agg["TRD_QTY"].replace(0, pd.NA)) * 100

    # SURGE — this week's delivery run-rate vs the prior baseline's.
    if len(base_dates):
        base = panel[panel["DATE"].isin(base_dates)]
        base_rate = base.groupby("SYMBOL")["DELIV_QTY"].sum() / len(base_dates)
        win_rate = agg["DELIV_QTY"] / agg["DAYS"].clip(lower=1)
        agg["SURGE"] = win_rate / base_rate.reindex(agg.index).replace(0, pd.NA)
    else:
        agg["SURGE"] = pd.NA

    # ── Filters ───────────────────────────────────────────────────────────────
    move = agg["MOVE_PCT"]
    if direction == "up":
        keep = move >= min_move
    elif direction == "down":
        keep = move <= -min_move
    else:
        keep = move.abs() >= min_move

    keep &= agg["TURNOVER_CR"] >= min_turnover_cr
    keep &= agg["CLOSE"] >= min_price
    keep &= agg["DELIV_QTY"] > 0

    out = agg[keep].reset_index()
    out = out.sort_values("DELIV_VAL_CR", ascending=False)
    return out[RESULT_COLS].reset_index(drop=True)


def window_dates(panel: pd.DataFrame, window: int = 5) -> tuple[str, str]:
    """Human-readable first/last trading date of the scan window."""
    dates = sorted(panel["DATE"].unique())[-window:]
    fmt = lambda d: pd.Timestamp(d).strftime("%d %b %Y")
    return fmt(dates[0]), fmt(dates[-1])
