#!/usr/bin/env python3
"""Make a route preview PDF for the user to review before approving a route.

Usage:
  preview.py HIKE_DIR CANDIDATE_YAML [--out preview.pdf] [--open]

CANDIDATE_YAML (written by planAHike for each candidate):
  name: Candidate F - Kithurst Hill, Amberley, South Stoke
  summary: one or two sentences describing the loop
  routing_points: "START@lat,lon;~lat,lon;CP1@...;FINISH@lat,lon"   # routed on HIKE_DIR/.osm
  pace_kmh: 4
  checkpoints:            # same ids/order as the labels in routing_points
    - {id: START, place: Kithurst Hill car park (free), access: vehicle, note: Street View 2021}
    - {id: CP4, place: ..., access: foot, note: "on foot only: 2.3 km from ..."}
  rule_breaches: []       # each needs the user's OK; becomes brief.exceptions
  lost_risk: []           # places teams could go wrong and what covers them
  prewalk_checks: []      # anything not confirmed by data: the user checks it on the pre-walk
  options: []             # changes the user could ask for

The preview is a temporary file for the user to look at: delete it (and the
candidate file) once the route is approved or rejected.

Page 1: summary, checkpoint table (grid refs and km from the routed line), rule
breaches, lost-risk notes, pre-walk checks, options. Page 2: full-page map.
"""
import sys; sys.dont_write_bytecode = True  # no __pycache__ next to the tools
import argparse, json, os, subprocess, sys, tempfile, shutil
import yaml
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_map
from build_docs import fit, map_page, md, gr, pages
from osgb import gridref
from plan_route import route, road_contacts, hav
from build_docs import load_settings

ICON = {"vehicle": "Vehicle", "foot": "On foot only", "unknown": "Unconfirmed"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hike_dir"); ap.add_argument("candidate")
    ap.add_argument("--out", default="preview.pdf")
    ap.add_argument("--open", action="store_true")
    a = ap.parse_args(); hd = os.path.abspath(a.hike_dir)
    c = yaml.safe_load(open(a.candidate))
    t = route(os.path.join(hd, ".osm"), c["routing_points"], c.get("pace_kmh", 4))
    for w in t["snaps"]: print("WARNING:", w)
    tcp = {x["label"]: x for x in t["checkpoints"]}
    legs = {l["to"]: l for l in t["legs"]}
    pace = c.get("pace_kmh", 4)
    surf = t.get("surface_m", {}); T = t["total_km"]*1000
    road = surf.get("road", 0) + surf.get("lane", 0)
    rows, run = [], 0
    for cp in c["checkpoints"]:
        x = tcp[cp["id"]]; l = legs.get(cp["id"])
        mins = round(l["km"]/pace*60) if l else 0; run += mins
        cls = ' bgcolor="#fff4c7"' if cp.get("toilets") else ' bgcolor="#e8f0fb"' if cp.get("access") != "vehicle" else ""
        rows.append(f'<tr{cls}><td class="cp">{cp["id"]}</td><td>{gr(x["gr"])}</td><td>{md(cp["place"])}</td>'
                    f'<td>{ICON.get(cp.get("access"), cp.get("access", ""))}{"<br>" + md(cp["note"]) if cp.get("note") else ""}</td>'
                    f'<td>{x["km"]:.1f}</td><td>{f"{mins} min" if l else "–"}</td><td>{run//60}:{run%60:02d}</td></tr>')
    tc = next((cp for cp in c["checkpoints"] if cp.get("toilets")), None)
    stats = [f'{T/1000:.1f} km ({T/1609.34:.1f} miles)', f'{100*surf.get("bridleway", 0)/T:.0f}% bridleway',
             f'{road:.0f} m on lanes/roads']
    if tc: stats.append(f'toilets at {tc["id"]} ({100*tcp[tc["id"]]["km"]*1000/T:.0f}% of the way)')
    S = load_settings(); cover = S.get("crossing_cover_m", 100)
    xing = []   # rule 23: every significant road contact needs an adult supervising it
    for x in road_contacts(t, tuple(S.get("significant_road_classes") or ("trunk", "primary", "secondary", "tertiary"))):
        near = min(tcp.values(), key=lambda p: hav((p["lat"], p["lon"]), (x["lat"], x["lon"])))
        d = hav((near["lat"], near["lon"]), (x["lat"], x["lon"]))
        who = f'{near["label"]} leader ({d:.0f} m)' if d <= cover else f'**needs a marshal** (nearest checkpoint {near["label"]}, {d:.0f} m)'
        xing.append(f'{x["road"]} at {x["km"]:.1f} km, {x["gr"]}' + (f' (walked {x["along_m"]} m)' if x["along_m"] else "") + f": {who}")
    def lst(title, items, colour):
        if not items: return ""
        return (f'<table width="100%" border="1" cellspacing="0" cellpadding="4" style="margin-top:2mm"><tr><td bgcolor="{colour}">'
                f'<b>{title}</b><ul>' + "".join(f"<li>{md(i)}</li>" for i in items) + "</ul></td></tr></table>")
    body = "\n".join([
        f'<h1>Route preview: {md(c["name"])}</h1>',
        f'<div class="sub">{" · ".join(stats)}</div>',
        f'<p>{md(c.get("summary", ""))}</p>',
        '<h2>Checkpoints</h2><table width="100%" border="1" cellspacing="0" cellpadding="3">'
        '<tr><th width="8%">CP</th><th width="13%">Grid ref</th><th>Place</th><th width="26%">Leader access</th><th width="7%">km</th><th width="9%">Leg</th><th width="8%">Running</th></tr>'
        + "".join(rows) + "</table>",
        f'<p class="small">Leg times at {pace:g} km/h, no stops. The map is on page 2.</p>',
        lst("Rule breaches (need your OK)", c.get("rule_breaches"), "#fde8e8"),
        lst("Significant road crossings: each needs an adult supervising it (rule 23)", xing, "#efe6f7"),
        lst("Where teams could go wrong", c.get("lost_risk"), "#e8f0fb"),
        lst("Pre-walk checks (for you to confirm on the pre-walk)", c.get("prewalk_checks"), "#fff7ed"),
        lst("Options you could ask for", c.get("options"), "#eeeeee"),
    ])
    tmp = tempfile.mkdtemp(prefix="preview_")
    try:
        p1, fs, ok = fit("preview_p1", "Route preview", body, 1, tmp)
        ms = []
        for i, cp in enumerate(c["checkpoints"]):
            x = tcp[cp["id"]]
            kind = "start" if cp["id"] == "START" else "finish" if cp["id"] == "FINISH" else "toilet" if cp.get("toilets") else "cp"
            ms.append(dict(label=cp["id"], lat=x["lat"], lon=x["lon"], kind=kind))
        png = os.path.join(tmp, "map.png")   # temporary: only the PDF is kept
        render_map.render([tuple(p) for p in t["track"]], ms, png)
        p2 = os.path.join(tmp, "p2.pdf"); map_page(png, "Route in red, arrows show direction. " + " · ".join(
            f'{cp["id"]} {cp["place"].replace("**", "")}' for cp in c["checkpoints"] if cp["id"] != "FINISH"), f"Route preview: {c['name']}", p2)
        out = os.path.join(hd, a.out)
        subprocess.run(["pdfunite", p1, p2, out], check=True)
        print("wrote", out, f"({pages(out)} pages)", "" if ok else "- page 1 OVERFLOWS, shorten the lists")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if a.open:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([opener, out], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

if __name__ == "__main__":
    main()
