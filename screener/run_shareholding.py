"""
run_shareholding.py — report the companies that have already filed a newer
shareholding pattern than the rest of the market, with their latest holdings.

Pipeline:
  1. Scrape every stock from a screener.in screen — either a saved screen URL
     or a raw query (--query).
  2. Visit each company page one by one — spaced out by ScreenerClient so the
     IP isn't rate-limited — and read the shareholding-pattern section.
  3. Log each company's holdings as it is processed, and append it to the
     "all" CSV immediately, so a long run is never lost to a late failure.
  4. Write the final CSV of early filers, newest quarter first, then by the
     largest combined FII + DII increase.

How "early filer" is decided:
  SEBI LODR Reg. 31 gives companies 21 days after a quarter-end to file the
  shareholding pattern. The baseline is therefore the latest quarter whose
  filing deadline has passed — "last quarter" — and any column newer than it
  counts as fresh, whatever its label. On 2026-09-23 the baseline is Jun 2026,
  so Sep 2026 filers are picked up, and so are companies that file interim
  patterns and show a Jul 2026 or Aug 2026 column. The baseline rolls forward
  on its own (to Sep 2026 on 2026-10-22), so nothing is hardcoded. Use
  --quarter to pin one exact label instead, or --any-quarter to keep
  everything scanned.

Re-slicing costs nothing: --from-csv rebuilds the output from a previous run's
"all" CSV without touching screener.in.

Usage:
    python screener/run_shareholding.py                       # saved screen
    python screener/run_shareholding.py --query               # mcap>1000 & public holding down
    python screener/run_shareholding.py --quarter "Sep 2026"  # exactly that label
    python screener/run_shareholding.py --any-quarter         # no freshness filter
    python screener/run_shareholding.py --from-csv shareholding_sep2026_all.csv
"""

import argparse
import csv
import os
import sys
import urllib.parse
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import NamedTuple
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from screener import ScreenerClient, screens, shareholding
from screener.models import ShareholdingChange

DEFAULT_SCREEN = "https://www.screener.in/screens/3798218/companiesfiidiibuying/"

# "Market cap > 1000 Cr and public holding fell last quarter", as a raw query.
# Screener exposes no "Change in public holding" ratio, so this uses its
# algebraic complement: promoters + FII + DII + government + public = 100 %,
# so public holding fell exactly when the rest rose in aggregate. (Government
# holding has no "change in" ratio either, but it almost never moves.)
PUBLIC_DOWN_QUERY = (
    "Market Capitalization > 1000 AND "
    "Change in promoter holding + Change in FII holding + Change in DII holding > 0"
)

RAW_SCREEN_URL = "https://www.screener.in/screen/raw/"

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

_QUARTER_END_MONTHS = (12, 9, 6, 3)   # Dec / Sep / Jun / Mar, newest first

# SEBI LODR Reg. 31: the shareholding pattern is due within 21 days of quarter-end.
FILING_DEADLINE_DAYS = 21

_CATEGORIES = ["promoter", "fii", "dii", "government", "public", "shareholders"]

CSV_COLUMNS = (
    ["name", "ticker", "url", "cmp", "market_cap", "latest_quarter",
     "prev_quarter", "is_fresh"]
    + [f"{cat}_{suffix}"
       for cat in _CATEGORIES
       for suffix in ("prev", "latest", "change")]
)


class Scanned(NamedTuple):
    """One company's parsed holdings plus the price/size columns off the screen."""
    change: ShareholdingChange
    cmp: str
    market_cap: str


def main() -> None:
    args = parse_args()

    if args.from_csv:
        rows = load_csv(args.from_csv)
        log(f"Loaded {len(rows)} companies from {args.from_csv} — no scraping.")
    else:
        url = args.url
        if args.query is not None:
            url = f"{RAW_SCREEN_URL}?query={urllib.parse.quote(args.query)}"
        rows = scan(url, args.all_output or _all_path(args.output))

    if not rows:
        log("\n[done] nothing parsed — no output written.")
        return

    selected, label = select(rows, args)

    # Newest quarter first, then biggest combined FII + DII increase.
    selected.sort(
        key=lambda r: (quarter_key(r.change.latest_quarter),
                       r.change.fii_dii_change or 0),
        reverse=True,
    )

    write_csv(args.output, selected)
    log(f"\n[done] {len(selected)} of {len(rows)} companies — {label} → {args.output}")
    for r in selected:
        log(f"  {r.change}")


# ------------------------------------------------------------------
# Scanning
# ------------------------------------------------------------------

def scan(url: str, all_output: str) -> list[Scanned]:
    """
    Scrape the screen at *url*, then read each company's shareholding pattern,
    streaming every parsed row to *all_output* as it is read.
    """
    client = ScreenerClient()

    log(f"Step 1/2 — scraping screen: {url}")
    try:
        screen = screens.fetch(client, url)
    except Exception as exc:
        print(f"[ERROR] could not fetch screen: {exc}", file=sys.stderr)
        sys.exit(1)

    stocks = screen.stocks
    if not stocks:
        print("[ERROR] screen returned no stocks — check the URL / credentials.", file=sys.stderr)
        sys.exit(1)

    log(f"  {screen.screen_name} — {len(stocks)} companies")

    log(f"\nStep 2/2 — reading shareholding pattern for {len(stocks)} companies")
    log(f"  streaming every row to {all_output} as it is read\n")

    rows: list[Scanned] = []
    with open(all_output, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()

        for i, stock in enumerate(stocks, 1):
            try:
                change = shareholding.fetch(client, stock.url, name=stock.name)
            except Exception as exc:
                log(f"  [{i:>3}/{len(stocks)}] {stock.name:<28} error — {exc}")
                continue

            row = Scanned(
                change=change,
                cmp=_metric(stock, "CMP"),
                market_cap=_metric(stock, "Mar Cap", "Market Cap"),
            )
            rows.append(row)
            writer.writerow(row_for(row, fresh=""))
            fh.flush()
            log(f"  [{i:>3}/{len(stocks)}] {change}")

    return rows


def load_csv(path: str) -> list[Scanned]:
    """Rebuild scan results from a previous run's CSV, without re-scraping."""
    rows: list[Scanned] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for record in csv.DictReader(fh):
            change = ShareholdingChange(
                name=record["name"],
                url=record["url"],
                latest_quarter=record["latest_quarter"] or None,
                prev_quarter=record["prev_quarter"] or None,
            )
            for cat in _CATEGORIES:
                for suffix in ("prev", "latest"):
                    raw = record.get(f"{cat}_{suffix}", "")
                    if raw != "":
                        setattr(change, f"{cat}_{suffix}", float(raw))
            rows.append(Scanned(
                change=change,
                cmp=record.get("cmp", ""),
                market_cap=record.get("market_cap", ""),
            ))
    return rows


# ------------------------------------------------------------------
# Quarter helpers
# ------------------------------------------------------------------

def quarter_key(label: str | None) -> tuple[int, int]:
    """'Sep 2026' → (2026, 9), for ordering. Unparseable → (0, 0)."""
    if not label:
        return (0, 0)
    parts = label.split()
    if len(parts) != 2 or parts[0] not in _MONTHS or not parts[1].isdigit():
        return (0, 0)
    return (int(parts[1]), _MONTHS.index(parts[0]) + 1)


def baseline_quarter(today: date | None = None) -> str:
    """
    "Last quarter": the latest quarter-end whose filing deadline has passed,
    e.g. 'Jun 2026' from 2026-07-22 up to 2026-10-21. Every company should have
    filed it by now, so any newer column is a fresh filing.
    """
    today = today or datetime.now(ZoneInfo("Asia/Kolkata")).date()
    for year in (today.year, today.year - 1):
        for month in _QUARTER_END_MONTHS:
            quarter_end = date(year, month, monthrange(year, month)[1])
            if quarter_end + timedelta(days=FILING_DEADLINE_DAYS) < today:
                return f"{_MONTHS[month - 1]} {year}"
    raise AssertionError("unreachable: last year's Dec deadline has always passed")


def is_fresh(change: ShareholdingChange, baseline: str) -> bool:
    """True when the company's latest column is newer than *baseline*."""
    return quarter_key(change.latest_quarter) > quarter_key(baseline)


def select(rows: list[Scanned], args) -> tuple[list[Scanned], str]:
    """Apply the freshness filter, returning (selected rows, description)."""
    if args.quarter:
        return ([r for r in rows if r.change.latest_quarter == args.quarter],
                f"latest filing is exactly {args.quarter}")

    if args.any_quarter:
        return (list(rows), "every company scanned")

    baseline = baseline_quarter()
    fresh = [r for r in rows if is_fresh(r.change, baseline)]
    return fresh, f"filed newer than last quarter ({baseline})"


# ------------------------------------------------------------------
# Output helpers
# ------------------------------------------------------------------

def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _all_path(output: str) -> str:
    stem, ext = os.path.splitext(output)
    return f"{stem}_all{ext or '.csv'}"


def _metric(stock, *needles: str) -> str:
    """First screen-column value whose header contains one of *needles*."""
    for needle in needles:
        for header, value in stock.metrics.items():
            if needle.lower() in header.lower():
                return value
    return ""


def _ticker(url: str) -> str:
    parts = [p for p in url.split("/") if p]
    if "company" in parts:
        idx = parts.index("company")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return ""


def row_for(row: Scanned, fresh) -> dict:
    change = row.change
    out = {
        "name": change.name,
        "ticker": _ticker(change.url),
        "url": change.url,
        "cmp": row.cmp,
        "market_cap": row.market_cap,
        "latest_quarter": change.latest_quarter or "",
        "prev_quarter": change.prev_quarter or "",
        "is_fresh": fresh,
    }
    for cat in _CATEGORIES:
        for suffix in ("prev", "latest"):
            value = getattr(change, f"{cat}_{suffix}")
            out[f"{cat}_{suffix}"] = "" if value is None else value
        delta = getattr(change, f"{cat}_change")
        out[f"{cat}_change"] = "" if delta is None else delta
    return out


def write_csv(path: str, selected: list[Scanned]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in selected:
            writer.writerow(row_for(row, fresh=True))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Scan a screener.in screen and report the companies that have "
            "filed a shareholding pattern newer than last quarter."
        )
    )
    parser.add_argument(
        "url", nargs="?", default=DEFAULT_SCREEN,
        help=f"Screen URL to scan (default: {DEFAULT_SCREEN})",
    )
    parser.add_argument(
        "--query", nargs="?", const=PUBLIC_DOWN_QUERY, metavar="TEXT",
        help="Run a raw screener query instead of a saved screen. Bare "
             "--query uses the built-in 'mcap > 1000 Cr and public holding "
             "fell last quarter' query.",
    )
    parser.add_argument(
        "--from-csv", metavar="FILE",
        help="Re-slice a previous run's CSV instead of scraping again.",
    )
    parser.add_argument(
        "-o", "--output", metavar="FILE", default="shareholding_changes.csv",
        help="Where to write the early filers (default: %(default)s)",
    )
    parser.add_argument(
        "--all-output", metavar="FILE",
        help="Where to stream every scanned company (default: <output>_all.csv)",
    )
    parser.add_argument(
        "--quarter", metavar="'Sep 2026'",
        help="Keep only companies whose latest filing carries exactly this "
             "label, instead of comparing against last quarter.",
    )
    parser.add_argument(
        "--any-quarter", action="store_true",
        help="Don't filter at all — report every company scanned.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
