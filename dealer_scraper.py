# """
# Nepal Car Dealer Scraper
# Extracts dealer name, address, phone from car brand websites.
# Handles: static HTML, JS-rendered pages, tables, cards, lists, and API interception.

# Requirements:
#     pip install playwright beautifulsoup4 requests lxml
#     playwright install chromium
# """

# import re
# import json
# import time
# import asyncio
# from urllib.parse import urljoin, urlparse
# from bs4 import BeautifulSoup
# from playwright.async_api import async_playwright


# # ─────────────────────────────────────────────
# # REGEX PATTERNS
# # ─────────────────────────────────────────────

# PHONE_PATTERNS = [
#     # Nepal numbers: 01-XXXXXXX, 9XXXXXXXXX, +977-XX-XXXXXXX
#     r'\+977[\s\-]?\d{2}[\s\-]?\d{6,7}',
#     r'\b01[\s\-]?\d{7}\b',                  # Kathmandu landline
#     r'\b0\d{2}[\s\-]?\d{6,7}\b',            # Other city landlines
#     r'\b9[78]\d{8}\b',                       # Mobile (98XXXXXXXX, 97XXXXXXXX)
#     r'\b9[0-9]{9}\b',                        # General 10-digit mobile
# ]

# EMAIL_PATTERN = r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'

# # Keywords that hint a container holds dealer info
# DEALER_KEYWORDS = [
#     'dealer', 'showroom', 'outlet', 'branch', 'service center',
#     'authorized', 'distributor', 'contact', 'location', 'address'
# ]

# # ─────────────────────────────────────────────
# # UTILITIES
# # ─────────────────────────────────────────────

# def extract_phones(text: str) -> list[str]:
#     found = []
#     for pattern in PHONE_PATTERNS:
#         matches = re.findall(pattern, text)
#         found.extend(matches)
#     # Deduplicate while preserving order
#     seen = set()
#     result = []
#     for p in found:
#         clean = re.sub(r'[\s\-]', '', p)
#         if clean not in seen:
#             seen.add(clean)
#             result.append(p.strip())
#     return result


# def extract_emails(text: str) -> list[str]:
#     return list(set(re.findall(EMAIL_PATTERN, text)))


# def clean_text(text: str) -> str:
#     return re.sub(r'\s+', ' ', text).strip()


# def score_dealer_container(text: str) -> int:
#     """Score how likely a block of text is a dealer entry."""
#     text_lower = text.lower()
#     score = 0
#     for kw in DEALER_KEYWORDS:
#         if kw in text_lower:
#             score += 2
#     if extract_phones(text):
#         score += 5
#     if re.search(r'\b(kathmandu|pokhara|lalitpur|bhaktapur|chitwan|biratnagar|butwal|narayanghat|hetauda|dharan)\b', text_lower):
#         score += 3
#     return score


# # ─────────────────────────────────────────────
# # STRATEGY 1: Parse static / rendered HTML
# # ─────────────────────────────────────────────

# def parse_dealers_from_html(html: str, base_url: str = '') -> list[dict]:
#     """
#     Tries multiple sub-strategies to extract dealer cards from HTML.
#     Returns a list of dealer dicts.
#     """
#     soup = BeautifulSoup(html, 'lxml')
#     dealers = []

#     # Remove noise
#     for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
#         tag.decompose()

#     # ── Sub-strategy A: Table rows ──
#     dealers += _parse_tables(soup)

#     # ── Sub-strategy B: Repeated card/block elements ──
#     if not dealers:
#         dealers += _parse_card_blocks(soup)

#     # ── Sub-strategy C: List items ──
#     if not dealers:
#         dealers += _parse_lists(soup)

#     # ── Sub-strategy D: Fallback — scan all text blocks ──
#     if not dealers:
#         dealers += _parse_generic_blocks(soup)

#     return dealers


# def _parse_tables(soup) -> list[dict]:
#     dealers = []
#     for table in soup.find_all('table'):
#         headers = [clean_text(th.get_text()) for th in table.find_all('th')]
#         for row in table.find_all('tr'):
#             cells = [clean_text(td.get_text()) for td in row.find_all('td')]
#             if not cells:
#                 continue
#             if len(cells) < 2:
#                 continue
#             dealer = _build_dealer_from_cells(headers, cells)
#             if dealer:
#                 dealers.append(dealer)
#     return dealers


# def _build_dealer_from_cells(headers: list, cells: list) -> dict | None:
#     """Map table cells to dealer fields using header names."""
#     dealer = {'name': '', 'address': '', 'phone': [], 'email': []}
#     all_text = ' '.join(cells)

#     phones = extract_phones(all_text)
#     emails = extract_emails(all_text)
#     if not phones and not emails:
#         return None  # Probably not a dealer row

#     # Try to map by headers
#     for i, header in enumerate(headers):
#         if i >= len(cells):
#             break
#         h = header.lower()
#         val = cells[i]
#         if any(k in h for k in ['name', 'dealer', 'showroom', 'outlet']):
#             dealer['name'] = val
#         elif any(k in h for k in ['address', 'location', 'city']):
#             dealer['address'] = val
#         elif any(k in h for k in ['phone', 'tel', 'mobile', 'contact']):
#             dealer['phone'] = extract_phones(val) or extract_phones(all_text)
#         elif any(k in h for k in ['email', 'mail']):
#             dealer['email'] = extract_emails(val)

#     # Fallback: first cell is usually name
#     if not dealer['name'] and cells:
#         dealer['name'] = cells[0]
#     if not dealer['address'] and len(cells) > 1:
#         dealer['address'] = cells[1]
#     if not dealer['phone']:
#         dealer['phone'] = phones
#     if not dealer['email']:
#         dealer['email'] = emails

#     return dealer if dealer['name'] or dealer['phone'] else None


# def _parse_card_blocks(soup) -> list[dict]:
#     """Look for repeated sibling elements that look like dealer cards."""
#     dealers = []
#     candidates = []

#     # Common card container selectors
#     for selector in [
#         '[class*="dealer"]', '[class*="showroom"]', '[class*="location"]',
#         '[class*="branch"]', '[class*="outlet"]', '[class*="card"]',
#         '[class*="store"]', '[class*="contact"]', 'article', '.item'
#     ]:
#         try:
#             elements = soup.select(selector)
#         except Exception:
#             continue
#         if len(elements) >= 2:
#             candidates.extend(elements)

#     seen_texts = set()
#     for el in candidates:
#         text = clean_text(el.get_text(separator=' '))
#         if text in seen_texts or len(text) < 20:
#             continue
#         seen_texts.add(text)
#         if score_dealer_container(text) < 3:
#             continue
#         dealer = _extract_dealer_from_block(el, text)
#         if dealer:
#             dealers.append(dealer)

#     return dealers


# def _parse_lists(soup) -> list[dict]:
#     dealers = []
#     for ul in soup.find_all(['ul', 'ol']):
#         items = ul.find_all('li')
#         if len(items) < 2:
#             continue
#         for li in items:
#             text = clean_text(li.get_text(separator=' '))
#             if score_dealer_container(text) < 3:
#                 continue
#             dealer = _extract_dealer_from_block(li, text)
#             if dealer:
#                 dealers.append(dealer)
#     return dealers


# def _parse_generic_blocks(soup) -> list[dict]:
#     """Last resort: find any div/section with phone numbers."""
#     dealers = []
#     seen = set()
#     for tag in soup.find_all(['div', 'section', 'p']):
#         text = clean_text(tag.get_text(separator=' '))
#         if text in seen or len(text) < 30 or len(text) > 800:
#             continue
#         seen.add(text)
#         phones = extract_phones(text)
#         if not phones:
#             continue
#         dealer = {
#             'name': _guess_name_from_block(tag, text),
#             'address': _guess_address_from_text(text),
#             'phone': phones,
#             'email': extract_emails(text),
#         }
#         dealers.append(dealer)
#     return dealers


# def _extract_dealer_from_block(el, full_text: str) -> dict | None:
#     phones = extract_phones(full_text)
#     emails = extract_emails(full_text)

#     name = _guess_name_from_block(el, full_text)
#     address = _guess_address_from_text(full_text)

#     if not name and not phones:
#         return None

#     return {
#         'name': name,
#         'address': address,
#         'phone': phones,
#         'email': emails,
#     }


# def _guess_name_from_block(el, full_text: str) -> str:
#     # Look for heading tags inside the element
#     for heading in el.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'strong', 'b']):
#         name = clean_text(heading.get_text())
#         if name and len(name) < 100:
#             return name
#     # First line heuristic
#     lines = [l.strip() for l in full_text.splitlines() if l.strip()]
#     if lines:
#         candidate = lines[0]
#         # Skip if it looks like a phone number or address
#         if not extract_phones(candidate) and len(candidate) < 80:
#             return candidate
#     return ''


# def _guess_address_from_text(text: str) -> str:
#     # Look for Nepal city/district names
#     cities = [
#         'Kathmandu', 'Pokhara', 'Lalitpur', 'Bhaktapur', 'Chitwan',
#         'Biratnagar', 'Butwal', 'Narayanghat', 'Hetauda', 'Dharan',
#         'Birgunj', 'Janakpur', 'Dhangadhi', 'Nepalgunj', 'Itahari',
#         'Birtamod', 'Damak', 'Tansen', 'Baglung', 'Palpa'
#     ]
#     # Find sentences containing a city name
#     sentences = re.split(r'[,\n|•]', text)
#     for sent in sentences:
#         for city in cities:
#             if city.lower() in sent.lower():
#                 candidate = clean_text(sent)
#                 if len(candidate) < 200:
#                     return candidate
#     return ''


# # ─────────────────────────────────────────────
# # STRATEGY 2: Intercept XHR/Fetch API calls
# # ─────────────────────────────────────────────

# async def intercept_api_calls(url: str) -> list[dict]:
#     """
#     Load page with Playwright, intercept any JSON responses that look
#     like dealer/location data.
#     """
#     captured_dealers = []
#     api_responses = []

#     async with async_playwright() as p:
#         browser = await p.chromium.launch(headless=False)
#         context = await browser.new_context(
#             user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
#         )
#         page = await context.new_page()

#         async def handle_response(response):
#             try:
#                 content_type = response.headers.get('content-type', '')
#                 if 'json' in content_type:
#                     body = await response.json()
#                     text = json.dumps(body)
#                     # Check if it contains dealer-like data
#                     if any(k in text.lower() for k in ['dealer', 'showroom', 'phone', 'address', 'location']):
#                         api_responses.append({'url': response.url, 'data': body})
#             except Exception:
#                 pass

#         page.on('response', handle_response)

#         await page.goto(url, wait_until='networkidle', timeout=30000)
#         await page.wait_for_timeout(3000)  # Wait for lazy loads

#         # Also get the rendered HTML for static parsing
#         html = await page.content()

#         await browser.close()

#     # Try to parse captured API responses
#     for resp in api_responses:
#         dealers = _extract_dealers_from_json(resp['data'])
#         captured_dealers.extend(dealers)

#     return captured_dealers, html


# def _extract_dealers_from_json(data, depth=0) -> list[dict]:
#     """Recursively search JSON for objects with dealer-like fields."""
#     dealers = []
#     if depth > 5:
#         return dealers

#     if isinstance(data, list):
#         for item in data:
#             dealers.extend(_extract_dealers_from_json(item, depth + 1))
#     elif isinstance(data, dict):
#         keys_lower = {k.lower(): k for k in data.keys()}
#         # Check if this dict looks like a dealer record
#         has_phone = any(k in keys_lower for k in ['phone', 'tel', 'mobile', 'contact_no', 'phone_no'])
#         has_name = any(k in keys_lower for k in ['name', 'dealer', 'showroom', 'title'])
#         has_address = any(k in keys_lower for k in ['address', 'location', 'city', 'district'])

#         if has_phone or (has_name and has_address): # use or instead of and
#             dealer = {
#                 'name': '',
#                 'address': '',
#                 'phone': [],
#                 'email': [],
#             }
#             for field, keys in [
#                 ('name', ['name', 'dealer_name', 'showroom_name', 'title', 'dealer']),
#                 ('address', ['address', 'full_address', 'location', 'city', 'district']),
#                 ('phone', ['phone', 'phone_no', 'tel', 'mobile', 'contact_no', 'telephone']),
#                 ('email', ['email', 'email_address', 'mail']),
#             ]:
#                 for key in keys:
#                     if key in keys_lower:
#                         val = data[keys_lower[key]]
#                         if field in ('phone', 'email'):
#                             if isinstance(val, list):
#                                 dealer[field] = [str(v) for v in val]
#                             elif val:
#                                 dealer[field] = [str(val)]
#                         else:
#                             dealer[field] = str(val) if val else ''
#                         break

#             # Fallback phone extraction from stringified record
#             if not dealer['phone']:
#                 dealer['phone'] = extract_phones(json.dumps(data))

#             dealers.append(dealer)
#         else:
#             # Recurse into values
#             for v in data.values():
#                 dealers.extend(_extract_dealers_from_json(v, depth + 1))

#     return dealers


# # ─────────────────────────────────────────────
# # STRATEGY 3: Map / search bar interaction
# # ─────────────────────────────────────────────

# async def interact_map_or_search(url: str, search_queries: list[str] = None) -> list[dict]:
#     """
#     For sites with interactive maps or search bars:
#     - Clicks map markers to reveal popups
#     - OR submits search queries and parses results
#     """
#     dealers = []

#     async with async_playwright() as p:
#         browser = await p.chromium.launch(headless=True)
#         page = await browser.new_page()
#         await page.goto(url, wait_until='networkidle', timeout=30000)
#         await page.wait_for_timeout(2000)

#         # ── Try clicking map markers ──
#         marker_selectors = [
#             '.leaflet-marker-icon',
#             '[class*="marker"]',
#             '[class*="pin"]',
#             'img[src*="marker"]',
#             'img[src*="pin"]',
#             '[data-lat]',
#             '[data-lng]',
#         ]

#         for selector in marker_selectors:
#             try:
#                 markers = await page.query_selector_all(selector)
#                 if not markers:
#                     continue
#                 print(f"  Found {len(markers)} markers with selector: {selector}")
#                 for i, marker in enumerate(markers[:50]):  # Cap at 50
#                     try:
#                         await marker.click(timeout=3000)
#                         await page.wait_for_timeout(800)
#                         # Look for popup content
#                         popup_html = ''
#                         for popup_sel in ['.leaflet-popup-content', '[class*="popup"]', '[class*="tooltip"]', '[class*="infowindow"]']:
#                             popup = await page.query_selector(popup_sel)
#                             if popup:
#                                 popup_html = await popup.inner_html()
#                                 break
#                         if popup_html:
#                             soup = BeautifulSoup(popup_html, 'lxml')
#                             text = clean_text(soup.get_text(separator=' '))
#                             dealer = {
#                                 'name': _guess_name_from_block(soup, text),
#                                 'address': _guess_address_from_text(text),
#                                 'phone': extract_phones(text),
#                                 'email': extract_emails(text),
#                             }
#                             if dealer['name'] or dealer['phone']:
#                                 dealers.append(dealer)
#                     except Exception as e:
#                         continue
#                 if dealers:
#                     break
#             except Exception:
#                 continue

#         # ── Try search bar ──
#         if not dealers and search_queries:
#             search_selectors = [
#                 'input[type="search"]',
#                 'input[placeholder*="search" i]',
#                 'input[placeholder*="location" i]',
#                 'input[placeholder*="dealer" i]',
#                 'input[placeholder*="city" i]',
#                 '#search', '.search-input', '[name="search"]',
#             ]
#             for query in search_queries:
#                 for sel in search_selectors:
#                     try:
#                         inp = await page.query_selector(sel)
#                         if not inp:
#                             continue
#                         await inp.click()
#                         await inp.fill(query)
#                         await inp.press('Enter')
#                         await page.wait_for_timeout(2000)
#                         html = await page.content()
#                         new_dealers = parse_dealers_from_html(html)
#                         dealers.extend(new_dealers)
#                         break
#                     except Exception:
#                         continue

#         await browser.close()

#     return dealers


# # ─────────────────────────────────────────────
# # MAIN SCRAPER ORCHESTRATOR
# # ─────────────────────────────────────────────

# async def scrape_dealers(url: str, search_queries: list[str] = None) -> list[dict]:
#     """
#     Main entry point. Tries all strategies in order of reliability.
#     Returns a deduplicated list of dealer dicts.
#     """
#     print(f"\n{'='*60}")
#     print(f"Scraping: {url}")
#     print('='*60)

#     all_dealers = []

#     # Strategy 1 + 2: Load page, intercept APIs, parse rendered HTML
#     print("→ Strategy 1/2: Loading page & intercepting API calls...")
#     try:
#         api_dealers, html = await intercept_api_calls(url)
#         if api_dealers:
#             print(f"  ✓ Found {len(api_dealers)} dealers via API interception")
#             all_dealers.extend(api_dealers)
#         else:
#             print("  No JSON API data captured, parsing HTML...")
#             html_dealers = parse_dealers_from_html(html, url)
#             print(f"  ✓ Found {len(html_dealers)} dealers from HTML")
#             all_dealers.extend(html_dealers)
#     except Exception as e:
#         print(f"  ✗ Strategy 1/2 failed: {e}")

#     # Strategy 3: Map markers / search bar (if no dealers found yet)
#     if not all_dealers:
#         print("→ Strategy 3: Trying map markers / search bar interaction...")
#         nepal_cities = search_queries or [
#             'Kathmandu', 'Pokhara', 'Lalitpur', 'Chitwan',
#             'Biratnagar', 'Butwal', 'Dharan', 'Birgunj'
#         ]
#         try:
#             map_dealers = await interact_map_or_search(url, nepal_cities)
#             print(f"  ✓ Found {len(map_dealers)} dealers via map/search")
#             all_dealers.extend(map_dealers)
#         except Exception as e:
#             print(f"  ✗ Strategy 3 failed: {e}")

#     # Deduplicate by phone number
#     seen_phones = set()
#     unique_dealers = []
#     for d in all_dealers:
#         key = tuple(sorted(d.get('phone', []))) or d.get('name', '')
#         if key and key not in seen_phones:
#             seen_phones.add(key)
#             unique_dealers.append(d)

#     print(f"\n✅ Total unique dealers found: {len(unique_dealers)}")
#     return unique_dealers


# # ─────────────────────────────────────────────
# # CLI ENTRY POINT
# # ─────────────────────────────────────────────

# async def main():
#     import sys

#     # Example URLs for Nepal car brands — replace with actual URLs
#     test_urls = [
#         # "https://www.hyundai.com.np/dealers",
#         # "https://www.toyota.com.np/dealer-locator",
#         # "https://www.kia.com.np/find-a-dealer",
#     ]

#     if len(sys.argv) > 1:
#         test_urls = sys.argv[1:]

#     if not test_urls:
#         print("Usage: python dealer_scraper.py <url1> [url2] ...")
#         print("\nExample:")
#         print("  python dealer_scraper.py https://www.hyundai.com.np/dealers")
#         return

#     results = {}
#     for url in test_urls:
#         domain = urlparse(url).netloc
#         dealers = await scrape_dealers(url)
#         results[domain] = dealers

#         # Print results
#         print(f"\n── Dealers from {domain} ──")
#         for i, d in enumerate(dealers, 1):
#             print(f"\n[{i}] {d['name']}")
#             print(f"    Address : {d['address']}")
#             print(f"    Phone   : {', '.join(d['phone'])}")
#             print(f"    Email   : {', '.join(d['email'])}")

#     # Save to JSON
#     output_file = 'dealers_output.json'
#     with open(output_file, 'w', encoding='utf-8') as f:
#         json.dump(results, f, ensure_ascii=False, indent=2)
#     print(f"\n💾 Saved to {output_file}")


# if __name__ == '__main__':
#     asyncio.run(main())