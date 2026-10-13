#!/usr/bin/env python3
"""
refresh.py — Rebuild the committed data snapshot the app reads.

    python refresh.py            # 75 trading days, writes data/panel.csv.gz
    python refresh.py --days 90

Run by GitHub Actions on a schedule (see .github/workflows/refresh-delivery.yml),
or by hand from your own machine if NSE ever blocks the CI runner's IP.

Keeping fetch and serve separate is deliberate: the Streamlit app never has to
reach NSE at page load, so it stays fast and it stays up even when NSE is down
or rate-limiting.
"""

from __future__ import annotations

import argparse
import sys

import nse_data
import scan

# The app scans EQ only. BE (trade-to-trade) is 100% delivery by rule and
# everything else NSE publishes (SM/ST/GS/GB/BZ …) is never read, so it is
# dropped before the snapshot is committed.
KEEP_SERIES = ("EQ",)

# Longest window (1M = 20 days) plus its 50-day baseline, with a little slack.
DEFAULT_DAYS = scan.needed_days(max(scan.WINDOWS.values())) + 5


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS,
                    help=f"trading days of history to keep (default {DEFAULT_DAYS})")
    ap.add_argument("--no-cache", action="store_true",
                    help="ignore the local .cache and refetch every day")
    args = ap.parse_args()

    print(f"Fetching {args.days} trading days of NSE delivery data …")
    panel = nse_data.fetch_history(
        trading_days=args.days,
        # ~250 trading days a year, plus holidays — 1.6× calendar days is ample.
        lookback_calendar=int(args.days * 1.6) + 10,
        use_cache=not args.no_cache,
        progress=lambda a, b: print(f"  {a}/{b} days", flush=True),
    )

    before = panel["SYMBOL"].nunique()
    panel = nse_data.drop_etfs(panel, use_cache=not args.no_cache)
    print(f"  dropped {before - panel['SYMBOL'].nunique()} ETFs")

    rows = len(panel)
    panel = panel[panel["SERIES"].isin(KEEP_SERIES)].reset_index(drop=True)
    print(f"  dropped {rows - len(panel):,} rows outside {'/'.join(KEEP_SERIES)}")

    path = nse_data.save_panel(panel)
    first, last = scan.window_dates(panel, panel["DATE"].nunique())
    kb = path.stat().st_size // 1024
    print(f"\nWrote {path}  ({kb} KB)")
    print(f"  {panel['DATE'].nunique()} trading days: {first} → {last}")
    print(f"  {panel['SYMBOL'].nunique():,} symbols, {len(panel):,} rows")

    # Smoke-test the default scan so a broken snapshot fails here, not in the UI.
    hits = scan.signals(scan.build_scan(panel, window=5), window=5)
    print(f"  default scan (1W, surge ≥2×): {len(hits)} hits, "
          f"top = {hits.iloc[0]['SYMBOL'] if len(hits) else 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
