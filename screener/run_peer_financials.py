"""
run_peer_financials.py — screen → unique peers CSV with financials + results status.

Pipeline:
  1. Fetch every stock in a screener.in screen and their peers.
  2. Deduplicate peers (many stocks share the same peer companies).
  3. For each unique peer, check whether the latest quarterly results
     have been published on screener.in.
  4. Write a CSV: one row per unique peer, with financials and
     a results_pending boolean.

Usage:
    python screener/run_peer_financials.py <screen-url>
    python screener/run_peer_financials.py <screen-url> -o peers_financials.csv
    python screener/run_peer_financials.py <screen-url> --skip-results
    python screener/run_peer_financials.py <screen-url> --standalone
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from screener import ScreenerClient
from screener import screen_peers, unique_peers, results_check
from screener.results_check import expected_latest_quarter


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch peers for every stock in a screener.in screen, deduplicate them, "
            "and output a CSV with key financials and results-pending status."
        )
    )
    parser.add_argument("url", help="Full URL of the screener.in screen")
    parser.add_argument(
        "--standalone",
        action="store_true",
        help="Use standalone financials (default: consolidated with fallback)",
    )
    parser.add_argument(
        "--skip-results",
        action="store_true",
        help="Skip the results-pending check (faster; omits latest_quarter and results_pending columns)",
    )
    parser.add_argument(
        "-o", "--output",
        metavar="FILE",
        help="Write CSV to FILE instead of stdout",
    )
    args = parser.parse_args()

    client = ScreenerClient()

    # ── Step 1: fetch screen peers ────────────────────────────────────
    def progress(msg: str) -> None:
        print(msg, file=sys.stderr)

    progress("Step 1/3 — fetching screen and peer tables…")
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

    # ── Step 2: deduplicate peers ─────────────────────────────────────
    progress(f"\nStep 2/3 — deduplicating {len(rows)} rows…")
    peers = unique_peers.deduplicate(rows)
    progress(f"  {len(peers)} unique peer tickers (from {len(rows)} total rows)")

    # ── Step 3: results-pending check ────────────────────────────────
    if not args.skip_results:
        expected = expected_latest_quarter()
        progress(f"\nStep 3/3 — checking results for {len(peers)} peers (expected: {expected})…")
        for i, peer in enumerate(peers, 1):
            try:
                latest, pending = results_check.fetch(
                    client, peer.ticker, consolidated=not args.standalone
                )
            except Exception as exc:
                print(
                    f"  [{i}/{len(peers)}] {peer.ticker}: error — {exc}",
                    file=sys.stderr,
                )
                latest, pending = None, True

            peer.latest_quarter  = latest
            peer.results_pending = pending

            status = "PENDING" if pending else "ok"
            progress(
                f"  [{i}/{len(peers)}] {peer.ticker:<15} latest={latest or '?':<10} {status}"
            )
    else:
        progress("\nStep 3/3 — skipped (--skip-results)")

    # ── Output ────────────────────────────────────────────────────────
    if args.output:
        with open(args.output, "w", newline="", encoding="utf-8") as f:
            unique_peers.to_csv(peers, file=f)
        print(f"\n[done] {len(peers)} unique peers → {args.output}", file=sys.stderr)
    else:
        print(unique_peers.to_csv(peers), end="")


if __name__ == "__main__":
    main()
