from bs4 import BeautifulSoup
import pandas as pd

with open("lsauto.html", "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")

contact_blocks = soup.find_all("div", class_="contact-add")

data = {}

def decode_cfemail(encoded):
    r = int(encoded[:2], 16)
    email = ''.join(
        chr(int(encoded[i:i+2], 16) ^ r)
        for i in range(2, len(encoded), 2)
    )
    return email

for block in contact_blocks:
    title_tag = block.find("h4")
    value_tag = block.find("p")

    if not title_tag or not value_tag:
        continue

    title = title_tag.get_text(strip=True).lower()
    value = value_tag.get_text(strip=True)

    if "address" in title:
        data["address"] = value

    elif "call" in title:
        raw_phone = value.strip()

        if raw_phone:
            parts = [p.strip() for p in raw_phone.split("/")]

            data["phone1"] = parts[0] if len(parts) >= 1 else None
            data["phone2"] = parts[1] if len(parts) >= 2 else None
        else:
            data["phone1"] = None
            data["phone2"] = None

    elif "email" in title:
        encoded_tag = block.find("span", class_="__cf_email__")
    
        if encoded_tag:
            encoded = encoded_tag.get("data-cfemail")
            decoded_email = decode_cfemail(encoded)
            data["email"] = decoded_email
        else:
            data["email"] = value

    elif "website" in title:
        link_tag = block.find("a")
        if link_tag:
            data["website"] = link_tag.get("href")


print(data)
