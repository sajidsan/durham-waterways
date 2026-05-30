"""
Builds river_smooth.geojson with:
  - Endpoint-merged chains (connected segments joined into continuous paths)
  - Chaikin corner smoothing
  - Correct west→east orientation (Ellerbe Creek flows WNW→ENE per USGS/Wikipedia)
  - Elevation sampled along the actual WNW→ENE creek path, NOT north-south

Source verified: Wikipedia + USGS NWIS
  Origin:  36°01'32"N 078°58'25"W  (lon -78.974)  elevation 460 ft
  Mouth:   36°04'15"N 078°47'06"W  (lon -78.785)  elevation 252 ft
  Drop:    208 ft over 13.04 miles  (~16 ft/mile)
  Direction: EAST (west-northwest to east-northeast)

The AI overview's claim of "flows south" is INCORRECT.
"""

import json, math, urllib.request
from collections import defaultdict

SNAP  = 0.000045   # ~5 m snapping
BBOX  = dict(w=-78.921, e=-78.880, s=35.986, n=36.016)

def in_bbox(lon, lat):
    return BBOX['w'] < lon < BBOX['e'] and BBOX['s'] < lat < BBOX['n']

def snap(lon, lat):
    return (round(lon / SNAP), round(lat / SNAP))

def chaikin(coords, n=2):
    for _ in range(n):
        out = [coords[0]]
        for a, b in zip(coords, coords[1:]):
            out.append([a[0]*.75+b[0]*.25, a[1]*.75+b[1]*.25])
            out.append([a[0]*.25+b[0]*.75, a[1]*.25+b[1]*.75])
        out.append(coords[-1])
        coords = out
    return coords

# ── Load & filter ──────────────────────────────────────────────────────────────
with open('data/river_merged.geojson') as f:
    raw = json.load(f)

segs = [
    feat['geometry']['coordinates']
    for feat in raw['features']
    if feat['geometry']['type'] == 'LineString'
    and len(feat['geometry']['coordinates']) >= 2
    and any(in_bbox(c[0], c[1]) for c in feat['geometry']['coordinates'])
]
print(f"Input segments in bbox: {len(segs)}")

# ── Build graph & trace chains ────────────────────────────────────────────────
adj   = defaultdict(list)
keys  = []
for i, coords in enumerate(segs):
    s, e = snap(*coords[0]), snap(*coords[-1])
    keys.append((s, e))
    adj[s].append((e, i, False))
    adj[e].append((s, i, True))

visited = set()
chains  = []

def trace(si, rev):
    coords = list(reversed(segs[si])) if rev else list(segs[si])
    visited.add(si)
    tail = snap(*coords[-1])
    while True:
        cands = [(ok, i, r) for ok, i, r in adj[tail] if i not in visited]
        if len(cands) != 1:
            break
        ok, i, r = cands[0]
        nxt = list(reversed(segs[i])) if r else list(segs[i])
        coords.extend(nxt[1:])
        visited.add(i)
        tail = snap(*coords[-1])
    return coords

for i in range(len(segs)):
    if i in visited:
        continue
    chain = trace(i, False)
    if len(chain) >= 2:
        chains.append(chain)

print(f"Traced {len(chains)} chains from {len(visited)} segments")

# ── Orient chains west→east (correct flow direction for Ellerbe Creek) ────────
# Ellerbe flows WNW→ENE: smaller longitude = upstream, larger lon = downstream.
def orient_west_to_east(chain):
    """Ensure first point is further west (smaller lon) than last point."""
    if chain[0][0] > chain[-1][0]:
        return list(reversed(chain))
    return chain

chains = [orient_west_to_east(c) for c in chains]
print(f"Oriented all chains west→east (upstream→downstream)")

# ── Chaikin smoothing ──────────────────────────────────────────────────────────
smooth_chains = [chaikin(c, n=2) for c in chains]

# ── Elevation along actual WNW→ENE creek path through downtown ────────────────
# The creek enters the downtown hex from the west (~-78.915) near Durham Athletic
# Park and exits east (~-78.883). Sample along this actual W→E transect.
# Per USGS/Wikipedia: ~16 ft/mile elevation drop overall.
# Approximate elevation in downtown: ~380 ft west, ~345 ft east (interpolated
# from 460 ft source at -78.974 to 252 ft at Falls Lake -78.785).

CREEK_TRANSECT = [
    # (lon, lat) — points tracing the actual Ellerbe Creek path through downtown
    # Running WNW to ENE: Durham Athletic Park → under downtown → toward E Durham
    (-78.9145, 36.0065),   # West entry near Durham Athletic Park
    (-78.9080, 36.0030),   # Under W Corporation / Trinity area
    (-78.9020, 36.0010),   # Central downtown culvert zone
    (-78.8980, 35.9995),   # Near Rigsbee Ave / Foster St
    (-78.8940, 35.9990),   # East downtown exit
    (-78.8890, 35.9985),   # Approaching E Durham / toward Falls Lake
]

def usgs_elev(lon, lat):
    url = (f"https://epqs.nationalmap.gov/v1/json"
           f"?x={lon:.6f}&y={lat:.6f}&wkid=4326&units=Feet&includeDate=false")
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            data = json.loads(r.read())
            val = float(data.get('value') or 0)
            return val if val > 0 else None
    except Exception:
        return None

print("\nQuerying USGS elevation along WNW→ENE creek transect:")
print("(Flow: west=upstream=higher elevation → east=downstream=lower elevation)")
elevations = []
for lon, lat in CREEK_TRANSECT:
    e = usgs_elev(lon, lat)
    if e:
        elevations.append({'lon': lon, 'lat': lat, 'elevation_ft': e})
        direction = "upstream" if lon < -78.905 else "downstream"
        print(f"  lon {lon:.4f}  lat {lat:.4f}  →  {e:.1f} ft  ({direction})")
    else:
        print(f"  lon {lon:.4f}  lat {lat:.4f}  →  (query failed)")

if elevations:
    west = elevations[0]['elevation_ft']
    east = elevations[-1]['elevation_ft']
    print(f"\n  West (upstream):   {west:.1f} ft")
    print(f"  East (downstream): {east:.1f} ft")
    drop = west - east
    print(f"  Drop across hex:   {drop:.1f} ft  "
          f"({'✓ correct — east is lower' if drop > 0 else '✗ unexpected — check data'})")

# ── Save outputs ──────────────────────────────────────────────────────────────
features = [
    {'type': 'Feature',
     'geometry': {'type': 'LineString', 'coordinates': c},
     'properties': {'length': len(c)}}
    for c in smooth_chains
]

elev_profile = {
    'type': 'FeatureCollection',
    'features': [
        {'type': 'Feature',
         'geometry': {'type': 'Point', 'coordinates': [p['lon'], p['lat']]},
         'properties': {
             'elevation_ft': p['elevation_ft'],
             'label': f"{p['elevation_ft']:.0f} ft",
             'upstream': p['lon'] < -78.905,
         }}
        for p in elevations
    ],
    'meta': {
        'source': 'USGS Elevation Point Query Service',
        'flow_direction': 'west_to_east (WNW→ENE)',
        'verified': 'Wikipedia Ellerbe Creek article + USGS NWIS',
        'note': 'AI overview claim of "flows south" is incorrect per USGS/Wikipedia',
    }
}

with open('data/river_smooth.geojson', 'w') as f:
    json.dump({'type': 'FeatureCollection', 'features': features}, f)
with open('data/elevation_profile.geojson', 'w') as f:
    json.dump(elev_profile, f)

print(f"\nSaved {len(features)} smooth chains → data/river_smooth.geojson")
print(f"Saved {len(elevations)} elevation points → data/elevation_profile.geojson")
