# Install dependencies if needed:
# pip install pytrends yfinance pandas matplotlib

import pandas as pd
import matplotlib.pyplot as plt
from pytrends.request import TrendReq
import yfinance as yf

pytrends = TrendReq(hl='en-IN', tz=330)

# Dictionary: Ticker -> Search Keyword
tickers = {
    "RELIANCE.NS": "Reliance Industries",
    "TCS.NS": "TCS",
    "INFY.NS": "Infosys",
    "ETERNAL.NS": "Zomato",
    "PAYTM.NS": "Paytm",
    "IRCTC.NS": "IRCTC",
    "TATAMOTORS.NS": "Tata Motors"
}

for ticker, keyword in tickers.items():
    print(f"\n=== {ticker} | {keyword} ===")
    
    # --- Step 1: Fetch Google Trends ---
    pytrends.build_payload([keyword], timeframe="today 1-m", geo="IN")
    trend_data = pytrends.interest_over_time()
    if trend_data.empty:
        print("No Google Trends data found.")
        continue

    trend_data = trend_data.drop(columns=["isPartial"])
    trend_data.rename(columns={keyword: "Search_Interest"}, inplace=True)

    # --- Step 2: Fetch Stock Data ---
    stock = yf.Ticker(ticker)
    stock_data = stock.history(period="1mo", interval="1d")[["Volume"]]

    # --- Step 3: Align Dates ---
    trend_data.index = trend_data.index.tz_localize(None)
    stock_data.index = stock_data.index.tz_localize(None)
    combined = pd.concat([trend_data, stock_data], axis=1).dropna()

    if combined.empty:
        print("No overlapping data to compare.")
        continue

    # --- Step 4: Correlation (same-day) ---
    correlation = combined["Search_Interest"].corr(combined["Volume"])
    print(f"Same-day Correlation: {correlation:.3f}")

    # --- Step 5: Lag Correlation (yesterday's searches vs today's volume) ---
    combined["Search_Interest_Lag1"] = combined["Search_Interest"].shift(1)
    lag_corr = combined["Search_Interest_Lag1"].corr(combined["Volume"])
    print(f"Lag-1 Correlation: {lag_corr:.3f}")

    # --- Step 6: Plot ---
    fig, ax1 = plt.subplots(figsize=(8, 4))
    ax1.set_xlabel("Date")
    ax1.set_ylabel("Search Interest", color="tab:blue")
    ax1.plot(combined.index, combined["Search_Interest"], color="tab:blue", label="Search Interest")
    ax1.tick_params(axis="y", labelcolor="tab:blue")

    ax2 = ax1.twinx()
    ax2.set_ylabel("Volume", color="tab:red")
    ax2.plot(combined.index, combined["Volume"], color="tab:red", alpha=0.6, label="Volume")
    ax2.tick_params(axis="y", labelcolor="tab:red")

    plt.title(f"{keyword} ({ticker}): Search Interest vs Volume\nSame-day Corr={correlation:.2f}, Lag-1 Corr={lag_corr:.2f}")
    plt.show()
