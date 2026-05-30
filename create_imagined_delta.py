"""
create_imagined_delta.py — v2
Derives hypothesis waterway connections directly from the real creek data.

Algorithm:
  1. Load river_smooth.geojson (merged, smoothed real chains)
  2. Extract every chain endpoint (first + last coordinate)
  3. Mark endpoints as "dangling" if no other chain comes within SNAP_M metres
  4. For every pair of dangling endpoints from different chains:
       - Compute gap distance in metres
       - Score confidence from distance + flow alignment (WNW→ENE = east = positive)
  5. Deduplicate, filter < MAX_GAP_M, cap total connections
  6. Save data/imagined_delta.geojson with provenance metadata

Decisions recorded in each feature's properties, not guessed from maps.
"""

import json, math
from collections import defaultdict
from itertools import combinations

# ── Config ─────────────────────────────────────────────────────────────────────
SNAP_M      = 18     # endpoints within 18m are already "connected" — skip
MAX_GAP_M   = 400    # largest gap we'll bridge

# Tier caps
MAX_MICRO   = 40     # < 60m  — near-certain missing culverts
MAX_SHORT   = 20     # 60–150m — plausible buried sections
MAX_LONG    = 15     # 150–400m — speculative but flow-aligned

# Flow alignment: for longer gaps, only accept if vector is within ALIGN_DEG of east
ALIGN_DEG   = 55     # ±55° off due-east allowed
BBOX        = dict(w=-78.921, e=-78.880, s=35.986, n=36.016)

# Ellerbe Creek flow vector (WNW→ENE ≈ east + tiny north)
FLOW_VEC = (1.0, 0.08)   # (east, north) normalised-ish

def in_bbox(lon, lat):
    return BBOX['w'] < lon < BBOX['e'] and BBOX['s'] < lat < BBOX['n']

def dist_m(a, b):
    mid_lat = (a[1] + b[1]) / 2
    dx = (b[0] - a[0]) * 111_000 * math.cos(math.radians(mid_lat))
    dy = (b[1] - a[1]) * 111_000
    return math.sqrt(dx * dx + dy * dy)

def flow_score(a, b):
    """1.0 if gap goes eastward (correct WNW→ENE), 0.0 if westward."""
    dx = b[0] - a[0]
    return max(0.0, min(1.0, (dx / (abs(dx) + 0.0001) + 1) / 2))

def is_flow_aligned(a, b, max_deg=ALIGN_DEG):
    """True if the vector a→b is within max_deg degrees of due east."""
    mid_lat = (a[1] + b[1]) / 2
    dx = (b[0] - a[0]) * 111_000 * math.cos(math.radians(mid_lat))
    dy = (b[1] - a[1]) * 111_000
    if dx == 0 and dy == 0:
        return False
    angle_deg = math.degrees(math.atan2(abs(dy), abs(dx)))
    # angle_deg is 0° for due E/W, 90° for due N/S
    return angle_deg <= max_deg and dx >= 0   # must go eastward

def confidence(d_m, a, b):
    """Score 0.80–0.95 from gap distance and flow alignment."""
    # Distance component: 0.95 at 0m → 0.80 at MAX_GAP_M
    dist_score = 0.95 - 0.15 * (d_m / MAX_GAP_M)
    # Flow bonus: up to +0.03 for eastward, -0.03 for westward
    flow_bonus  = (flow_score(a, b) - 0.5) * 0.06
    return round(max(0.80, min(0.95, dist_score + flow_bonus)), 3)

# ── Load data ──────────────────────────────────────────────────────────────────
with open('data/river_smooth.geojson') as f:
    smooth = json.load(f)

chains = [
    feat['geometry']['coordinates']
    for feat in smooth['features']
    if feat['geometry']['type'] == 'LineString'
    and len(feat['geometry']['coordinates']) >= 2
    and any(in_bbox(c[0], c[1]) for c in feat['geometry']['coordinates'])
]
print(f"Loaded {len(chains)} real chains")

# ── Extract all endpoints ──────────────────────────────────────────────────────
# Each endpoint: (lon, lat, chain_index, position='start'|'end')
all_eps = []
for i, chain in enumerate(chains):
    if in_bbox(*chain[0]):
        all_eps.append({'coord': chain[0],  'chain': i, 'pos': 'start'})
    if in_bbox(*chain[-1]):
        all_eps.append({'coord': chain[-1], 'chain': i, 'pos': 'end'})

print(f"Total endpoints: {len(all_eps)}")

# ── Spatial grid for fast proximity check ─────────────────────────────────────
GRID_M = 25
def cell(lon, lat):
    x = int(lon * 111_000 * math.cos(math.radians(lat)) / GRID_M)
    y = int(lat * 111_000 / GRID_M)
    return (x, y)

grid = defaultdict(list)
for ep in all_eps:
    grid[cell(*ep['coord'])].append(ep)

def nearby(coord, radius_m):
    cx, cy = cell(*coord)
    r = math.ceil(radius_m / GRID_M) + 1
    found = []
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            for ep in grid.get((cx + dx, cy + dy), []):
                if dist_m(coord, ep['coord']) <= radius_m:
                    found.append(ep)
    return found

# ── Find dangling endpoints ────────────────────────────────────────────────────
dangling = []
for ep in all_eps:
    neighbors = [n for n in nearby(ep['coord'], SNAP_M)
                 if n['chain'] != ep['chain']]
    if not neighbors:
        dangling.append(ep)

print(f"Dangling endpoints: {len(dangling)}")

# ── Find gap pairs ─────────────────────────────────────────────────────────────
# For every pair of dangling endpoints from different chains, within MAX_GAP_M
candidates = []
seen_pairs = set()

for i, a in enumerate(dangling):
    nearby_dangling = [
        b for b in nearby(a['coord'], MAX_GAP_M)
        if b['chain'] != a['chain']
        and (b['chain'], b['pos']) in {(ep['chain'], ep['pos']) for ep in dangling}
    ]
    for b in nearby_dangling:
        pair_key = tuple(sorted([
            (a['chain'], a['pos']),
            (b['chain'], b['pos'])
        ]))
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)
        d = dist_m(a['coord'], b['coord'])
        if d < SNAP_M or d > MAX_GAP_M:
            continue
        conf = confidence(d, a['coord'], b['coord'])
        candidates.append({
            'a': a['coord'], 'b': b['coord'],
            'dist_m': round(d, 1), 'confidence': conf,
            'chain_a': a['chain'], 'chain_b': b['chain'],
        })

# Sort: shorter gaps first (more confident)
candidates.sort(key=lambda x: x['dist_m'])
print(f"Gap candidates before dedup: {len(candidates)}")

# ── Three-tier selection ───────────────────────────────────────────────────────
used = defaultdict(int)

def pick(min_d, max_d, cap, require_aligned, max_per_chain=2):
    links = []
    for c in candidates:
        if not (min_d <= c['dist_m'] < max_d):
            continue
        ca, cb = c['chain_a'], c['chain_b']
        if used[ca] >= max_per_chain or used[cb] >= max_per_chain:
            continue
        if require_aligned and not is_flow_aligned(c['a'], c['b']):
            continue
        links.append(c)
        used[ca] += 1
        used[cb] += 1
        if len(links) >= cap:
            break
    return links

micro_links = pick(SNAP_M, 60,  MAX_MICRO, require_aligned=False)
short_links = pick(60,     150, MAX_SHORT, require_aligned=False)
long_links  = pick(150,    MAX_GAP_M, MAX_LONG, require_aligned=True, max_per_chain=1)

filtered = micro_links + short_links + long_links
print(f"Selected {len(micro_links)} micro + {len(short_links)} short + {len(long_links)} long = {len(filtered)} total")

# ── Build GeoJSON features ─────────────────────────────────────────────────────
features = []
for idx, c in enumerate(filtered):
    a, b = c['a'], c['b']
    # Orient west→east (upstream→downstream)
    if a[0] > b[0]:
        a, b = b, a
    d = c['dist_m']

    # Classify the gap type based on distance
    if d < 60:
        gap_type = "micro_gap"
        reasoning = (f"Only {d:.0f}m between real chain endpoints — almost certainly "
                     "a short culvert under a road or parking lot missing from the utility DB.")
    elif d < 150:
        gap_type = "short_gap"
        reasoning = (f"{d:.0f}m gap. Likely a culverted section under a road crossing "
                     "or small building not captured in the stormwater database.")
    elif d < 250:
        gap_type = "medium_gap"
        reasoning = (f"{d:.0f}m flow-aligned gap. Plausible buried tributary. "
                     "Included only if vector is eastward (WNW→ENE flow direction).")
    else:
        gap_type = "long_bridge"
        reasoning = (f"{d:.0f}m flow-aligned bridge. Speculative — requires field verification. "
                     "Included because it spans the largest visible network gaps "
                     "while following the confirmed WNW→ENE Ellerbe Creek flow direction.")

    features.append({
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": [a, b]},
        "properties": {
            "id": f"gap-{idx:03d}",
            "confidence": c['confidence'],
            "gap_type": gap_type,
            "gap_distance_m": d,
            "reasoning": reasoning,
            "flow_direction": "WNW→ENE (west=upstream)",
            "min_width_ft": 3,
            "source": "derived from real chain endpoints in river_smooth.geojson",
            "note": "Both endpoints anchored to actual stormwater data — no hardcoded guesses",
        },
    })

out = {
    "type": "FeatureCollection",
    "features": features,
    "metadata": {
        "method": "endpoint proximity from real data",
        "snap_m": SNAP_M,
        "max_gap_m": MAX_GAP_M,
        "flow_direction": "WNW→ENE (USGS verified)",
        "all_endpoints_from": "river_smooth.geojson (real Durham stormwater utility data)",
    },
}

with open('data/imagined_delta.geojson', 'w') as f:
    json.dump(out, f)

# ── Summary ────────────────────────────────────────────────────────────────────
if filtered:
    dists = [c['dist_m'] for c in filtered]
    confs = [c['confidence'] for c in filtered]
    counts = defaultdict(int)
    for feat in features:
        counts[feat['properties']['gap_type']] += 1

    print(f"\nGap distance range: {min(dists):.0f}m – {max(dists):.0f}m")
    print(f"Confidence range:   {min(confs):.2f} – {max(confs):.2f}")
    print(f"\nGap types:")
    for t, n in sorted(counts.items()):
        print(f"  {t}: {n}")
    print(f"\nSaved {len(features)} hypothesis connections → data/imagined_delta.geojson")
