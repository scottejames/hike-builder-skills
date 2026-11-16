#!/usr/bin/env python3
"""Build hike documentation from hike.yaml (the documentMyHike generator).

Usage:
  build_docs.py HIKE_DIR [--check] [--refresh-osm]

HIKE_DIR holds hike.yaml (the only source), streetview/ (fetched photos) and
.osm/ (OpenStreetMap cache). The route line is never stored: it is re-routed
from route.routing_points on the cached data on every run. The cache is
re-fetched from route.osm_bbox when missing, stale (osm_cache_max_age_days in
rules.md), for a different area, or with --refresh-osm. If routing fails on a
cache, it is refreshed once and retried.
--check  validate only (grid refs, toilet position, leg spacing, access notes,
         files present); exit code 1 on errors.

Writes into HIKE_DIR (see hike-kit/documentation-style.md):
  <slug>_leader_pack.pdf, <slug>_team_card.pdf,
  <slug>.gpx, <slug>_map.png

PDF pipeline (LibreOffice lessons): text pages are separate HTML files that
use HTML table attributes (CSS borders are ignored) and are converted with
soffice writer_web_pdf_Export. Images are dropped by that filter, so the map
and Street View pages are drawn with PIL and merged with pdfunite. Each
text section is shrunk from 9.4pt to 7.8pt until it fits its page budget, and
trailing blank pages are removed.
"""
import sys; sys.dont_write_bytecode = True  # no __pycache__ next to the tools
import argparse, html, json, math, os, re, shutil, subprocess, sys, tempfile
import yaml
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from osgb import gridref
import render_map
from plan_route import route as do_route, NoPath
import osm_fetch

GR_RE = re.compile(r"^[A-Z]{2} \d{3} \d{3}$")
GR_ANY = re.compile(r"\b([HNOST][A-Z]) (\d{3,5}) (\d{3,5})\b")
FB, FR = render_map.FB, render_map.FR
GREEN = "#2d5a27"

# ---------------------------------------------------------------- settings
def load_settings():
    txt = open(os.path.join(KIT, "rules.md")).read()
    m = re.search(r"```yaml\n(.*?)```", txt, re.S)
    return yaml.safe_load(m.group(1)) if m else {}

def merged(h, s):
    """Effective numbers: rules.md settings, then section defaults, then hike.yaml."""
    sec = (s.get("section_defaults") or {}).get(h["hike"].get("section"), {})
    pace = {**s.get("pace", {}), **{k: v for k, v in sec.items() if k.endswith("_kmh")}, **(h.get("pace") or {})}
    ct = h.get("checkpoint_timing") or {}
    teams = h.get("teams") or {}
    return dict(
        pace=pace,
        leg_target=s.get("leg_target_min", [40, 50]),
        leg_max=s.get("leg_hard_max_min", 65),
        toilet_window=s.get("toilet_window_pct", [35, 65]),
        open_before=ct.get("open_before_first_min", s.get("open_before_first_min", 30)),
        close_after=ct.get("close_after_last_min", s.get("close_after_last_min", 15)),
        stop=teams.get("toilet_stop_min") or s.get("toilet_stop_min", {"min": 0, "max": 30}),
        teams=teams,
    )

# ---------------------------------------------------------------- helpers
def md(t):
    """Escape, **bold**, and wrap grid refs as non-breaking bold monospace."""
    t = html.escape(str(t), quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    return GR_ANY.sub(lambda m: f'<span class="gr">{m.group(1)}&nbsp;{m.group(2)}&nbsp;{m.group(3)}</span>', t)

def hm(mins, start=None):
    mins = int(mins)
    if start:
        h, m = map(int, str(start).split(":"))
        t = h*60 + m + mins
        return f"{(t//60) % 24:02d}:{t % 60:02d}"
    sign = "-" if mins < 0 else "+"
    return f"{sign}{abs(mins)//60}:{abs(mins) % 60:02d}"

def cpmap(h):
    return {c["id"]: c for c in h["checkpoints"]}

def toilet_cp(h):
    return next((c for c in h["checkpoints"] if c.get("toilets") and c["id"] not in ("START", "FINISH")), None)

def short(c):
    return c["name"].split("(")[0].split(",")[0].strip()

# ---------------------------------------------------------------- timings
def timings(h, E):
    cps = h["checkpoints"]; P = E["pace"]; tc = toilet_cp(h)
    tkm = tc["km"] if tc else None
    teams = E["teams"]; count = teams.get("count"); iv = teams.get("start_interval_min") or 0
    rows, run = [], 0
    for i, c in enumerate(cps):
        leg_km = c["km"] - cps[i-1]["km"] if i else 0.0
        leg_min = round(leg_km / P["planning_kmh"] * 60) if i else 0
        run += leg_min
        after = tkm is not None and c["km"] > tkm + 1e-6
        earliest = math.floor(c["km"]*60/P["fastest_kmh"]) + (E["stop"]["min"] if after else 0)
        r = dict(id=c["id"], leg_km=leg_km, leg_min=leg_min, run_min=run, km=c["km"],
                 earliest=earliest, open=earliest - E["open_before"], planned=run + (E["stop"]["min"] if after else 0))
        if count:
            latest = (count-1)*iv + math.ceil(c["km"]*60/P["slowest_kmh"]) + (E["stop"]["max"] if after else 0)
            r.update(latest=latest, close=latest + E["close_after"])
        rows.append(r)
    by = {r["id"]: r for r in rows}
    for c in cps:  # shared checkpoints: one leader, open at the earliest, close at the latest
        o = c.get("shared_with")
        if o and o in by:
            a, b = by[c["id"]], by[o]
            first, second = (a, b) if a["km"] <= b["km"] else (b, a)
            second["open_shared"] = first["id"]
            if "close" in a:
                first["close"] = max(a["close"], b["close"])
                second["close_shared"] = first["id"]
    return rows

# ---------------------------------------------------------------- checks
def get_route(h, hd, E, settings, refresh=False):
    osm = os.path.join(hd, ".osm"); r = h["route"]
    bbox = r.get("osm_bbox")
    age = settings.get("osm_cache_max_age_days", 90)
    if bbox: osm_fetch.ensure(osm, tuple(bbox), age, refresh)
    elif not os.path.exists(os.path.join(osm, "ways.json")):
        sys.exit("No OSM cache and no route.osm_bbox in hike.yaml to fetch one from.")
    try:
        return do_route(osm, r["routing_points"], E["pace"]["planning_kmh"])
    except NoPath as e:
        if refresh or not bbox: sys.exit(f"Routing failed: {e}")
        print(f"Routing failed on the cached data ({e}); refreshing the cache once.")
        return get_route(h, hd, E, settings, refresh=True)

def check(h, hd, E, R):
    err, warn = [], []
    cps = h["checkpoints"]; ids = [c["id"] for c in cps]; C = cpmap(h)
    if ids[0] != "START" or ids[-1] != "FINISH": err.append("checkpoints must begin with START and end with FINISH")
    for c in cps:
        g = c.get("grid_ref", "")
        if not GR_RE.match(g): err.append(f"{c['id']}: grid_ref '{g}' is not 6-figure 'TQ 333 129' form")
        elif "lat" in c and gridref(c["lat"], c["lon"]) != g:
            err.append(f"{c['id']}: grid_ref {g} but coordinates give {gridref(c['lat'], c['lon'])}")
        if not c.get("vehicle_access") and not str(c.get("access", "")).startswith(("**On foot only:**", "As for")):
            warn.append(f"{c['id']}: foot-only checkpoint - access should start '**On foot only:**' with walk-in distance/time")
        if c.get("shared_with") and C.get(c["shared_with"], {}).get("shared_with") != c["id"]:
            err.append(f"{c['id']}: shared_with {c['shared_with']} is not reciprocated")
    for i in range(1, len(cps)):
        if cps[i]["km"] < cps[i-1]["km"]: err.append(f"{cps[i]['id']}: km goes backwards")
    # legs
    legs = h.get("legs", [])
    want = list(zip(ids, ids[1:]))
    got = [(l["from"], l["to"]) for l in legs]
    if got != want: err.append(f"legs {got} do not match checkpoint order {want}")
    for l in legs:
        for d in l.get("directions", []):
            g = d.get("grid_ref", "")
            if not GR_RE.match(g): err.append(f"leg {l['from']}->{l['to']} {d.get('id')}: grid_ref '{g}' not 6-figure")
            elif "lat" in d and gridref(d["lat"], d["lon"]) != g:
                err.append(f"{d['id']}: grid_ref {g} but coordinates give {gridref(d['lat'], d['lon'])}")
            elif d.get("id") in C and C[d["id"]]["grid_ref"] != g:
                err.append(f"{d['id']} in leg directions: {g} differs from checkpoint {C[d['id']]['grid_ref']}")
            first = re.sub(r"[*]", "", d.get("text", "")).split(" ")[0]
            if d.get("id", "").startswith("T") and not first[:1].isupper():
                warn.append(f"{d['id']}: direction should start with a verb")
    # toilet
    tot = cps[-1]["km"]; tc = toilet_cp(h)
    if not tc: err.append("MUST: no checkpoint has toilets (rule 1)")
    else:
        pct = 100*tc["km"]/tot; lo, hi = E["toilet_window"]
        if not lo <= pct <= hi:
            msg = f"MUST: toilet checkpoint {tc['id']} is at {pct:.1f}% of the route, outside {lo}-{hi}% (rule 1)"
            if not _excepted(h, "toilet"): err.append(msg)
            else: print("NOTE:", msg, "- accepted exception")
    # leg spacing
    for r in timings(h, E)[1:]:
        lo, hi = E["leg_target"]
        if r["leg_min"] > E["leg_max"] and not _excepted(h, r["id"]):
            err.append(f"leg to {r['id']}: {r['leg_min']} min exceeds hard max {E['leg_max']} (rule 10) - add a via checkpoint or record an exception")
        elif not lo <= r["leg_min"] <= hi and not _excepted(h, "guide"):
            warn.append(f"leg to {r['id']}: {r['leg_min']} min, outside the {lo}-{hi} min guide")
    # files
    # the routed line must still match the checkpoint data written in hike.yaml
    for w in R["snaps"]: warn.append("routing point " + w)
    rc = {x["label"]: x for x in R["checkpoints"]}
    for c in cps:
        x = rc.get(c["id"])
        if not x: err.append(f"{c['id']}: not in route.routing_points"); continue
        if abs(x["km"] - c["km"]) > 0.1:
            err.append(f"{c['id']}: hike.yaml says {c['km']} km but the route now gives {x['km']:.2f} km "
                       "(OSM data or routing points changed - review the route and update km/directions)")
        if x["gr"] != c["grid_ref"]:
            err.append(f"{c['id']}: route now snaps to {x['gr']}, hike.yaml says {c['grid_ref']}")
    sv = h.get("streetview") or {}
    if sv.get("enabled"):
        covered = {x for loc in sv.get("locations", []) for x in loc["checkpoints"]}
        for c in cps:
            if c["id"] not in covered and c.get("vehicle_access"): warn.append(f"{c['id']}: no Street View location listed")
        for loc in sv.get("locations", []):
            for hd_ in ("000", "090", "180", "270"):
                p = os.path.join(hd, sv.get("images_dir", "streetview"), f"{loc['prefix']}_h{hd_}.jpg")
                if not os.path.exists(p):
                    (err if loc.get("date") else warn).append(f"Street View image not fetched yet: {p}" + ("" if loc.get("date") else " (documentMyHike fetches it)"))
    for c in cps:
        if (c.get("shared_with") or not c.get("vehicle_access")) and c["id"] not in ("START", "FINISH"):
            if not h.get("leader_notes"): warn.append(f"{c['id']}: shared/foot-only checkpoint but no leader_notes")
    return err, warn

def _excepted(h, key):
    return any(key.lower() in str(e).lower() for e in (h.get("brief") or {}).get("exceptions") or [])

# ---------------------------------------------------------------- HTML
CSS = """
  @page {{ size: A4; margin: 11mm; }}
  body {{ font-family: "Liberation Sans", Arial, sans-serif; font-size: {fs}pt; color: #111; margin: 0; }}
  h1, h2, h3 {{ font-family: "Liberation Sans", Arial, sans-serif; }}
  h1 {{ font-size: {h1}pt; margin: 0 0 1mm 0; }}
  .sub {{ font-size: {fs}pt; color: #333; margin-bottom: 2mm; }}
  h2 {{ font-size: {h2}pt; margin: 3mm 0 1.5mm 0; color: #2d5a27; border-bottom: 1.5px solid #2d5a27; }}
  h3 {{ font-size: {h3}pt; margin: 2mm 0 0.5mm 0; color: #2d5a27; }}
  table {{ border-collapse: collapse; }}
  th, td {{ vertical-align: top; text-align: left; font-size: {fs}pt; }}
  th {{ background: #e4ecdf; }}
  .cp {{ font-weight: bold; white-space: nowrap; }}
  .wc {{ background: #fff4c7; }}
  .mb {{ background: #e8f0fb; }}
  .tot {{ background: #eeeeee; font-weight: bold; }}
  .gr {{ font-family: "Liberation Mono", monospace; font-weight: bold; white-space: nowrap; }}
  ul {{ margin: 0; padding-left: 4.5mm; }}
  li {{ margin-bottom: 0.5mm; }}
  .small {{ font-size: {sm}pt; color: #444; }}
"""

def doc(title, body, fs):
    css = CSS.format(fs=fs, h1=fs+6.5, h2=fs+1.8, h3=fs+0.8, sm=fs-0.9)
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{html.escape(title)}</title><style>{css}</style></head><body>\n{body}\n</body></html>'

def cellp(t):
    """LibreOffice adds paragraph spacing inside table cells; wrap each cell in a zero-margin <p>."""
    return re.sub(r'(<t[dh][^>]*>)(.*?)(</t[dh]>)', r'\1<p style="margin-top:0;margin-bottom:0">\2</p>\3', t)

def gr(g):
    return f'<span class="gr">{g.replace(" ", "&nbsp;")}</span>'

def summary_line(h, E):
    cps = h["checkpoints"]; tot = cps[-1]["km"]; r = h["route"]; tc = toilet_cp(h)
    bits = [h["hike"].get("area", ""), f"{tot:.1f} km ({tot/1.609344:.1f} miles) {h['hike'].get('type', 'circular')}"]
    if r.get("bridleway_pct") is not None: bits.append(f"{r['bridleway_pct']}% bridleway")
    if r.get("road_statement"): bits.append(r["road_statement"])
    if tc: bits.append(f"toilets at {tc['id']} ({100*tc['km']/tot:.0f}% of the way)")
    if h["hike"].get("map"): bits.append(f"Map: {h['hike']['map']}")
    if h["hike"].get("date"): bits.append(f"Date: {h['hike']['date']}")
    return " · ".join(md(b) for b in bits if b)

def page_checkpoints(h, E, T, warns):
    cps = h["checkpoints"]; P = E["pace"]; by = {r["id"]: r for r in T}
    o = [f'<h1>Scout Hike: {md(h["hike"]["name"])}</h1>', f'<div class="sub">{summary_line(h, E)}</div>',
         '<h2>Checkpoints</h2>',
         '<table width="100%" border="1" cellspacing="0" cellpadding="3">',
         f'<tr><th width="7%">CP</th><th width="12%">Grid ref</th><th>Location</th><th width="21%">Access for leaders</th>'
         f'<th width="7%">Leg</th><th width="8%">Leg time ({P["planning_kmh"]:g} km/h)</th><th width="9%">Running total</th><th width="13%">Give team</th></tr>']
    for i, c in enumerate(cps):
        r = by[c["id"]]
        cls = ' class="wc"' if c.get("toilets") and c["id"] not in ("START", "FINISH") else \
              ' class="mb"' if c.get("shared_with") or not c.get("vehicle_access") else ""
        nxt = f'<b>{cps[i+1]["id"]}</b><br>{gr(cps[i+1]["grid_ref"])}' if i+1 < len(cps) else "–"
        leg = f'{r["leg_km"]:.1f} km' if i else "–"
        lt = f'<b>{r["leg_min"]} min</b>' if i else "–"
        o.append(f'<tr{cls}><td class="cp">{c["id"]}</td><td>{gr(c["grid_ref"])}</td><td>{md(c.get("location", c["name"]))}</td>'
                 f'<td>{md(c.get("access", ""))}</td><td>{leg}</td><td>{lt}</td><td>{c["km"]:.1f} km<br>{hm(r["run_min"])[1:]}</td><td>{nxt}</td></tr>')
    last = T[-1]
    o.append(f'<tr class="tot"><td colspan="4">Total</td><td>{cps[-1]["km"]:.1f} km</td><td>{last["run_min"]} min</td>'
             f'<td>{hm(last["run_min"])[1:]}</td><td></td></tr></table>')
    o = [cellp(x) if x.startswith("<tr") or x.startswith("<table") else x for x in o]
    note = f'Leg times are at {P["planning_kmh"]:g} km/h with no stops.'
    if h["route"].get("climb_note"): note += " " + h["route"]["climb_note"]
    o.append(f'<p class="small" style="margin:1mm 0 0 0">{md(note)}</p>')
    for n in h.get("leader_notes") or []:
        pts = "".join(f"<li>{md(p)}</li>" for p in n.get("points", []))
        o.append(f'<table width="100%" border="1" cellspacing="0" cellpadding="4" style="margin-top:2mm"><tr><td class="mb" bgcolor="#e8f0fb">'
                 f'<b>{md(n["title"])}</b><ul>{pts}</ul></td></tr></table>')
    ver = [md(h["route"].get("verification", ""))]
    exc = (h.get("brief") or {}).get("exceptions") or []
    if exc: ver.append("<b>Accepted exceptions to the planning rules:</b> " + "; ".join(md(e) for e in exc) + ".")
    if warns: ver.append("<b>Build checks:</b> " + "; ".join(md(w) for w in warns) + ".")
    o.append('<table width="100%" border="1" cellspacing="0" cellpadding="4" style="margin-top:2mm"><tr><td bgcolor="#fff7ed">'
             '<b>Verification.</b> ' + "<br>".join(v for v in ver if v) + '</td></tr></table>')
    return "\n".join(o)

def page_legs(h, E, T, break_before=None):
    by = {r["id"]: r for r in T}
    o = ['<h2 style="margin-top:0">Leg directions for leaders (T-numbers match the map)</h2>']
    for n, l in enumerate(h["legs"], 1):
        r = by[l["to"]]
        brk = ' style="page-break-before:always"' if n == break_before else ""
        o.append(f'<h3{brk}>Leg {n}: {l["from"]} → {l["to"]} · {r["leg_km"]:.1f} km · {r["leg_min"]} min · {md(l.get("effort", ""))}</h3>')
        o.append('<table width="100%" border="1" cellspacing="0" cellpadding="2"><tr><th width="9%">Point</th><th width="13%">Grid ref</th><th width="7%">km</th><th>Instruction</th></tr>')
        for d in l["directions"]:
            o.append(f'<tr><td class="cp">{d["id"]}</td><td>{gr(d["grid_ref"])}</td><td>{d["km"]:.1f}</td><td>{md(d["text"])}</td></tr>')
        o.append("</table>")
    return cellp("\n".join(o))

def page_safety(h, E, T):
    teams = E["teams"]; start = teams.get("first_start"); P = E["pace"]; C = cpmap(h)
    L = ['<h2 style="margin-top:0">Safety notes</h2><ul>' + "".join(f"<li>{md(s)}</li>" for s in h.get("safety", [])) + "</ul>",
         '<h2>Kit list</h2><ul>' + "".join(f"<li>{md(s)}</li>" for s in h.get("kit", [])) + "</ul>"]
    em = h.get("emergency") or {}
    eml = ["<b>Emergency: 999 or 112.</b> Give the grid reference of the last checkpoint you passed.",
           "The <b>OS Locate</b> or <b>what3words</b> app gives your exact position."]
    if em.get("hospital"): eml.append(f"Nearest A&amp;E: {md(em['hospital'])}.")
    for x in em.get("extra", []) or []: eml.append(md(x))
    L.append('<h2>Emergency</h2><ul>' + "".join(f"<li>{x}</li>" for x in eml) + "</ul>")
    has_close = "close" in T[0]
    R = ['<h2 style="margin-top:0">Checkpoint opening times</h2>',
         '<table width="100%" border="1" cellspacing="0" cellpadding="2">']
    if not start:
        R.append(f'<tr><td colspan="{6 if has_close else 5}" height="22"><b>First team start time:</b> ____________ &nbsp;(add the offsets below)</td></tr>')
    R.append(f'<tr><th width="24%">CP</th><th>Open by (−{E["open_before"]} min)</th><th>Earliest arrival ({P["fastest_kmh"]:g} km/h)</th>'
             f'<th>Plan ({P["planning_kmh"]:g} km/h)</th>' + (f'<th>Close (+{E["close_after"]} min)</th>' if has_close else "")
             + ('<th width="15%">Clock time to open</th>' if not start else "") + "</tr>")
    for r in T[1:]:
        c = C[r["id"]]
        op = f'(already open as {r["open_shared"]})' if r.get("open_shared") else f'<b>{hm(r["open"], start)}</b>'
        row = f'<tr><td>{r["id"]} {html.escape(short(c))}</td><td>{op}</td><td>{hm(r["earliest"], start)}</td><td>{hm(r["planned"], start)}</td>'
        if has_close: row += f'<td>{"(as " + r["close_shared"] + ")" if r.get("close_shared") else "<b>" + hm(r["close"], start) + "</b>"}</td>'
        if not start: row += "<td></td>"
        R.append(row + "</tr>")
    R.append("</table>")
    tc = toilet_cp(h); expl = [f'"Earliest arrival" is the first team at {P["fastest_kmh"]:g} km/h']
    if tc: expl[0] += f' stopping {E["stop"]["min"]} min at {tc["id"]}'
    expl.append(f'"Planned" is the first team at {P["planning_kmh"]:g} km/h.')
    if has_close:
        expl.append(f'Closing allows for {teams["count"]} teams starting {teams.get("start_interval_min", 0)} min apart, the last walking at '
                    f'{P["slowest_kmh"]:g} km/h' + (f' with a {E["stop"]["max"]} min stop at {tc["id"]}.' if tc else "."))
    else:
        expl.append("Set <b>teams.count</b> in hike.yaml to get closing times.")
    for c in h["checkpoints"]:
        if c.get("walk_in_min"):
            r = next(x for x in T if x["id"] == c["id"])
            go = r["open"] - c["walk_in_min"]
            when = hm(go, start) if start else (f"{-go} min before the first start" if go < 0 else hm(go))
            expl.append(f'The {c["id"]} leader needs about {c["walk_in_min"]} min to walk in, so they set off by <b>{when}</b>.')
    R.append(f'<p class="small" style="margin:1mm 0 0 0">{" ".join(expl)}</p>')
    R.append('<h2>Checkpoint log</h2><table width="100%" border="1" cellspacing="0" cellpadding="3">'
             '<tr><th width="20%">CP</th><th>Leader / mobile</th><th width="19%">Team in</th><th width="19%">Team out</th></tr>')
    seen = {}
    for c in h["checkpoints"]:
        lead = f'(same leader as {seen[c["shared_with"]]})' if c.get("shared_with") in seen else ""
        seen[c["id"]] = c["id"]
        R.append(f'<tr><td height="26">{c["id"]}</td><td>{lead}</td><td></td><td></td></tr>')
    R.append('</table><table width="100%" border="1" cellspacing="0" cellpadding="3" style="margin-top:2mm">'
             + "".join(f'<tr><td width="40%" height="24"><b>{k}</b></td><td width="60%">{v}</td></tr>'
                       for k, v in [("Date", html.escape(str(h["hike"].get("date") or ""))), ("Team name / size", ""), ("Start time", ""), ("Home contact", "")])
             + "</table>")
    return ('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tbody><tr><td width="50%" valign="top" style="padding-right:4mm">'
            + "\n".join(L) + '</td><td width="50%" valign="top">' + "\n".join(R) + "</td></tr></tbody></table>")

def team_card(h, E):
    cps = h["checkpoints"]; s = cps[0]; n = len(cps) - 2
    tc = h.get("team_card") or {}
    safety = tc.get("safety") or ["You will cross roads. Stop, gather the whole team, and cross together.",
                                  "Close every gate behind you.", "Stay together. Never split the team."]
    rows = "".join(f'<tr><td height="34"><b>{i}</b></td><td></td><td></td><td></td><td></td></tr>' for i in range(1, n+1))
    rows += '<tr><td height="34"><b>Finish</b></td><td></td><td></td><td></td><td></td></tr>'
    box = lambda k, w="": f'<tr><td width="28%" height="30"><b>{k}</b></td><td>{w}</td></tr>'
    return "\n".join([
        f'<h1>{md(h["hike"]["name"])}: Team card</h1>',
        '<table width="100%" border="1" cellspacing="0" cellpadding="4">' + box("Team name") + box("Team members") + box("Start time") + "</table>",
        f'<h2>START: {md(short(s))}, {gr(s["grid_ref"])}</h2>',
        '<p><b>How it works:</b> At each checkpoint the leader gives you the grid reference of the next one. Plot it, plan your route, then go.</p>',
        '<h2>Your log</h2><table width="100%" border="1" cellspacing="0" cellpadding="4">'
        '<tr><th width="10%">CP</th><th width="30%">Grid ref given to you</th><th>Time in</th><th>Time out</th><th width="18%">Leader initials</th></tr>' + rows + "</table>",
        '<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr><td width="50%" valign="top" style="padding-right:4mm">',
        '<h2>Kit</h2><ul>' + "".join(f"<li>{md(k)}</li>" for k in h.get("kit", [])) + "</ul>",
        '</td><td width="50%" valign="top">',
        '<h2>Stay safe</h2><ul>' + "".join(f"<li>{md(k)}</li>" for k in safety) + "</ul>",
        '</td></tr></table>',
        '<h2>Emergency</h2><p><b>Call 999.</b> Tell them the grid reference of the last checkpoint you passed.</p>',
        '<table width="100%" border="1" cellspacing="0" cellpadding="4">' + box("Leader phone 1") + box("Leader phone 2") + "</table>",
    ])

# ---------------------------------------------------------------- PDF
def soffice(html_path, outdir):
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf:writer_web_pdf_Export", "--outdir", outdir, html_path],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return os.path.splitext(os.path.join(outdir, os.path.basename(html_path)))[0] + ".pdf"

def pages(pdf):
    out = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True).stdout
    return int(re.search(r"Pages:\s+(\d+)", out).group(1))

def page_text(pdf, i):
    return subprocess.run(["pdftotext", "-f", str(i), "-l", str(i), pdf, "-"], capture_output=True, text=True).stdout.strip()

def keep_pages(pdf, n, tmp):
    stem = os.path.join(tmp, os.path.basename(pdf)[:-4] + "_p%d.pdf")
    subprocess.run(["pdfseparate", "-l", str(n), pdf, stem], check=True)
    out = pdf[:-4] + "_trim.pdf"
    subprocess.run(["pdfunite", *[stem % i for i in range(1, n+1)], out], check=True)
    return out

def fit(name, title, body, budget, tmp, sizes=(9.4, 9.0, 8.6, 8.2, 7.8), quiet=False):
    """Convert body to PDF, shrinking the font until it fits `budget` pages."""
    for fs in sizes:
        p = os.path.join(tmp, f"{name}.html")
        open(p, "w").write(doc(title, body, fs))
        pdf = soffice(p, tmp); n = pages(pdf)
        while n > budget and len(page_text(pdf, n)) < 5: n -= 1      # trailing blank pages
        if n <= budget:
            return (keep_pages(pdf, n, tmp) if n < pages(pdf) else pdf), fs, True
    if not quiet: print(f"WARNING: section '{name}' still overflows {budget} page(s) at 7.8pt - shorten its text")
    return pdf, sizes[-1], False

A4 = (1240, 1754)  # 150 dpi

def _f(path, s):
    try: return ImageFont.truetype(path, s)
    except OSError: return ImageFont.load_default()

def _wrap(d, text, font, width):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= width: cur = t
        else: lines.append(cur); cur = w
    return lines + [cur] if cur else lines

def map_page(map_png, caption, title, out):
    pg = Image.new("RGB", A4, "white"); d = ImageDraw.Draw(pg); M = 70
    d.text((M, M), title, fill=GREEN, font=_f(FB, 34))
    d.line((M, M+48, A4[0]-M, M+48), fill=GREEN, width=3)
    capf = _f(FR, 22); cap = _wrap(d, caption, capf, A4[0]-2*M)
    top, bottom = M+70, A4[1]-M-len(cap)*30-10
    im = Image.open(map_png); sc = min((A4[0]-2*M)/im.width, (bottom-top)/im.height)
    im = im.resize((int(im.width*sc), int(im.height*sc)), Image.LANCZOS)
    pg.paste(im, ((A4[0]-im.width)//2, top)); d.rectangle(((A4[0]-im.width)//2, top, (A4[0]+im.width)//2, top+im.height), outline="black", width=2)
    y = top + im.height + 14
    for line in cap: d.text((M, y), line, fill="black", font=capf); y += 30
    pg.save(out, resolution=150)

def streetview_pages(h, hd, out_prefix):
    sv = h["streetview"]; C = cpmap(h); idir = os.path.join(hd, sv.get("images_dir", "streetview"))
    locs = sv.get("locations", []); outs = []; M = 60; per = 5
    for k in range(0, len(locs), per):
        pg = Image.new("RGB", A4, "white"); d = ImageDraw.Draw(pg)
        d.text((M, M), "Checkpoint photos (Street View)", fill=GREEN, font=_f(FB, 34))
        d.line((M, M+48, A4[0]-M, M+48), fill=GREEN, width=3)
        d.text((M, M+58), "Dates vary, so vegetation, parking and signs may have changed. Each row looks N, E, S and W.",
               fill=(70, 70, 70), font=_f(FR, 20))
        y = M + 100; w = (A4[0]-2*M-3*12)//4
        for loc in locs[k:k+per]:
            c0 = C[loc["checkpoints"][0]]
            ttl = f"{' / '.join(loc['checkpoints'])} – {short(c0)} – {c0['grid_ref']}"
            d.text((M, y), ttl, fill="black", font=_f(FB, 24))
            meta = f"{loc.get('date', '')} · {loc.get('source', '')}" + (f" · {loc['caption']}" if loc.get("caption") else "")
            d.text((M, y+30), meta, fill=(70, 70, 70), font=_f(FR, 19)); y += 60
            hh = 0
            for j, hd_ in enumerate(("000", "090", "180", "270")):
                im = Image.open(os.path.join(idir, f"{loc['prefix']}_h{hd_}.jpg")).convert("RGB")
                im = im.resize((w, int(im.height*w/im.width)), Image.LANCZOS); hh = im.height
                x = M + j*(w+12); pg.paste(im, (x, y))
                d.rectangle((x, y, x+34, y+30), fill=(255, 255, 255)); d.text((x+17, y+15), "NESW"[j], fill="black", font=_f(FB, 22), anchor="mm")
            y += hh + 22
        o = f"{out_prefix}_{k//per}.pdf"; pg.save(o, resolution=150); outs.append(o)
    return outs

# ---------------------------------------------------------------- GPX / map
def markers(h):
    ms = []
    for c in h["checkpoints"]:
        kind = "start" if c["id"] == "START" else "finish" if c["id"] == "FINISH" else "toilet" if c.get("toilets") else "cp"
        ms.append(dict(label=c["id"], lat=c["lat"], lon=c["lon"], kind=kind))
    for l in h["legs"]:
        for d in l["directions"]:
            if d["id"].startswith("T") and "lat" in d:
                ms.append(dict(label=d["id"], lat=d["lat"], lon=d["lon"], kind="turn"))
    return ms

def map_caption(h):
    seen, bits = set(), []
    for c in h["checkpoints"]:
        if c["id"] in seen: continue
        o = c.get("shared_with"); ids = [c["id"]] + ([o] if o else [])
        if c["id"] == "START" and h["checkpoints"][-1]["grid_ref"] == c["grid_ref"]: ids = ["START", "FINISH"]
        seen.update(ids)
        lab = "S/F" if ids == ["START", "FINISH"] else "/".join(ids)
        bits.append(f"{lab} {short(c)} {c['grid_ref']}" + (" (toilets)" if c.get("toilets") else ""))
    turns = [d["id"] for l in h["legs"] for d in l["directions"] if d["id"].startswith("T") and "lat" in d]
    if turns: bits.append(f"{turns[0]}–{turns[-1]} turn points (see leg directions)")
    return "Route in red, arrows show direction. " + " · ".join(bits) + "."

def gpx(h, track, out):
    e = lambda s: html.escape(str(s))
    w, seen = [], set()
    for c in h["checkpoints"]:
        if c["grid_ref"] in seen: continue
        seen.add(c["grid_ref"])
        ids = [x["id"] for x in h["checkpoints"] if x["grid_ref"] == c["grid_ref"]]
        w.append(f'<wpt lat="{c["lat"]:.6f}" lon="{c["lon"]:.6f}"><name>{e("/".join(ids))} {e(short(c))}</name><desc>{e(c["grid_ref"])}</desc></wpt>')
    for l in h["legs"]:
        for d in l["directions"]:
            if d["id"].startswith("T") and "lat" in d:
                w.append(f'<wpt lat="{d["lat"]:.6f}" lon="{d["lon"]:.6f}"><name>{e(d["id"])}</name><desc>{e(d["grid_ref"])} {e(re.sub(r"[*]", "", d["text"]))}</desc></wpt>')
    pts = "".join(f'<trkpt lat="{a:.6f}" lon="{b:.6f}"/>' for a, b in track)
    open(out, "w").write('<?xml version="1.0" encoding="UTF-8"?>\n<gpx version="1.1" creator="hike-kit build_docs" xmlns="http://www.topografix.com/GPX/1/1">\n'
                         f'<metadata><name>{e(h["hike"]["name"])}</name></metadata>\n' + "\n".join(w)
                         + f'\n<trk><name>{e(h["hike"]["name"])}</name><trkseg>{pts}</trkseg></trk>\n</gpx>\n')

# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("hike_dir"); ap.add_argument("--check", action="store_true")
    ap.add_argument("--refresh-osm", action="store_true")
    a = ap.parse_args(); hd = os.path.abspath(a.hike_dir)
    h = yaml.safe_load(open(os.path.join(hd, "hike.yaml"))); S = load_settings(); E = merged(h, S)
    R = get_route(h, hd, E, S, a.refresh_osm)
    err, warn = check(h, hd, E, R)
    for x in err: print("ERROR:", x)
    for x in warn: print("WARN: ", x)
    T = timings(h, E)
    print("\nCP       km   leg   run   open  earliest planned" + ("  close" if "close" in T[0] else ""))
    for r in T:
        print(f"{r['id']:<7}{r['km']:5.2f} {r['leg_min']:4d} {hm(r['run_min']):>6} {hm(r['open']):>6} {hm(r['earliest']):>6} {hm(r['planned']):>6}"
              + (f" {hm(r['close']):>6}" if "close" in r else "") + (f"  (shared with {r.get('open_shared')})" if r.get("open_shared") else ""))
    if a.check or err:
        print("\nCHECK", "FAILED" if err else "OK"); sys.exit(1 if err else 0)

    slug = h["hike"]["slug"]; O = h.get("outputs") or {}
    track = [tuple(p) for p in R["track"]]
    map_png = os.path.join(hd, f"{slug}_map.png")
    render_map.render(track, markers(h), map_png); print("wrote", map_png)
    if O.get("gpx", True): gpx(h, track, os.path.join(hd, f"{slug}.gpx")); print("wrote", os.path.join(hd, f"{slug}.gpx"))
    title = f"Scout Hike: {h['hike']['name']}"
    p1, p2, p4 = page_checkpoints(h, E, T, warn), page_legs(h, E, T), page_safety(h, E, T)
    sv_on = bool((h.get("streetview") or {}).get("enabled"))
    tmp = tempfile.mkdtemp(prefix="hikedocs_")
    try:
        if O.get("leader_pack", True):
            parts = []
            pdf, fs, ok = fit("p1", title, p1, 1, tmp); parts.append(pdf); print(f"  p1: {fs}pt{'' if ok else ' OVERFLOW'}")
            # leg directions: one page if it fits at 8.2pt or larger, otherwise two pages
            pdf, fs, ok = fit("p2", title, p2, 1, tmp, sizes=(9.4, 9.0, 8.6, 8.2), quiet=True)
            if not ok:  # break between legs at the row half-way point so no table splits
                rows = [len(l["directions"]) + 2 for l in h["legs"]]; half, acc, k = sum(rows)/2, 0, 1
                for k, r in enumerate(rows, 1):
                    acc += r
                    if acc >= half: break
                pdf, fs, ok = fit("p2", title, page_legs(h, E, T, break_before=k+1), 2, tmp)
            parts.append(pdf); print(f"  p2: {fs}pt, {pages(pdf)} page(s){'' if ok else ' OVERFLOW'}")
            mp = os.path.join(tmp, "p3.pdf"); map_page(map_png, map_caption(h), f"Route map: {h['hike']['name']}", mp); parts.append(mp)
            pdf, fs, ok = fit("p4", title, p4, 1, tmp); parts.append(pdf); print(f"  p4: {fs}pt{'' if ok else ' OVERFLOW'}")
            if sv_on: parts += streetview_pages(h, hd, os.path.join(tmp, "p5"))
            out = os.path.join(hd, f"{slug}_leader_pack.pdf")
            subprocess.run(["pdfunite", *parts, out], check=True); print("wrote", out, f"({pages(out)} pages)")
        if O.get("team_card", True):
            pdf, fs, ok = fit("team_card", f"{h['hike']['name']}: Team card", team_card(h, E), 1, tmp, sizes=(11, 10.4, 9.8, 9.4, 9.0, 8.6))
            out = os.path.join(hd, f"{slug}_team_card.pdf"); shutil.copy(pdf, out)
            print("wrote", out, f"({fs}pt)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if not O.get("map", True): os.remove(map_png)

if __name__ == "__main__":
    main()
