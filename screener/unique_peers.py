"""
unique_peers.py — collapse screen→peer rows into a deduplicated peer list.

Inverts the relation: instead of "stock X has peers [A, B, C]", we get
"peer A is a peer of [X, Y]".  Duplicate appearances of the same ticker
across different screen stocks are merged; financial values are taken
from the first non-null occurrence.

Usage:
    from screener import screen_peers, unique_peers

    rows  = screen_peers.fetch(client, screen_url)
    peers = unique_peers.deduplicate(rows)

    for p in peers:
        print(p.ticker, p.peer_of, p.pe_ratio)
"""

from __future__ import annotations

import csv
import io
from typing import Optional

from .models import UniquePeer
from .screen_peers import ScreenPeerRow

_FINANCIAL_FIELDS = (
    "current_price", "pe_ratio", "market_cap", "div_yield",
    "net_profit_qtr", "qtr_profit_var", "sales_qtr", "qtr_sales_var", "roce",
)

_CSV_FIELDS = [
    "ticker", "name", "peer_of",
    "current_price", "pe_ratio", "market_cap", "div_yield",
    "net_profit_qtr", "qtr_profit_var", "sales_qtr", "qtr_sales_var", "roce",
    "latest_quarter", "results_pending",
]


def deduplicate(rows: list[ScreenPeerRow]) -> list[UniquePeer]:
    """
    Collapse a flat list of ScreenPeerRow into unique UniquePeer entries.

    - Each peer ticker appears exactly once in the output.
    - peer_of is the sorted list of screen stock tickers that listed this
      company as a peer.
    - Financial fields are taken from the first row where they are non-None,
      then filled forward from later rows for any that were initially absent.
    """
    seen: dict[str, UniquePeer] = {}

    for row in rows:
        ticker = (row.peer_ticker or "").strip()
        if not ticker:
            continue

        if ticker not in seen:
            seen[ticker] = UniquePeer(
                ticker=ticker,
                name=row.peer_name,
                peer_of=[row.screen_stock_ticker],
                **{f: getattr(row, f) for f in _FINANCIAL_FIELDS},
            )
        else:
            up = seen[ticker]
            if row.screen_stock_ticker not in up.peer_of:
                up.peer_of.append(row.screen_stock_ticker)
            _fill_missing(up, row)

    # Sort peer_of lists for deterministic output
    for up in seen.values():
        up.peer_of.sort()

    return list(seen.values())


def to_csv(peers: list[UniquePeer], file=None) -> Optional[str]:
    """
    Serialise a list of UniquePeer to CSV.

    peer_of is written as a semicolon-separated string.
    results_pending is written as True/False/'' (empty when not yet checked).

    Args:
        peers: Output of deduplicate() (optionally enriched with results data).
        file:  File-like object.  If None, returns a string.
    """
    if not peers:
        return "" if file is None else None

    output = file or io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_CSV_FIELDS)
    writer.writeheader()

    for p in peers:
        writer.writerow({
            "ticker":          p.ticker,
            "name":            p.name,
            "peer_of":         ";".join(p.peer_of),
            "current_price":   p.current_price,
            "pe_ratio":        p.pe_ratio,
            "market_cap":      p.market_cap,
            "div_yield":       p.div_yield,
            "net_profit_qtr":  p.net_profit_qtr,
            "qtr_profit_var":  p.qtr_profit_var,
            "sales_qtr":       p.sales_qtr,
            "qtr_sales_var":   p.qtr_sales_var,
            "roce":            p.roce,
            "latest_quarter":  p.latest_quarter,
            "results_pending": "" if p.results_pending is None else p.results_pending,
        })

    if file is None:
        return output.getvalue()
    return None


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _fill_missing(up: UniquePeer, row: ScreenPeerRow) -> None:
    for f in _FINANCIAL_FIELDS:
        if getattr(up, f) is None:
            setattr(up, f, getattr(row, f))
