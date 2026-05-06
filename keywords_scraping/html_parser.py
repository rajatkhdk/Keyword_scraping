from keywords_scraping.contact_regex import _block_to_dealer, extract_phones, extract_emails, _walk_up_to_card, BLOCK_TAGS, clean
import re
from bs4 import BeautifulSoup, NavigableString, Tag


# ─────────────────────────────────────────────────────────────────────────────
# HTML PARSER
# ─────────────────────────────────────────────────────────────────────────────

async def extract_from_initial_html(page, state):

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

    html = await popup.inner_html()
    text = await popup.inner_text()

    # strategy 1
    mymaps = _parse_google_mymaps_panel(html)

    if mymaps:
        state.popup_dealers.append(mymaps)

    # strategy 2
    popup_entity = {
        'name': text.split('\n')[0].strip(),
        'address': '\n'.join(text.split('\n')[1:]).strip(),
        'phone': extract_phones(text),
        'email': extract_emails(text),
    }

    if popup_entity['phone']:
        state.popup_dealers.append(popup_entity)

    # strategy 3
    links = await popup.query_selector_all('a[href]')

    for link in links:

        href = await link.get_attribute('href')

        if not href:
            continue

        if href.startswith('mailto:'):
            continue

        if href.startswith('tel:'):
            continue

        state.discovered_urls.add(href)

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
