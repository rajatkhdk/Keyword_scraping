"""
Nepal Car Dealer Scraper — v2
Strategy: Find phone numbers first, then walk UP the DOM to find the
          smallest enclosing block that also contains name + address.

Requirements:
    pip install playwright beautifulsoup4 lxml
    playwright install chromium
"""

import re
import json
import asyncio
from urllib.parse import urlparse
from bs4 import BeautifulSoup, NavigableString, Tag
from playwright.async_api import async_playwright


# ─────────────────────────────────────────────────────────────────────────────
# PHONE REGEX  (covers all common Nepal formats)
# ─────────────────────────────────────────────────────────────────────────────

_PHONE_RE = re.compile(
    r'(?:'
    # +977 country code variants
    r'\+977[\s\-./]?(?:\d[\s\-./]?){9,10}'
    r'|977[\s\-./]?(?:\d[\s\-./]?){9,10}'
    # 10-digit mobile (98x, 97x, 96x)
    r'|9[6-9]\d[\s\-./]?\d{3}[\s\-./]?\d{4}'
    # Landline with area code: 01-XXXXXXX / 021-XXXXXX / 071-XXXXXX
    r'|0\d{1,2}[\s\-./]\d{6,7}'
    # Plain 7-digit Kathmandu landline (4XXXXXX / 5XXXXXX)
    r'|[45]\d{6}'
    # Dash/space separated 7-digit blocks e.g. 441-2345
    r'|\b\d{3}[\s\-]\d{4}\b'
    r')',
    re.VERBOSE,
)

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')

# Nepal cities / districts
NEPAL_PLACES = re.compile(
    r'\b(kathmandu|pokhara|lalitpur|bhaktapur|chitwan|biratnagar|butwal|'
    r'narayanghat|hetauda|dharan|birgunj|janakpur|dhangadhi|nepalgunj|'
    r'itahari|birtamod|damak|tansen|baglung|palpa|surkhet|tulsipur|'
    r'ghorahi|bharatpur|siddharthanagar|lumbini|mahendranagar|'
    r'banepa|dhulikhel|panauti|kirtipur|madhyapur|thimi|'
    r'naxal|thamel|new road|putalisadak|koteshwor|kalanki|'
    r'chabahil|balaju|baneshwor|lazimpat|bagbazar|tinkune)\b',
    re.IGNORECASE,
)


def extract_phones(text: str) -> list[str]:
    raw = _PHONE_RE.findall(text)
    seen, result = set(), []
    for p in raw:
        key = re.sub(r'[\s\-./]', '', p)
        if len(key) >= 7 and key not in seen:
            seen.add(key)
            result.append(p.strip())
    return result


def extract_emails(text: str) -> list[str]:
    return list(set(EMAIL_RE.findall(text)))


def clean(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


# ─────────────────────────────────────────────────────────────────────────────
# CORE: Phone-anchored DOM walker
# ─────────────────────────────────────────────────────────────────────────────

BLOCK_TAGS = {'div', 'section', 'article', 'li', 'tr', 'td', 'aside',
              'figure', 'main', 'p', 'address'}

STOP_TAGS = {'body', 'html', 'form'}


def _text_of(tag: Tag) -> str:
    return clean(tag.get_text(separator=' '))


def _has_address_signal(text: str) -> bool:
    if NEPAL_PLACES.search(text):
        return True
    return bool(re.search(
        r'\b(road|marg|chowk|ward|tole|nagar|bazar|bazaar|'
        r'street|avenue|lane|chok|sadak|galli)\b', text, re.I
    ))


def _has_name_signal(text: str) -> bool:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for line in lines:
        if len(line) < 4 or len(line) > 120:
            continue
        if extract_phones(line):
            continue
        if re.match(r'[A-Z]', line):
            return True
    return False


def _score_block(tag: Tag, anchor_phones: set) -> float:
    """
    Score a candidate ancestor block.
    We want the SMALLEST block that still has name + address + phone.
    """
    text = _text_of(tag)

    # Must still contain the phone(s) we anchored on
    if not any(p in text for p in anchor_phones):
        return -1.0

    score = 0.0
    if _has_address_signal(text):
        score += 3.0
    if _has_name_signal(text):
        score += 2.0

    # Penalise overly large containers (too many phones = parent wrapping all cards)
    phones_found = extract_phones(text)
    if len(phones_found) > 5:
        score -= (len(phones_found) - 5) * 0.8

    # Prefer smaller blocks
    score -= len(text) / 4000

    return score


def _walk_up_to_card(phone_tag: Tag) -> Tag | None:
    """
    Walk from the phone-containing tag upward.
    Return the highest-scoring block-level ancestor that looks like a dealer card.
    """
    anchor_phones = set(extract_phones(_text_of(phone_tag)))
    candidates = []
    node = phone_tag.parent
    depth = 0

    while node and getattr(node, 'name', None) not in STOP_TAGS and depth < 15:
        if isinstance(node, Tag) and node.name in BLOCK_TAGS:
            s = _score_block(node, anchor_phones)
            if s > 0:
                candidates.append((s, depth, node))
        node = node.parent
        depth += 1

    if not candidates:
        return None

    # Best score wins; on tie prefer shallower (smaller block)
    candidates.sort(key=lambda x: (-x[0], x[1]))
    return candidates[0][2]


# ─────────────────────────────────────────────────────────────────────────────
# FIELD EXTRACTORS (run on the identified card block)
# ─────────────────────────────────────────────────────────────────────────────

def _extract_name(block: Tag) -> str:
    # 1. Heading / strong / bold tags
    for tag_name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'b']:
        for el in block.find_all(tag_name):
            t = clean(el.get_text())
            if t and len(t) < 120 and not extract_phones(t):
                return t

    # 2. First capitalised line that isn't phone/email/address
    for line in _text_of(block).splitlines():
        line = line.strip()
        if not line or len(line) < 3 or len(line) > 120:
            continue
        if extract_phones(line) or EMAIL_RE.search(line):
            continue
        if _has_address_signal(line) and len(line) > 10:
            continue
        if re.match(r'[A-Z]', line):
            return line
    return ''


def _extract_address(block: Tag) -> str:
    # 1. Semantic <address> tag
    addr_tag = block.find('address')
    if addr_tag:
        return clean(addr_tag.get_text())

    # 2. Element with address-hint class or microdata
    for el in block.find_all(True):
        cls = ' '.join(el.get('class', []))
        attr = el.get('itemprop', '') or el.get('data-type', '')
        if re.search(r'address|location|addr', cls + attr, re.I):
            t = clean(el.get_text())
            if t and len(t) < 300:
                return t

    # 3. Line containing a Nepal place name
    for line in _text_of(block).splitlines():
        line = line.strip()
        if _has_address_signal(line) and not extract_phones(line):
            return line

    return ''


def _block_to_dealer(block: Tag) -> dict:
    text = _text_of(block)
    return {
        'name':    _extract_name(block),
        'address': _extract_address(block),
        'phone':   extract_phones(text),
        'email':   extract_emails(text),
    }


# ─────────────────────────────────────────────────────────────────────────────
# HTML PARSER
# ─────────────────────────────────────────────────────────────────────────────

def parse_dealers_from_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, 'lxml')

    for tag in soup(['script', 'style', 'noscript', 'nav', 'footer', 'head']):
        tag.decompose()

    dealers = []
    used_block_ids: set[int] = set()

    # Iterate every tag; check only its OWN text (not children) for a phone
    for tag in soup.find_all(True):
        own_text = ''.join(
            str(s) for s in tag.children if isinstance(s, NavigableString)
        )
        if not extract_phones(own_text):
            continue

        card = _walk_up_to_card(tag)

        # Fallback: nearest block-level parent
        if card is None:
            node = tag
            while node and node.name not in BLOCK_TAGS:
                node = node.parent
            card = node

        if card is None or id(card) in used_block_ids:
            continue

        used_block_ids.add(id(card))
        dealer = _block_to_dealer(card)
        if dealer['phone']:
            dealers.append(dealer)

    # Deduplicate by normalised phone set
    seen, unique = set(), []
    for d in dealers:
        key = frozenset(re.sub(r'\D', '', p) for p in d['phone'])
        if key and key not in seen:
            seen.add(key)
            unique.append(d)

    return unique


# ─────────────────────────────────────────────────────────────────────────────
# JSON API INTERCEPTOR
# ─────────────────────────────────────────────────────────────────────────────

def _extract_dealers_from_json(data, depth=0) -> list[dict]:
    dealers = []
    if depth > 6:
        return dealers
    if isinstance(data, list):
        for item in data:
            dealers.extend(_extract_dealers_from_json(item, depth + 1))
    elif isinstance(data, dict):
        kl = {k.lower(): k for k in data}
        has_phone   = any(k in kl for k in ['phone','tel','mobile','contact_no','phone_no','telephone'])
        has_name    = any(k in kl for k in ['name','dealer','showroom','title'])
        has_address = any(k in kl for k in ['address','location','city','district'])
        if has_phone or (has_name and has_address):
            d = {'name': '', 'address': '', 'phone': [], 'email': []}
            for field, keys in [
                ('name',    ['name','dealer_name','showroom_name','title','dealer']),
                ('address', ['address','full_address','location','city','district']),
                ('phone',   ['phone','phone_no','tel','mobile','contact_no','telephone']),
                ('email',   ['email','email_address','mail']),
            ]:
                for key in keys:
                    if key in kl:
                        val = data[kl[key]]
                        if field in ('phone', 'email'):
                            d[field] = [str(val)] if val and not isinstance(val, list) else (val or [])
                        else:
                            d[field] = str(val) if val else ''
                        break
            if not d['phone']:
                d['phone'] = extract_phones(json.dumps(data))
            dealers.append(d)
        else:
            for v in data.values():
                dealers.extend(_extract_dealers_from_json(v, depth + 1))
    return dealers


# ─────────────────────────────────────────────────────────────────────────────
# PLAYWRIGHT LOADER
# ─────────────────────────────────────────────────────────────────────────────

async def _load_page(url: str):
    api_dealers = []
    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=False, slow_mo=300)
    context = await browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    )
    page = await context.new_page()

    async def on_response(resp):
        try:
            ct = resp.headers.get('content-type', '')
            if 'json' in ct:
                body = await resp.json()
                txt = json.dumps(body).lower()
                if any(k in txt for k in ['dealer','showroom','phone','address','location']):
                    api_dealers.extend(_extract_dealers_from_json(body))
        except Exception:
            pass

    page.on('response', on_response)
    await page.goto(url, wait_until='networkidle', timeout=30000)
    await page.wait_for_timeout(3000)
    # html = await page.content()
    # await browser.close()
    return page, browser, api_dealers, p


async def _try_map_and_search(url: str, queries: list[str]) -> list[dict]:
    dealers = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await page.wait_for_timeout(2000)

        for sel in ['.leaflet-marker-icon','[class*="marker"]','[class*="pin"]',
                    'img[src*="marker"]','[data-lat]']:
            markers = await page.query_selector_all(sel)
            if not markers:
                continue
            for marker in markers[:50]:
                try:
                    await marker.click(timeout=3000)
                    await page.wait_for_timeout(700)
                    for ps in ['.leaflet-popup-content','[class*="popup"]',
                                '[class*="infowindow"]','[class*="tooltip"]']:
                        popup = await page.query_selector(ps)
                        if popup:
                            dealers.extend(parse_dealers_from_html(await popup.inner_html()))
                            break
                except Exception:
                    pass
            if dealers:
                break

        if not dealers:
            for query in queries:
                for sel in ['input[type="search"]','input[placeholder*="search" i]',
                            'input[placeholder*="location" i]','#search','.search-input']:
                    try:
                        inp = await page.query_selector(sel)
                        if not inp:
                            continue
                        await inp.fill(query)
                        await inp.press('Enter')
                        await page.wait_for_timeout(2000)
                        dealers.extend(parse_dealers_from_html(await page.content()))
                        break
                    except Exception:
                        pass

        await browser.close()
    return dealers

async def interact_and_collect(page, api_dealers):
    print("→ Running generic UI exploration...")

    collected = []
    seen_api_count = len(api_dealers)

    selects = await page.query_selector_all("select")

    for select in selects:
        options = await select.query_selector_all("option")

        for opt in options:
            try:
                text = (await opt.inner_text()).strip().lower()

                # skip useless options
                if not text or len(text) < 3:
                    continue
                if any(k in text for k in ["select", "sort", "filter", "date"]):
                    continue

                print(f"[UI] Trying option: {text}")

                value = await opt.get_attribute("value")
                await select.select_option(value=value)

                # CRITICAL: trigger possible UI updates
                await page.wait_for_timeout(1000)

                # Try clicking ALL visible buttons
                buttons = await page.query_selector_all("button")

                for btn in buttons:
                    try:
                        label = (await btn.inner_text()).lower()

                        if any(k in label for k in ["search", "find", "go", "submit"]):
                            print(f"[UI] Clicking button: {label}")
                            await btn.click()
                            await page.wait_for_load_state("networkidle")
                            await page.wait_for_timeout(1500)
                            break
                    except:
                        continue

                # Detect NEW API data
                if len(api_dealers) > seen_api_count:
                    new_items = api_dealers[seen_api_count:]
                    print(f"[UI] +{len(new_items)} new dealers from API")
                    collected.extend(new_items)
                    seen_api_count = len(api_dealers)

                # Also parse updated HTML
                html = await page.content()
                html_dealers = parse_dealers_from_html(html)
                collected.extend(html_dealers)

            except Exception as e:
                print(f"[UI] skip error: {e}")
                continue

    return collected
# ─────────────────────────────────────────────────────────────────────────────
# ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────

async def scrape_dealers(url: str, search_queries: list[str] | None = None) -> list[dict]:
    print("URL : ", url)
    print(f"\n{'='*60}\nScraping: {url}\n{'='*60}")

    queries = search_queries or [
        'Kathmandu','Pokhara','Lalitpur','Chitwan',
        'Biratnagar','Butwal','Dharan','Birgunj',
    ]

    print("→ Loading page & intercepting API calls...")
    page, browser, api_dealers, p = await _load_page(url)

    # ─────────────────────────────────────────────
    # STEP 1: UI INTERACTION (IMPORTANT FIX)
    # ─────────────────────────────────────────────
    print("→ Running UI interactions...")
    ui_dealers = await interact_and_collect(page, api_dealers)

    # wait for final JS updates
    await page.wait_for_timeout(3000)

    # ─────────────────────────────────────────────
    # STEP 2: FINAL HTML SNAPSHOT
    # ─────────────────────────────────────────────
    html = await page.content()

    # close browser safely
    await browser.close()
    await p.stop()

    # ─────────────────────────────────────────────
    # STEP 3: COLLECT DATA
    # ─────────────────────────────────────────────

    dealers = []

    print(f"  ✓ API dealers: {len(api_dealers)}")
    dealers.extend(api_dealers)

    print(f"  ✓ UI dealers: {len(ui_dealers)}")
    dealers.extend(ui_dealers)

    html_dealers = parse_dealers_from_html(html)
    print(f"  ✓ HTML dealers: {len(html_dealers)}")
    dealers.extend(html_dealers)

    # fallback only if NOTHING worked
    if not dealers:
        print("→ Trying map/search fallback...")
        dealers = await _try_map_and_search(url, queries)
        print(f"  ✓ {len(dealers)} dealers from map/search")

    # ─────────────────────────────────────────────
    # STEP 4: CLEAN DEDUPLICATION (VERY IMPORTANT FIX)
    # ─────────────────────────────────────────────

    seen = set()
    unique = []

    for d in dealers:
        phone_key = tuple(sorted(
            re.sub(r'\D', '', p) for p in d.get('phone', [])
        ))

        name_key = d.get('name', '').strip().lower()

        key = phone_key if phone_key else (name_key,)

        if key in seen:
            continue

        seen.add(key)
        unique.append(d)

    print(f"\n✅ Total unique dealers: {len(unique)}")
    return unique


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    import sys
    urls = sys.argv[1:] if len(sys.argv) > 1 else []
    if not urls:
        print("Usage: python dealer_scraper.py <url1> [url2] ...")
        return

    results = {}
    for url in urls:
        domain = urlparse(url).netloc
        dealers = await scrape_dealers(url)
        results[domain] = dealers
        print(f"\n── Dealers from {domain} ──")
        for i, d in enumerate(dealers, 1):
            print(f"\n[{i}] {d['name']}")
            print(f"    Address : {d['address']}")
            print(f"    Phone   : {', '.join(d['phone'])}")
            print(f"    Email   : {', '.join(d['email'])}")

    out = 'dealers_output.json'
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Saved to {out}")


if __name__ == '__main__':
    asyncio.run(main())