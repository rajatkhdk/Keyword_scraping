from keywords_scraping.contact_regex import _block_to_dealer, extract_phones, extract_emails, _walk_up_to_card, BLOCK_TAGS, clean
import re
from bs4 import BeautifulSoup, NavigableString, Tag


# ─────────────────────────────────────────────────────────────────────────────
# HTML PARSER
# ─────────────────────────────────────────────────────────────────────────────

async def extract_from_initial_html(page, state):

    print("inside initial html parser")

    scopes = [
        'main',
        '#dealer-locator',
        '.dealer',
        '.showroom',
        '[class*="dealer"]',
        '[class*="showroom"]',
    ]

    html = None

    for sel in scopes:
        try:
            el = await page.query_selector(sel)
            if el:
                html = await el.inner_html()
                break
        except:
            continue

    if not html:
        html = await page.content()

    dealers = parse_dealers_from_html(html)

    if dealers:
        state.html_dealers.extend(dealers)

async def extract_popup_data(popup, state):

    print("inside popup parser")

    html = await popup.inner_html()
    text = await popup.inner_text()

    # strategy 1
    mymaps = _parse_google_mymaps_panel(html)

    if mymaps:
        state.popup_dealers.append(mymaps)

    # strategy 2
    soup = BeautifulSoup(html, 'lxml')

    dealer_blocks = []

    # Try explicit block tags first
    for tag in soup.find_all(BLOCK_TAGS):

        text = tag.get_text(" ", strip=True)

        if extract_phones(text):
            dealer_blocks.append(tag)

    # Fallback: entire popup
    if not dealer_blocks:
        dealer_blocks = [soup]

    seen_phones = set()

    for block in dealer_blocks:

        try:

            dealer = _block_to_dealer(block)

            phones = tuple(sorted(
                re.sub(r'\D', '', p)
                for p in dealer.get('phone', [])
            ))

            if not phones:
                continue

            if phones in seen_phones:
                continue

            seen_phones.add(phones)

            state.popup_dealers.append(dealer)

        except Exception:
            continue

    # ---------------------------------------------------------
    # Strategy 3
    # Discover detail links
    # ---------------------------------------------------------

    try:
        links = await popup.query_selector_all('a[href]')
    except Exception:
        links = []

    for link in links:

        try:
            href = await link.get_attribute('href')

            if not href:
                continue

            href = href.strip()

            if href.startswith('mailto:'):
                continue

            if href.startswith('tel:'):
                continue

            if href == '#':
                continue

            state.discovered_urls.add(href)

        except Exception:
            continue

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

    print("inside html parser")

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

def _parse_google_mymaps_panel(html: str) -> dict | None:

    """
    Parses Google My Maps sidebar/card panels and converts them
    into a normalized dealer block using `_block_to_dealer()`.

    Goal:
        Avoid custom field extraction logic and centralize all
        dealer parsing inside `_block_to_dealer()`.
    """

    print("Inside parse google mymaps panel")

    soup = BeautifulSoup(html, 'lxml')

    # ---------------------------------------------------------
    # Locate MyMaps panels
    # ---------------------------------------------------------

    panels = soup.find_all(
        class_=lambda c:
            c and 'qqvbed-p83tee' in c
    )

    if not panels:
        return None

    # ---------------------------------------------------------
    # Build normalized pseudo-card HTML
    # ---------------------------------------------------------

    card = BeautifulSoup('<div class="dealer-card"></div>', 'lxml')

    card_root = card.div

    for panel in panels:

        try:

            label_el = panel.find(
                class_=lambda c:
                    c and 'V1ur5d' in c
            )

            value_el = panel.find(
                class_=lambda c:
                    c and 'lTBxed' in c
            )

            if not label_el or not value_el:
                continue

            label = clean(
                label_el.get_text(" ", strip=True)
            )

            value = clean(
                value_el.get_text(" ", strip=True)
            )

            if not value:
                continue

            # ---------------------------------------------
            # Convert label/value pair into generic HTML
            # ---------------------------------------------

            row = card.new_tag("div")

            strong = card.new_tag("strong")
            strong.string = f"{label}: "

            span = card.new_tag("span")
            span.string = value

            row.append(strong)
            row.append(span)

            card_root.append(row)

        except Exception:
            continue

    # ---------------------------------------------------------
    # Fallback: raw text dump
    # ---------------------------------------------------------

    if not card_root.get_text(strip=True):

        raw_div = card.new_tag("div")
        raw_div.string = soup.get_text("\n", strip=True)

        card_root.append(raw_div)

    # ---------------------------------------------------------
    # Unified extraction
    # ---------------------------------------------------------

    dealer = _block_to_dealer(card_root)

    # ---------------------------------------------------------
    # Additional fallbacks
    # ---------------------------------------------------------

    all_text = card_root.get_text(" ", strip=True)

    if not dealer.get('phone'):
        dealer['phone'] = extract_phones(all_text)

    if not dealer.get('email'):
        dealer['email'] = extract_emails(all_text)

    # ---------------------------------------------------------
    # Metadata
    # ---------------------------------------------------------

    dealer['source'] = 'google_mymaps_panel'

    # ---------------------------------------------------------
    # Validation
    # ---------------------------------------------------------

    if any([
        dealer.get('name'),
        dealer.get('phone'),
        dealer.get('email'),
        dealer.get('address'),
    ]):
        return dealer

    return None
