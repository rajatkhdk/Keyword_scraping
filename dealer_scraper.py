import re
import json
import asyncio
from urllib.parse import urlparse
from bs4 import BeautifulSoup, NavigableString, Tag
from playwright.async_api import async_playwright
from keywords_scraping.contact_regex import _block_to_dealer, extract_phones, extract_emails, _walk_up_to_card, BLOCK_TAGS, clean
from keywords_scraping.html_parser import parse_dealers_from_html, extract_from_initial_html, extract_popup_data, _parse_google_mymaps_panel
from keywords_scraping.map_scrape import get_selected_option, is_placeholder, is_select_meaningful, _try_map_and_search, discover_map_entities, deduplicate_dealers
from keywords_scraping.json_parser import _extract_dealers_from_json

import os
# import logging

from dataclasses import dataclass, field

@dataclass
class ScraperState:
    api_dealers: list = field(default_factory=list)
    html_dealers: list = field(default_factory=list)
    popup_dealers: list = field(default_factory=list)

    discovered_urls: set = field(default_factory=set)
    visited_urls: set = field(default_factory=set)

    intercepted_responses: list = field(default_factory=list)

# ─────────────────────────────────────────────────────────────────────────────
# PLAYWRIGHT LOADER
# ─────────────────────────────────────────────────────────────────────────────

async def create_browser_session(url: str):
    p = await async_playwright().start()

    browser = await p.chromium.launch(
        headless=False,
        slow_mo=100,
    )

    context = await browser.new_context(
        user_agent=(
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36'
        )
    )

    page = await context.new_page()

    await page.goto(
        url,
        wait_until='networkidle',
        timeout=45000,
    )

    return p, browser, context, page

async def attach_global_interceptor(page, state: ScraperState):

    async def handle_response(response):
        try:
            ct = response.headers.get('content-type','')
            if 'json' not in ct:
                return
            
            url_lower = response.url.lower()

            IMPORTANT_KEYWORDS = [
                'dealer',
                'showroom',
                'location',
                'branch',
                'store',
                'map',
                'marker',
                'contact',
                'address',
                'network',
            ]

            if not any(k in url_lower for k in IMPORTANT_KEYWORDS):
                return
            body = await response.json()

            state.intercepted_responses.append({
                'url': response.url,
                'data': body,
            })

            dealers = _extract_dealers_from_json(body)

            if dealers:
                state.api_dealers.extend(dealers)

        except Exception as e:
            # logger.debug(f'[API] interceptor error: {e}')
            print(f'[API] interceptor error: {e}')

    page.on('response', handle_response)

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
            # await select.select_option(value=value)
            await select.evaluate(
                """
                (el, value) => {

                    const nativeSetter =
                        Object.getOwnPropertyDescriptor(
                            window.HTMLSelectElement.prototype,
                            'value'
                        ).set;

                    nativeSetter.call(el, value);

                    el.dispatchEvent(
                        new Event('change', {
                            bubbles: true
                        })
                    );

                    el.dispatchEvent(
                        new Event('input', {
                            bubbles: true
                        })
                    );
                }
                """,
                value
            )

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

async def scrape_discovered_urls(page, state):

    for url in state.discovered_urls:

        if url in state.visited_urls:
            continue

        try:
            state.visited_urls.add(url)

            # logger.info(f'[DETAIL] scraping: {url}')
            print(f'[DETAIL] scraping: {url}')

            await page.goto(
                url,
                wait_until='networkidle',
                timeout=30000,
            )

            html = await page.content()

            dealers = parse_dealers_from_html(html)

            if dealers:
                state.html_dealers.extend(dealers)

        except Exception as e:
            # logger.debug(f'[DETAIL] failed: {e}')
            print(f'[DETAIL] failed: {e}')



# async def scrape_dealers(url: str):

#     state = ScraperState()

#     p, browser, context, page = await create_browser_session(url)
    
#     try:
#         # global API interception
#         await attach_global_interceptor(page, state)

#         # initial HTML extraction
#         await extract_from_initial_html(page, state)

#         # interactive UI exploration
#         await interact_and_collect(page, state)

#         # map discovery
#         await discover_map_entities(page, state)

#         # merge + dedupe
#         final = deduplicate_dealers(
#             state.api_dealers +
#             state.html_dealers +
#             state.popup_dealers
#         )

#         return final
    
#     finally:
#         await browser.close()
#         await p.stop()
 
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
        # logger.info("Usage: python dealer_scraper.py <url1> [url2] ...")
        return

    results = {}
    for url in urls:
        domain = urlparse(url).netloc
        dealers = await scrape_dealers(url)
        results[domain] = dealers
        print(f"\n── Dealers from {domain} ──")
        # logger.info(f"\n── Dealers from {domain} ──")
        for i, d in enumerate(dealers, 1):
            print(f"\n[{i}] {d['name']}")
            print(f"    Address : {d['address']}")
            print(f"    Phone   : {', '.join(d['phone'])}")
            print(f"    Email   : {', '.join(d['email'])}")

    out = 'dealers_output.json'
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {out}")


if __name__ == '__main__':
    asyncio.run(main())