"""
scan.py — Find stocks whose delivery has stepped up against their own normal.

The question this answers: over the last 3 days / 1 week / 2 weeks / 1 month,
which stocks are seeing clearly more shares *delivered* (kept, not day-traded)
than they usually do — and is that a steady build-up or a one-day spike?

Two numbers do the work:

  SURGE      average daily delivery in the window ÷ average daily delivery over
             the BASELINE trading days before it. 1.0 = normal, 2.0 = double.
  HOT_DAYS   how many days in the window had delivery ≥ 1.5× the baseline.
             Steady accumulation shows up on most days; a block deal shows up
             on one.

Why these thresholds (backtest on ~1 year of NSE EQ data, Oct 2025–Oct 2026,
forward 20-day return vs the median stock):

  * Surge 2–5× is the useful band. Below 2× is noise; above 5× the edge
    disappears — those are mostly one-off block/bulk deals.
  * Steady beats spiky. With surge 2–5×, stocks hot on ≥ 2/3 of window days
    beat the median by ~+1.1–1.4% (median) with a 54–55% hit rate; stocks hot
    on < 1/3 of days *underperformed*.
  * 3-day windows are noisy; 1 week to 1 month carry the signal.

These are modest, noisy edges — a shortlist to research, not a buy list.
"""

from __future__ import annotations

import pandas as pd

WINDOWS = {"3D": 3, "1W": 5, "2W": 10, "1M": 20}
BASELINE = 50          # trading days of "normal" before the window
HOT_MULT = 1.5         # a day counts as hot at ≥ 1.5× baseline delivery
MIN_TURNOVER_CR = 1.0  # avg daily turnover over the baseline, ₹ crore
MIN_PRICE = 20.0
MAX_SURGE = 5.0        # above this it's usually a block deal

RESULT_COLS = [
    "SYMBOL", "SURGE", "HOT_DAYS", "DELIV_PCT", "BASE_DELIV_PCT",
    "MOVE_PCT", "CLOSE", "TURNOVER_CR",
]


def needed_days(window: int) -> int:
    return window + BASELINE


def build_scan(panel: pd.DataFrame, window: int, baseline: int = BASELINE) -> pd.DataFrame:
    """
    Every liquid EQ stock with its surge and hot-day count for the last
    `window` trading days. No surge filter — callers decide the cut-off.
    """
    panel = panel[panel["SERIES"] == "EQ"]
    dates = sorted(panel["DATE"].unique())
    if len(dates) < window + 10:
        raise ValueError(f"Need at least {window + 10} trading days, have {len(dates)}.")
    win_dates = dates[-window:]
    base_dates = dates[-(window + baseline):-window]

    dq = panel.pivot_table(index="DATE", columns="SYMBOL", values="DELIV_QTY",
                           aggfunc="last").fillna(0)
    tq = panel.pivot_table(index="DATE", columns="SYMBOL", values="TTL_TRD_QNTY",
                           aggfunc="last").fillna(0)
    to = panel.pivot_table(index="DATE", columns="SYMBOL", values="TURNOVER_LACS",
                           aggfunc="last").fillna(0)
    cl = panel.pivot_table(index="DATE", columns="SYMBOL", values="CLOSE_PRICE",
                           aggfunc="last")
    pc = panel.pivot_table(index="DATE", columns="SYMBOL", values="PREV_CLOSE",
                           aggfunc="last")

    w, b = dq.loc[win_dates], dq.loc[base_dates]
    base_rate = b.mean()
    out = pd.DataFrame({
        "SURGE": w.mean() / base_rate.where(base_rate > 0),
        "HOT_DAYS": w.ge(HOT_MULT * base_rate).sum(),
        "DELIV_PCT": w.sum() / tq.loc[win_dates].sum().where(lambda s: s > 0) * 100,
        "BASE_DELIV_PCT": b.sum() / tq.loc[base_dates].sum().where(lambda s: s > 0) * 100,
        "MOVE_PCT": (cl.loc[win_dates[-1]] / pc.loc[win_dates[0]] - 1) * 100,
        "CLOSE": cl.loc[win_dates[-1]],
        "TURNOVER_CR": to.loc[base_dates].mean() / 100,
    })
    # Recent listings have no real "normal" yet — need most baseline days traded.
    traded = to.loc[base_dates].gt(0).sum() >= 0.8 * len(base_dates)
    out = out[traded.reindex(out.index, fill_value=False)]
    out = out.dropna(subset=["SURGE", "CLOSE", "MOVE_PCT"])
    out = out[(out["TURNOVER_CR"] >= MIN_TURNOVER_CR) & (out["CLOSE"] >= MIN_PRICE)]
    out = out.rename_axis("SYMBOL").reset_index()
    return out[RESULT_COLS]


def signals(scan: pd.DataFrame, window: int, min_surge: float = 2.0) -> pd.DataFrame:
    """
    The shortlist: surge in [min_surge, MAX_SURGE] and hot on at least half
    the window's days, steadiest first.
    """
    min_hot = max(2, -(-window // 2))  # ceil(window / 2)
    s = scan[scan["SURGE"].between(min_surge, MAX_SURGE) & (scan["HOT_DAYS"] >= min_hot)]
    return s.sort_values(["HOT_DAYS", "SURGE"], ascending=False).reset_index(drop=True)


def spikes(scan: pd.DataFrame) -> pd.DataFrame:
    """Surge above MAX_SURGE — usually a block/bulk deal, shown separately."""
    return scan[scan["SURGE"] > MAX_SURGE].sort_values("SURGE", ascending=False)


def window_dates(panel: pd.DataFrame, window: int = 5) -> tuple[str, str]:
    """Human-readable first/last trading date of the scan window."""
    dates = sorted(panel["DATE"].unique())[-window:]
    fmt = lambda d: pd.Timestamp(d).strftime("%d %b %Y")
    return fmt(dates[0]), fmt(dates[-1])
