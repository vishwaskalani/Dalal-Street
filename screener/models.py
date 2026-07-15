from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class Peer:
    name: str
    url: str                          # screener.in relative URL e.g. /company/MCX/consolidated/
    current_price: Optional[str] = None
    pe_ratio: Optional[str] = None
    market_cap: Optional[str] = None  # in Cr
    div_yield: Optional[str] = None
    net_profit_qtr: Optional[str] = None
    qtr_profit_var: Optional[str] = None
    sales_qtr: Optional[str] = None
    qtr_sales_var: Optional[str] = None
    roce: Optional[str] = None
    extra: dict = field(default_factory=dict)  # absorbs any additional columns

    def __str__(self) -> str:
        return (
            f"{self.name:<30}  Price: {self.current_price or '—':>10}  "
            f"PE: {self.pe_ratio or '—':>8}  MCap: {self.market_cap or '—':>12}"
        )


@dataclass
class ScreenStock:
    name: str
    url: str                           # screener.in relative URL e.g. /company/INFY/
    metrics: dict[str, Any] = field(default_factory=dict)  # header → value, varies per screen

    def __str__(self) -> str:
        metrics_str = "  ".join(f"{k}: {v}" for k, v in self.metrics.items())
        return f"{self.name:<35}  {metrics_str}"


@dataclass
class ScreenResult:
    screen_name: str                   # human-readable name parsed from page title
    screen_url: str
    headers: list[str]                 # ordered column names
    stocks: list[ScreenStock]

    def __str__(self) -> str:
        lines = [
            f"Screen — {self.screen_name}",
            f"URL    : {self.screen_url}",
            f"{'—' * 70}",
        ]
        lines += [str(s) for s in self.stocks]
        lines.append(f"{'—' * 70}")
        lines.append(f"Total: {len(self.stocks)} stocks")
        return "\n".join(lines)


@dataclass
class UniquePeer:
    """A peer company, deduplicated across all screen stocks."""
    ticker: str
    name: str
    peer_of: list[str]                  # screen stock tickers this peer appeared under
    current_price: Optional[str] = None
    pe_ratio: Optional[str] = None
    market_cap: Optional[str] = None
    div_yield: Optional[str] = None
    net_profit_qtr: Optional[str] = None
    qtr_profit_var: Optional[str] = None
    sales_qtr: Optional[str] = None
    qtr_sales_var: Optional[str] = None
    roce: Optional[str] = None
    latest_quarter: Optional[str] = None   # e.g. "Mar 2026"
    results_pending: Optional[bool] = None


@dataclass
class PeerTable:
    source_company: str               # ticker used to fetch peers, e.g. "MCX"
    source_url: str
    headers: list[str]
    peers: list[Peer]

    def __str__(self) -> str:
        lines = [
            f"Peer Comparison — {self.source_company}",
            f"Source : {self.source_url}",
            f"{'—' * 70}",
        ]
        lines += [str(p) for p in self.peers]
        lines.append(f"{'—' * 70}")
        lines.append(f"Total peers: {len(self.peers)}")
        return "\n".join(lines)
