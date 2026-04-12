import requests
from bs4 import BeautifulSoup

url = "https://www.meroauto.com/"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://google.com",
    "Connection": "keep-alive"
}

response = requests.get(url, headers=headers)

response.encoding = 'utf-8'  # force correct encoding

with open("page1.html", "w", encoding="utf-8") as f:
    f.write(response.text)

