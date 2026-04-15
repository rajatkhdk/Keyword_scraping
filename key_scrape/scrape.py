from googlesearch import search

query = "hyundai Nepal official website"

for url in search(query, num_results=1, sleep_interval=5):
    print(url)