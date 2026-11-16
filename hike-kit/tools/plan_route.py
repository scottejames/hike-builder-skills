#!/usr/bin/env python3
"""Route a hike through ordered points on OSM paths, preferring bridleways.

Usage:
  plan_route.py OSM_DIR "START@lat,lon;~lat,lon;CP1@lat,lon;...;FINISH@lat,lon" \
      [--pace 4] [--junctions]

Library: route(osm_dir, points, pace) returns the track, checkpoints and legs.
Nothing is written to disk: the routing points in hike.yaml plus the OSM cache
are the source, and every tool re-routes from them when it needs the line.

Points: LABEL@lat,lon is a checkpoint; ~lat,lon is a shaping point (forces the
line through a place without making it a checkpoint). Legs run checkpoint to
checkpoint. Edges already walked are penalised x4 so a loop comes back a
different way.

Prints, per leg: distance, time at --pace, metres by surface class and road
metres. With --junctions also prints every decision point (turns and
junctions) with grid refs, and a LOST-RISK review per leg.

Surface classes and weights (lower = preferred):
  bridleway 1.0 (public/permissive bridleway, byway)   footpath 1.6
  path 1.8 (unclassified track/path/footway)          lane 3.0 (service/residential)
  road 25 (tertiary and above: effectively avoided; crossings still allowed)
"""
import sys; sys.dont_write_bytecode = True  # no __pycache__ next to the tools
import argparse, heapq, json, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from osgb import gridref

W = {"bridleway": 1.0, "footpath": 1.6, "path": 1.8, "lane": 3.0, "road": 25.0}

def hav(a, b):
    R = 6371000; la1, lo1 = map(math.radians, a); la2, lo2 = map(math.radians, b)
    h = math.sin((la2-la1)/2)**2 + math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
    return 2*R*math.asin(math.sqrt(h))

def brg(a, b):
    y = math.sin(math.radians(b[1]-a[1]))*math.cos(math.radians(b[0]))
    x = (math.cos(math.radians(a[0]))*math.sin(math.radians(b[0]))
         - math.sin(math.radians(a[0]))*math.cos(math.radians(b[0]))*math.cos(math.radians(b[1]-a[1])))
    return (math.degrees(math.atan2(y, x)) + 360) % 360

def compass(b):
    n = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]
    return n[int((b + 11.25)//22.5) % 16]

def cls(t):
    hw = t.get("highway"); des = t.get("designation", "")
    if hw in ("steps", "corridor", "motorway", "trunk", "trunk_link", "proposed", "construction", "platform"):
        return None
    if t.get("access") in ("private", "no") or t.get("foot") == "no":
        return None
    if "bridleway" in des or hw == "bridleway" or "byway" in des: return "bridleway"
    if "footpath" in des: return "footpath"
    if hw in ("track", "path", "footway", "cycleway", "pedestrian"): return "path"
    if hw in ("service", "unclassified", "residential", "living_street"): return "lane"
    return "road"

def load_graph(osm_dir):
    D = json.load(open(os.path.join(osm_dir, "ways.json")))
    G, edges, nb = {}, {}, {}
    for e in D["elements"]:
        t = e["tags"]; g = [(p["lat"], p["lon"]) for p in e["geometry"]]
        lab = t.get("designation") or t.get("highway")
        for a, b in zip(g, g[1:]):
            nb.setdefault(a, set()).add(b); nb.setdefault(b, set()).add(a)
            edges.setdefault((a, b), (None, lab, t.get("name", ""))); edges.setdefault((b, a), (None, lab, t.get("name", "")))
        c = cls(t)
        if not c: continue
        for a, b in zip(g, g[1:]):
            d = hav(a, b)
            for u, v in ((a, b), (b, a)):
                G.setdefault(u, []).append((v, d * W[c]))
                edges[(u, v)] = (c, lab, t.get("name", ""))
    return G, edges, nb

class NoPath(Exception):
    pass

def shortest(G, a, b, used):
    dist = {a: 0}; prev = {}; pq = [(0, a)]
    while pq:
        d, u = heapq.heappop(pq)
        if u == b: break
        if d > dist[u]: continue
        for v, w in G.get(u, ()):
            if (u, v) in used: w *= 4
            nd = d + w
            if nd < dist.get(v, 1e18): dist[v] = nd; prev[v] = u; heapq.heappush(pq, (nd, v))
    if b not in dist: raise NoPath(f"No path between {a} and {b} - widen the OSM area, refresh the cache, or move the point.")
    path = [b]
    while path[-1] != a: path.append(prev[path[-1]])
    return path[::-1]

def parse_points(s):
    pts = []
    for tok in s.split(";"):
        tok = tok.strip()
        if tok.startswith("~"): pts.append((None, tuple(map(float, tok[1:].split(",")))))
        else:
            lab, ll = tok.split("@"); pts.append((lab.strip(), tuple(map(float, ll.split(",")))))
    return pts

_GRAPHS = {}

def route(osm_dir, points, pace=4.0):
    """Route through the points string. Returns a dict with track, checkpoints,
    legs, total_km, surface_m and snap warnings (plus internals for --junctions)."""
    key = os.path.abspath(osm_dir)
    if key not in _GRAPHS: _GRAPHS[key] = load_graph(osm_dir)
    G, edges, nb = _GRAPHS[key]
    pts = parse_points(points)
    nodes = [min(G, key=lambda n: hav(n, p)) for _, p in pts]
    snaps = [f"{lab or 'shaping point'} snapped {hav(n, p):.0f} m to the nearest path"
             for (lab, p), n in zip(pts, nodes) if hav(n, p) > 150]
    full = [nodes[0]]; used = set(); marks = [0]
    for x, y in zip(nodes, nodes[1:]):
        p = shortest(G, x, y, used); full += p[1:]; marks.append(len(full) - 1)
        for u, v in zip(p, p[1:]): used.add((u, v)); used.add((v, u))
    cum = [0.0]
    for u, v in zip(full, full[1:]): cum.append(cum[-1] + hav(u, v))
    cps = [dict(label=lab, lat=full[i][0], lon=full[i][1], km=round(cum[i]/1000, 3), gr=gridref(*full[i]))
           for (lab, _), i in zip(pts, marks) if lab]
    cp_idx = [i for (lab, _), i in zip(pts, marks) if lab]
    legs = []
    for k, (i0, i1) in enumerate(zip(cp_idx, cp_idx[1:])):
        s = {}
        for u, v in zip(full[i0:i1], full[i0+1:i1+1]):
            c = edges[(u, v)][0]; s[c] = s.get(c, 0) + hav(u, v)
        d = cum[i1] - cum[i0]
        legs.append(dict(frm=cps[k]["label"], to=cps[k+1]["label"], km=round(d/1000, 2),
                         minutes=round(d/1000/pace*60), surface={c: round(m) for c, m in s.items()}))
    tot = {}
    for l in legs:
        for c, m in l["surface"].items(): tot[c] = tot.get(c, 0) + m
    return dict(track=full, checkpoints=cps, legs=legs, total_km=round(cum[-1]/1000, 3),
                surface_m={c: round(m) for c, m in tot.items()}, snaps=snaps,
                _cum=cum, _cp_idx=cp_idx, _edges=edges, _nb=nb)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("osm_dir"); ap.add_argument("points")
    ap.add_argument("--pace", type=float, default=4.0)
    ap.add_argument("--junctions", action="store_true")
    a = ap.parse_args()
    try:
        r = route(a.osm_dir, a.points, a.pace)
    except NoPath as e:
        sys.exit(str(e))
    for w in r["snaps"]: print("WARNING:", w)
    full, cum, cps, legs, cp_idx = r["track"], r["_cum"], r["checkpoints"], r["legs"], r["_cp_idx"]
    edges, nb = r["_edges"], r["_nb"]
    tot = r["surface_m"]
    T = cum[-1]
    print(f"TOTAL {T/1000:.2f} km ({T/1609.34:.2f} mi), {T/1000/a.pace*60:.0f} min at {a.pace} km/h")
    print("  surface: " + ", ".join(f"{c} {m/1000:.2f} km ({100*m/T:.0f}%)" for c, m in sorted(tot.items(), key=lambda x: -x[1])))
    for c in cps: print(f"  {c['label']:<8} {c['km']:6.2f} km  {c['gr']}  {c['lat']:.5f},{c['lon']:.5f}")
    for l in legs:
        flag = "  <-- outside 40-50 min guide" if not 40 <= l["minutes"] <= 50 else ""
        print(f"LEG {l['frm']}->{l['to']}: {l['km']:.2f} km {l['minutes']} min  road={l['surface'].get('road',0)} m  "
              + " ".join(f"{c}={m}" for c, m in l["surface"].items()) + flag)
    # revisits
    seen = {}
    revisits = []
    for i, n in enumerate(full):
        if len(nb.get(n, ())) >= 3:
            if n in seen and cum[i] - cum[seen[n]] > 300: revisits.append((n, cum[seen[n]], cum[i]))
            seen.setdefault(n, i)
    if a.junctions:
        print("\nDECISION POINTS (junctions where the route turns or other paths leave)")
        last = -1e9; leg = 0; per_leg = [0]*(len(legs) or 1); sharp = [0]*(len(legs) or 1)
        def at(i, dm, fwd):
            j = i
            while 0 < j < len(full)-1 and abs(cum[j]-cum[i]) < dm: j += 1 if fwd else -1
            return full[j]
        for i in range(1, len(full)-1):
            while leg < len(cp_idx)-1 and i > cp_idx[leg+1]: leg += 1
            n = full[i]; others = [m for m in nb.get(n, ()) if m not in (full[i-1], full[i+1])]
            if not others or cum[i]-last < 40: continue
            bi = brg(at(i, 40, False), n); bo = brg(n, at(i, 40, True)); turn = ((bo-bi+540) % 360)-180
            last = cum[i]
            word = "STRAIGHT" if abs(turn) < 30 else ("RIGHT" if turn > 0 else "LEFT") + (" (sharp)" if abs(turn) > 110 else "")
            li = min(leg, len(per_leg)-1)
            if abs(turn) >= 30: per_leg[li] += 1
            if abs(turn) > 110: sharp[li] += 1
            olab = sorted({edges.get((n, m), (None, '?', ''))[1] or '?' for m in others})
            print(f"  {cum[i]/1000:5.2f} km {word:<15} {gridref(*n)}  {n[0]:.5f},{n[1]:.5f}  heading {compass(bo)}  "
                  f"in:{edges[(full[i-1], n)][1]} out:{edges[(n, full[i+1])][1]} others:{','.join(olab)}")
        print("\nLOST-RISK REVIEW")
        for k, l in enumerate(legs):
            notes = []
            if per_leg[k] >= 5: notes.append(f"{per_leg[k]} turns - consider a via checkpoint")
            if sharp[k]: notes.append(f"{sharp[k]} sharp turn(s)")
            if l["minutes"] > 55: notes.append("long leg - consider a via checkpoint")
            pathy = l["surface"].get("path", 0) + l["surface"].get("footpath", 0)
            if pathy > 0.4*l["km"]*1000: notes.append("mostly unsigned paths - harder to follow")
            print(f"  {l['frm']}->{l['to']}: {per_leg[k]} turns; " + ("; ".join(notes) if notes else "low risk"))
        for n, d1, d2 in revisits:
            ib = full.index(n)
            print(f"  REVISIT {gridref(*n)} at {d1/1000:.2f} km and {d2/1000:.2f} km - teams pass twice: "
                  "strong via-checkpoint candidate (brief which way to leave each time)")

if __name__ == "__main__":
    main()
