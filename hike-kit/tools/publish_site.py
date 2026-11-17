#!/usr/bin/env python3
"""Build the leaders' micro-site from every documented hike and publish it to AWS Amplify.

Usage (run in the workspace):
  publish_site.py [--workspace DIR] [--out DIR] [--deploy]

  --out DIR   write the site to DIR so you can look at it (nothing is uploaded)
  --deploy    build in a temporary folder, upload it to Amplify Hosting, then delete it

The site is regenerated from the hike folders every time and never stored: each
<workspace>/<slug>/ with a hike.yaml and a built leader pack becomes a page with the
summary, checkpoint table, map and leg directions, plus links to the leader pack,
team card, risk assessment, GPX and full-size map. The index lists every hike. Hikes without
documents yet are skipped with a warning (run documentMyHike first).

Hosting settings come from <workspace>/.env (never commit them):
  HIKE_SITE_AMPLIFY_APP_ID   Amplify app with a manually deployed branch
  HIKE_SITE_BRANCH           default main
The site password is set on the Amplify branch (basic auth), not in this script.
Needs the AWS CLI with credentials that can deploy to that app.
"""
import sys; sys.dont_write_bytecode = True  # no __pycache__ next to the tools
import argparse, datetime, html, json, os, shutil, subprocess, tempfile, time, urllib.request, zipfile
import yaml
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_docs import md, gr, toilet_cp

CSS = """
body{font-family:system-ui,-apple-system,"Segoe UI",Arial,sans-serif;max-width:60rem;margin:0 auto;padding:1rem;color:#111;background:#fff;line-height:1.4}
h1{font-size:1.5rem;margin:.2rem 0} h2{color:#2d5a27;border-bottom:2px solid #2d5a27;font-size:1.15rem;margin-top:1.6rem}
a{color:#1d4ed8} .sub{color:#444} .gr{font-family:"Liberation Mono",Menlo,Consolas,monospace;font-weight:bold;white-space:nowrap}
table{border-collapse:collapse;width:100%;font-size:.92rem} th,td{border:1px solid #bbb;padding:.3rem .4rem;text-align:left;vertical-align:top}
th{background:#e4ecdf} tr.wc td{background:#fff4c7} .wrap{overflow-x:auto}
.dl a{display:inline-block;margin:.2rem .4rem .2rem 0;padding:.35rem .7rem;border:1px solid #2d5a27;border-radius:4px;text-decoration:none;color:#2d5a27}
.note{background:#e8f0fb;padding:.5rem .8rem;margin:.5rem 0} .verify{background:#fff7ed;padding:.5rem .8rem}
img.map{width:100%;height:auto;border:1px solid #333} details{margin:.4rem 0} summary{cursor:pointer;font-weight:bold}
footer{margin-top:2rem;color:#666;font-size:.85rem}
@media (prefers-color-scheme: dark){body{background:#121212;color:#e5e5e5} a{color:#93c5fd} .sub{color:#aaa}
 th{background:#2a3a28} tr.wc td{background:#4a4220} .note{background:#1e2a3d} .verify{background:#3a2c1c}
 h2{color:#8fc488;border-color:#8fc488} .dl a{color:#8fc488;border-color:#8fc488} th,td{border-color:#555}}
"""

def page(title, body, up=""):
    return (f'<!doctype html><html lang="en-GB"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">'
            f'<title>{html.escape(title)}</title><link rel="stylesheet" href="{up}style.css"></head><body>\n{body}\n'
            f'<footer>For scout leaders only. Please don\'t share outside the group. Built {datetime.date.today():%d %b %Y}.</footer>'
            f'</body></html>\n')

def outputs(hd, slug):
    f = {k: f"{slug}{s}" for k, s in (("pack", "_leader_pack.pdf"), ("card", "_team_card.pdf"), ("gpx", ".gpx"), ("map", "_map.png"), ("ra", "_risk_assessment.pdf"))}
    return {k: v for k, v in f.items() if os.path.exists(os.path.join(hd, v))}

def hike_page(h, slug, have):
    H, r, cps = h["hike"], h.get("route", {}), h["checkpoints"]
    tot = cps[-1]["km"]; tc = toilet_cp(h)
    facts = [H.get("area", ""), f"{tot:.1f} km ({tot/1.609344:.1f} miles) {H.get('type', 'circular')}", H.get("section", "")]
    if r.get("bridleway_pct") is not None: facts.append(f"{r['bridleway_pct']}% bridleway")
    if tc: facts.append(f"toilets at {tc['id']}")
    if H.get("map"): facts.append(md(H["map"]))
    o = ['<p><a href="../">← All hikes</a></p>', f'<h1>{html.escape(H["name"])}</h1>',
         f'<p class="sub">{" · ".join(x for x in facts if x)}</p>']
    if H.get("date"): o.append(f'<p><b>Date:</b> {html.escape(str(H["date"]))}</p>')
    if r.get("road_statement"): o.append(f'<p><b>Roads:</b> {md(r["road_statement"])}</p>')
    names = {"pack": "Leader pack (PDF)", "card": "Team card (PDF)", "ra": "Risk assessment (PDF)", "gpx": "GPX for OS Maps", "map": "Full-size map"}
    o.append('<p class="dl">' + "".join(f'<a href="{have[k]}">{names[k]}</a>' for k in names if k in have) + "</p>")

    o.append('<h2>Checkpoints</h2><div class="wrap"><table><tr><th>CP</th><th>Grid ref</th><th>Location</th><th>Access for leaders</th><th>km</th></tr>')
    for c in cps:
        cls = ' class="wc"' if c.get("toilets") else ""
        o.append(f'<tr{cls}><td><b>{c["id"]}</b></td><td>{gr(c["grid_ref"])}</td><td>{md(c.get("location", c.get("name", "")))}</td>'
                 f'<td>{md(c.get("access", ""))}</td><td>{c["km"]:.1f}</td></tr>')
    o.append("</table></div>")
    for n in h.get("leader_notes") or []:
        o.append(f'<div class="note"><b>{md(n["title"])}</b><ul>' + "".join(f"<li>{md(p)}</li>" for p in n.get("points", [])) + "</ul></div>")
    if r.get("verification"): o.append(f'<p class="verify"><b>Verification and pre-walk checks:</b> {md(r["verification"])}</p>')

    if "map" in have:
        o.append(f'<h2>Map</h2><a href="{have["map"]}"><img class="map" src="map.jpg" alt="Route map for {html.escape(H["name"])}"></a>')

    o.append("<h2>Leg directions</h2>")
    for i, l in enumerate(h.get("legs") or [], 1):
        rows = "".join(f'<tr><td><b>{d["id"]}</b></td><td>{gr(d["grid_ref"])}</td><td>{d["km"]:.1f}</td><td>{md(d["text"])}</td></tr>'
                       for d in l.get("directions", []))
        o.append(f'<details><summary>Leg {i}: {l["from"]} → {l["to"]} · {md(l.get("effort", ""))}</summary><div class="wrap"><table>'
                 f'<tr><th>Point</th><th>Grid ref</th><th>km</th><th>Instruction</th></tr>{rows}</table></div></details>')
    if h.get("safety"):
        o.append("<h2>Safety</h2><ul>" + "".join(f"<li>{md(s)}</li>" for s in h["safety"]) + "</ul>")
    em = h.get("emergency") or {}
    if em.get("hospital"): o.append(f'<p><b>Nearest A&amp;E:</b> {md(em["hospital"])}</p>')
    return page(H["name"], "\n".join(o), up="../")

def build(ws, out):
    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, "style.css"), "w").write(CSS)
    open(os.path.join(out, "robots.txt"), "w").write("User-agent: *\nDisallow: /\n")
    rows, n = [], 0
    for slug in sorted(os.listdir(ws)):
        hd = os.path.join(ws, slug); y = os.path.join(hd, "hike.yaml")
        if not os.path.isfile(y): continue
        h = yaml.safe_load(open(y)); have = outputs(hd, slug)
        if "pack" not in have:
            print(f"skip {slug}: no leader pack yet (run /documentMyHike {slug})"); continue
        d = os.path.join(out, slug); os.makedirs(d, exist_ok=True)
        for f in have.values(): shutil.copy2(os.path.join(hd, f), d)
        if "map" in have:  # web-sized preview; the full PNG stays linked
            im = Image.open(os.path.join(hd, have["map"])).convert("RGB"); im.thumbnail((1600, 1600))
            im.save(os.path.join(d, "map.jpg"), quality=82)
        open(os.path.join(d, "index.html"), "w").write(hike_page(h, slug, have))
        H, cps = h["hike"], h["checkpoints"]; tot = cps[-1]["km"]
        rows.append(f'<tr><td><a href="{slug}/"><b>{html.escape(H["name"])}</b></a></td><td>{html.escape(H.get("area", ""))}</td>'
                    f'<td>{tot:.1f} km ({tot/1.609344:.1f} mi)</td><td>{html.escape(H.get("section", ""))}</td>'
                    f'<td>{html.escape(str(H.get("date") or "not set"))}</td><td>{gr(cps[0]["grid_ref"])}</td></tr>')
        n += 1; print(f"added {slug}")
    body = ('<h1>Scout hike routes</h1><p class="sub">Checkpoint routes for leaders. Each page has the checkpoints, map, '
            'leg directions and the printable leader pack and team card.</p><div class="wrap"><table>'
            '<tr><th>Hike</th><th>Area</th><th>Distance</th><th>Section</th><th>Date</th><th>Start</th></tr>'
            + "".join(rows) + "</table></div>")
    open(os.path.join(out, "index.html"), "w").write(page("Scout hike routes", body))
    return n

def env(ws):
    e = {}
    p = os.path.join(ws, ".env")
    if os.path.exists(p):
        for line in open(p):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.strip().split("=", 1); e[k] = v
    return e

def aws(*args):
    r = subprocess.run(["aws", "amplify", *args, "--output", "json"], capture_output=True, text=True)
    if r.returncode: sys.exit(f"aws amplify {args[0]} failed: {r.stderr.strip()}")
    return json.loads(r.stdout or "{}")

def deploy(site, app, branch):
    z = site + ".zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(site):
            for f in files:
                p = os.path.join(root, f); zf.write(p, os.path.relpath(p, site))
    d = aws("create-deployment", "--app-id", app, "--branch-name", branch)
    req = urllib.request.Request(d["zipUploadUrl"], data=open(z, "rb").read(), method="PUT",
                                 headers={"Content-Type": "application/zip"})
    urllib.request.urlopen(req, timeout=300).read()
    job = d["jobId"]; aws("start-deployment", "--app-id", app, "--branch-name", branch, "--job-id", job)
    for _ in range(120):
        s = aws("get-job", "--app-id", app, "--branch-name", branch, "--job-id", job)["job"]["summary"]["status"]
        if s in ("SUCCEED", "FAILED", "CANCELLED"): break
        time.sleep(5)
    print(f"deployment {job}: {s}")
    if s != "SUCCEED": sys.exit(1)
    print(f"https://{branch}.{app}.amplifyapp.com")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=os.getcwd()); ap.add_argument("--out"); ap.add_argument("--deploy", action="store_true")
    a = ap.parse_args(); ws = os.path.abspath(a.workspace)
    if not a.out and not a.deploy: ap.error("give --out DIR, --deploy, or both")
    if a.out:
        print(f"{build(ws, a.out)} hike(s) written to {a.out}")
    if a.deploy:
        e = env(ws); app = e.get("HIKE_SITE_AMPLIFY_APP_ID"); branch = e.get("HIKE_SITE_BRANCH") or "main"
        if not app: sys.exit(f"HIKE_SITE_AMPLIFY_APP_ID is not set in {ws}/.env (see the publishHikes skill)")
        tmp = tempfile.mkdtemp(prefix="hikesite_")
        try:
            site = os.path.join(tmp, "site")
            if not build(ws, site): sys.exit("no documented hikes to publish")
            deploy(site, app, branch)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    main()
