"""
Merges Ellerbe Creek open channels + underground culverts into a single
non-overlapping river network.

Strategy: streams take priority. A culvert segment is excluded if ANY of
its coordinate points falls within ~20 yards (18m) of a stream point.
Result: clean single-line network with no doubled-up overlapping segments.

Output: data/river_merged.geojson
"""

import json, math
from collections import defaultdict

THRESHOLD_M = 18   # ~20 yards

# Grid cell size: use half the threshold so neighboring cells always overlap
GRID_LAT = (THRESHOLD_M / 2) / 111_000          # degrees latitude
GRID_LON = (THRESHOLD_M / 2) / (111_000 * math.cos(math.radians(36.0)))

def cell(lon, lat):
    return (int(lon / GRID_LON), int(lat / GRID_LAT))

def neighbors(cx, cy):
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            yield (cx + dx, cy + dy)


# ── Load data ─────────────────────────────────────────────────────────────────
with open("data/ellerbe_streams.geojson") as f:
    streams_raw = json.load(f)
with open("data/culverts_creek.geojson") as f:
    culverts_raw = json.load(f)

ellerbe_culverts = [
    feat for feat in culverts_raw["features"]
    if feat["properties"].get("OPERATIONALAREA") == "Ellerbe Creek"
]

print(f"Input: {len(streams_raw['features'])} stream segments, "
      f"{len(ellerbe_culverts)} Ellerbe culvert segments")


# ── Index all stream points into grid ─────────────────────────────────────────
stream_grid = set()

def index_coords(coords):
    for pt in coords:
        stream_grid.add(cell(pt[0], pt[1]))

stream_features = []
for feat in streams_raw["features"]:
    geom = feat["geometry"]
    coords = geom["coordinates"]
    if geom["type"] == "LineString":
        index_coords(coords)
        stream_features.append(feat)
    elif geom["type"] == "MultiLineString":
        for line in coords:
            index_coords(line)
            stream_features.append({
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": line},
                "properties": feat["properties"],
            })


# ── Filter culverts: exclude those near any stream point ──────────────────────
def near_stream(coords):
    """True if ANY point in coords is within ~18m of a stream point."""
    for pt in coords:
        cx, cy = cell(pt[0], pt[1])
        for nb in neighbors(cx, cy):
            if nb in stream_grid:
                return True
    return False

culvert_features = []
skipped = 0
for feat in ellerbe_culverts:
    geom = feat["geometry"]
    coords = geom["coordinates"]
    if geom["type"] == "MultiLineString":
        for line in coords:
            if not near_stream(line):
                culvert_features.append({
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": line},
                    "properties": feat["properties"],
                })
            else:
                skipped += 1
    elif geom["type"] == "LineString":
        if not near_stream(coords):
            culvert_features.append(feat)
        else:
            skipped += 1


# ── Combine and save ──────────────────────────────────────────────────────────
merged = stream_features + culvert_features
output = {"type": "FeatureCollection", "features": merged}

with open("data/river_merged.geojson", "w") as f:
    json.dump(output, f)

print(f"Skipped {skipped} culvert segments (within 18m of a stream)")
print(f"Output: {len(merged)} total segments  "
      f"({len(stream_features)} streams + {len(culvert_features)} unique culverts)")
print("Saved data/river_merged.geojson")
