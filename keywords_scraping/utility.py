import re


# -------------------------
# SAFE LIST HANDLER
# -------------------------
def ensure_list(value):
    if not value:
        return []

    if isinstance(value, list):
        return value

    return [value]


# -------------------------
# SPLIT CONTACTS CLEANLY
# -------------------------
def split_contacts(values):
    result = []

    values = ensure_list(values)

    for value in values:
        if not value:
            continue

        parts = re.split(r"[,;\n]", str(value))

        for part in parts:
            cleaned = part.strip()

            if cleaned:
                result.append(cleaned)

    return result


# -------------------------
# PHONE NORMALIZATION (IMPROVED)
# -------------------------
def normalize_phone(phone):
    if not phone:
        return ""

    phone = str(phone).strip()

    # keep digits only
    phone = re.sub(r"\D", "", str(phone))

    # remove +977 or 977
    phone = re.sub(r"^(\+977|977)", "", phone)

    # # remove leading zero duplication cases safely
    # phone = phone.lstrip("0") if phone.startswith("0") else phone

    return phone.strip()


# -------------------------
# EMAIL NORMALIZATION
# -------------------------
def normalize_email(email):
    if not email:
        return ""

    return str(email).strip().lower()


# -------------------------
# DEALER STANDARDIZATION (FIXED)
# -------------------------
def standardize_dealers(dealers):

    if not isinstance(dealers, list):
        return []

    standardized = []

    for dealer in dealers:

        if not isinstance(dealer, dict):
            continue

        raw_phones = dealer.get("phones") or dealer.get("phone") or []
        raw_emails = dealer.get("emails") or dealer.get("email") or []

        phones = [
            p for p in split_contacts(raw_phones) if p
        ]

        emails = [
            e for e in split_contacts(raw_emails) if e
        ]

        standardized.append({
            "name": dealer.get("name", "").strip(),
            "address": dealer.get("address", "").strip(),
            "phones": phones,
            "emails": emails,
        })

    return standardized


# -------------------------
# FLATTEN LIST (SAFE)
# -------------------------
def flatten_list(values):
    flattened = []

    for value in values:

        if isinstance(value, list):
            flattened.extend(flatten_list(value))
        else:
            flattened.append(value)

    return flattened


# -------------------------
# DEDUPLICATION ENGINE (FIXED)
# -------------------------
def deduplicate_contacts(result):

    if not isinstance(result, dict):
        return {
            "website": "",
            "phones": [],
            "emails": [],
            "dealers": []
        }

    # -------------------------
    # GLOBAL DATA (NORMALIZED EARLY)
    # -------------------------
    global_phones = {
        normalize_phone(p)
        for p in flatten_list(result.get("phones", []))
        if normalize_phone(p)
    }

    global_emails = {
        normalize_email(e)
        for e in flatten_list(result.get("emails", []))
        if normalize_email(e)
    }

    dealers = result.get("dealers", [])

    dealer_phones = set()
    dealer_emails = set()

    # -------------------------
    # COLLECT DEALER CONTACTS
    # -------------------------
    for dealer in dealers:

        if not isinstance(dealer, dict):
            continue

        phones = split_contacts(
            dealer.get("phones") or dealer.get("phone") or []
        )

        emails = split_contacts(
            dealer.get("emails") or dealer.get("email") or []
        )

        for phone in phones:
            normalized = normalize_phone(phone)
            if normalized:
                dealer_phones.add(normalized)

        for email in emails:
            normalized = normalize_email(email)
            if normalized:
                dealer_emails.add(normalized)

    # -------------------------
    # CLEAN GLOBAL PHONES
    # -------------------------
    cleaned_phones = [
        p for p in global_phones
        if p and p not in dealer_phones
    ]

    # -------------------------
    # CLEAN GLOBAL EMAILS
    # -------------------------
    cleaned_emails = [
        e for e in global_emails
        if e and e not in dealer_emails
    ]

    # -------------------------
    # UPDATE RESULT
    # -------------------------
    result["phones"] = sorted(cleaned_phones)
    result["emails"] = sorted(cleaned_emails)

    return result