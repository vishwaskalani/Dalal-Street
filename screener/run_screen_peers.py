"""
run_screen_peers.py — fetch peers of all stocks in a screener.in screen.

Outputs a CSV with one row per (screen stock, peer) pair.

Usage:
    # Print CSV to stdout
    python screener/run_screen_peers.py <screen-url>

    # Save to a file
    python screener/run_screen_peers.py <screen-url> -o peers.csv

    # Use standalone financials
    python screener/run_screen_peers.py <screen-url> --standalone
"""

import argparse
import sys
import os

# Allow running from anywhere: make sure the project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from screener import ScreenerClient
from screener import screen_peers


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch peers for every stock in a screener.in screen and output CSV"
    )
    parser.add_argument("url", help="Full URL of the screen")
    parser.add_argument(
        "--standalone",
        action="store_true",
        help="Use standalone financials (default: consolidated)",
    )
    parser.add_argument(
        "-o", "--output",
        metavar="FILE",
        help="Write CSV to FILE instead of stdout",
    )
    args = parser.parse_args()

    client = ScreenerClient()

    def progress(msg: str) -> None:
        print(msg, file=sys.stderr)

    try:
        rows = screen_peers.fetch(
            client,
            args.url,
            consolidated=not args.standalone,
            on_progress=progress,
        )
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    if not rows:
        print("[WARN] No peer rows collected — check the screen URL and credentials.", file=sys.stderr)
        sys.exit(0)

    if args.output:
        with open(args.output, "w", newline="", encoding="utf-8") as f:
            screen_peers.to_csv(rows, file=f)
        print(f"[done] {len(rows)} rows → {args.output}", file=sys.stderr)
    else:
        print(screen_peers.to_csv(rows), end="")


if __name__ == "__main__":
    main()
