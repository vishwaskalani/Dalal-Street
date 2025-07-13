import requests, os

API_KEY = os.getenv('NEWSAPI_KEY', 'demo')
url = f"https://newsapi.org/v2/top-headlines?category=business&apiKey={API_KEY}"
r = requests.get(url)
with open('data/raw/news.json', 'w') as f:
    f.write(r.text)
