import re
from urllib.parse import urljoin, urlparse
import json
import asyncio
import requests
from bs4 import BeautifulSoup, NavigableString, Tag
from playwright.sync_api import sync_playwright

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

def extract_address(text):
    pass

# # searches for brand logo in navbar, footer
# def extract_logo(soup, base_url: str):
    
#     def to_full_url(src):
#         if not src or src.startswith(("data:", "blob:", "javascript:")):
#         # if not src:
#             return None
        
#         return urljoin(base_url, src)

#     # ── 0. META TAG (MOST RELIABLE) ─────────────────────────────
#     # og = soup.find("meta", property="og:image")
#     # if og and og.get("content"):
#     #     return to_full_url(og["content"])

#     # ── 1. Navbar: find img inside header/nav ─────────────────────
#     for tag in soup.find_all(["header", "nav"]):
#         img = tag.find("img", src=True)
#         if img:
#             return to_full_url(img["src"])

#         # 2. Try logo-like div/span
#         for el in tag.find_all(True):  # all elements
#             attrs = " ".join([
#                 " ".join(el.get("class", [])),
#                 el.get("id", "")
#             ]).lower()

#             if "logo" in attrs:
                
#                 # check inline style
#                 style = el.get("style", "")
#                 if "url(" in style:
#                     match = re.search(r'url\(["\']?(.*?)["\']?\)', style)
#                     if match:
#                         return to_full_url(match.group(1))

#     # ── 2. Any tag whose class/id/alt contains "logo" ─────────────
#     for img in soup.find_all("img", src=True):
#         attrs = " ".join([
#             " ".join(img.get("class", [])),
#             img.get("id", ""),
#             img.get("alt", ""),
#             img.get("src", "")
#         ]).lower()

#         if "logo" in attrs:
#             return to_full_url(img["src"])

#     # ── 3. CSS background-image logos ───────────────────────────
#     for tag in soup.find_all(style=True):
#         style = tag["style"].lower()

#         if "logo" in style and "url(" in style:
#             match = re.search(r'url\(["\']?(.*?)["\']?\)', style)
#             if match:
#                 return to_full_url(match.group(1))

#     # ── 4. SVG / XMLNS logos ────────────────────────────────────
#     # Look for SVG with logo hints
#     for svg in soup.find_all("svg"):
#         attrs = " ".join([
#             " ".join(svg.get("class", [])),
#             svg.get("id", "")
#         ]).lower()

#         if "logo" in attrs:
#             return "SVG_LOGO_DETECTED"

#     # also check <use href="#logo">
#     use_tag = soup.find("use")
#     if use_tag and use_tag.get("href"):
#         return use_tag["href"]

#     # ── 5. Footer: find img inside footer ─────────────────────────
#     footer = soup.find("footer")
#     if footer:
#         img = footer.find("img", src=True)
#         if img:
#             return to_full_url(img["src"])

#     return None

def extract_logo_from_css(css_text, base_url):

    # Match full CSS blocks: selector { ... }
    blocks = re.findall(r'([^{]+)\{([^}]+)\}', css_text)

    for selector, body in blocks:
        selector_lower = selector.lower()

        # check if selector relates to logo
        if "logo" in selector_lower:

            # extract background or background-image url
            match = re.search(r'url\(["\']?(.*?)["\']?\)', body)
            if match:
                return urljoin(base_url, match.group(1))

    return None

# -----------------------------
# MAIN FUNCTION
# -----------------------------
def extract_logo(soup, base_url):

    # -----------------------------
    # helpers
    # -----------------------------
    def to_full_url(src):
        if not src or src.startswith(("data:", "blob:", "javascript:")):
            return None
        return urljoin(base_url, src)

    def safe_get(url):
        try:
            r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                return r.text
        except:
            pass
        return ""

    def score_img(img, context_bonus=0):
        attrs = " ".join([
            " ".join(img.get("class", [])),
            img.get("id", ""),
            img.get("alt", ""),
            img.get("src", "")
        ]).lower()

        score = 0

        if "logo" in attrs:
            score += 10
        if img.find_parent(["header", "nav"]):
            score += 3
        if context_bonus:
            score += context_bonus

        return score

    # -----------------------------
    # 1. META TAG (og:image fallback)
    # -----------------------------
    # og = soup.find("meta", property="og:image")
    # if og and og.get("content"):
    #     return to_full_url(og["content"])

    

    

    

    # -----------------------------
    # 5. INLINE CSS BACKGROUND LOGO
    # -----------------------------
    for tag in soup.find_all(style=True):
        style = tag["style"].lower()
        if "logo" in style and "url(" in style:
            match = re.search(r'url\(["\']?(.*?)["\']?\)', style)
            if match:
                return to_full_url(match.group(1))

    # -----------------------------
    # 6. EXTERNAL CSS (basic scan)
    # -----------------------------
    css_links = []
    for link in soup.find_all("link", rel="stylesheet"):
        href = link.get("href")
        if href:
            css_links.append(urljoin(base_url, href))

    for css_url in css_links[:5]:  # limit to avoid heavy scraping
        css_text = safe_get(css_url)
        print("CSS URL: ",css_url)
        if not css_text:
            print("No CSS Text: ",css_url)
            continue

        logo_url = extract_logo_from_css(css_text, css_url)

        if logo_url:
            print("Logo found:", logo_url)
            return logo_url

        # # find logo-related background images
        # matches = re.findall(r'url\(["\']?(.*?)["\']?\)', css_text)

        # # print("Matches : ",matches)

        # for m in matches:
        #     if "logo" in css_text.lower():
        #         print("Logo found: ",m)
        #         return to_full_url(m)
        
    # -----------------------------
    # 3. HEADER + NAV IMAGE CANDIDATES
    # -----------------------------
    candidates = []

    for tag in soup.find_all(["header", "nav"]):
        
        imgs = tag.find_all("img", src=True)
        for img in imgs:
            candidates.append((img, score_img(img, context_bonus=5)))

    # also global images
    for img in soup.find_all("img", src=True):
        candidates.append((img, score_img(img)))

    # pick best image
    if candidates:
        # print("Candidates : ", candidates)
        best_img = max(candidates, key=lambda x: x[1])[0]
        return to_full_url(best_img["src"])
    
    # -----------------------------
    # 2. SVG LOGO (sprite-safe)
    # -----------------------------
    for svg in soup.find_all("svg"):
        attrs = " ".join([
            " ".join(svg.get("class", [])),
            svg.get("id", "")
        ]).lower()

        use_tag = svg.find("use")
        if use_tag:
            href = use_tag.get("href") or use_tag.get("xlink:href")
            if href:
                # return structured SVG reference (safe fallback)
                if "logo" in attrs or "logo" in href.lower():
                    return f"SVG_SPRITE:{href}"
    # -----------------------------
    # 7. FOOTER IMAGE FALLBACK
    # -----------------------------
    footer = soup.find("footer")
    if footer:
        imgs = footer.find_all("img", src=True)
        if imgs:
            best_footer = max(imgs, key=lambda i: score_img(i))
            return to_full_url(best_footer["src"])

    
    # -----------------------------
    # 4. INLINE / CLASS-BASED LOGOS
    # -----------------------------
    for img in soup.find_all("img", src=True):
        attrs = " ".join([
            " ".join(img.get("class", [])),
            img.get("id", ""),
            img.get("alt", ""),
            img.get("src", "")
        ]).lower()

        if "logo" in attrs:
            return to_full_url(img["src"])
        
    # -----------------------------
    # NOTHING FOUND
    # -----------------------------
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
    socials = {key: set() for key in SOCIAL_PATTERNS}

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        full_url = urljoin(base_url, href)

        parsed = urlparse(full_url)
        domain = parsed.netloc.lower()

        # remove "www." if present
        if domain.startswith("www."):
            domain = domain[4:]

        for platform, domains in SOCIAL_PATTERNS.items():
            for d in domains:
                 if domain == d or domain.endswith("." + d): 

                    if any(bad in full_url for bad in BAD_SOCIAL_PATTERNS):
                        continue

                    socials[platform].add(full_url)

    # convert sets → list
    return {k: list(v) for k, v in socials.items()}

def fetch_dynamic_html(url):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)

            context = browser.new_context()
            page = context.new_page()

            # page = browser.new_page(
            #     user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
            # )
            
            page.goto(url, timeout=60000)
            page.wait_for_load_state("domcontentloaded")

            # ADD THIS
            page.wait_for_timeout(8000)  # wait extra 5 seconds

            # try to bypass redirect loop
            for _ in range(3):
                html = page.content()

                if "Please wait while your request is being verified" not in html:
                    break

                print("Still on challenge page... waiting")
                page.wait_for_timeout(5000)

            html = page.content()

            # if "Please wait while your request is being verified" in html:
            #     print("Bot protection detected, waiting...")
            #     page.wait_for_timeout(8000)
            #     html = page.content()

            browser.close()

            print("inside dynamic fetch")
            return html
    except Exception as e:
        print("Dynamic fetch error: ",e)
        return None
    
def fetch_static_html(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.text
    except Exception as e:
        print("Static fetch error: ", e)
        return None
    
def is_dynamic_page(html):
    if not html:
        return True

    # heuristics
    if len(html) < 2000:
        return True

    if "id=\"root\"" in html or "id=\"__next\"" in html:
        return True

    return False

# extracts the html from certain url and returns the text soup
def fetch_soup(url):
    html = fetch_static_html(url)
    
    # decide if we need JS rendering
    if is_dynamic_page(html):
        print("Using dynamic scraping (fetch_soup): ", url)
        html = fetch_dynamic_html(url)

    if not html:
        return None
    
    # with open("page4.html", "w", encoding="utf-8") as f:
    #     f.write(html)

    return BeautifulSoup(html, "html.parser")

# extracts the html from certain url and extracts the required info
def extract_basic_info(url):
    soup = fetch_soup(url)

    if not soup:
        return {
            "website": url,
            "phones": [],
            "emails": [],
            "logo": None,
            "facebook": [],
            "instagram": [],
            "twitter": [],
            "linkedin": [],
            "youtube": [],
            "tiktok": [],
        }
    
    text = soup.get_text(" ")

    # with open("page_text.txt", "w", encoding="utf-8") as f:
    #     f.write(text)

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