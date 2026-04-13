import re
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
import json
from ddgs_search import get_urls

def extract_phones(text):
    pattern = r'(\+?977[\s\-]?\d{9,10}|0\d{1,2}[\-\s]?\d{6,8}|9\d{9})'
    phones = re.findall(pattern, text)

    # normalize
    cleaned = []
    for p in phones:
        p = re.sub(r"[^\d+]", "", p)
        if len(p) >= 8:
            cleaned.append(p)

    return list(set(cleaned))

def extract_emails(text):
    pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = re.findall(pattern, text)

    # filter junk
    return list(set([
        e for e in emails
        if not any(x in e for x in ["example", "test", "noreply"])
    ]))

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

def extract_internal_links(soup, base_url):
    links = set()
    base_domain = urlparse(base_url).netloc

    for a in soup.find_all("a", href=True):
        href = a['href']
        full_url = urljoin(base_url, href)

        if urlparse(full_url).netloc == base_domain:
            links.add(full_url)

    return list(links)

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

def get_pages_to_scrape(homepage_soup, base_url):
    links = extract_internal_links(homepage_soup, base_url)
    filtered = [l for l in links if is_important(l)]
    ranked = rank_links(filtered)

    return ranked[:5]  # limit crawl depth

def extract_basic_info(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers, timeout=10)

    soup = BeautifulSoup(resp.text, "lxml")
    text = soup.get_text(" ")

    phones = extract_phones(text)
    emails = extract_emails(text)
    logo = extract_logo(soup, url)

    return {
        "website": url,
        "phones": phones,
        "emails": emails,
        "logo": logo
    }

def fetch_soup(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers, timeout=10)

    return BeautifulSoup(resp.text, "lxml")

# PAGES = ["", "/contact", "/contact-us", "/about"]

# for p in PAGES:
#     full_url = urljoin(base_url, p)

# def extract_internal_links(soup, base_url):
#     links = set()

#     for tag in soup.find_all("a", href=True):
#         href = tag["href"]

#         full_url = urljoin(base_url, href)

#         # keep only same domain links
#         if base_url.split("//")[1].split("/")[0] in full_url:
#             links.add(full_url)

#     return list(links)

results = get_urls("bmw")  
r = results[0]
# print("Result 1: ",r)
# info = extract_basic_info(r[1])
# print(info)

base_url = r[1]

homepage_soup = fetch_soup(base_url)

pages = get_pages_to_scrape(homepage_soup, base_url)

# include homepage itself
pages = [base_url] + pages

all_phones = []
all_emails = []
logo = None

for page in pages:
    print(f"Scraping: {page}")

    try:
        data = extract_basic_info(page)

        all_phones.extend(data["phones"])
        all_emails.extend(data["emails"])

        # keep first valid logo
        if not logo and data["logo"]:
            logo = data["logo"]

    except Exception as e:
        print(f"Error: {e}")

final_data = {
    "website": base_url,
    "phones": list(set(all_phones)),
    "emails": list(set(all_emails)),
    "logo": logo
}

print(final_data)