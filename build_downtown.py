"""
Builds a downtown Durham polygon by tracing actual OSM street geometries:
  N Gregson St (west) · W Trinity Ave (north) · N Mangum St (east) · Chapel Hill St (south)

Outputs: data/downtown.geojson, data/downtown_mask.geojson
"""

import json
import urllib.request
import urllib.parse

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
BBOX = "35.985,-78.916,36.010,-78.882"


def overpass(query):
    params = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request(OVERPASS_URL, data=params, method="POST")
    req.add_header("User-Agent", "DurhamCreekViz/1.0")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def fetch_coords(name_pattern):
    q = f"""
[out:json][timeout:30];
way["name"~"{name_pattern}"]["highway"~"primary|secondary|tertiary|residential|unclassified"]({BBOX});
out body; >; out skel qt;
"""
    data = overpass(q)
    nodes = {el["id"]: (el["lon"], el["lat"])
             for el in data["elements"] if el["type"] == "node"}
    all_coords = []
    for el in data["elements"]:
        if el["type"] != "way":
            continue
        for nid in el.get("nodes", []):
            if nid in nodes:
                all_coords.append(nodes[nid])
    return dedupe(all_coords)


def dedupe(coords):
    seen = set()
    out = []
    for c in coords:
        k = (round(c[0], 7), round(c[1], 7))
        if k not in seen:
            seen.add(k)
            out.append(c)
    return out


def clip(coords, axis, lo, hi):
    return [(x, y) for x, y in coords if lo <= (x if axis == 0 else y) <= hi]


def sort_by(coords, axis, reverse=False):
    return sorted(coords, key=lambda c: c[axis], reverse=reverse)


print("Fetching street geometries from OSM…")
gregson    = fetch_coords("Gregson")
trinity    = fetch_coords("Trinity")
mangum     = fetch_coords("Mangum")
chapelhill = fetch_coords("Chapel Hill")

# From inspecting the actual coordinate ranges:
#   Gregson:    lon -78.910→-78.908   lat 35.995→36.017   (runs N-S on west side)
#   Trinity:    lon -78.912→-78.882   lat 36.005→36.008   (runs E-W on north side)
#   Mangum:     lon -78.904→-78.892   lat 35.988→36.012   (runs N-S on east side)
#   Chapel Hill:lon -78.917→-78.898   lat 35.997→35.997   (runs E-W on south side)
#
# Approximate intersection latitudes/longitudes:
#   Trinity latitude:    ~36.006
#   Chapel Hill latitude: ~35.997
#   Gregson longitude:   ~-78.909  (west boundary)
#   Mangum longitude:    spans -78.904→-78.892, so use center ~-78.898 for midpoint

# Chapel Hill's actual latitude is 35.9969–35.9970.
# Trinity's actual latitude range is 36.005–36.008.
# The N-S streets (Mangum, Gregson) must be clipped to [LAT_CH, LAT_TRINITY_HI]
# so they don't spike past the E-W streets at either end.
LAT_CH = 35.9968
LAT_TRINITY_HI = 36.008   # Trinity's northernmost lat — stop N-S streets HERE

# Trinity clips: west at Gregson's lon, east at where Mangum actually crosses Trinity
LON_TRINITY_W = -78.910   # Gregson's longitude
LON_TRINITY_E = -78.896   # Mangum's approximate lon at Trinity's latitude

# Side 1 — Trinity (north edge, W→E):
trinity_seg = clip(trinity,     axis=1, lo=36.004, hi=36.009)
trinity_seg = clip(trinity_seg, axis=0, lo=LON_TRINITY_W, hi=LON_TRINITY_E)
trinity_seg = sort_by(dedupe(trinity_seg), axis=0)   # west → east

# Side 2 — Mangum (east edge, N→S):
#   hi=LAT_TRINITY_HI stops Mangum at Trinity's latitude, preventing north spike
mangum_seg  = clip(mangum, axis=1, lo=LAT_CH, hi=LAT_TRINITY_HI)
mangum_seg  = sort_by(dedupe(mangum_seg), axis=1, reverse=True)  # north → south

# Side 3 — Chapel Hill (south edge, E→W):
ch_seg      = clip(chapelhill, axis=1, lo=35.995, hi=36.000)
ch_seg      = clip(ch_seg,     axis=0, lo=-78.912, hi=-78.892)
ch_seg      = sort_by(dedupe(ch_seg), axis=0, reverse=True)  # east → west

# Side 4 — Gregson (west edge, S→N):
#   hi=LAT_TRINITY_HI stops Gregson at Trinity's latitude, preventing north spike
gregson_seg = clip(gregson, axis=1, lo=LAT_CH, hi=LAT_TRINITY_HI)
gregson_seg = sort_by(dedupe(gregson_seg), axis=1)   # south → north

print(f"Segment points after clipping:")
print(f"  Trinity    (W→E):  {len(trinity_seg)}")
print(f"  Mangum     (N→S):  {len(mangum_seg)}")
print(f"  Chapel Hill(E→W):  {len(ch_seg)}")
print(f"  Gregson    (S→N):  {len(gregson_seg)}")

assert all(len(s) > 1 for s in [trinity_seg, mangum_seg, ch_seg, gregson_seg]), \
    "One or more segments clipped to empty — check coordinate bounds"

# Assemble CCW ring: start NW, go east along Trinity → south along Mangum
#   → west along Chapel Hill → north along Gregson → back to start
ring = trinity_seg + mangum_seg + ch_seg + gregson_seg
if ring[0] != ring[-1]:
    ring.append(ring[0])

print(f"Final polygon ring: {len(ring)} points")

# ── Save files ────────────────────────────────────────────────────────────────
downtown = {
    "type": "FeatureCollection",
    "features": [{
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": {"name": "Downtown Durham"},
    }],
}
with open("data/downtown.geojson", "w") as f:
    json.dump(downtown, f)
print("Saved data/downtown.geojson")

# Inverted mask: world with downtown cut out (outer CCW, hole CW)
mask = {
    "type": "FeatureCollection",
    "features": [{
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [[-180,-85],[180,-85],[180,85],[-180,85],[-180,-85]],
                list(reversed(ring)),
            ],
        },
        "properties": {},
    }],
}
with open("data/downtown_mask.geojson", "w") as f:
    json.dump(mask, f)
print("Saved data/downtown_mask.geojson")
