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
class ShareholdingChange:
    """
    A company's shareholding pattern for its latest reported quarter versus the
    quarter before it, parsed from the shareholding-pattern section.

    Percentages are floats (e.g. 26.07 for "26.07%"); None when a value is
    missing or the section could not be parsed. `shareholders_*` is a plain
    count, not a percentage.
    """
    name: str
    url: str                              # screener.in relative URL, e.g. /company/MCX/
    latest_quarter: Optional[str] = None  # e.g. "Sep 2026" — newest column present
    prev_quarter: Optional[str] = None    # the column immediately before it
    promoter_latest: Optional[float] = None
    promoter_prev: Optional[float] = None
    fii_latest: Optional[float] = None
    fii_prev: Optional[float] = None
    dii_latest: Optional[float] = None
    dii_prev: Optional[float] = None
    government_latest: Optional[float] = None
    government_prev: Optional[float] = None
    public_latest: Optional[float] = None
    public_prev: Optional[float] = None
    shareholders_latest: Optional[float] = None
    shareholders_prev: Optional[float] = None

    @staticmethod
    def _delta(latest: Optional[float], prev: Optional[float]) -> Optional[float]:
        if latest is None or prev is None:
            return None
        return round(latest - prev, 2)

    @property
    def promoter_change(self) -> Optional[float]:
        return self._delta(self.promoter_latest, self.promoter_prev)

    @property
    def fii_change(self) -> Optional[float]:
        return self._delta(self.fii_latest, self.fii_prev)

    @property
    def dii_change(self) -> Optional[float]:
        return self._delta(self.dii_latest, self.dii_prev)

    @property
    def government_change(self) -> Optional[float]:
        return self._delta(self.government_latest, self.government_prev)

    @property
    def public_change(self) -> Optional[float]:
        return self._delta(self.public_latest, self.public_prev)

    @property
    def shareholders_change(self) -> Optional[float]:
        return self._delta(self.shareholders_latest, self.shareholders_prev)

    @property
    def fii_dii_change(self) -> Optional[float]:
        """Combined FII + DII move; None only when both legs are missing."""
        legs = [c for c in (self.fii_change, self.dii_change) if c is not None]
        return round(sum(legs), 2) if legs else None

    @property
    def fii_increased(self) -> bool:
        c = self.fii_change
        return c is not None and c > 0

    @property
    def dii_increased(self) -> bool:
        c = self.dii_change
        return c is not None and c > 0

    def __str__(self) -> str:
        def fmt(v: Optional[float], sign: bool = False) -> str:
            if v is None:
                return "—"
            return f"{v:+.2f}" if sign else f"{v:.2f}"
        return (
            f"{self.name:<28}  {self.latest_quarter or '—':>9}  "
            f"Prom {fmt(self.promoter_latest):>6} ({fmt(self.promoter_change, True):>6})  "
            f"FII {fmt(self.fii_latest):>6} ({fmt(self.fii_change, True):>6})  "
            f"DII {fmt(self.dii_latest):>6} ({fmt(self.dii_change, True):>6})  "
            f"Pub {fmt(self.public_latest):>6} ({fmt(self.public_change, True):>6})"
        )


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
