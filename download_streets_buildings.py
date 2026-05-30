"""
Downloads OSM streets and buildings for the downtown Durham hex area.
Outputs: data/streets_downtown.geojson, data/buildings_downtown.geojson
"""

import json, urllib.request, urllib.parse

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
BBOX = "35.986,-78.921,36.016,-88.880"  # hex area + margin
BBOX = "35.986,-78.921,36.016,-78.880"

def overpass(query):
    params = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request(OVERPASS_URL, data=params, method="POST")
    req.add_header("User-Agent", "DurhamCreekViz/1.0")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())

def node_lookup(elements):
    return {el["id"]: (el["lon"], el["lat"]) for el in elements if el["type"] == "node"}

# ── Streets ───────────────────────────────────────────────────────────────────
print("Fetching streets...")
streets_raw = overpass(f"""
[out:json][timeout:30];
way["highway"~"primary|secondary|tertiary|residential|unclassified|living_street"]({BBOX});
out body; >; out skel qt;
""")
nodes = node_lookup(streets_raw["elements"])

street_features = []
for el in streets_raw["elements"]:
    if el["type"] != "way": continue
    tags = el.get("tags", {})
    coords = [[nodes[n][0], nodes[n][1]] for n in el.get("nodes", []) if n in nodes]
    if len(coords) < 2: continue
    street_features.append({
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coords},
        "properties": {
            "name": tags.get("name", ""),
            "highway": tags.get("highway", ""),
        },
    })

with open("data/streets_downtown.geojson", "w") as f:
    json.dump({"type": "FeatureCollection", "features": street_features}, f)
print(f"  Saved {len(street_features)} street ways → data/streets_downtown.geojson")

# ── Buildings ─────────────────────────────────────────────────────────────────
print("Fetching buildings...")
bldg_raw = overpass(f"""
[out:json][timeout:30];
way["building"]({BBOX});
out body; >; out skel qt;
""")
nodes = node_lookup(bldg_raw["elements"])

bldg_features = []
for el in bldg_raw["elements"]:
    if el["type"] != "way": continue
    tags = el.get("tags", {})
    coords = [[nodes[n][0], nodes[n][1]] for n in el.get("nodes", []) if n in nodes]
    if len(coords) < 4: continue

    # Height: prefer explicit height, fall back to levels, default 2 floors
    try:
        height_m = float(tags.get("height", 0))
    except ValueError:
        height_m = 0
    if not height_m:
        try:
            levels = float(tags.get("building:levels", 2))
        except ValueError:
            levels = 2
        height_m = levels * 4.0

    bldg_features.append({
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [coords]},
        "properties": {
            "name": tags.get("name", tags.get("addr:housename", "")),
            "height_m": height_m,
        },
    })

with open("data/buildings_downtown.geojson", "w") as f:
    json.dump({"type": "FeatureCollection", "features": bldg_features}, f)
print(f"  Saved {len(bldg_features)} building polygons → data/buildings_downtown.geojson")
