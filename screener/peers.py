"""
peers.py — scrape the Peer Comparison table from a screener.in company page.

screener.in loads the peer table dynamically via:
  GET /api/company/{warehouseId}/peers/
where warehouseId lives in data-warehouse-id on #company-info.

Usage:
    from screener import ScreenerClient, peers

    client = ScreenerClient()
    table  = peers.fetch(client, "MCX")                      # consolidated (default)
    table  = peers.fetch(client, "MCX", consolidated=False)  # standalone

    print(table)                       # pretty summary
    for peer in table.peers:
        print(peer.name, peer.pe_ratio)
"""

from __future__ import annotations

from bs4 import BeautifulSoup, Tag

from .client import BASE_URL, ScreenerClient
from .models import Peer, PeerTable

# Column header (lowercased, with units stripped or included) → Peer field name
_FIELD_MAP = {
    # CMP column
    "cmp rs.":          "current_price",
    "cmp":              "current_price",
    "current price":    "current_price",
    # P/E
    "p/e":              "pe_ratio",
    # Market cap
    "mar cap rs.cr.":   "market_cap",
    "mar cap":          "market_cap",
    # Dividend yield
    "div yld %":        "div_yield",
    "div yield":        "div_yield",
    # Net profit (quarterly)
    "np qtr rs.cr.":    "net_profit_qtr",
    "net profit":       "net_profit_qtr",
    # Quarterly profit growth
    "qtr profit var %": "qtr_profit_var",
    # Sales (quarterly)
    "sales qtr rs.cr.": "sales_qtr",
    "sales qtr":        "sales_qtr",
    # Quarterly sales growth
    "qtr sales var %":  "qtr_sales_var",
    # ROCE
    "roce %":           "roce",
}


def build_company_url(ticker: str, consolidated: bool = True) -> str:
    variant = "consolidated" if consolidated else "standalone"
    return f"{BASE_URL}/company/{ticker.upper().strip()}/{variant}/"


def build_bare_url(ticker: str) -> str:
    """URL without a variant suffix — screener redirects to whichever variant exists."""
    return f"{BASE_URL}/company/{ticker.upper().strip()}/"


def fetch(
    client: ScreenerClient,
    ticker: str,
    consolidated: bool = True,
) -> PeerTable:
    """
    Fetch and parse the Peer Comparison table for *ticker*.

    Args:
        client:       An authenticated ScreenerClient instance.
        ticker:       NSE/BSE ticker symbol, e.g. "MCX", "RELIANCE".
        consolidated: Use consolidated financials (default True).

    Returns:
        A PeerTable dataclass with all peers and their metrics.
    """
    company_url = build_company_url(ticker, consolidated)

    # Step 1 — load company page to extract warehouseId
    page_resp = client.get(company_url)
    warehouse_id = _extract_warehouse_id(page_resp.text, ticker)

    # Step 2 — call the peers API (returns an HTML fragment)
    peers_api_url = f"{BASE_URL}/api/company/{warehouse_id}/peers/"
    api_resp = client.get(peers_api_url)

    return _parse(api_resp.text, ticker, company_url)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _extract_warehouse_id(html: str, ticker: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    info = soup.find(id="company-info")
    if not info or not isinstance(info, Tag):
        raise ValueError(
            f"Could not find #company-info on the page for '{ticker}'. "
            "The ticker may be invalid."
        )
    wid = info.get("data-warehouse-id")
    if not wid:
        raise ValueError(
            f"data-warehouse-id missing for '{ticker}'. "
            "The page layout may have changed."
        )
    return wid


def _parse(html: str, ticker: str, source_url: str) -> PeerTable:
    soup = BeautifulSoup(html, "lxml")

    table = soup.find("table")
    if not isinstance(table, Tag):
        raise ValueError(
            f"No table found in peers API response for '{ticker}'. "
            "The API response format may have changed."
        )

    headers = _parse_headers(table)
    rows    = _parse_rows(table, headers)

    return PeerTable(
        source_company=ticker.upper(),
        source_url=source_url,
        headers=headers,
        peers=rows,
    )


def _parse_headers(table: Tag) -> list[str]:
    # Headers live in the first <tr> inside <tbody> as <th> elements.
    # Each <th> may contain a nested <span> for units — include it.
    tbody = table.find("tbody") or table
    header_row = tbody.find("tr")
    if not header_row:
        return []
    return [th.get_text(separator=" ", strip=True) for th in header_row.find_all("th")]


def _parse_rows(table: Tag, headers: list[str]) -> list[Peer]:
    tbody = table.find("tbody") or table
    result: list[Peer] = []

    # Row layout: td[0]=S.No.  td[1]=Name(link)  td[2..]=metrics
    # Skip the first <tr> (header row of <th>s) and the <tfoot> median row.
    for tr in tbody.find_all("tr")[1:]:
        cells = tr.find_all("td")
        # Need at least S.No. + Name + one metric cell
        if len(cells) < 3:
            continue

        name_cell = cells[1]
        anchor    = name_cell.find("a")
        name      = anchor.get_text(strip=True) if anchor else name_cell.get_text(strip=True)
        href      = anchor["href"] if anchor and anchor.get("href") else ""

        if not name:
            continue

        peer = Peer(name=name, url=href)
        # metric cells start at cells[2], aligned to headers[2:]
        _fill_fields(peer, cells[2:], headers[2:])
        result.append(peer)

    return result


def _fill_fields(peer: Peer, cells: list[Tag], headers: list[str]) -> None:
    for idx, cell in enumerate(cells):
        if idx >= len(headers):
            break
        key   = headers[idx].lower().strip()
        value = cell.get_text(strip=True) or None
        field = _FIELD_MAP.get(key)
        if field:
            setattr(peer, field, value)
        else:
            peer.extra[headers[idx]] = value
