"""
results_check.py — determine whether the latest quarterly results are
available on screener.in for a given company.

Logic:
  1. Compute the most recently ended quarter based on today's date
     (quarter ends: Mar 31, Jun 30, Sep 30, Dec 31).
  2. Fetch the company page and parse the column headers of the quarterly
     results table (section#quarters).
  3. If the most recent ended quarter is absent from those headers,
     results are considered pending.

Usage:
    from screener import ScreenerClient, results_check

    client = ScreenerClient()
    latest, pending = results_check.fetch(client, "MCX")
    print(latest, pending)   # "Mar 2026", False
"""

from __future__ import annotations

import sys
from datetime import date
from typing import Optional

import requests
from bs4 import BeautifulSoup, Tag

from .client import BASE_URL, ScreenerClient

_MONTHS = {"Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"}

# Quarter end dates within a year (month, day)
_QUARTER_ENDS = ((3, 31), (6, 30), (9, 30), (12, 31))


def expected_latest_quarter(today: date | None = None) -> str:
    """
    Return the most recently ended quarter as 'Mon YYYY', e.g. 'Mar 2026'.

    Quarter ends: March 31, June 30, September 30, December 31.
    """
    today = today or date.today()
    year  = today.year

    candidates = [date(year - 1, 12, 31)] + [
        date(year, m, d) for m, d in _QUARTER_ENDS
    ]
    most_recent = max(d for d in candidates if d <= today)
    return most_recent.strftime("%b %Y")


def fetch(
    client: ScreenerClient,
    ticker: str,
    consolidated: bool = True,
) -> tuple[Optional[str], bool]:
    """
    Return (latest_quarter, results_pending) for *ticker*.

    latest_quarter: the most recent quarter string found on the page,
                    e.g. "Mar 2026", or None if unparseable.
    results_pending: True when the expected latest quarter is absent
                     from the quarterly results table, or when the page
                     could not be fetched/parsed.

    Uses the same consolidated → standalone → bare fallback as peers.
    """
    expected = expected_latest_quarter()

    html = _fetch_page_html(client, ticker, consolidated)
    if html is None:
        return None, True

    latest = _parse_latest_quarter(html)
    pending = (latest != expected) if latest is not None else True
    return latest, pending


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _fetch_page_html(
    client: ScreenerClient,
    ticker: str,
    consolidated: bool,
) -> Optional[str]:
    """
    Fetch the company page HTML with a three-step fallback:
      consolidated → standalone → bare URL.

    Returns None on persistent 404; re-raises other HTTP errors.
    """
    def _try_url(url: str) -> Optional[str]:
        try:
            return client.get(url).text
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return None
            raise

    ticker = ticker.upper().strip()

    if consolidated:
        html = _try_url(f"{BASE_URL}/company/{ticker}/consolidated/")
        if html is not None:
            return html

    html = _try_url(f"{BASE_URL}/company/{ticker}/standalone/")
    if html is not None:
        return html

    # Bare URL — let screener redirect to whichever variant exists.
    # A 404 here means the company genuinely has no page; propagate as None.
    try:
        return client.get(f"{BASE_URL}/company/{ticker}/").text
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            print(
                f"[results_check] {ticker}: no screener page found — skipping",
                file=sys.stderr,
            )
            return None
        raise


def _parse_latest_quarter(html: str) -> Optional[str]:
    """
    Return the most recent quarter string from the quarterly results table,
    e.g. 'Mar 2026', or None if not found.

    Screener renders quarterly results in <section id="quarters">.
    Column headers are <th> elements containing strings like 'Mar 2026'.
    The first valid quarter found is the most recent (columns go newest→oldest).
    """
    soup    = BeautifulSoup(html, "lxml")
    section = soup.find(id="quarters")

    # Fall back to the whole page if the section is absent
    search_root = section if isinstance(section, Tag) else soup

    table = search_root.find("table") if isinstance(search_root, Tag) else None
    if not isinstance(table, Tag):
        return None

    thead      = table.find("thead") or table
    header_row = thead.find("tr")
    if not header_row:
        return None

    # Columns run oldest → newest; the rightmost valid quarter is the most recent.
    latest = None
    for th in header_row.find_all("th"):
        text = th.get_text(strip=True)
        if _is_quarter_string(text):
            latest = text

    return latest


def _is_quarter_string(text: str) -> bool:
    parts = text.split()
    return len(parts) == 2 and parts[0] in _MONTHS and parts[1].isdigit()
