# Screener Scraping Utilities

Authenticated scraping tools for [screener.in](https://www.screener.in), built to grow with your research workflow.

---

## Setup

**1. Install dependencies**
```bash
pip install requests beautifulsoup4 lxml python-dotenv
```

**2. Create your `.env` file** in the `Dalal-Street/` root:
```bash
cp .env.example .env
# then edit .env with your screener.in credentials
```

```
SCREENER_USERNAME=your_email@example.com
SCREENER_PASSWORD=your_password
```

---

## Peer Comparison

Fetches the **Peer Comparison** table for any listed company — the same table you see on `screener.in/company/MCX/consolidated/`.

### Command line

Run from the `Dalal-Street/` root:

```bash
# Single ticker
python3 screener/run_peers.py MCX

# Multiple tickers in one shot (single login)
python3 screener/run_peers.py MCX RELIANCE HDFCBANK

# Use standalone financials instead of consolidated
python3 screener/run_peers.py MCX --standalone
```

**Example output:**
```
Peer Comparison — MCX
Source : https://www.screener.in/company/MCX/consolidated/
----------------------------------------------------------------------
BSE                             Price:    3851.90  PE:    63.13  MCap:    156887.53
Multi Comm. Exc.                Price:    3156.90  PE:    60.45  MCap:     80498.38
Indian Energy Ex                Price:     127.21  PE:    23.95  MCap:     11343.22
----------------------------------------------------------------------
Total peers: 3
```

### In your own script

```python
from screener import ScreenerClient, peers

client = ScreenerClient()  # reads .env automatically

# Fetch peers for a ticker
table = peers.fetch(client, "MCX")                      # consolidated (default)
table = peers.fetch(client, "MCX", consolidated=False)  # standalone

# Pretty print
print(table)

# Iterate over peers
for peer in table.peers:
    print(peer.name, peer.url, peer.pe_ratio, peer.market_cap)

# Access any column not mapped to a named field
for peer in table.peers:
    print(peer.extra)  # dict of remaining columns
```

### `Peer` fields

| Field | Screener column |
|---|---|
| `name` | Company name |
| `url` | screener.in relative URL |
| `current_price` | CMP (Rs.) |
| `pe_ratio` | P/E |
| `market_cap` | Mar Cap (Rs. Cr.) |
| `div_yield` | Div Yld % |
| `net_profit_qtr` | NP Qtr (Rs. Cr.) |
| `qtr_profit_var` | Qtr Profit Var % |
| `sales_qtr` | Sales Qtr (Rs. Cr.) |
| `qtr_sales_var` | Qtr Sales Var % |
| `roce` | ROCE % |
| `extra` | Any additional columns (dict) |

---

## Screens

Fetches every stock from a screener.in **screen** (saved query/filter) — handles pagination automatically so you always get the full list in one call.

### Command line

```bash
python3 screener/run_screen.py "https://www.screener.in/screens/3655407/good-results-debt-free/"
```

**Example output:**
```
Screen — Good Results Debt Free
URL    : https://www.screener.in/screens/3655407/good-results-debt-free/
----------------------------------------------------------------------
Tips Music                           CMP Rs.: 641.80  P/E: 37.85  Mar Cap Rs.Cr.: 8204.23  ...
Sanofi Consumer                      CMP Rs.: 4611.90  P/E: 42.01  Mar Cap Rs.Cr.: 10621.49  ...
...
----------------------------------------------------------------------
Total: 48 stocks
```

### In your own script

```python
from screener import ScreenerClient, screens

client = ScreenerClient()  # reads .env automatically

url = "https://www.screener.in/screens/3655407/good-results-debt-free/"
result = screens.fetch(client, url)

# Pretty print
print(result)

# Iterate over stocks
for stock in result.stocks:
    print(stock.name, stock.url)
    print(stock.metrics.get("P/E"), stock.metrics.get("ROCE %"))
```

### `ScreenStock` fields

| Field | Description |
|---|---|
| `name` | Company name |
| `url` | screener.in relative URL |
| `metrics` | Dict of all columns → values (varies per screen) |

Since each screen has user-defined columns, all metric values live in `stock.metrics` keyed by the exact column header (e.g. `"CMP Rs."`, `"P/E"`, `"ROCE %"`). Use `result.headers` to see the full ordered list of columns for a given screen.

---

## Screen → Peers (composite tool)

Combines the screen scraper and peer scraper: fetches every stock in a screen, then fetches the Peer Comparison table for each one.  Output is a flat CSV with one row per (screen stock, peer) pair.

### Command line

```bash
# CSV to stdout
python3 screener/run_screen_peers.py "https://www.screener.in/screens/3655407/good-results-debt-free/"

# Save to a file
python3 screener/run_screen_peers.py "https://www.screener.in/screens/3655407/good-results-debt-free/" -o peers.csv

# Use standalone financials
python3 screener/run_screen_peers.py "https://www.screener.in/screens/3655407/good-results-debt-free/" --standalone
```

Progress (stocks found, peers per stock) is printed to **stderr** so it doesn't pollute the CSV on stdout.

### In your own script

```python
from screener import ScreenerClient, screen_peers

client = ScreenerClient()

rows = screen_peers.fetch(
    client,
    "https://www.screener.in/screens/3655407/good-results-debt-free/",
    consolidated=True,
    on_progress=print,   # optional live progress
)

# Write CSV to a file
with open("peers.csv", "w", newline="") as f:
    screen_peers.to_csv(rows, file=f)

# Or get a CSV string
csv_str = screen_peers.to_csv(rows)

# Iterate directly
for row in rows:
    print(row.screen_stock_name, "→", row.peer_name, row.pe_ratio)
```

### `ScreenPeerRow` fields

| Field | Description |
|---|---|
| `screen_stock_name` | Name of the stock from the screen |
| `screen_stock_ticker` | Ticker extracted from its screener.in URL |
| `peer_name` | Name of the peer company |
| `peer_ticker` | Ticker of the peer |
| `current_price` | CMP (Rs.) |
| `pe_ratio` | P/E |
| `market_cap` | Mar Cap (Rs. Cr.) |
| `div_yield` | Div Yld % |
| `net_profit_qtr` | NP Qtr (Rs. Cr.) |
| `qtr_profit_var` | Qtr Profit Var % |
| `sales_qtr` | Sales Qtr (Rs. Cr.) |
| `qtr_sales_var` | Qtr Sales Var % |
| `roce` | ROCE % |
| `extra` | Any additional peer columns (dict) |

Stocks where peer fetching fails are skipped with a stderr warning — the rest of the run continues.

---

## Adding a new utility

1. Create `screener/<utility_name>.py`
2. Accept a `ScreenerClient` as the first argument — auth is handled for you, and a single client shares one login across all calls
3. Compose from existing modules (`screens`, `peers`, `screen_peers`) or call `client.get(url)` directly
4. Return typed data (add new dataclasses to `models.py` if needed)
5. Add a runner script at `screener/run_<utility_name>.py` following the same pattern

The `ScreenerClient` maintains a single session, so chaining multiple utilities in one script costs only one login.

claude --resume e8b63155-44a8-42e0-a4c0-339a7e1a328c
