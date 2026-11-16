#!/usr/bin/env python3
"""List hike resources from an osm_fetch.py cache, with 6-figure grid references.

Usage: facilities.py OSM_DIR [--known-huts known-huts.yaml]

Sections printed:
  TOILETS / PARKING / CAFES-PUBS / SCOUT HUTS  - from pois.json (+ known huts)
  ROAD ACCESS - points where a bridleway/byway meets a public road: the
                vehicle-accessible checkpoint candidates.
"""
import sys; sys.dont_write_bytecode = True  # no __pycache__ next to the tools
import argparse, collections, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from osgb import gridref

ROADS = ("primary", "secondary", "tertiary", "unclassified", "residential", "trunk")

def centre(e):
    c = e.get("center", e)
    return c["lat"], c["lon"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("osm_dir"); ap.add_argument("--known-huts")
    a = ap.parse_args()
    pois = json.load(open(os.path.join(a.osm_dir, "pois.json")))["elements"]
    groups = collections.defaultdict(list)
    for e in pois:
        t = e.get("tags", {}); am = t.get("amenity"); lat, lon = centre(e)
        name = t.get("name", "")
        if t.get("club") == "scout" or "scout" in name.lower():
            groups["SCOUT HUTS (OSM - confirm access before relying on one)"].append((name or "scout site", lat, lon, ""))
        elif am == "toilets":
            groups["TOILETS"].append((name or "toilets", lat, lon, f"access={t.get('access','?')} {t.get('opening_hours','')}".strip()))
        elif am == "parking":
            if t.get("access") in ("private", "permit", "customers") or t.get("parking") == "street_side" and not name:
                continue
            if not (name or t.get("operator") or t.get("fee")):
                continue
            groups["PARKING"].append((name or t.get("operator", "car park"), lat, lon, f"fee={t.get('fee','?')} {t.get('operator','')}".strip()))
        elif am in ("cafe", "pub"):
            groups["CAFES / PUBS (toilets for customers)"].append((name or am, lat, lon, f"{am} {t.get('opening_hours','')}".strip()))
        elif am == "drinking_water":
            groups["DRINKING WATER"].append((name or "tap", lat, lon, ""))
    if a.known_huts and os.path.exists(a.known_huts):
        import yaml
        for h in (yaml.safe_load(open(a.known_huts)) or {}).get("huts") or []:
            if h.get("lat") and h.get("lon"):
                groups["KNOWN HUTS (from known-huts.yaml)"].append((h["name"], h["lat"], h["lon"], f"toilets={h.get('toilets')} contact={h.get('contact','')}"))
    for g, items in groups.items():
        print(f"== {g}")
        for n, la, lo, x in items:
            print(f"  {gridref(la, lo)}  {la:.5f},{lo:.5f}  {n}  {x}")
    # road access points
    ways = json.load(open(os.path.join(a.osm_dir, "ways.json")))["elements"]
    rn = collections.defaultdict(set); bn = set()
    for e in ways:
        t = e["tags"]; g = [(q["lat"], q["lon"]) for q in e["geometry"]]
        if t.get("highway") in ROADS and t.get("access") not in ("private", "no"):
            for x in g: rn[x].add(t.get("name") or t.get("ref") or t["highway"])
        des = t.get("designation", "")
        if "bridleway" in des or "byway" in des or t.get("highway") == "bridleway":
            bn.update(g)
    pts = []
    for x in sorted(p for p in bn if p in rn):
        if all(abs(x[0] - o[0]) > 0.002 or abs(x[1] - o[1]) > 0.003 for o, _ in pts):
            pts.append((x, rn[x]))
    print("== ROAD ACCESS (bridleway meets public road)")
    for (la, lo), n in pts:
        print(f"  {gridref(la, lo)}  {la:.5f},{lo:.5f}  {', '.join(sorted(n))}")

if __name__ == "__main__":
    main()
