"""
run_shareholding_delta.py — daily job: find the shareholding patterns that
appeared on screener.in since the previous run, and optionally mail them.

A company is in today's delta when both of these hold:
  1. Its latest column is newer than last quarter (see
     run_shareholding.baseline_quarter), so it is a fresh filing, not a
     straggler catching up on last quarter.
  2. That column was not there on the previous run: the company is new to the
     state file, or its latest quarter has moved forward since then.

State lives in data/shareholding_state.csv: one row per company, holding the
latest pattern seen. It is merged, not overwritten, so a company that fails to
load today, or drops out of the screen, keeps its old row. Otherwise it would
come back as "new" the next time it loads. The first run has no state, so
every fresh filer counts as new.

Outputs:
  data/deltas/shareholding_delta_<date>.csv   today's delta (always written)
  data/shareholding_state.csv                 updated state

Usage:
    python screener/run_shareholding_delta.py
    python screener/run_shareholding_delta.py --mail-to a@x.com b@y.com
"""

import argparse
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from screener import mailer
from screener.run_shareholding import (
    DEFAULT_SCREEN, Scanned, baseline_quarter, is_fresh, load_csv, log,
    quarter_key, scan, write_csv, _ticker,
)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
STATE_PATH = os.path.join(DATA_DIR, "shareholding_state.csv")
SCAN_PATH = os.path.join(DATA_DIR, "shareholding_last_scan.csv")
DELTA_DIR = os.path.join(DATA_DIR, "deltas")

MAIL_SUBJECT = "Automated shareholding delta mail"


def main() -> None:
    args = parse_args()
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    baseline = baseline_quarter(today)

    previous = _by_ticker(load_csv(STATE_PATH)) if os.path.exists(STATE_PATH) else {}
    log(f"Last quarter is {baseline}; {len(previous)} companies in saved state.\n")

    os.makedirs(DELTA_DIR, exist_ok=True)
    scanned = scan(args.url, SCAN_PATH)
    current = {t: r for t, r in _by_ticker(scanned).items() if r.change.latest_quarter}
    log(f"\n{len(current)} of {len(scanned)} companies parsed with a shareholding table.")

    delta = [r for t, r in current.items()
             if is_fresh(r.change, baseline) and _moved_forward(r, previous.get(t))]
    delta.sort(
        key=lambda r: (quarter_key(r.change.latest_quarter),
                       r.change.fii_dii_change or 0),
        reverse=True,
    )

    delta_path = os.path.join(DELTA_DIR, f"shareholding_delta_{today.isoformat()}.csv")
    write_csv(delta_path, delta)
    write_csv(STATE_PATH, sorted({**previous, **current}.values(),
                                 key=lambda r: r.change.name.lower()))

    log(f"\n[done] {len(delta)} new filings newer than {baseline} → {delta_path}")
    for r in delta:
        log(f"  {r.change}")

    if args.mail_to:
        body = _mail_body(delta, baseline, today)
        mailer.send(args.mail_to, MAIL_SUBJECT, body,
                    attachment=delta_path if delta else None)
        log(f"\nMailed {len(delta)} rows to {', '.join(args.mail_to)}")


def _by_ticker(rows: list[Scanned]) -> dict[str, Scanned]:
    return {_ticker(r.change.url) or r.change.url: r for r in rows}


def _moved_forward(now: Scanned, before: Scanned | None) -> bool:
    if before is None:
        return True
    return quarter_key(now.change.latest_quarter) > quarter_key(before.change.latest_quarter)


def _mail_body(delta: list[Scanned], baseline: str, today) -> str:
    if not delta:
        return (f"No new shareholding patterns newer than {baseline} "
                f"were published since the previous run ({today:%d %b %Y}).")

    def fmt(v):
        return "n/a" if v is None else f"{v:+.2f}"

    lines = [f"{len(delta)} new shareholding pattern(s) newer than {baseline}, "
             f"seen on {today:%d %b %Y}. Full CSV attached.", ""]
    for r in delta:
        c = r.change
        lines.append(
            f"{c.name} ({c.latest_quarter} vs {c.prev_quarter}): "
            f"FII {fmt(c.fii_change)}, DII {fmt(c.dii_change)}, "
            f"Promoter {fmt(c.promoter_change)}, Public {fmt(c.public_change)}"
        )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report shareholding patterns published since the previous run."
    )
    parser.add_argument(
        "url", nargs="?", default=DEFAULT_SCREEN,
        help=f"Screen URL to scan (default: {DEFAULT_SCREEN})",
    )
    parser.add_argument(
        "--mail-to", nargs="+", metavar="EMAIL",
        help="Mail the delta to these addresses (needs SMTP_USER / SMTP_PASSWORD).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
