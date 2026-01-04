import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import warnings

# 1. Suppress the messy warnings from the library
warnings.simplefilter(action='ignore', category=FutureWarning)

def read_timeframes(filename="Timeframes.txt"):
    """Reads start date and duration from the text file."""
    params = {}
    try:
        with open(filename, 'r') as f:
            lines = f.readlines()
            for line in lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    params[key.strip()] = value.strip().replace('"', '')
        
        start_date = datetime.strptime(params['StartDate'], "%d-%m-%Y")
        duration = int(params['DurationInMonths'])
        return start_date, duration
    except FileNotFoundError:
        print(f"Error: {filename} not found.")
        exit()
    except Exception as e:
        print(f"Error parsing {filename}: {e}")
        exit()

def read_stocks(filename="Stocks.txt"):
    """Reads tickers and investment amounts."""
    portfolio = []
    try:
        with open(filename, 'r') as f:
            lines = f.readlines()
            for line in lines:
                parts = line.strip().split(',')
                if len(parts) >= 2: # Check >= 2 in case of extra commas
                    ticker = parts[0].strip()
                    amount = float(parts[1].strip())
                    portfolio.append({'Ticker': ticker, 'Invested_INR': amount})
        return portfolio
    except FileNotFoundError:
        print(f"Error: {filename} not found.")
        exit()

def get_avg_price_on_date(ticker, target_date):
    """
    Fetches OHLC data. 
    Tries NSE first (.NS), then BSE (.BO) if NSE fails.
    Returns (High + Low) / 2.
    """
    end_window = target_date + timedelta(days=7)
    
    # List of suffixes to try. If NSE fails, try BSE.
    suffixes_to_try = ['.NS', '.BO']
    
    for suffix in suffixes_to_try:
        yf_ticker = f"{ticker}{suffix}"
        
        try:
            # Added auto_adjust=True to handle splits/bonuses automatically
            # and prevent warnings.
            df = yf.download(yf_ticker, start=target_date, end=end_window, 
                           progress=False, auto_adjust=True)
            
            # If data is found, process it and break the loop
            if not df.empty:
                first_valid_day = df.iloc[0]
                actual_date = df.index[0].strftime("%Y-%m-%d")
                
                # Handle cases where data might be a Series or scalar
                high_price = float(first_valid_day['High'].iloc[0]) if isinstance(first_valid_day['High'], pd.Series) else float(first_valid_day['High'])
                low_price = float(first_valid_day['Low'].iloc[0]) if isinstance(first_valid_day['Low'], pd.Series) else float(first_valid_day['Low'])
                
                avg_price = (high_price + low_price) / 2
                return avg_price, actual_date

        except Exception:
            # If NSE fails, silently continue to the next iteration (BSE)
            continue
            
    # If both failed
    print(f"  > Warning: Could not fetch data for {ticker} (tried NSE & BSE)")
    return None, None

def run_backtest():
    print("--- Starting Backtest ---")
    
    start_date, duration_months = read_timeframes()
    portfolio_data = read_stocks()
    end_date = start_date + relativedelta(months=duration_months)
    
    print(f"Investment Period: {start_date.strftime('%d-%m-%Y')} to {end_date.strftime('%d-%m-%Y')}")
    print(f"Duration: {duration_months} Months")
    print("-" * 50)

    results = []
    total_invested = 0
    total_final_value = 0

    for item in portfolio_data:
        ticker = item['Ticker']
        invested = item['Invested_INR']
        
        buy_price, buy_date = get_avg_price_on_date(ticker, start_date)
        sell_price, sell_date = get_avg_price_on_date(ticker, end_date)
        
        if buy_price and sell_price:
            units_bought = invested / buy_price
            final_value = units_bought * sell_price
            abs_return = final_value - invested
            pct_return = (abs_return / invested) * 100
            
            total_invested += invested
            total_final_value += final_value
            
            results.append({
                'Ticker': ticker,
                'Invested': invested,
                'Buy_Date': buy_date,
                'Buy_Avg_Price': buy_price,
                'Sell_Date': sell_date,
                'Sell_Avg_Price': sell_price,
                'Final_Value': final_value,
                'Abs_Return': abs_return,
                'Pct_Return': pct_return
            })

    if not results:
        print("No valid data found.")
        return

    df_results = pd.DataFrame(results)
    
    best_stock = df_results.loc[df_results['Pct_Return'].idxmax()]
    worst_stock = df_results.loc[df_results['Pct_Return'].idxmin()]
    
    portfolio_abs_return = total_final_value - total_invested
    portfolio_pct_return = (portfolio_abs_return / total_invested) * 100

    print("\n" + "="*65)
    print("DETAILED BACKTEST REPORT")
    print("="*65)
    
    # Formatting for cleaner display
    display_cols = ['Ticker', 'Buy_Date', 'Buy_Avg_Price', 'Sell_Date', 'Sell_Avg_Price', 'Pct_Return']
    display_df = df_results[display_cols].copy()
    
    display_df['Buy_Avg_Price'] = display_df['Buy_Avg_Price'].map('{:,.2f}'.format)
    display_df['Sell_Avg_Price'] = display_df['Sell_Avg_Price'].map('{:,.2f}'.format)
    display_df['Pct_Return'] = display_df['Pct_Return'].map('{:,.2f}%'.format)
    
    # Adjust pandas display width to prevent wrapping
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    print(display_df.to_string(index=False, justify='right'))
    
    print("-" * 65)
    print(f"TOTAL INVESTED      : ₹ {total_invested:,.2f}")
    print(f"CURRENT PORTFOLIO   : ₹ {total_final_value:,.2f}")
    print(f"NET PROFIT/LOSS     : ₹ {portfolio_abs_return:,.2f}")
    print(f"PORTFOLIO CAGR/RET  : {portfolio_pct_return:.2f}%")
    print("-" * 65)
    print(f"BEST PERFORMER      : {best_stock['Ticker']} ({best_stock['Pct_Return']:.2f}%)")
    print(f"WORST PERFORMER     : {worst_stock['Ticker']} ({worst_stock['Pct_Return']:.2f}%)")
    print("="*65)

if __name__ == "__main__":
    run_backtest()