#!/usr/bin/env python3
"""
top_performers.py — Top 25 best performing NSE stocks for a given timeframe.

Usage:
    python Performers/top_performers.py <timeframe>

Timeframes: 1d  1w  2w  1m  3m  6m  1y  3y  5y  10y  15y
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

# ── Global configuration (adjust manually as needed) ───────────────────────────
MIN_MARKET_CAP_CR = 5_000   # minimum market cap in crores
TOP_N             = 25      # number of top performers to return
MCAP_BATCH        = 100     # market-cap candidates checked per batch
MCAP_WORKERS      = 20      # parallel threads for market-cap fetches
# ──────────────────────────────────────────────────────────────────────────────

EQUITY_CSV = Path(__file__).parent.parent / "EQUITY_L.csv"

VALID_TIMEFRAMES = ["1d", "1w", "2w", "1m", "3m", "6m", "1y", "3y", "5y", "10y", "15y"]

# For long timeframes use coarser intervals to keep download size reasonable
_INTERVAL: dict[str, str] = {
    "1d":  "1d",
    "1w":  "1d",
    "2w":  "1d",
    "1m":  "1d",
    "3m":  "1d",
    "6m":  "1d",
    "1y":  "1d",
    "3y":  "1wk",
    "5y":  "1wk",
    "10y": "1mo",
    "15y": "1mo",
}

# Extra days added to start so weekends / holidays don't eat into the window
_START_BUFFER: dict[str, timedelta] = {
    "1d":  timedelta(days=7),    # need at least 2 trading points
    "1w":  timedelta(days=7),
    "2w":  timedelta(days=7),
    "1m":  timedelta(days=7),
    "3m":  timedelta(days=7),
    "6m":  timedelta(days=7),
    "1y":  timedelta(days=7),
    "3y":  timedelta(days=14),
    "5y":  timedelta(days=14),
    "10y": timedelta(days=30),
    "15y": timedelta(days=30),
}

_TARGET_DELTA: dict[str, timedelta] = {
    "1d":  timedelta(days=1),
    "1w":  timedelta(weeks=1),
    "2w":  timedelta(weeks=2),
    "1m":  timedelta(days=30),
    "3m":  timedelta(days=91),
    "6m":  timedelta(days=182),
    "1y":  timedelta(days=365),
    "3y":  timedelta(days=365 * 3),
    "5y":  timedelta(days=365 * 5),
    "10y": timedelta(days=365 * 10),
    "15y": timedelta(days=365 * 15),
}

# Max gap allowed between target_start and a stock's first available price.
# Stocks listed later than this are excluded (their return would not be a true
# X-year return). Only applied for tf >= 3m.
_LISTING_TOLERANCE: dict[str, timedelta] = {
    "3m":  timedelta(days=7),
    "6m":  timedelta(days=14),
    "1y":  timedelta(days=21),
    "3y":  timedelta(days=30),
    "5y":  timedelta(days=60),
    "10y": timedelta(days=120),
    "15y": timedelta(days=180),
}


def download_start(tf: str) -> date:
    today = date.today()
    return today - _TARGET_DELTA[tf] - _START_BUFFER[tf]


def load_tickers() -> list[str]:
    df = pd.read_csv(EQUITY_CSV)
    df.columns = df.columns.str.strip()
    eq = df[df["SERIES"].str.strip() == "EQ"]["SYMBOL"].str.strip()
    return [f"{s}.NS" for s in eq.tolist()]


def filter_by_listing(close: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Drop tickers whose first available price is too far after target_start."""
    if tf not in _LISTING_TOLERANCE:
        return close

    target_start = pd.Timestamp(date.today()) - pd.Timedelta(_TARGET_DELTA[tf])
    cutoff       = target_start + pd.Timedelta(_LISTING_TOLERANCE[tf])

    keep = []
    for col in close.columns:
        fv = close[col].first_valid_index()
        if fv is not None and fv <= cutoff:
            keep.append(col)
    return close[keep]


def bulk_returns(tickers: list[str], tf: str) -> pd.Series:
    start    = download_start(tf)
    end      = date.today() + timedelta(days=1)   # yfinance `end` is exclusive
    interval = _INTERVAL[tf]

    print(f"[*] Downloading {len(tickers)} tickers | interval={interval} | {start} → {end}")

    raw = yf.download(
        tickers,
        start=start.isoformat(),
        end=end.isoformat(),
        interval=interval,
        auto_adjust=True,
        progress=True,
        threads=True,
    )

    if raw.empty:
        return pd.Series(dtype=float)

    # MultiIndex when >1 ticker; flat when exactly 1
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]

    before = close.shape[1]
    close  = filter_by_listing(close, tf)
    after  = close.shape[1]
    if tf in _LISTING_TOLERANCE:
        print(f"[*] Listing-date filter: kept {after} / {before} tickers with prices near window start")

    if close.empty:
        return pd.Series(dtype=float)

    if tf == "1d":
        clean = close.ffill().dropna(how="all")
        if len(clean) < 2:
            print(
                "[ERROR] Not enough trading data for 1d "
                "(try again on a trading day after market open).",
                file=sys.stderr,
            )
            return pd.Series(dtype=float)
        first = clean.iloc[-2]
        last  = clean.iloc[-1]
    else:
        first = close.bfill().iloc[0]
        last  = close.ffill().iloc[-1]

    ret = (last - first) / first * 100
    return ret.dropna().sort_values(ascending=False)


def get_mcap_cr(ticker: str) -> float | None:
    try:
        mcap = yf.Ticker(ticker).fast_info.market_cap
        if not mcap:
            return None
        return round(mcap / 1e7, 2)   # INR → crores  (1 Cr = 10M)
    except Exception:
        return None


def fetch_mcap_batch(tickers: list[str], label: str) -> dict[str, float]:
    """Parallel-fetch market cap for a batch of tickers; return only successes."""
    out: dict[str, float] = {}
    with ThreadPoolExecutor(max_workers=MCAP_WORKERS) as pool:
        futs = {pool.submit(get_mcap_cr, t): t for t in tickers}
        done = 0
        for fut in as_completed(futs):
            done += 1
            t   = futs[fut]
            val = fut.result()
            if val is not None:
                out[t] = val
            tag = f"{val:>12,.0f} Cr" if val else f"{'N/A':>15}"
            print(f"  [{label} {done:>3}/{len(tickers)}] {t:<22}  mcap={tag}", flush=True)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Top 25 best performing NSE stocks for a given timeframe",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Timeframes: 1d  1w  2w  1m  3m  6m  1y  3y  5y  10y  15y",
    )
    parser.add_argument("timeframe", choices=VALID_TIMEFRAMES, metavar="timeframe")
    args = parser.parse_args()
    tf = args.timeframe

    print(f"\n[*] Timeframe : {tf}")
    print(f"[*] Min MCap  : {MIN_MARKET_CAP_CR:,} Cr")

    tickers = load_tickers()
    print(f"[*] Universe  : {len(tickers)} NSE EQ stocks\n")

    returns = bulk_returns(tickers, tf)
    if returns.empty:
        print("[ERROR] No return data available.", file=sys.stderr)
        sys.exit(1)

    print(f"\n[*] Got return data for {len(returns)} stocks (post listing filter)")

    # Adaptive pool: keep scanning batches by descending return until TOP_N qualify
    candidates_all = returns.index.tolist()
    qualifying: list[dict] = []
    cursor    = 0
    batch_num = 0

    while len(qualifying) < TOP_N and cursor < len(candidates_all):
        batch_num += 1
        batch  = candidates_all[cursor : cursor + MCAP_BATCH]
        rng    = f"{cursor + 1}-{cursor + len(batch)}"
        cursor += len(batch)

        print(f"\n[*] Batch {batch_num} — candidates {rng}  (have {len(qualifying)}/{TOP_N})")
        mcaps = fetch_mcap_batch(batch, f"b{batch_num}")

        for ticker in batch:                          # batch is in return-desc order
            if len(qualifying) >= TOP_N:
                break
            mcap = mcaps.get(ticker)
            if mcap is None or mcap < MIN_MARKET_CAP_CR:
                continue
            qualifying.append({
                "ticker":        ticker.removesuffix(".NS"),
                "return_pct":    round(float(returns[ticker]), 2),
                "market_cap_cr": mcap,
            })

    # ── Print results ──────────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print(f"  TOP {TOP_N} PERFORMERS  |  {tf.upper()}  |  Min MCap: {MIN_MARKET_CAP_CR:,} Cr")
    print("=" * 70)
    print(f"  {'#':<4}  {'Ticker':<18}  {'Return %':>10}  {'Market Cap (Cr)':>16}")
    print(f"  {'-' * 62}")
    for rank, s in enumerate(qualifying, 1):
        print(
            f"  {rank:<4}  {s['ticker']:<18}  "
            f"{s['return_pct']:>9.2f}%  "
            f"{s['market_cap_cr']:>14,.0f}"
        )
    print("=" * 70)

    if len(qualifying) < TOP_N:
        print(
            f"\n[!] Only {len(qualifying)} / {TOP_N} stocks passed the MCap filter "
            f"after scanning all {len(candidates_all)} candidates. "
            f"Consider lowering MIN_MARKET_CAP_CR (currently {MIN_MARKET_CAP_CR:,} Cr)."
        )


if __name__ == "__main__":
    main()
