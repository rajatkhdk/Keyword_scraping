import json
from collections import defaultdict

with open("provinces.json", encoding="utf-8") as f:
    provinces = json.load(f)

with open("districts.json", encoding="utf-8") as f:
    districts = json.load(f)

with open("local_levels.json", encoding="utf-8") as f:
    locals = json.load(f)

province_map = {p["province_id"]: p for p in provinces}
district_map = {d["district_id"]: d for d in districts}

LOCATION_DB = []

# 1. Add municipality entries
for loc in locals:
    district = district_map.get(loc["district_id"])
    province = province_map.get(district["province_id"]) if district else None

    LOCATION_DB.append({
        "name": loc["name"].lower(),
        "type": "municipality",
        "municipality": loc["name"].lower(),
        "district": district["name"].lower() if district else None,
        "province": province["name"].lower() if province else None
    })

# 2. Add district entries separately
for d in districts:
    province = province_map.get(d["province_id"])

    LOCATION_DB.append({
        "name": d["name"].lower(),
        "type": "district",
        "municipality": None,
        "district": d["name"].lower(),
        "province": province["name"].lower() if province else None
    })

# print(LOCATION_DB)

# Build lookup without overwriting
LOCATION_LOOKUP = defaultdict(list)

for item in LOCATION_DB:
    # ALWAYS index by name
    LOCATION_LOOKUP[item["name"]].append(item)

    # # ALSO index by district (important fix)
    # if item["district"]:
    #     LOCATION_LOOKUP[item["district"]].append(item)

    # # ALSO index by municipality if exists
    # if item["municipality"]:
    #     LOCATION_LOOKUP[item["municipality"]].append(item)

# print(LOCATION_LOOKUP)

with open("address.json", "w", encoding = "utf-8") as f:
    json.dump(LOCATION_LOOKUP, f, ensure_ascii=False, indent=2)