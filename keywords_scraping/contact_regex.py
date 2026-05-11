import re
from bs4 import BeautifulSoup, NavigableString, Tag
import json

# ─────────────────────────────────────────────────────────────────────────────
# load address json
# ─────────────────────────────────────────────────────────────────────────────
with open("address_json/location_list.json", "r", encoding="utf-8") as f:
    location_list = json.load(f)


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
# def _extract_name(block: Tag) -> str:
#     text = _text_of(block)
#     lines = [l.strip() for l in text.splitlines() if l.strip()]

#     BUSINESS_SIGNALS = r'\b(pvt|ltd|private|limited|traders|motors|auto|group|enterprise|suppliers|trading)\b'

#     # # 1. Heading / strong / bold tags
#     # for tag_name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'b']:
#     #     for el in block.find_all(tag_name):
#     #         t = clean(el.get_text())
#     #         if t and 5 < len(t) < 120 and not extract_phones(t):
#     #             return t

#     # 2. First capitalised line that isn't phone/email/address
#     for line in lines:
#         line = line.strip()
#         if not line or len(line) < 3 or len(line) > 120:
#             continue
#         if extract_phones(line) or EMAIL_RE.search(line):
#             continue
#         if re.search(BUSINESS_SIGNALS, line, re.I):
#             return line
#         if _has_address_signal(line):
#             continue
#         if re.match(r'[A-Z]', line):
#             return line
#     return ''
 
def _extract_name(block: Tag) -> str:

    lines = [
        clean(l) for l in _text_line(block) if clean(l)      
    ]

    if not lines:
        return ""
    
    BUSINESS_SIGNALS = re.compile(
        r'\b('
        r'pvt|ltd|private|limited|'
        r'trader|motor|auto|group|'
        r'enterprise|supplier|trading|'
        r'showroom|dealer|automobiles'
        r')\b',
        re.I
    )

    BAD_SIGNALS = re.compile(
        r'\b('
        r'contact|call|phone|email|'
        r'direction|location|map|'
        r'click|view|details|'
        r'book|test drive|'
        r'open|close|website'
        r')\b',
        re.I
    )

    candidates = []

    for line in lines:

        score = 0

        line = clean(line)

        heading_lines = {
            clean(t.get_text())
            for t in block.find_all(
                ['h1','h2','h3','h4','h5','strong','b']
            )
        }

        if len(line) < 3 or len(line) > 120:
            continue

        if extract_phones(line):
            continue

        if EMAIL_RE.search(line):
            continue

        if BUSINESS_SIGNALS.search(line):
            score += 50

        if re.match(r'^[A-Z]', line):
            score += 20

        words = line.split()

        if 2 <= len(words) <= 8:
            score += 15

        if line in heading_lines:
            score += 10

        if BAD_SIGNALS.search(line):
            score -= 40
        

        # # penalize address-like lines
        # if _has_address_signal(line):
        #     score -= 15

        # penalize ALL CAPS
        if line.isupper():
            score -= 10

        candidates.append((score, line))

    if not candidates:
        return ""

    candidates.sort(reverse=True)

    best_score, best_line = candidates[0]

    # reject low confidence
    if best_score < 20:
        return ""

    return best_line

# Find and extract the address containing line
# def _extract_address(block: Tag) -> str:
#     # 1. Semantic <address> tag
#     addr_tag = block.find('address')
#     if addr_tag:
#         return clean(addr_tag.get_text())

#     # 3. Line containing a Nepal place name
#     for line in _text_line(block):
#         line = line.strip()
#         if _has_address_signal(line) and not extract_phones(line):
#             return line

#     return ''
 
def extract_location_tokens(text):

    found = []

    text = clean(text).lower()

    for match in LOCATION_REGEX.finditer(text):

        token = clean(match.group(0))

        if token:
            found.append(token)

    # dedupe preserve order
    seen = set()

    final = []

    for f in found:

        key = f.lower()

        if key in seen:
            continue

        seen.add(key)

        final.append(f)

    return final

def _extract_address(block: Tag):

    best = []

    for line in _text_line(block):

        line = clean(line)

        if not line:
            continue

        if extract_phones(line):
            continue

        tokens = extract_location_tokens(line)

        if len(tokens) > len(best):
            best = tokens

    if not best:
        return ""

    return ", ".join(best)

# creates a dictionary with name + address _ phone + email
def _block_to_dealer(block: Tag) -> dict:
    text = _text_of(block)
    return {
        'name':    _extract_name(block),
        'address': _extract_address(block),
        'phone':   extract_phones(text),
        'email':   extract_emails(text),
    }

