from bs4 import BeautifulSoup
import pandas as pd
import requests
import time

# Load brands.csv
df = pd.read_csv("brands.csv")

# Email decoder
def decode_cfemail(encoded):
    r = int(encoded[:2], 16)
    return ''.join(
        chr(int(encoded[i:i+2], 16) ^ r)
        for i in range(2, len(encoded), 2)
    )

# Scrapper function
def scrape_brand_details(html):
    soup = BeautifulSoup(html, "html.parser")
    contact_blocks = soup.find_all("div", class_="contact-add")

    data = {
        "address": None,
        "phone1": None,
        "phone2": None,
        "email": None,
        "website": None
    }

    for block in contact_blocks:
        title_tag = block.find("h4")
        value_tag = block.find("p")

        if not title_tag or not value_tag:
            continue

        title = title_tag.get_text(strip=True).lower()
        value = value_tag.get_text(strip=True)

        # Address
        if "address" in title:
            data["address"] = value

        # Phone
        elif "call" in title:
            parts = [p.strip() for p in value.split("/") if p.strip()]
            data["phone1"] = parts[0] if len(parts) > 0 else None
            data["phone2"] = parts[1] if len(parts) > 1 else None

        # Email
        elif "email" in title:
            encoded_tag = block.find("span", class_="__cf_email__")

            if encoded_tag and encoded_tag.get("data-cfemail"):
                data["email"] = decode_cfemail(encoded_tag["data-cfemail"])
            else:
                data["email"] = value

        # Website
        elif "website" in title:
            link_tag = block.find("a")
            if link_tag:
                data["website"] = link_tag.get("href")

    return data

# Loop through each brand
results = []

for index, row in df.iterrows():
    url = row["link"]

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        details = scrape_brand_details(response.text)

        # merge original + scraped data
        combined = {
            "name": row["name"],
            "link": row["link"],
            "image": row["image"],
            **details
        }

        results.append(combined)

        print(f"Scraped: {row['name']}")

        time.sleep(1)  # be polite to server

    except Exception as e:
        print(f"Failed: {row['name']} -> {e}")

        results.append({
            "name": row["name"],
            "link": row["link"],
            "image": row["image"],
            "address": None,
            "phone1": None,
            "phone2": None,
            "email": None,
            "website": None
        })


# Export final CSV
final_df = pd.DataFrame(results)
final_df.to_csv("brand_detail.csv", index=False)

print("Done → brand_detail.csv created")