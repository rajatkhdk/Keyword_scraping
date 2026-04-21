import json

with open("provinces.json", encoding="utf-8") as f:
    provinces = json.load(f)

with open("districts.json", encoding="utf-8") as f:
    districts = json.load(f)

with open("local_levels.json", encoding="utf-8") as f:
    locals = json.load(f)

province_map = {p["province_id"]: p for p in provinces}
district_map = {d["district_id"]: d for d in districts}

LOCATION_DB = []

for loc in locals:
    district = district_map.get(loc["district_id"])
    province = province_map.get(district["province_id"]) if district else None

    LOCATION_DB.append({
        "municipality": loc["name"].lower(),
        "district": district["name"].lower() if district else None,
        "province": province["name"].lower() if province else None
    })

# print(LOCATION_DB)

LOCATION_LOOKUP = {}

for item in LOCATION_DB:
    # municipality
    if item["municipality"]:
        LOCATION_LOOKUP[item["municipality"]] = item
    
    # district
    if item["district"]:
        LOCATION_LOOKUP[item["district"]] = item

print(LOCATION_LOOKUP)