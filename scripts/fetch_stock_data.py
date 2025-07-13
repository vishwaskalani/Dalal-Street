import requests, os

API_KEY = os.getenv('ALPHAVANTAGE_API_KEY', 'demo')
symbol = "IBM"
url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={symbol}&apikey={API_KEY}"
r = requests.get(url)
with open('data/raw/stock_data.json', 'w') as f:
    f.write(r.text)
