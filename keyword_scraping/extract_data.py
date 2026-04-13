import requests
from bs4 import BeautifulSoup
import re
import json
from urllib.parse import urljoin

from ddgs_search import get_urls

def extract_contact_info(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        full_text = soup.get_text(separator=" ")

        data = {
            "name": None,
            "website": url,
            "email": [],
            "phone": [],
            "address": [],
            "logo_url": None
        }

        # 1. JSON-LD Structured Data (best source)
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                ld = json.loads(script.string)
                if isinstance(ld, dict) and ld.get("@type") in ["Organization", "AutoDealer", "LocalBusiness"]:
                    data["name"] = ld.get("name") or data["name"]
                    data["email"] = ld.get("email") or data["email"]
                    if isinstance(data["email"], str):
                        data["email"] = [data["email"]]
                    
                    # Phone
                    tel = ld.get("telephone")
                    if tel:
                        data["phone"].append(tel)
                    # Address
                    addr = ld.get("address")
                    if isinstance(addr, dict):
                        data["address"] = f"{addr.get('streetAddress', '')}, {addr.get('addressLocality', '')}, {addr.get('addressRegion', '')} {addr.get('postalCode', '')}".strip()
                    # Logo
                    logo = ld.get("logo") or ld.get("image")
                    if isinstance(logo, dict):
                        logo = logo.get("url")
                    if logo:
                        data["logo_url"] = urljoin(url, logo) if isinstance(logo, str) else logo
            except:
                continue

        # 2. Regex fallback (very reliable for Nepal sites)
        # Email
        emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', full_text)
        data["email"] = list(set(data["email"] + emails))

        # Phone (Nepal formats: +977, 98xxxxxxxx, 01-xxx-xxxx)
        phones = re.findall(r'(\+977\s?)?[0-9]{1,3}[-.\s]?[0-9]{3,4}[-.\s]?[0-9]{3,4}', full_text)
        data["phone"] = list(set(data["phone"] + [p.strip() for p in phones if len(p.replace('+', '').replace('-', '').replace(' ', '')) >= 8]))

        # 3. Name & Address heuristics
        if not data["name"]:
            title_tag = soup.find("title")
            data["name"] = title_tag.string.strip().split("|")[0].strip() if title_tag else None

        if not data["address"]:
            # Look for common Nepal address patterns
            addr_match = re.search(r'(Tinkune|Kathmandu|Bagmati|Nepal)[\s\w,-]+(?:\d{5,6})?', full_text, re.I)
            if addr_match:
                data["address"] = addr_match.group(0).strip()

        # 4. Logo (fallback)
        if not data["logo_url"]:
            logo_img = (
                soup.find("img", attrs={"alt": re.compile("logo", re.I)}) or
                soup.find("img", class_=re.compile("logo", re.I)) or
                soup.find("link", rel=re.compile("icon", re.I))
            )
            if logo_img:
                src = logo_img.get("src") or logo_img.get("href")
                if src:
                    data["logo_url"] = urljoin(url, src)

        return data

    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return None

results = get_urls("hyndai")  
r = results[0]
print(r)
info = extract_contact_info(r[1])
print(info)