import json

with open("address_json/address.json", "r", encoding="utf-8") as f:
    location_data = json.load(f)

LOCATION_LOOKUP = {}
location_list = []

for key, entries in location_data.items():
    for entry in entries:
        name = entry["name"].strip().lower()
        LOCATION_LOOKUP[name] = entry
        # print("Location lookup name : ", name)
        location_list.append(name)

# print("Location list : ", location_list)

with open("address_json/location_list.json", "w", encoding="utf-8") as f:
    json.dump(location_list, f, ensure_ascii=False, indent=2)

