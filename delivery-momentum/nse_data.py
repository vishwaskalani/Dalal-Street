"""
nse_data.py — Fetch NSE "Security-wise Price Volume & Deliverable Position" data.

NSE publishes one CSV per trading day at

    https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_DDMMYYYY.csv

with these columns (leading spaces in the header are stripped on load):

    SYMBOL SERIES DATE1 PREV_CLOSE OPEN_PRICE HIGH_PRICE LOW_PRICE LAST_PRICE
    CLOSE_PRICE AVG_PRICE TTL_TRD_QNTY TURNOVER_LACS NO_OF_TRADES
    DELIV_QTY DELIV_PER

DELIV_QTY is the part of the day's volume that actually moved between demat
accounts — i.e. real ownership change, not intraday churn. That is the whole
point of this tool: high delivery behind a price move means someone took a
position, not that jobbers passed stock around.

Missing dates (weekends, holidays, not-yet-published) 404 and are skipped, so
callers walk back over calendar days until they have enough trading days.
"""

from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

ARCHIVE = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv"

# nsearchives serves these static files to a plain browser-shaped request.
# (www.nseindia.com itself 403s without a cookie handshake — we never need it.)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv,application/csv,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

CACHE_DIR = Path(__file__).parent / ".cache"
DATA_DIR = Path(__file__).parent / "data"
# Gzipped CSV rather than parquet: pandas + stdlib gzip is the whole dependency
# list, so this runs anywhere without pinning pyarrow. The panel is small
# enough (~1-2 MB) that the format costs nothing.
PANEL_PATH = DATA_DIR / "panel.csv.gz"

# Columns we keep. Everything the scan needs, nothing else — the panel gets
# committed to git, so it stays small.
KEEP = [
    "SYMBOL", "SERIES", "DATE", "PREV_CLOSE", "CLOSE_PRICE", "AVG_PRICE",
    "TTL_TRD_QNTY", "TURNOVER_LACS", "DELIV_QTY",
]

NUMERIC = ["PREV_CLOSE", "CLOSE_PRICE", "AVG_PRICE", "TTL_TRD_QNTY",
           "TURNOVER_LACS", "DELIV_QTY"]

MAX_WORKERS = 6  # be polite to NSE; 6 is plenty for ~40 small files


def _cache_path(day: date) -> Path:
    return CACHE_DIR / f"{day:%Y-%m-%d}.csv.gz"


def _parse(text: str, day: date) -> pd.DataFrame | None:
    """Parse one raw bhavcopy CSV into the trimmed panel shape."""
    df = pd.read_csv(io.StringIO(text))
    df.columns = [c.strip() for c in df.columns]
    if "DELIV_QTY" not in df.columns:
        return None

    for c in df.select_dtypes("object"):
        df[c] = df[c].str.strip()

    df["DATE"] = pd.Timestamp(day)
    # Trade-to-trade and some illiquid scrips report "-" instead of a number.
    for c in NUMERIC:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df[KEEP].dropna(subset=["CLOSE_PRICE"])
    return df


def fetch_day(day: date, session: requests.Session | None = None,
              use_cache: bool = True) -> pd.DataFrame | None:
    """One trading day's delivery panel, or None if NSE has no file for it."""
    cp = _cache_path(day)
    if use_cache and cp.exists():
        try:
            return pd.read_csv(cp, parse_dates=["DATE"])
        except Exception:
            cp.unlink(missing_ok=True)  # corrupt/partial write — refetch

    s = session or requests.Session()
    url = ARCHIVE.format(ddmmyyyy=day.strftime("%d%m%Y"))
    try:
        r = s.get(url, headers=HEADERS, timeout=30)
    except requests.RequestException:
        return None
    if r.status_code != 200 or not r.text.lstrip().upper().startswith("SYMBOL"):
        return None

    df = _parse(r.text, day)
    if df is None or df.empty:
        return None

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(cp, index=False)
    return df


def fetch_history(trading_days: int = 30, lookback_calendar: int = 75,
                  end: date | None = None, use_cache: bool = True,
                  progress=None) -> pd.DataFrame:
    """
    Walk back from `end` and return the most recent `trading_days` days of data
    as one long panel.

    Weekends are skipped up front; holidays and the not-yet-published current
    day simply 404 and drop out. `lookback_calendar` bounds the walk so a long
    NSE outage can't turn into an unbounded crawl.
    """
    end = end or date.today()
    candidates = [
        end - timedelta(days=i)
        for i in range(lookback_calendar)
        if (end - timedelta(days=i)).weekday() < 5
    ]

    frames: list[pd.DataFrame] = []
    session = requests.Session()

    # Fetch in chunks, newest first, and stop as soon as we have enough days.
    CHUNK = MAX_WORKERS * 2
    for i in range(0, len(candidates), CHUNK):
        batch = candidates[i:i + CHUNK]
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            got = list(ex.map(lambda d: fetch_day(d, session, use_cache), batch))
        frames.extend(f for f in got if f is not None and not f.empty)
        if progress:
            progress(min(len(frames), trading_days), trading_days)
        if len(frames) >= trading_days:
            break

    if not frames:
        raise RuntimeError(
            "No NSE delivery data could be fetched. Either the network blocked "
            "nsearchives.nseindia.com, or NSE has not published recent files."
        )

    panel = pd.concat(frames, ignore_index=True)
    keep_dates = sorted(panel["DATE"].unique())[-trading_days:]
    return panel[panel["DATE"].isin(keep_dates)].reset_index(drop=True)


# ── ETF exclusion ─────────────────────────────────────────────────────────────

ETF_LIST = "https://nsearchives.nseindia.com/content/equities/eq_etfseclist.csv"
ETF_CACHE = CACHE_DIR / "etf_symbols.csv"


def etf_symbols(use_cache: bool = True) -> set[str]:
    """
    NSE's ETF list, used as a blocklist.

    ETFs trade in the EQ series and rack up huge delivery, so SILVERBEES and
    friends otherwise crowd out the actual stocks. This is a blocklist rather
    than an equity whitelist on purpose: a whitelist would silently drop
    freshly-listed companies, which are often exactly what a momentum scan
    should surface.

    Returns an empty set if the list can't be fetched — better to show a few
    ETFs than to fail the scan.
    """
    if use_cache and ETF_CACHE.exists():
        try:
            return set(pd.read_csv(ETF_CACHE)["Symbol"].astype(str).str.strip())
        except Exception:
            ETF_CACHE.unlink(missing_ok=True)
    try:
        r = requests.get(ETF_LIST, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            return set()
        df = pd.read_csv(io.StringIO(r.text))
        df.columns = [c.strip() for c in df.columns]
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df[["Symbol"]].to_csv(ETF_CACHE, index=False)
        return set(df["Symbol"].astype(str).str.strip())
    except Exception:
        return set()


def drop_etfs(panel: pd.DataFrame, use_cache: bool = True) -> pd.DataFrame:
    etfs = etf_symbols(use_cache)
    if not etfs:
        return panel
    return panel[~panel["SYMBOL"].isin(etfs)].reset_index(drop=True)


# ── Committed snapshot ────────────────────────────────────────────────────────

def save_panel(panel: pd.DataFrame, path: Path = PANEL_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    # mtime=0 makes the output byte-identical for identical data. gzip stamps
    # the current time into its header by default, so without this every
    # refresh looks like a change to git and commits ~2 MB even on a day when
    # NSE published nothing new.
    panel.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0})
    return path


def load_panel(path: Path = PANEL_PATH) -> pd.DataFrame | None:
    """The snapshot committed to the repo. None if it isn't there yet."""
    if not path.exists():
        return None
    try:
        return pd.read_csv(path, parse_dates=["DATE"])
    except Exception:
        return None
