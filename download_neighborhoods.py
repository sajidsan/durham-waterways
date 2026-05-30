"""
Downloads Durham NC neighborhood boundaries from OpenStreetMap via Overpass API.
Handles both way-based and relation-based neighbourhood polygons.
Outputs: data/neighborhoods.geojson
"""

import json
import urllib.request
import urllib.parse

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
BBOX = "35.95,-78.96,36.06,-78.85"


def overpass(query):
    params = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request(OVERPASS_URL, data=params, method="POST")
    req.add_header("User-Agent", "DurhamCreekViz/1.0")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def build_node_lookup(elements):
    return {el["id"]: (el["lon"], el["lat"]) for el in elements if el["type"] == "node"}


def way_to_ring(way, nodes):
    coords = [nodes[nid] for nid in way.get("nodes", []) if nid in nodes]
    if len(coords) < 3:
        return None
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return coords


# ── 1. Ways tagged as neighbourhoods ─────────────────────────────────────────
print("Fetching neighbourhood ways from OSM...")
q_ways = f"""
[out:json][timeout:30];
way["place"~"neighbourhood|suburb|quarter"]["name"]({BBOX});
out body; >; out skel qt;
"""
osm_ways = overpass(q_ways)
nodes = build_node_lookup(osm_ways["elements"])

features = []
for el in osm_ways["elements"]:
    if el["type"] != "way":
        continue
    tags = el.get("tags", {})
    name = tags.get("name")
    if not name:
        continue
    ring = way_to_ring(el, nodes)
    if not ring:
        continue
    features.append({
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": {"name": name, "place": tags.get("place", ""), "osm_id": el["id"]},
    })

print(f"  Got {len(features)} way-based neighbourhood polygons")

# ── 2. Relation-based neighbourhoods (e.g. Downtown Durham) ──────────────────
print("Fetching neighbourhood relations from OSM...")
q_rels = f"""
[out:json][timeout:30];
relation["place"~"neighbourhood|suburb|quarter"]["name"]({BBOX});
out body; >; out skel qt;
"""
osm_rels = overpass(q_rels)
rel_nodes = build_node_lookup(osm_rels["elements"])

# Build way lookup from the relation response
way_lookup = {el["id"]: el for el in osm_rels["elements"] if el["type"] == "way"}

for el in osm_rels["elements"]:
    if el["type"] != "relation":
        continue
    tags = el.get("tags", {})
    name = tags.get("name")
    if not name:
        continue

    # Collect outer rings
    outer_rings = []
    for member in el.get("members", []):
        if member.get("type") == "way" and member.get("role") in ("outer", ""):
            way = way_lookup.get(member["ref"])
            if not way:
                continue
            ring = way_to_ring(way, rel_nodes)
            if ring:
                outer_rings.append(ring)

    if not outer_rings:
        continue

    geom = (
        {"type": "Polygon", "coordinates": outer_rings}
        if len(outer_rings) == 1
        else {"type": "MultiPolygon", "coordinates": [[r] for r in outer_rings]}
    )
    features.append({
        "type": "Feature",
        "geometry": geom,
        "properties": {"name": name, "place": tags.get("place", ""), "osm_id": el["id"]},
    })

print(f"  Got {len([f for f in features if f['properties']['osm_id'] > 0])} total features after relations")

# ── 3. Save ──────────────────────────────────────────────────────────────────
geojson = {"type": "FeatureCollection", "features": features}
with open("data/neighborhoods.geojson", "w") as f:
    json.dump(geojson, f)

print(f"\nSaved {len(features)} neighbourhoods to data/neighborhoods.geojson")
for feat in sorted(features, key=lambda x: x["properties"]["name"]):
    print(f"  · {feat['properties']['name']}")
