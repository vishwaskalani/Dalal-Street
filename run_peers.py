"""
run_peers.py — fetch and display Peer Comparison for one or more tickers.

Usage:
    python run_peers.py MCX
    python run_peers.py MCX RELIANCE HDFCBANK
    python run_peers.py MCX --standalone
"""

import argparse
import sys

from screener import ScreenerClient, peers


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch Peer Comparison from screener.in"
    )
    parser.add_argument("tickers", nargs="+", help="Ticker symbols, e.g. MCX RELIANCE")
    parser.add_argument(
        "--standalone",
        action="store_true",
        help="Use standalone financials (default: consolidated)",
    )
    args = parser.parse_args()

    client = ScreenerClient()   # reads .env automatically

    for ticker in args.tickers:
        try:
            table = peers.fetch(client, ticker, consolidated=not args.standalone)
            print()
            print(table)
        except Exception as exc:
            print(f"[ERROR] {ticker}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
