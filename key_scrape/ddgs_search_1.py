from ddgs import DDGS
from urllib.parse import urlparse

# Check if the brand name is present in the url
def brand_in_domain(url, brand):
    try:
        hostname = urlparse(url).netloc.lower()

        return brand.lower() in hostname

    except:
        return False

# Scores the url and returns the list of urls arranged in descending order of score
def find_best_url(results, brand):
    """Score each url and return the most likely official/local one"""

    # Keywords that suggest official
    PRIORITY_DOMAINS = [".com.np", ".org.np", ".net.np"]
    GOOD_SIGNALS = ["official"]
    BAD_SIGNALS = ["review", "compare", "blog", "news", "techlekh", "autoyas", "nepaldrives", "wikipedia", "facebook", "youtube", "instagram", "tiktok", "daraz"]

    scored = []

    for r in results:
        url = r["href"].lower()
        title = r["title"].lower()
        body = r["title"].lower()
        score = 0

        # Nepali domain:
        if any(d in url for d in PRIORITY_DOMAINS):
            score += 2
            # print(score)

        if brand_in_domain(url, brand):
            score += 5
            # print(score)

        # Bad signals:
        if any(b in url or b in title or b in body for b in BAD_SIGNALS):
            score -= 3
            # print(score)

        # Good signals
        if any(g in url for g in GOOD_SIGNALS):
            score += 3
            # print(score)

        # Prefer shorter URLs (official sites tend to be cleaner)
        score -= url.count("/") * 0.5
        # print(score)

        scored.append((score, url, title, body))

    # Sort by score descending
    scored.sort(reverse=True)
    return scored

# finds all the urls based on keyword and ranks them
def get_urls(brand):
    with DDGS() as ddgs:
        results = list(ddgs.text(f"{brand} Nepal official", max_results=15))

    ranked = find_best_url(results, brand)
    # for score, url, title, body in ranked:
    #     print(f"{score:.1f}  →  {url} \ntitle: {title} \nbosy: {body}")
        
    return ranked

    

# get_urls("hyundai")