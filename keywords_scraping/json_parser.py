import json
from keywords_scraping.contact_regex import _block_to_dealer, extract_phones

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

