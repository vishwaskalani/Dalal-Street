from dataclasses import dataclass, field
from typing import Optional


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
