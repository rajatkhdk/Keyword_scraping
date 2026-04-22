"""
Independent file:
Counts the no. of entries in address.json with same municipality and district value
e.g. 
{
      "name": "kathmandu",
      "type": "municipality",
      "municipality": "kathmandu",
      "district": "kathmandu",
      "province": "bagmati pradesh"
    }
"""

import json

with open("address.json", encoding="utf-8") as f:
    LOCATION_LOOKUP = json.load(f)

count = 0

for items in LOCATION_LOOKUP.values():
    for item in items:
        if (
            item.get("municipality") == item.get("district")
        ):
            count += 1

print("Total count:", count)