from urllib.parse import urlparse

url = "https://www.tiktok.com/@hyundainepalofficial"

print( urlparse(url).netloc.lower())