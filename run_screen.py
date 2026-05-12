"""
run_screen.py — fetch and display all stocks from a screener.in screen.

Usage:
    python3 run_screen.py https://www.screener.in/screens/3655407/good-results-debt-free/
"""

import argparse
import sys

from screener import ScreenerClient, screens


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch all stocks from a screener.in screen"
    )
    parser.add_argument("url", help="Full URL of the screen")
    args = parser.parse_args()

    client = ScreenerClient()
    try:
        result = screens.fetch(client, args.url)
        print(result)
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
