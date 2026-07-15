"""
screen_peers.py — composite tool: screen → peers.

Fetches every stock in a screener.in screen then fetches the peer
comparison table for each one.  Returns a flat list of ScreenPeerRow,
one row per (source stock, peer) pair, ready to be written as CSV.

Usage (as a library):
    from screener import ScreenerClient, screen_peers

    client = ScreenerClient()
    rows   = screen_peers.fetch(client, "https://www.screener.in/screens/…/")
    csv_str = screen_peers.to_csv(rows)          # string
    screen_peers.to_csv(rows, file=open("out.csv", "w"))  # to file
"""

from __future__ import annotations

import csv
import io
import sys
from dataclasses import dataclass, field
from typing import Callable, Optional
from urllib.parse import urlparse

import requests

from .client import BASE_URL, ScreenerClient
from . import peers, screens


@dataclass
class ScreenPeerRow:
    """One row in the flattened output: a peer of a stock found in the screen."""
    screen_stock_name: str
    screen_stock_ticker: str
    peer_name: str
    peer_ticker: str
    current_price: Optional[str] = None
    pe_ratio: Optional[str] = None
    market_cap: Optional[str] = None
    div_yield: Optional[str] = None
    net_profit_qtr: Optional[str] = None
    qtr_profit_var: Optional[str] = None
    sales_qtr: Optional[str] = None
    qtr_sales_var: Optional[str] = None
    roce: Optional[str] = None
    extra: dict = field(default_factory=dict)


# Ordered base columns for CSV output (extra columns are appended after)
_BASE_FIELDS = [
    "screen_stock_name", "screen_stock_ticker",
    "peer_name", "peer_ticker",
    "current_price", "pe_ratio", "market_cap", "div_yield",
    "net_profit_qtr", "qtr_profit_var", "sales_qtr", "qtr_sales_var", "roce",
]


def fetch(
    client: ScreenerClient,
    screen_url: str,
    consolidated: bool = True,
    on_progress: Optional[Callable[[str], None]] = None,
) -> list[ScreenPeerRow]:
    """
    Fetch peers for every stock in a screen.

    Args:
        client:       Authenticated ScreenerClient.
        screen_url:   Full URL of the screener.in screen.
        consolidated: Use consolidated financials (default True).
        on_progress:  Optional callback called with a status string after
                      each stock is processed; useful for live progress output.

    Returns:
        Flat list of ScreenPeerRow, one per (screen stock, peer) pair.
        Stocks whose peer fetch fails are skipped with a stderr warning.
    """
    screen_result = screens.fetch(client, screen_url)

    if on_progress:
        on_progress(
            f"Screen '{screen_result.screen_name}': "
            f"{len(screen_result.stocks)} stocks"
        )

    rows: list[ScreenPeerRow] = []

    for stock in screen_result.stocks:
        ticker = _ticker_from_url(stock.url)
        if not ticker:
            print(f"[WARN] Cannot extract ticker from '{stock.url}' — skipping", file=sys.stderr)
            continue

        try:
            peer_table, variant = _fetch_peers_with_fallback(client, ticker, consolidated)
        except Exception as exc:
            print(f"[WARN] {stock.name} ({ticker}): {exc} — skipping", file=sys.stderr)
            continue

        if on_progress:
            on_progress(f"  {stock.name} ({ticker}) [{variant}]: {len(peer_table.peers)} peers")

        for peer in peer_table.peers:
            rows.append(ScreenPeerRow(
                screen_stock_name=stock.name,
                screen_stock_ticker=ticker,
                peer_name=peer.name,
                peer_ticker=_ticker_from_url(peer.url),
                current_price=peer.current_price,
                pe_ratio=peer.pe_ratio,
                market_cap=peer.market_cap,
                div_yield=peer.div_yield,
                net_profit_qtr=peer.net_profit_qtr,
                qtr_profit_var=peer.qtr_profit_var,
                sales_qtr=peer.sales_qtr,
                qtr_sales_var=peer.qtr_sales_var,
                roce=peer.roce,
                extra=dict(peer.extra),
            ))

    return rows


def to_csv(rows: list[ScreenPeerRow], file=None) -> Optional[str]:
    """
    Serialise rows to CSV.

    Args:
        rows: Output of fetch().
        file: File-like object to write into.  If None, returns a string.

    Returns:
        CSV string when file is None, otherwise None.
    """
    if not rows:
        return "" if file is None else None

    # Preserve insertion order of extra columns across all rows
    extra_keys: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for k in row.extra:
            if k not in seen:
                extra_keys.append(k)
                seen.add(k)

    fieldnames = _BASE_FIELDS + extra_keys
    output = file or io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()

    for row in rows:
        d = {f: getattr(row, f, None) for f in _BASE_FIELDS}
        d.update(row.extra)
        writer.writerow(d)

    if file is None:
        return output.getvalue()
    return None


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _fetch_peers_with_fallback(
    client: ScreenerClient,
    ticker: str,
    consolidated: bool,
) -> tuple:
    """
    Fetch peers with a three-step fallback:
      1. /company/<TICKER>/consolidated/
      2. /company/<TICKER>/standalone/
      3. /company/<TICKER>/            (bare URL — screener redirects to whichever exists)

    Rate-limit errors (429) and unexpected HTTP errors are always re-raised.
    """
    def _is_404(exc: requests.HTTPError) -> bool:
        return exc.response is not None and exc.response.status_code == 404

    attempts = (
        [(True, "consolidated"), (False, "standalone")]
        if consolidated
        else [(False, "standalone")]
    )

    for use_consolidated, label in attempts:
        try:
            return peers.fetch(client, ticker, consolidated=use_consolidated), label
        except requests.HTTPError as exc:
            if _is_404(exc):
                continue
            raise
        except ValueError:
            continue

    # Last resort: bare URL (no /consolidated/ or /standalone/ suffix)
    try:
        table = _fetch_bare(client, ticker)
        return table, "bare (fallback)"
    except requests.HTTPError as exc:
        if _is_404(exc):
            raise ValueError(f"No screener page found for '{ticker}'") from exc
        raise


def _fetch_bare(client: ScreenerClient, ticker: str):
    """Fetch peers via the bare company URL and let screener redirect."""
    from .peers import _extract_warehouse_id, _parse
    bare_url = f"{BASE_URL}/company/{ticker.upper().strip()}/"
    page_resp = client.get(bare_url)
    warehouse_id = _extract_warehouse_id(page_resp.text, ticker)
    api_resp = client.get(f"{BASE_URL}/api/company/{warehouse_id}/peers/")
    return _parse(api_resp.text, ticker, bare_url)


def _ticker_from_url(url: str) -> str:
    """
    Extract the ticker symbol from a screener.in company URL.

    Handles query params and both forms:
      /company/MCX/
      /company/MCX/consolidated/
    """
    path = urlparse(url).path
    parts = [p for p in path.strip("/").split("/") if p]
    if len(parts) >= 2 and parts[0] == "company":
        return parts[1].upper()
    return ""
