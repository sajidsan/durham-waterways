"""
Downloads Durham creek/culvert GeoJSON from Durham's ArcGIS REST API.
Run once: python3 download_data.py
Creates: data/ellerbe_streams.geojson, data/culverts_ellerbe.geojson
"""

import json
import os
import urllib.request
import urllib.parse

BASE = "https://webgis2.durhamnc.gov/server/rest/services/PublicWorksServices/StormwaterUtilitiesMapService/MapServer"

# Tight bbox: Ellerbe Creek corridor through downtown Durham
# Covers Durham Athletic Park → Trinity Park → Walltown → downtown core
BBOX_CULVERTS = "-78.945,35.985,-78.870,36.020"


def fetch_all(layer_id, where, label):
    """Paginate through ArcGIS query results and return merged FeatureCollection."""
    features = []
    offset = 0
    page_size = 1000

    while True:
        params = urllib.parse.urlencode({
            "where": where,
            "outFields": "*",
            "f": "geojson",
            "outSR": "4326",
            "resultOffset": offset,
            "resultRecordCount": page_size,
        })
        url = f"{BASE}/{layer_id}/query?{params}"
        print(f"  Fetching {label} offset={offset}...")

        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read())

        batch = data.get("features", [])
        features.extend(batch)

        if not data.get("exceededTransferLimit") or len(batch) == 0:
            break
        offset += page_size

    print(f"  Got {len(features)} features for {label}")
    return {"type": "FeatureCollection", "features": features}


def fetch_bbox(layer_id, bbox, label):
    """Fetch features within a bounding box."""
    xmin, ymin, xmax, ymax = bbox.split(",")
    features = []
    offset = 0
    page_size = 1000

    while True:
        params = urllib.parse.urlencode({
            "where": "1=1",
            "geometry": f"{xmin},{ymin},{xmax},{ymax}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*",
            "f": "geojson",
            "outSR": "4326",
            "resultOffset": offset,
            "resultRecordCount": page_size,
        })
        url = f"{BASE}/{layer_id}/query?{params}"
        print(f"  Fetching {label} offset={offset}...")

        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read())

        batch = data.get("features", [])
        features.extend(batch)

        if not data.get("exceededTransferLimit") or len(batch) == 0:
            break
        offset += page_size

    print(f"  Got {len(features)} features for {label}")
    return {"type": "FeatureCollection", "features": features}


os.makedirs("data", exist_ok=True)

print("Downloading Ellerbe Creek open channels (above-ground streams)...")
streams = fetch_all(
    layer_id=4,
    where="OPERATIONALAREA LIKE '%Ellerbe%'",
    label="Ellerbe streams",
)
with open("data/ellerbe_streams.geojson", "w") as f:
    json.dump(streams, f)
print(f"  Saved data/ellerbe_streams.geojson ({len(streams['features'])} features)\n")

print("Downloading underground pipes in Ellerbe Creek corridor (tight bbox)...")
culverts = fetch_bbox(
    layer_id=6,
    bbox=BBOX_CULVERTS,
    label="culverts (Ellerbe corridor)",
)
with open("data/culverts_ellerbe.geojson", "w") as f:
    json.dump(culverts, f)
print(f"  Saved data/culverts_ellerbe.geojson ({len(culverts['features'])} features)\n")

print("Done. Files in ./data/")
print("  ellerbe_streams.geojson   — Ellerbe Creek above-ground channels")
print("  culverts_ellerbe.geojson  — underground pipes in Ellerbe corridor (buried segments)")
