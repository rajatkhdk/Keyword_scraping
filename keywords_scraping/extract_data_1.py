import re
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

# use regex to extract phone no.
def extract_phones(text):
    pattern = r'\b(\+?977[\s\-]?9[6-8]\d{8}|01[\-\s]?\d{7}|9[6-8]\d{8})\b'
    phones = re.findall(pattern, text)

    # normalize
    cleaned = []
    for p in phones:
        p = re.sub(r"[^\d+]", "", p)
        if len(p) >= 8:
            cleaned.append(p)

    return list(set(cleaned))

# uses regex to extract email
def extract_emails(text):
    pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = re.findall(pattern, text)

    # filter junk
    return list(set([
        e for e in emails
        if not any(x in e for x in ["example", "test", "noreply"])
    ]))

# searches for brand logo in navbar, footer
def extract_logo(soup, base_url: str):
    
    def to_full_url(src):
        if not src or src.startswith("data:"):
            return None
        return urljoin(base_url, src)

    # ── 1. Navbar: find img inside header/nav ─────────────────────
    for tag in soup.find_all(["header", "nav"]):
        img = tag.find("img", src=True)
        if img:
            return to_full_url(img["src"])

    # ── 2. Any tag whose class/id/alt contains "logo" ─────────────
    for img in soup.find_all("img", src=True):
        attrs = " ".join([
            " ".join(img.get("class", [])),
            img.get("id", ""),
            img.get("alt", ""),
            img.get("src", "")
        ]).lower()

        if "logo" in attrs:
            return to_full_url(img["src"])

    # ── 3. Footer: find img inside footer ─────────────────────────
    footer = soup.find("footer")
    if footer:
        img = footer.find("img", src=True)
        if img:
            return to_full_url(img["src"])

    # ── 4. Fallback: first img in body ────────────────────────────
    img = soup.find("img", src=True)
    if img:
        return to_full_url(img["src"])

    return None

# returns all the internal links -> < a href "...">
def extract_internal_links(soup, base_url):
    links = set()
    base_domain = urlparse(base_url).netloc

    for a in soup.find_all("a", href=True):
        href = a['href']
        full_url = urljoin(base_url, href)

        if urlparse(full_url).netloc == base_domain:
            links.add(full_url)

    return list(links)

# Check if the internal links contain the keywords that are most likely to have the required data
def is_important(url):
    KEYWORDS = [
    "contact",
    "about",
    "location",
    "showroom",
    "dealer",
    "distributor",
    "dealership",
    "map",
    "branch"
    ]

    url = url.lower()
    return any(k in url for k in KEYWORDS)

# rank all the internal links using scores prioritizing certain keywords
def rank_links(links):
    scored = []

    for url in links:
        score = 0

        if "contact" in url:
            score += 5
        if "dealer" in url:
            score += 4
        if "about" in url:
            score += 3
        if "location" in url:
            score += 3

        scored.append((score, url))

    scored.sort(reverse=True)
    return [url for score, url in scored]

# get internal link, checks if they are important and ranks them and returns top 5 links
def get_pages_to_scrape(homepage_soup, base_url):
    links = extract_internal_links(homepage_soup, base_url)
    filtered = [l for l in links if is_important(l)]
    ranked = rank_links(filtered)

    return ranked[:5]  # limit crawl depth

SOCIAL_PATTERNS = {
    "facebook": ["facebook.com"],
    "instagram": ["instagram.com"],
    "twitter": ["twitter.com", "x.com"],
    "linkedin": ["linkedin.com"],
    "youtube": ["youtube.com", "youtu.be"],
    "tiktok": ["tiktok.com"]
}

BAD_SOCIAL_PATTERNS = [
    "share",
    "intent",
    "sharer",
    "watch?",
    "status",
    "hashtag"
]

def extract_social_links(soup, base_url):
    socials = {
        "facebook": set(),
        "instagram": set(),
        "twitter": set(),
        "linkedin": set(),
        "youtube": set(),
        "tiktok": set()
    }

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        full_url = urljoin(base_url, href)

        for platform, domains in SOCIAL_PATTERNS.items():
            if any(domain in full_url for domain in domains):

                if any(bad in full_url for bad in BAD_SOCIAL_PATTERNS):
                    continue

                socials[platform].add(full_url)

    # convert sets → list
    return {k: list(v) for k, v in socials.items()}

# extracts the html from certain url and extracts the required info
def extract_basic_info(url):
    soup = fetch_soup(url)
    text = soup.get_text(" ")

    phones = extract_phones(text)
    emails = extract_emails(text)
    logo = extract_logo(soup, url)
    socials = extract_social_links(soup, url)

    return {
        "website": url,
        "phones": phones,
        "emails": emails,
        "logo": logo,
        
        "facebook": socials["facebook"],
        "instagram": socials["instagram"],
        "twitter": socials["twitter"],
        "linkedin": socials["linkedin"],
        "youtube": socials["youtube"],
        "tiktok": socials["tiktok"],
    }

# extracts the html from certain url and returns the text soup
def fetch_soup(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers, timeout=10)

    return BeautifulSoup(resp.text, "lxml")