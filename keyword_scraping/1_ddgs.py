from ddgs import DDGS

with DDGS() as ddgs:
    results = list(ddgs.text("BMW Nepal official website", max_results=5))

for r in results:
    print(r["href"])