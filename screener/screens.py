"""
screens.py — scrape all stocks from a screener.in screen (query/filter).

Handles pagination automatically, fetching all pages in one call.

Usage:
    from screener import ScreenerClient, screens

    client = ScreenerClient()

    # Pass the full URL of any screen
    result = screens.fetch(client, "https://www.screener.in/screens/3655407/good-results-debt-free/")

    print(result)                          # pretty summary

    for stock in result.stocks:
        print(stock.name, stock.metrics.get("P/E"), stock.metrics.get("ROCE %"))
"""

from __future__ import annotations

from urllib.parse import urlencode, urlparse, urlunparse, parse_qs

from bs4 import BeautifulSoup, Tag

from .client import ScreenerClient
from .models import ScreenResult, ScreenStock

_PAGE_LIMIT = 50   # max results per page screener.in supports


def fetch(client: ScreenerClient, url: str) -> ScreenResult:
    """
    Fetch every stock from a screener.in screen, across all pages.

    Args:
        client: An authenticated ScreenerClient instance.
        url:    Full URL of the screen, e.g.
                https://www.screener.in/screens/3655407/good-results-debt-free/

    Returns:
        A ScreenResult with all stocks and their metrics.
    """
    base_url   = _normalise_url(url)
    first_url  = _page_url(base_url, page=1)

    first_resp = client.get(first_url)
    soup       = BeautifulSoup(first_resp.text, "lxml")

    screen_name = _parse_screen_name(soup)
    headers     = _parse_headers(soup)
    stocks      = _parse_rows(soup, headers)

    for page in range(2, _last_page(soup) + 1):
        resp  = client.get(_page_url(base_url, page))
        soup  = BeautifulSoup(resp.text, "lxml")
        stocks.extend(_parse_rows(soup, headers))

    return ScreenResult(
        screen_name=screen_name,
        screen_url=base_url,
        headers=headers,
        stocks=stocks,
    )


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _normalise_url(url: str) -> str:
    """Strip any existing page/limit params so we control them cleanly."""
    parsed = urlparse(url)
    return urlunparse(parsed._replace(query=""))


def _page_url(base: str, page: int) -> str:
    params = urlencode({"limit": _PAGE_LIMIT, "page": page})
    return f"{base}?{params}"


def _parse_screen_name(soup: BeautifulSoup) -> str:
    tag = soup.find("h1") or soup.find("title")
    return tag.get_text(strip=True) if tag else "Unknown Screen"


def _parse_headers(soup: BeautifulSoup) -> list[str]:
    table = soup.find("table")
    if not isinstance(table, Tag):
        return []
    header_row = (table.find("tbody") or table).find("tr")
    if not header_row:
        return []
    # Skip S.No. and Name columns; keep metric columns
    ths = header_row.find_all("th")
    return [th.get_text(separator=" ", strip=True) for th in ths[2:]]


def _parse_rows(soup: BeautifulSoup, headers: list[str]) -> list[ScreenStock]:
    table = soup.find("table")
    if not isinstance(table, Tag):
        return []

    tbody  = table.find("tbody") or table
    stocks = []

    for tr in tbody.find_all("tr")[1:]:    # skip header row
        cells = tr.find_all("td")
        # Expect at least: S.No. + Name + one metric
        if len(cells) < 3:
            continue

        anchor = cells[1].find("a")
        name   = anchor.get_text(strip=True) if anchor else cells[1].get_text(strip=True)
        href   = anchor["href"] if anchor and anchor.get("href") else ""

        if not name:
            continue

        metrics = {
            headers[i]: cells[i + 2].get_text(strip=True)
            for i in range(len(headers))
            if i + 2 < len(cells)
        }

        stocks.append(ScreenStock(name=name, url=href, metrics=metrics))

    return stocks


def _last_page(soup: BeautifulSoup) -> int:
    """Return the highest page number found in the pagination block."""
    pagination = soup.find(class_="pagination")
    if not pagination:
        return 1
    page_nums = []
    for a in pagination.find_all("a", href=True):
        qs = parse_qs(urlparse(a["href"]).query)
        if "page" in qs:
            try:
                page_nums.append(int(qs["page"][0]))
            except ValueError:
                pass
    return max(page_nums, default=1)
