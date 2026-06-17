"""
index_engine.py — Build a market-cap weighted index from a sector file.

A sector file is a plain .txt with the sector name on the first line and
one NSE symbol per line afterwards, e.g.

    Banking
    HDFCBANK
    ICICIBANK
    ...

The index value at time t is:
    index(t) = 100 * Σᵢ (shares_i × price_i(t)) / Σᵢ (shares_i × price_i(t₀))

`shares_i` is the current shares-outstanding (one yfinance call per ticker,
cached upstream). `price_i(t)` is split- and dividend-adjusted (auto_adjust),
so the series is effectively a total-return index.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import yfinance as yf

SECTORS_DIR = Path(__file__).parent / "sectors"

# Period/interval combos that yfinance accepts directly. For "3y" we pull 5y
# and trim, because yfinance does not accept a literal "3y" period.
TF_CONFIG: dict[str, dict] = {
    "1d":  {"period": "2d",   "interval": "5m"},
    "1w":  {"period": "5d",   "interval": "30m"},
    "1m":  {"period": "1mo",  "interval": "1d"},
    "3m":  {"period": "3mo",  "interval": "1d"},
    "6m":  {"period": "6mo",  "interval": "1d"},
    "1y":  {"period": "1y",   "interval": "1d"},
    "3y":  {"period": "5y",   "interval": "1wk", "trim_years": 3},
    "5y":  {"period": "5y",   "interval": "1wk"},
    "10y": {"period": "10y",  "interval": "1mo"},
    "max": {"period": "max",  "interval": "1mo"},
}

TIMEFRAMES = list(TF_CONFIG.keys())


# ── Sector files ──────────────────────────────────────────────────────────────

def list_sectors() -> list[Path]:
    if not SECTORS_DIR.exists():
        return []
    return sorted(SECTORS_DIR.glob("*.txt"))


def load_sector(path: Path) -> tuple[str, list[str]]:
    """Return (sector_name, [tickers]). First non-empty line = name."""
    lines = [ln.strip() for ln in path.read_text().splitlines() if ln.strip()]
    if not lines:
        return path.stem, []
    return lines[0], [t.upper() for t in lines[1:]]


# ── Market data ───────────────────────────────────────────────────────────────

def _get_shares(yf_ticker: str) -> float | None:
    """Current shares outstanding. Tries fast_info.shares, falls back to
    market_cap / last_price."""
    try:
        fi = yf.Ticker(yf_ticker).fast_info
        for attr in ("shares", "shares_outstanding"):
            val = getattr(fi, attr, None)
            if val:
                return float(val)
        mcap, price = fi.market_cap, fi.last_price
        if mcap and price:
            return float(mcap) / float(price)
    except Exception:
        return None
    return None


def _fetch_shares_parallel(yf_tickers: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    with ThreadPoolExecutor(max_workers=10) as pool:
        for yt, val in zip(yf_tickers, pool.map(_get_shares, yf_tickers)):
            if val is not None:
                out[yt] = val
    return out


def fetch_prices(ticker: str, timeframe: str) -> pd.Series:
    """Split/dividend-adjusted close series for a single NSE ticker over the
    timeframe. Returns an empty Series if nothing is available."""
    cfg = TF_CONFIG[timeframe]
    raw = yf.download(
        f"{ticker}.NS",
        period=cfg["period"],
        interval=cfg["interval"],
        auto_adjust=True,
        progress=False,
    )
    if raw.empty:
        return pd.Series(dtype=float)

    close = raw["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    if "trim_years" in cfg and not close.empty:
        cutoff = pd.Timestamp.now(tz=close.index.tz) - pd.DateOffset(years=cfg["trim_years"])
        close = close[close.index >= cutoff]

    return close.dropna()


def fetch_index(
    tickers: list[str],
    timeframe: str,
) -> tuple[pd.Series, dict[str, dict], list[str]]:
    """
    Compute the market-cap weighted index over `timeframe`.

    Returns:
        index_series : pd.Series indexed by datetime, rebased to 100 at start
        constituents : dict[ticker] -> {price, mcap_cr, weight_pct}
        excluded     : list of tickers that had no usable data
    """
    cfg = TF_CONFIG[timeframe]
    yf_tickers = [f"{t}.NS" for t in tickers]

    # 1. Bulk price download ----------------------------------------------------
    raw = yf.download(
        yf_tickers,
        period=cfg["period"],
        interval=cfg["interval"],
        auto_adjust=True,
        progress=False,
        threads=True,
        group_by="column",
    )
    if raw.empty:
        return pd.Series(dtype=float), {}, list(tickers)

    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    if not isinstance(raw.columns, pd.MultiIndex):
        close.columns = yf_tickers[:1]

    # 2. Optional time-trim (3y) -----------------------------------------------
    if "trim_years" in cfg and not close.empty:
        cutoff = pd.Timestamp.now(tz=close.index.tz) - pd.DateOffset(years=cfg["trim_years"])
        close = close[close.index >= cutoff]

    # 3. Drop tickers with no data anywhere in the window ----------------------
    close = close.dropna(axis=1, how="all")
    available = list(close.columns)
    excluded  = [yt.removesuffix(".NS") for yt in yf_tickers if yt not in available]

    if not available:
        return pd.Series(dtype=float), {}, list(tickers)

    # 4. Current shares outstanding -------------------------------------------
    shares = _fetch_shares_parallel(available)
    available = [yt for yt in available if yt in shares]
    excluded += [yt.removesuffix(".NS") for yt in close.columns if yt not in shares]

    if not available:
        return pd.Series(dtype=float), {}, list(tickers)

    close = close[available].ffill().bfill()

    # 5. Build market-cap series and rebase ------------------------------------
    mcap = pd.DataFrame({yt: close[yt] * shares[yt] for yt in available})
    total = mcap.sum(axis=1).dropna()
    if total.empty or total.iloc[0] == 0:
        return pd.Series(dtype=float), {}, list(tickers)

    index_series = (total / total.iloc[0]) * 100.0
    index_series.name = "index"

    # 6. Constituent table (latest snapshot) -----------------------------------
    latest_prices = close.iloc[-1]
    latest_mcaps  = pd.Series({yt: latest_prices[yt] * shares[yt] for yt in available})
    total_mcap_now = latest_mcaps.sum()

    constituents: dict[str, dict] = {}
    for yt in available:
        sym = yt.removesuffix(".NS")
        constituents[sym] = {
            "price":      float(latest_prices[yt]),
            "mcap_cr":    float(latest_mcaps[yt]) / 1e7,
            "weight_pct": float(latest_mcaps[yt]) / float(total_mcap_now) * 100.0,
        }

    return index_series, constituents, sorted(set(excluded))
