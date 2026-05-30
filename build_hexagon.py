"""
Generates a regular hexagon (flat-top, Catan-style) centered on downtown Durham
that encompasses the full map area.  Outputs:
  data/downtown.geojson        — the hexagon polygon
  data/downtown_mask.geojson   — inverted mask (world minus hexagon)
"""

import json
import math

# ── Center of the downtown Durham map view ────────────────────────────────────
CX = -78.900   # longitude
CY =  36.001   # latitude

# ── Geographic correction ─────────────────────────────────────────────────────
# 1° latitude  ≈ 111 km  (constant)
# 1° longitude ≈ 111 km × cos(lat)  (shrinks toward poles)
COS_LAT = math.cos(math.radians(CY))

# ── Circumradius ──────────────────────────────────────────────────────────────
# The downtown rectangle spans roughly:
#   lon: -78.912 → -78.889  (0.023°, ≈ 1.67 km)
#   lat:  35.997 →  36.008  (0.011°, ≈ 1.22 km)
# A flat-top hex with r_lat = 0.014° gives:
#   width  = 2 × r_lon = 2 × (0.014/cos_lat) ≈ 0.035°  → comfortably wider than 0.023°
#   height = √3 × r_lat ≈ 0.024°                         → comfortably taller than 0.011°
R_LAT = 0.014                   # degrees latitude  (≈ 1.56 km)
R_LON = R_LAT / COS_LAT        # degrees longitude (corrected for aspect ratio)

print(f"Hexagon center:       ({CX}, {CY})")
print(f"Circumradius (lat):   {R_LAT:.4f}°  ≈ {R_LAT*111:.1f} km")
print(f"Circumradius (lon):   {R_LON:.4f}°  ≈ {R_LON*111*COS_LAT:.1f} km")

# ── Flat-top hexagon vertices ─────────────────────────────────────────────────
# Angles 0°, 60°, 120°, 180°, 240°, 300° going counterclockwise
# (GeoJSON exterior rings are CCW)
angles = [0, 60, 120, 180, 240, 300]
ring = []
for a in angles:
    rad = math.radians(a)
    ring.append([
        round(CX + R_LON * math.cos(rad), 7),
        round(CY + R_LAT * math.sin(rad), 7),
    ])
ring.append(ring[0])   # close the ring

print("\nHex vertices (lon, lat):")
labels = ["E  ", "NE ", "NW ", "W  ", "SW ", "SE "]
for lbl, pt in zip(labels, ring[:-1]):
    print(f"  {lbl}  {pt}")

# ── Verify it encompasses the downtown rectangle ──────────────────────────────
DT_BOUNDS = dict(w=-78.912, e=-78.889, s=35.997, n=36.008)
lons = [p[0] for p in ring]
lats = [p[1] for p in ring]
ok = (min(lons) <= DT_BOUNDS['w'] and max(lons) >= DT_BOUNDS['e'] and
      min(lats) <= DT_BOUNDS['s'] and max(lats) >= DT_BOUNDS['n'])
print(f"\nEncompasses downtown bounds: {'✓ YES' if ok else '✗ NO — increase R_LAT'}")

# ── Save hexagon polygon ──────────────────────────────────────────────────────
hex_geojson = {
    "type": "FeatureCollection",
    "features": [{
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": {"name": "Downtown Durham"},
    }],
}
with open("data/downtown.geojson", "w") as f:
    json.dump(hex_geojson, f)
print("Saved data/downtown.geojson")

# ── Save inverted mask (world with hex hole) ──────────────────────────────────
# Outer ring CCW (already is), hole ring must be CW (reverse the hex ring)
mask_geojson = {
    "type": "FeatureCollection",
    "features": [{
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [[-180,-85],[180,-85],[180,85],[-180,85],[-180,-85]],  # outer CCW
                list(reversed(ring)),                                    # hex hole CW
            ],
        },
        "properties": {},
    }],
}
with open("data/downtown_mask.geojson", "w") as f:
    json.dump(mask_geojson, f)
print("Saved data/downtown_mask.geojson")
