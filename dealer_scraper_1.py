import re
import json
import asyncio
from urllib.parse import urlparse
from bs4 import BeautifulSoup, NavigableString, Tag
from playwright.async_api import async_playwright

import os
import logging

# ─────────────────────────────────────────────────────────────────────────────
# log function
# ─────────────────────────────────────────────────────────────────────────────

print("RUNNING FILE:", __file__)
print("CWD:", os.getcwd())

# 1. Force the log file to be in the same folder as this script
script_dir = os.path.dirname(os.path.abspath(__file__))
log_path = os.path.join(script_dir, "scraper_log.txt")

# 2. Advanced config: Get the root logger and clear existing handlers
logger = logging.getLogger("scrape_logger")
logger.setLevel(logging.INFO)
logger.propagate = False

# Clear any handlers that might have been set by imports
if logger.hasHandlers():
    logger.handlers.clear()

# 3. Create File Handler (the log file)
try:
    file_handler = logging.FileHandler(log_path, mode='w', encoding='utf-8')
except Exception as e:
    print("FileHandler failed:", e)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# 4. Create Stream Handler (the terminal output)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

logger.setLevel(logging.DEBUG)

# 5. Add both to the logger
logger.addHandler(file_handler)
logger.addHandler(stream_handler)
print("FileHandler created at:", log_path)

print(f"DEBUG: Log file should be created at: {log_path}")

logger.info("Logger initialized successfully")

file_handler.flush()
print("LOG FILE EXISTS:", os.path.exists(log_path))

print("PATH:", log_path)
print("EXISTS DIR:", os.path.exists(script_dir))

# ─────────────────────────────────────────────────────────────────────────────
# load address json
# ─────────────────────────────────────────────────────────────────────────────
with open("address_json/location_list.json", "r", encoding="utf-8") as f:
    location_list = json.load(f)

# ─────────────────────────────────────────────────────────────────────────────
# Save and load html
# ─────────────────────────────────────────────────────────────────────────────
# def save_html(path: str, html: str):
#     with open(path, "w", encoding="utf-8") as f:
#         f.write(html)

# def load_html(path: str) -> str | None:
#     if os.path.exists(path):
#         with open(path, "r", encoding="utf-8") as f:
#             return f.read()
#     return None

# ─────────────────────────────────────────────────────────────────────────────
# PHONE REGEX  (covers all common Nepal formats)
# ─────────────────────────────────────────────────────────────────────────────

# Phone regex
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

# Email regex
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')

def build_location_regex(location_list):
    # sort by length (longest first → avoids partial matches like "lalit" vs "lalitpur")
    sorted_locations = sorted(location_list, key=len, reverse=True)

    pattern = r'\b(' + '|'.join(re.escape(loc) for loc in sorted_locations) + r')\b'
    return re.compile(pattern, re.IGNORECASE)

LOCATION_REGEX = build_location_regex(location_list)

# Match phone regex to get phone no.
def extract_phones(text: str) -> list[str]:
    raw = _PHONE_RE.findall(text)
    seen, result = set(), []
    for p in raw:
        key = re.sub(r'[\s\-./]', '', p)
        if len(key) >= 7 and key not in seen:
            seen.add(key)
            result.append(p.strip())
    return result

# Match email regex to get email
def extract_emails(text: str) -> list[str]:
    return list(set(EMAIL_RE.findall(text)))

# Detects and remove white space using regex
def clean(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


# ─────────────────────────────────────────────────────────────────────────────
# CORE: Phone-anchored DOM walker
# ─────────────────────────────────────────────────────────────────────────────

BLOCK_TAGS = {'div', 'section', 'article', 'li', 'tr', 'td', 'aside', 'figure', 'main', 'p', 'address'}

STOP_TAGS = {'body', 'html', 'form'}

#extracts all the text content inside the tag and its children
def _text_of(tag: Tag) -> str:
    return clean(tag.get_text(separator=' '))

def _text_line(tag: Tag) -> str:
    texts = tag.get_text(separator='\n')
    lines = [clean(l) for l in texts.split('\n') if clean(l)]
    return lines

# Check for address in given text
def _has_address_signal(text: str) -> bool:
    if not text:
        return False
    
    text = text.lower()

    # normalize ward numbers like "Pokhara-8"
    text = re.sub(r'[-–]\d+', '', text)

    # ✔ dynamic location match
    if LOCATION_REGEX.search(text):
        return True
    
    return bool(re.search(
        r'\b(road|marg|chowk|ward|tole|nagar|bazar|bazaar|'
        r'street|avenue|lane|chok|sadak|galli)\b', text, re.I
    ))

# Checks if the line contains brand name
def _has_name_signal(text: str) -> bool:
    lines = re.split(r'\n|\|', text)
    for line in lines:
        if len(line) < 4 or len(line) > 120:
            continue
        if extract_phones(line):
            continue
        if re.match(r'[a-zA-Z]', line):
            return True
    return False

def normalize(text):
    return re.sub(r'\D', '', text)

# Scores tags to obtain a smallest block with name + address + phone
def _score_block(tag: Tag, anchor_phones: set) -> float:
    """
    Score a candidate ancestor block.
    We want the SMALLEST block that still has name + address + phone.
    """
    text = _text_of(tag)

    # if debugging:
    #     logger.debug(f"[BLOCK] {text[:120]}")

    # Must still contain the phone(s) we anchored on
    if not any(normalize(p) in normalize(text) for p in anchor_phones):
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

# Anchor a phone no. and move upward to highest scoring block
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

# Find and extract the dealer name containing line
def _extract_name(block: Tag) -> str:
    text = _text_of(block)
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    BUSINESS_SIGNALS = r'\b(pvt|ltd|private|limited|traders|motors|auto|group|enterprise|suppliers|trading)\b'

    # 1. Heading / strong / bold tags
    for tag_name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'b']:
        for el in block.find_all(tag_name):
            t = clean(el.get_text())
            if t and 5 < len(t) < 120 and not extract_phones(t):
                return t

    # 2. First capitalised line that isn't phone/email/address
    for line in lines:
        line = line.strip()
        if not line or len(line) < 3 or len(line) > 120:
            continue
        if extract_phones(line) or EMAIL_RE.search(line):
            continue
        if re.search(BUSINESS_SIGNALS, line, re.I):
            return line
        if _has_address_signal(line):
            continue
        if re.match(r'[A-Z]', line):
            return line
    return ''

# Find and extract the address containing line
def _extract_address(block: Tag) -> str:
    # 1. Semantic <address> tag
    addr_tag = block.find('address')
    if addr_tag:
        return clean(addr_tag.get_text())

    # 3. Line containing a Nepal place name
    for line in _text_line(block):
        line = line.strip()
        if _has_address_signal(line) and not extract_phones(line):
            return line

    return ''

# creates a dictionary with name + address _ phone + email
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

    """
    Parses dealer information from HTML.
    This function ignores typical boilerplate (scripts, nav, footers) and 
    locates dealers by identifying tags containing phone numbers. Once a phone number is found, it "walks up" the DOM tree to find the logical container (card) for that dealer. 
    
    If multiple dealer blocks contain the same phone number, the function retains only the record with the most populated data fields.

    Args:
        html: A string containing the raw HTML content to be parsed.

    Returns:
        A list of dictionaries, where each dictionary represents a unique 
        dealer. Typical keys include 'phone', 'name', 'address', 'email', depending on the output of `_block_to_dealer`.
    """

    soup = BeautifulSoup(html, 'lxml')

    # Removes few blocks
    for tag in soup(['script', 'style', 'noscript', 'nav', 'footer', 'head']):
        tag.decompose()

    # used_block_ids -> if multiple phone no.in same dealer card, ensures no duplicate dealer is created
    dealers = []
    used_block_ids: set[int] = set()  

    # Iterate every tag; check only its OWN text (not text inside children tag) for a phone
    for tag in soup.find_all(True):

        # if no phone found in own_text -> continue
        # else search for phone and move upward to find dealer card
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

    # Deduplicate by normalised phone set, keeping the most complete record
    phone_to_best_dealer = {}
    # seen, unique = set(), []
    for d in dealers:
        # Create a unique key from normalized phone numbers
        phone_key = frozenset(re.sub(r'\D', '', p) for p in d.get('phone', []))
        if not phone_key:
            continue

        # Calculate a completeness score (count non-empty values)
        # Counts keys that have a truth value (not none, empty sting, or empty)
        current_score = sum(1 for value in d.values() if value)

        if phone_key not in phone_to_best_dealer:
            phone_to_best_dealer[phone_key] = d
        else:
            # Compare current score with the one already saved
            existing_dealer = phone_to_best_dealer[phone_key]
            existing_score = sum(1 for value in existing_dealer.values() if value)

            if current_score > existing_score:
                phone_to_best_dealer[phone_key] = d

    return list(phone_to_best_dealer.values())


# ─────────────────────────────────────────────────────────────────────────────
# JSON API INTERCEPTOR
# ─────────────────────────────────────────────────────────────────────────────
# Extract data from json -> api
def _extract_dealers_from_json(data, depth=0) -> list[dict]:

    """
    Recursively traverses a JSON-like structure to locate and extract dealer records.

    This function performs a depth-first search (up to 6 levels) to find dictionaries that contain dealer signatures (phone numbers or name/address pairs). It normalizes various naming conventions (e.g., 'tel' vs 'phone') into a consistent schema.

    Args:
        data: The JSON data to parse (can be a dict, list, or primitive).
        depth (int): The current recursion depth. Defaults to 0.

    Returns:
        list[dict]: A list of extracted dealer dictionaries with keys:
            'name', 'address', 'phone' (list), and 'email' (list).

    Note:
        If an object is identified as a dealer, the function extracts its data and stops recursing into that specific branch to avoid duplicate fragment extraction.
    """

    dealers = []
    if depth > 6:
        return dealers
    if isinstance(data, list):
        for item in data:
            dealers.extend(_extract_dealers_from_json(item, depth + 1))
    elif isinstance(data, dict):
        kl = {k.lower(): k for k in data}
        has_phone   = any(k in kl for k in ['phone','tel','mobile','contact_no','phone_no','telephone', 'contact'])
        has_name    = any(k in kl for k in ['name','dealer','showroom','title'])
        has_address = any(k in kl for k in ['address','location','city','district'])
        if has_phone or (has_name and has_address):
            d = {'name': '', 'address': '', 'phone': [], 'email': []}
            for field, keys in [
                ('name',    ['name','dealer_name','showroom_name','title','dealer']),
                ('address', ['address','full_address','location','city','district']),
                ('phone',   ['phone','phone_no','tel','mobile','contact_no','telephone', 'contact']),
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
                if any(k in txt for k in ['dealer','showroom','phone','address','location', 'contact']):
                    api_dealers.extend(_extract_dealers_from_json(body))
        except Exception:
            pass

    page.on('response', on_response)
    await page.goto(url, wait_until='networkidle', timeout=30000)
    await page.wait_for_timeout(3000)
    # html = await page.content()
    # await browser.close()
    return page, browser, api_dealers, p

# ─────────────────────────────────────────────────────────────────────────────
# MAP INTERACTION
# ─────────────────────────────────────────────────────────────────────────────

async def _try_map_and_search(url: str, queries: list[str]) -> list[dict]:
    dealers = []
    intercepted_data = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        async def handle_response(response):
            url_lower = response.url.lower()
            if any(kw in url_lower for kw in [
                'dealer', 'location', 'store', 'branch', 'marker', 'pin', 'map', 'poi'
            ]):
                try:
                    ct = response.headers.get('content-type', '')
                    if 'json' in ct:
                        body = await response.json()
                        intercepted_data.append({'url': response.url, 'data': body})
                except:
                    pass

        page.on('response', handle_response)
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await page.wait_for_timeout(3000)

        # Strategy 1: Network intercept
        if intercepted_data:
            for item in intercepted_data:
                parsed = _extract_dealers_from_json(item['data'])
                if parsed:
                    dealers.extend(parsed)
            if dealers:
                print(f"[NETWORK] Got {len(dealers)} dealers from XHR intercept")
                await browser.close()
                return dealers

        # Strategy 2: Find the right frame (iframe vs main page)
        MARKER_SELECTORS = [
            'img[src*="maps.gstatic.com/mapfiles"]',
            'img[src*="marker"]',
            'img[src*="pin"]',
            'area[title]',
            'gmp-advanced-marker',
            '.gm-style [role="button"]:not([aria-label*="zoom"]):not([aria-label*="Street"]):not([aria-label*="Map"]):not([aria-label*="Satellite"])',
            '.leaflet-marker-icon',
            '.leaflet-div-icon',
            '.mapboxgl-marker',
            '.maplibregl-marker',
            '[class*="marker"]:not([class*="markercluster-"])',
            '[class*="Marker"]:not([class*="MarkerCluster"])',
            '.marker-cluster',
            '[class*="cluster"]',
        ]

        frames = [page] + list(page.frames)

        for frame in frames:
            for selector in MARKER_SELECTORS:
                try:
                    markers = await frame.query_selector_all(selector)
                    if not markers:
                        continue

                    print(f"[DOM] Selector '{selector}' → {len(markers)} elements (frame: {frame.url[:80]})")

                    # ── KEY FIX: pass the frame itself so clicks happen inside it ──
                    frame_dealers = await _click_markers_and_extract(
                        marker_frame=frame,
                        page=page,
                        markers=markers,
                    )
                    dealers.extend(frame_dealers)

                    if frame_dealers:
                        break  # good selector found, stop trying others
                except Exception as e:
                    continue

            if dealers:
                break  # good frame found, stop trying others

        # Strategy 3: Canvas grid scan fallback
        if not dealers:
            dealers.extend(await _canvas_click_scan(page))

        await browser.close()

    return dealers

async def _canvas_click_scan(page) -> list[dict]:
    """Last resort for canvas/WebGL maps — grid click scan."""
    results = []

    map_selectors = [
        '.gm-style', '#map', '[id*="map"]', '[class*="map"]',
        'canvas', '.mapboxgl-canvas', '.maplibregl-canvas'
    ]

    map_el = None
    for sel in map_selectors:
        map_el = await page.query_selector(sel)
        if map_el:
            break

    if not map_el:
        return results

    box = await map_el.bounding_box()
    if not box:
        return results

    print(f"[CANVAS] Scanning map at {box} with grid clicks")

    cols, rows = 6, 4
    for row in range(rows):
        for col in range(cols):
            x = box['x'] + (box['width'] / (cols + 1)) * (col + 1)
            y = box['y'] + (box['height'] / (rows + 1)) * (row + 1)

            await page.mouse.click(x, y)
            await page.wait_for_timeout(800)

            popup = await page.query_selector('.gm-style-iw, [class*="popup"], [role="dialog"]')
            if not popup:
                continue

            html = await popup.inner_html()
            text = await popup.inner_text()
            print(f"  → Canvas popup: {text[:80].strip()}")

            # ── Try MyMaps parser first, then generic parser ──
            mymaps_result = _parse_google_mymaps_panel(html)
            if mymaps_result:
                results.append(mymaps_result)
            else:
                parsed = parse_dealers_from_html(html)
                if parsed:
                    results.extend(parsed)
                elif extract_phones(text) or text.strip():
                    results.append({
                        'name':    text.split('\n')[0].strip(),
                        'address': '\n'.join(text.split('\n')[1:]).strip(),
                        'phone':   extract_phones(text),
                        'email':   extract_emails(text),
                        'source':  'canvas_raw',
                    })

            # ── Close using page (no marker_frame here) ──
            for close_sel in ['[aria-label="Close"]', '.gm-ui-hover-effect', 'button[jsaction*="close"]']:
                try:
                    btn = await page.query_selector(close_sel)
                    if btn:
                        await btn.evaluate("el => el.click()")
                        await page.wait_for_timeout(300)
                        break
                except:
                    continue

    return results

def _parse_google_mymaps_panel(html: str) -> dict | None:
    """
    Parses Google My Maps feature card HTML.
    Structure: div.qqvbed-p83tee contains
      div.qqvbed-p83tee-V1ur5d (label) + div.qqvbed-p83tee-lTBxed (value)
    """
    soup = BeautifulSoup(html, 'lxml')

    # Find all label/value pairs
    panels = soup.find_all(class_=lambda c: c and 'qqvbed-p83tee' in c)
    
    data = {}
    for panel in panels:
        label_el = panel.find(class_=lambda c: c and 'V1ur5d' in c)
        value_el = panel.find(class_=lambda c: c and 'lTBxed' in c)
        
        if label_el and value_el:
            label = clean(label_el.get_text()).lower()
            value = clean(value_el.get_text())
            data[label] = value

    if not data:
        return None

    # Map known Honda My Maps labels → our schema
    result = {
        'name':    data.get('dealer name', data.get('name', '')),
        'address': data.get('address', data.get('location', '')),
        'phone':   extract_phones(data.get('phone no.', data.get('phone', data.get('contact', '')))),
        'email':   extract_emails(data.get('email address', data.get('email', ''))),
        'source':  'google_mymaps_panel',
    }

    # Fallback: scan ALL values for phones/emails in case label names differ
    all_values = ' '.join(data.values())
    if not result['phone']:
        result['phone'] = extract_phones(all_values)
    if not result['email']:
        result['email'] = extract_emails(all_values)

    return result if (result['name'] or result['phone']) else None

async def _debug_dump_frame_elements(frame, page):
    """
    Call this once to identify what elements appear after clicking a marker.
    Prints all visible elements with text content > 10 chars.
    """
    elements = await frame.evaluate("""() => {
        const results = [];
        document.querySelectorAll('*').forEach(el => {
            const text = el.innerText?.trim();
            const rect = el.getBoundingClientRect();
            if (
                text && text.length > 10 && text.length < 300 &&
                rect.width > 0 && rect.height > 0 &&
                !['SCRIPT','STYLE','HTML','BODY'].includes(el.tagName)
            ) {
                results.push({
                    tag: el.tagName,
                    id: el.id,
                    classes: el.className,
                    jsname: el.getAttribute('jsname') || '',
                    text: text.substring(0, 80)
                });
            }
        });
        return results.slice(0, 40);
    }""")
    
    print("\n[DEBUG FRAME ELEMENTS AFTER CLICK]")
    for el in elements:
        print(f"  <{el['tag']}> id='{el['id']}' class='{el['classes'][:50]}' jsname='{el['jsname']}' → {el['text'][:60]}")

async def _click_markers_and_extract(marker_frame, page, markers) -> list[dict]:
    results = []
    seen_positions = set()

    POPUP_SELECTORS = [
        '.qqvbed-p83tee',
        '[jsname="WOdXFb"]',
        '[class*="goog-container"]',
        '.qqvbed-nUpftc',
        '.gm-style-iw',
        '.gm-style-iw-c',
        '.gm-style-iw-d',
        '[class*="InfoWindow"]',
        '[class*="infowindow"]',
        '[class*="popup"]',
        '[class*="Popup"]',
        '.leaflet-popup-content',
        '.mapboxgl-popup-content',
        '[class*="sidebar"]',
        '[class*="Sidebar"]',
        '[class*="panel"]',
        '[class*="detail"]',
        '[role="dialog"]',
        '[role="tooltip"]',
    ]

    async def close_popup():
        for close_sel in [
            '[aria-label="Close"]',
            '.gm-ui-hover-effect',
            'button[jsaction*="close"]',
            '[data-dismiss]',
        ]:
            try:
                btn = await marker_frame.query_selector(close_sel)
                if btn:
                    await btn.evaluate("el => el.click()")
                    await page.wait_for_timeout(500)
                    return
            except:
                continue

    original_url = page.url

    # ── Snapshot BOTH the handle AND its bounding box ──
    # Handle = use for direct JS click (most reliable)
    # Box    = fallback if handle becomes stale after navigation
    marker_snapshots = []  # list of (handle, box)
    for marker in markers[:100]:
        try:
            box = await marker.bounding_box()
            if not box or box['width'] < 4 or box['height'] < 4:
                continue
            cell = (round(box['x'] / 5), round(box['y'] / 5))
            if cell in seen_positions:
                continue
            seen_positions.add(cell)
            marker_snapshots.append((marker, box))
        except:
            continue

    print(f"[CLICK] {len(marker_snapshots)} unique markers to process")

    for i, (handle, box) in enumerate(marker_snapshots):
        try:
            print(f"[CLICK] Marker {i+1}/{len(marker_snapshots)} at ({box['x']:.0f}, {box['y']:.0f})")

            # ── Click strategy: handle first, elementFromPoint as fallback ──
            clicked = False

            # Strategy 1: direct JS click on the stored handle (works even off-screen)
            try:
                await handle.evaluate("el => el.click()")
                clicked = True
            except Exception:
                pass  # handle is stale (post-navigation) — fall through

            # Strategy 2: re-find the element by its stored coordinates
            # NOTE: elementFromPoint in a frame uses the frame's OWN coordinate space,
            # NOT the page viewport. The bounding_box() from a frame element IS already
            # in the frame's coordinate space, so this is correct.
            if not clicked:
                try:
                    await marker_frame.evaluate(
                        """([x, y]) => {
                            const el = document.elementFromPoint(x, y);
                            if (el) el.click();
                        }""",
                        [box['x'], box['y']]
                    )
                    clicked = True
                except Exception as e:
                    print(f"  → Both click strategies failed: {e}")
                    continue

            await page.wait_for_timeout(2000)

            # ── Find popup ──
            popup = None
            popup_source = None

            for sel in POPUP_SELECTORS:
                for context, label in [(marker_frame, 'frame'), (page, 'page')]:
                    try:
                        el = await context.query_selector(sel)
                        if el and await el.is_visible():
                            txt = (await el.inner_text()).strip()
                            if len(txt) > 3:
                                popup = el
                                popup_source = context
                                print(f"  → Popup via '{sel}' in {label}")
                                break
                    except:
                        continue
                if popup:
                    break

            if not popup:
                print(f"  → No popup — scanning full frame HTML")
                try:
                    frame_html = await marker_frame.content()
                    parsed = parse_dealers_from_html(frame_html)
                    if parsed:
                        print(f"  → Extracted {len(parsed)} from full frame")
                        results.extend(parsed)
                except:
                    pass
                continue

            html = await popup.inner_html()
            text = await popup.inner_text()
            print(f"  → Text preview: {text[:120].strip()}")

            # ── Strategy A: Google My Maps structured panel ──
            mymaps_result = _parse_google_mymaps_panel(html)
            if mymaps_result:
                print(f"  → MyMaps: {mymaps_result['name']} | {mymaps_result['phone']}")
                results.append(mymaps_result)
                await close_popup()
                continue

            # ── Strategy B: standard HTML parser ──
            parsed = parse_dealers_from_html(html)
            if parsed:
                print(f"  → HTML parser: {len(parsed)} dealer(s)")
                results.extend(parsed)
                await close_popup()
                continue

            # ── Strategy C: follow detail link ──
            links = await popup.query_selector_all('a[href]')
            detail_found = False

            for link in links:
                href = await link.get_attribute('href')
                if not href:
                    continue

                if href.startswith('tel:'):
                    phone = re.sub(r'\D', '', href.replace('tel:', ''))
                    if phone:
                        results.append({
                            'name':    text.split('\n')[0].strip(),
                            'address': '\n'.join(text.split('\n')[1:]).strip(),
                            'phone':   [phone],
                            'email':   [],
                            'source':  'tel_link',
                        })
                    detail_found = True
                    continue

                if href.startswith('mailto:'):
                    continue

                try:
                    print(f"  → Following detail link: {href[:60]}")
                    await link.evaluate("el => el.click()")
                    await page.wait_for_timeout(2500)

                    if page.url != original_url:
                        # Full navigation
                        detail_html = await page.content()
                        detail_parsed = parse_dealers_from_html(detail_html)
                        if detail_parsed:
                            print(f"  → Got {len(detail_parsed)} from detail page")
                            results.extend(detail_parsed)
                            detail_found = True
                        await page.go_back()
                        await page.wait_for_load_state('networkidle')
                        await page.wait_for_timeout(1500)
                        break
                    else:
                        # Hash routing (Subaru #/dealer/125)
                        new_html = await page.content()
                        new_parsed = parse_dealers_from_html(new_html)
                        if new_parsed:
                            results.extend(new_parsed)
                            detail_found = True
                        await page.evaluate(f"window.location.href = '{original_url}'")
                        await page.wait_for_timeout(1500)
                        break

                except Exception as e:
                    print(f"  → Link error: {e}")
                    continue

            # ── Strategy D: raw fallback ──
            if not detail_found:
                raw = {
                    'name':    text.split('\n')[0].strip(),
                    'address': '\n'.join(text.split('\n')[1:]).strip(),
                    'phone':   extract_phones(text),
                    'email':   extract_emails(text),
                    'source':  'map_popup_raw',
                }
                print(f"  → Raw: {raw['name']} | phones: {raw['phone']}")
                results.append(raw)

            await close_popup()

        except Exception as e:
            print(f"[CLICK] Error on marker {i+1}: {e}")
            continue

    return results

def is_placeholder(text: str) -> bool:
    t = text.strip().lower()
    return t in [
        "",
        "select",
        "select province",
        "select district",
        "select city",
        "choose",
        "all",
        "all provinces",
        "all districts",
        "all cities"
    ]

async def get_selected_option(select):
    return await select.evaluate("""
        el => {
            const opt = el.options[el.selectedIndex];
            return opt ? opt.innerText.trim().toLowerCase() : "";
        }
    """)

async def is_select_meaningful(page, select):
    options = await select.query_selector_all("option")

    texts = [
        (await opt.inner_text()).strip().lower()
        for opt in options
    ]

    # if only placeholders → useless
    if all(is_placeholder(t) for t in texts):
        return False

    # if only "all + same values" → useless
    if any("all" in t for t in texts) and len(texts) <= 2:
        return False

    return True

async def is_full_dataset(page):
    selects = await page.query_selector_all("select")

    for select in selects:
        selected = await get_selected_option(select)

        # if ANY select is actively filtering → dataset is NOT full
        if not is_placeholder(selected):
            return False

    return True

# ─────────────────────────────────────────────────────────────────────────────
# SEARCH AND SELECT 
# ─────────────────────────────────────────────────────────────────────────────

async def find_submit_button(page):
    buttons = await page.query_selector_all("button, input[type='button'], input[type='submit']")

    for btn in buttons:
        try:
            text = (await btn.inner_text()).strip().lower()

            if any(k in text for k in [
                "search", "submit", "apply", "filter", "go", "find"
            ]):
                return btn
        except:
            continue

    return None

async def interact_and_collect(page, api_dealers):
    print("→ Smart adaptive scraping...")

    collected = []

    # STEP 1: baseline
    html = await page.content()
    collected.extend(parse_dealers_from_html(html))

    # STEP 2: if already full dataset → STOP
    if await is_full_dataset(page):
        print("[STOP] Full dataset detected.")
        return collected

    selects = await page.query_selector_all("select")

    # STEP 3: explore only meaningful selects
    for select in selects:

        if not await is_select_meaningful(page, select):
            print("[SKIP] meaningless select")
            continue

        options = await select.query_selector_all("option")

        for opt in options:
            text = (await opt.inner_text()).strip().lower()

            if is_placeholder(text):
                continue

            value = await opt.get_attribute("value")

            # 1. apply filter
            await select.select_option(value=value)

            # 2. IMPORTANT: trigger UI update
            btn = await find_submit_button(page)

            if btn:
                try:
                    await btn.click()
                    await page.wait_for_load_state("networkidle")
                except:
                    await page.wait_for_timeout(1500)
            else:
                # fallback for reactive UIs
                await page.wait_for_timeout(1500)

            html = await page.content()
            collected.extend(parse_dealers_from_html(html))

    return collected

# ─────────────────────────────────────────────────────────────────────────────
# ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────

def normalize_phones(phone_field):
    if not phone_field:
        return []

    # STEP 1: unify input type
    if isinstance(phone_field, list):
        raw = phone_field
    else:
        raw = [phone_field]

    numbers = []

    for item in raw:
        if not item:
            continue

        # STEP 2: split on ALL possible separators
        parts = re.split(r"[,\|;/\n]", str(item))

        for p in parts:
            digits = re.sub(r"\D", "", p)

            # ignore junk / invalid numbers
            if len(digits) < 7:
                continue

            numbers.append(digits)

    # STEP 3: deduplicate + stable ordering
    return sorted(set(numbers))

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

    # USE_CACHE = True
    # cache_file = "page5.html"

    # html = None
    # # Try loading cached HTML first
    # if USE_CACHE:
    #     html = load_html(cache_file)

    # if html:
    #     print("📂 Using cached HTML (page5.html)")
    # else:
    #     print("🌐 Fetching fresh HTML...")
    #     html = await page.content()
    #     save_html(cache_file, html)
    #     print("💾 Saved HTML to page5.html")

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

    # Deduplicate by normalised phone set, keeping the most complete record
    phone_to_best_dealer = {}
    # seen, unique = set(), []
    for d in dealers:
        # Create a unique key from normalized phone numbers
        # phone_key = frozenset(re.sub(r'\D', '', p) for p in d.get('phone', []))

        phone_list = normalize_phones(d.get('phone'))
        if not phone_list:
                    continue
        phone_key = tuple(phone_list)  # stable + hashable
        

        # Calculate a completeness score (count non-empty values)
        # Counts keys that have a truth value (not none, empty sting, or empty)
        current_score = sum(1 for value in d.values() if value)

        if phone_key not in phone_to_best_dealer:
            phone_to_best_dealer[phone_key] = d
        else:
            # Compare current score with the one already saved
            existing_dealer = phone_to_best_dealer[phone_key]
            existing_score = sum(1 for value in existing_dealer.values() if value)

            if current_score > existing_score:
                phone_to_best_dealer[phone_key] = d

    return list(phone_to_best_dealer.values())

    


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    import sys
    urls = sys.argv[1:] if len(sys.argv) > 1 else []
    if not urls:
        print("Usage: python dealer_scraper.py <url1> [url2] ...")
        logger.info("Usage: python dealer_scraper.py <url1> [url2] ...")
        return

    results = {}
    for url in urls:
        domain = urlparse(url).netloc
        dealers = await scrape_dealers(url)
        results[domain] = dealers
        print(f"\n── Dealers from {domain} ──")
        logger.info(f"\n── Dealers from {domain} ──")
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