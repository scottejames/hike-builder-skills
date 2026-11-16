#!/usr/bin/env python3
"""Download OpenStreetMap paths and facilities for a hike area into a cache folder.

Usage:
  osm_fetch.py --around LAT,LON --radius-km 4 --out HIKE_DIR/.osm
  osm_fetch.py --bbox S,W,N,E --out HIKE_DIR/.osm

Writes ways.json (every highway=* way with geometry), pois.json (toilets,
parking, cafes, pubs, drinking water, scout huts) and meta.json (bbox, fetch
date, query version). The folder is a cache only: it can always be deleted and
re-fetched from the bbox. ensure() re-fetches when the cache is missing, older
than max_age_days, covers a different bbox, was made by an older query, or when
refresh=True. Overpass is shared, rate-limited infrastructure: this script
sends a User-Agent (Overpass answers 406 without one), retries with backoff and
falls back to mirrors.
"""
import argparse, json, math, os, sys, time, urllib.parse, urllib.request

ENDPOINTS = ["https://overpass-api.de/api/interpreter",
             "https://overpass.private.coffee/api/interpreter",
             "https://overpass.kumi.systems/api/interpreter"]
UA = "hikeBuilder/1.0 (scout hike planning; low volume)"

def bbox_around(lat, lon, km):
    dlat = km / 111.0
    dlon = km / (111.0 * math.cos(math.radians(lat)))
    return (lat - dlat, lon - dlon, lat + dlat, lon + dlon)

def overpass(query, attempts=6):
    data = urllib.parse.urlencode({"data": query}).encode()
    wait = 15
    for i in range(attempts):
        url = ENDPOINTS[i % len(ENDPOINTS)]
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=180) as r:
                body = r.read()
            if body.lstrip().startswith(b"{"):
                return json.loads(body)
            print(f"  {url}: non-JSON reply (busy?)", file=sys.stderr)
        except Exception as e:  # network/HTTP errors: back off and try the next mirror
            print(f"  {url}: {e}", file=sys.stderr)
        time.sleep(wait); wait = min(wait * 2, 120)
    sys.exit("Overpass failed on all endpoints - wait a few minutes and retry.")

QUERY_VERSION = 1   # bump when the queries below change: old caches are then re-fetched

def queries(bb):
    return {
        "ways.json": f'[out:json][timeout:150];way["highway"]({bb});out tags geom;',
        "pois.json": (f'[out:json][timeout:90];(nwr["amenity"~"^(toilets|parking|cafe|pub|drinking_water)$"]({bb});'
                      f'nwr["club"="scout"]({bb});nwr["name"~"[Ss]cout"]({bb}););out center tags;'),
    }

def cache_status(out, bbox, max_age_days=90):
    """Return None if the cache is usable, else the reason it must be re-fetched."""
    mp = os.path.join(out, "meta.json")
    if not all(os.path.exists(os.path.join(out, f)) for f in ("ways.json", "pois.json", "meta.json")):
        return "cache missing"
    m = json.load(open(mp))
    if m.get("query_version") != QUERY_VERSION: return "cache made by an older query"
    if bbox and any(abs(x - y) > 1e-4 for x, y in zip(m["bbox"], bbox)): return "cache covers a different area"
    age = (time.time() - m.get("fetched_at", 0)) / 86400
    if age > max_age_days: return f"cache is {age:.0f} days old (limit {max_age_days})"
    return None

def fetch(out, bbox):
    s, w, n, e = bbox; bb = f"{s:.5f},{w:.5f},{n:.5f},{e:.5f}"
    os.makedirs(out, exist_ok=True)
    for fn, q in queries(bb).items():
        d = overpass(q)
        json.dump(d, open(os.path.join(out, fn), "w"))
        print(f"{fn}: {len(d.get('elements', []))} elements")
    json.dump({"bbox": list(bbox), "fetched_at": time.time(), "fetched": time.strftime("%Y-%m-%d"),
               "query_version": QUERY_VERSION}, open(os.path.join(out, "meta.json"), "w"))
    old = os.path.join(out, "bbox.json")
    if os.path.exists(old): os.remove(old)

def ensure(out, bbox, max_age_days=90, refresh=False):
    why = "refresh requested" if refresh else cache_status(out, bbox, max_age_days)
    if why:
        print(f"OSM cache: {why} - fetching {bbox}")
        fetch(out, bbox)
    return why

def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--around"); g.add_argument("--bbox")
    ap.add_argument("--radius-km", type=float, default=4.0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--max-age-days", type=int, default=90)
    a = ap.parse_args()
    if a.around:
        lat, lon = map(float, a.around.split(","))
        bbox = bbox_around(lat, lon, a.radius_km)
    else:
        bbox = tuple(map(float, a.bbox.split(",")))
    bbox = tuple(round(x, 5) for x in bbox)
    if not ensure(a.out, bbox, a.max_age_days, a.refresh): print("OSM cache: up to date")
    print("bbox " + ",".join(f"{x:.5f}" for x in bbox) + "   <- record this as route.osm_bbox in hike.yaml")

if __name__ == "__main__":
    main()
