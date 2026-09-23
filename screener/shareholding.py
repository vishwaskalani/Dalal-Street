"""
shareholding.py — parse the shareholding-pattern section of a screener.in
company page and report every holding category (promoters, FIIs, DIIs,
government, public, shareholder count) for the latest reported quarter,
alongside the quarter before it.

Motivation:
  A screener.in screen compares "change in FII/DII holding" using whatever the
  *latest available* quarter is for each company. But some companies report the
  newest quarter (e.g. Sep 2026) earlier than others, whose latest is still the
  previous quarter (e.g. Jun 2026). This module reads each company's own latest
  quarter straight from its page, so you can spot the fresh reporters and see
  exactly how holdings moved.

Usage:
    from screener import ScreenerClient, shareholding

    client = ScreenerClient()
    change = shareholding.fetch(client, "/company/GABRIEL/")
    print(change.latest_quarter, change.fii_change, change.public_change)
"""

from __future__ import annotations

import sys
from typing import Optional

import requests
from bs4 import BeautifulSoup, Tag

from .client import BASE_URL, ScreenerClient
from .models import ShareholdingChange


def fetch(client: ScreenerClient, url: str, name: str | None = None) -> ShareholdingChange:
    """
    Fetch a company page and return its latest-quarter FII / DII holding change.

    Args:
        client: An authenticated ScreenerClient (handles rate-limit spacing).
        url:    Company URL — absolute or relative (as scraped from a screen),
                e.g. "/company/TIPSMUSIC/" or ".../company/GVPIL/consolidated/".
        name:   Optional display name; parsed from the page when omitted.

    Returns:
        A ShareholdingChange. If the shareholding section is missing/unparseable,
        the quarter and holding fields are left as None.
    """
    full_url = url if url.startswith("http") else f"{BASE_URL}{url}"

    try:
        html = client.get(full_url).text
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        print(f"[shareholding] {url}: HTTP {status} — skipping", file=sys.stderr)
        return ShareholdingChange(name=name or _ticker_from_url(url), url=url)

    return parse(html, url=url, name=name)


def parse(html: str, url: str = "", name: str | None = None) -> ShareholdingChange:
    """Build a ShareholdingChange from company-page HTML."""
    soup = BeautifulSoup(html, "lxml")
    result = ShareholdingChange(name=name or _parse_name(soup) or _ticker_from_url(url), url=url)

    quarters, rows = _parse_quarterly_table(soup)
    if len(quarters) < 2:
        return result  # need at least two columns to compute a change

    result.latest_quarter = quarters[-1]
    result.prev_quarter = quarters[-2]

    # (attribute prefix, row-label substring) for every category we report.
    for prefix, label in (
        ("promoter", "Promoter"),
        ("fii", "FII"),
        ("dii", "DII"),
        ("government", "Government"),
        ("public", "Public"),
        ("shareholders", "Shareholders"),
    ):
        values = _find_row(rows, label)
        if values is not None and len(values) >= 2:
            setattr(result, f"{prefix}_latest", values[-1])
            setattr(result, f"{prefix}_prev", values[-2])

    return result


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _parse_quarterly_table(
    soup: BeautifulSoup,
) -> tuple[list[str], dict[str, list[Optional[float]]]]:
    """
    Return (quarter_labels, {category_label: [values]}) from the quarterly
    shareholding table. Columns run oldest → newest, so index -1 is the latest.

    Returns ([], {}) when the section or table is absent.
    """
    section = soup.find(id="shareholding")
    if not isinstance(section, Tag):
        return [], {}

    # The quarterly tab; fall back to the section's first table.
    holder = section.find(id="quarterly-shp")
    table = (holder if isinstance(holder, Tag) else section).find("table")
    if not isinstance(table, Tag):
        return [], {}

    thead = table.find("thead")
    header_row = thead.find("tr") if isinstance(thead, Tag) else None
    if header_row is None:
        return [], {}

    # First <th> is the blank category corner; the rest are quarter labels.
    quarters = [th.get_text(strip=True) for th in header_row.find_all("th")[1:]]

    body = table.find("tbody")
    rows: dict[str, list[Optional[float]]] = {}
    if isinstance(body, Tag):
        for tr in body.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) < 2:
                continue
            label = cells[0].get_text(strip=True).replace("+", "").strip()
            rows[label] = [_parse_percent(td.get_text(strip=True)) for td in cells[1:]]

    return quarters, rows


def _find_row(
    rows: dict[str, list[Optional[float]]], key: str
) -> Optional[list[Optional[float]]]:
    """Match a category row by substring, e.g. 'FII' → the 'FIIs' row."""
    key = key.upper()
    for label, values in rows.items():
        if key in label.upper():
            return values
    return None


def _parse_percent(text: str) -> Optional[float]:
    """'26.07%' → 26.07; '', '-' → None."""
    cleaned = text.replace("%", "").replace(",", "").strip()
    if not cleaned or cleaned in {"-", "–", "—"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_name(soup: BeautifulSoup) -> Optional[str]:
    tag = soup.find("h1")
    return tag.get_text(strip=True) if tag else None


def _ticker_from_url(url: str) -> str:
    """'/company/TIPSMUSIC/consolidated/' → 'TIPSMUSIC'."""
    parts = [p for p in url.split("/") if p]
    if "company" in parts:
        idx = parts.index("company")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return url or "?"
