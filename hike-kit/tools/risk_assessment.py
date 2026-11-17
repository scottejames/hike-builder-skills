#!/usr/bin/env python3
"""Build a hike's event risk assessment PDF: <slug>_risk_assessment.pdf.

Usage:
  risk_assessment.py HIKE_DIR [--check]

build_docs.py calls this too, so /documentMyHike writes the RA with the other documents.

Sources:
  <workspace>/risk-assessment.yaml   the group's base event RA (private, never in this repo):
      title, organisation, review_months, columns {hazard, who, controls, changes},
      hazards: [{id, hazard, who, controls: [..]}]   ("{prewalk_date}" in a control is filled in)
  <hike>/hike.yaml  risk_assessment:
      assessor, date, next_review, prewalk_date      (null prints a blank line to fill in by hand)
      changes: {<hazard id>: "route note for the 4th column"}
      route_risks: [{hazard, who, controls: [..]}]   hazards unique to this route
The event date comes from hike.date.

Page 1 onwards: header boxes, the base hazards with this route's notes in the 4th column,
then a numbered table of route-specific risks (R1, R2 ...) and a sign-off box.
"""
import sys; sys.dont_write_bytecode = True  # no __pycache__ next to the tools
import argparse, html, os, shutil, tempfile
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_docs import md, cellp, soffice, pages

BASE_FILE = "risk-assessment.yaml"

CSS = """
  @page {{ size: A4 landscape; margin: 10mm; }}
  body {{ font-family: "Liberation Sans", Arial, sans-serif; font-size: {fs}pt; color: #111; margin: 0; }}
  h1, h2 {{ font-family: "Liberation Sans", Arial, sans-serif; }}
  tr {{ page-break-inside: avoid; }}
  h1 {{ font-size: {h1}pt; margin: 0 0 1mm 0; }}
  h2 {{ font-size: {h2}pt; margin: 3mm 0 1.5mm 0; color: #2d5a27; border-bottom: 1.5px solid #2d5a27; }}
  .sub {{ color: #333; margin-bottom: 2mm; }}
  table {{ border-collapse: collapse; }}
  th, td {{ vertical-align: top; text-align: left; font-size: {fs}pt; }}
  th {{ background: #e4ecdf; }}
  ul {{ margin: 0; padding-left: 4mm; }}
  .gr {{ font-family: "Liberation Mono", monospace; font-weight: bold; white-space: nowrap; }}
  .rr {{ background: #fff4c7; }}
"""

def base_path(hd):
    return os.path.join(os.path.dirname(os.path.abspath(hd)), BASE_FILE)

def load_base(hd):
    p = base_path(hd)
    return yaml.safe_load(open(p)) if os.path.exists(p) else None

def check(h, base):
    """Return (errors, warnings) for build_docs --check."""
    err, warn = [], []
    ra = h.get("risk_assessment")
    if base is None:
        return err, [f"no {BASE_FILE} in the workspace: the risk assessment PDF is skipped"]
    if not ra:
        return err, ["no risk_assessment section: add route_risks for this route's own hazards"]
    ids = {z["id"] for z in base.get("hazards", [])}
    for k in (ra.get("changes") or {}):
        if k not in ids: err.append(f"risk_assessment.changes.{k}: no hazard with that id in {BASE_FILE}")
    if not ra.get("route_risks"): warn.append("risk_assessment.route_risks is empty: review the route for unique hazards")
    for i, r in enumerate(ra.get("route_risks") or [], 1):
        if not r.get("hazard") or not r.get("controls"): err.append(f"route risk R{i}: needs hazard and controls")
    return err, warn

def blank(v, width=40):
    return md(v) if v else "&nbsp;" * width

def ul(items, fill=None):
    items = [x.replace("{prewalk_date}", fill or "__________") if isinstance(x, str) else x for x in (items or [])]
    return "<ul>" + "".join(f"<li>{md(x)}</li>" for x in items) + "</ul>" if len(items) > 1 else (md(items[0]) if items else "")

def body(h, base):
    H, ra = h["hike"], h.get("risk_assessment") or {}
    C = base.get("columns", {}); cps = h["checkpoints"]; em = h.get("emergency") or {}
    ch = ra.get("changes") or {}; pw = ra.get("prewalk_date")
    o = [f'<h1>{html.escape(base.get("title", "Event Risk Assessment"))}: {html.escape(H["name"])}</h1>',
         f'<p class="sub">{html.escape(base.get("organisation", ""))} · {html.escape(H.get("area", ""))} · '
         f'{cps[-1]["km"]:.1f} km {H.get("type", "circular")} · {html.escape(H.get("section", ""))} · '
         f'start {md(cps[0]["grid_ref"])}' + (f' · nearest A&amp;E: {md(em["hospital"])}' if em.get("hospital") else "") + "</p>",
         '<table width="100%" border="1" cellspacing="0" cellpadding="4"><tr>'
         '<th>Person doing this RA</th><th>Date of RA</th><th>Date of next review</th><th>Date of event</th><th>Route pre-walked on</th></tr>'
         f'<tr><td height="22">{blank(ra.get("assessor"))}</td><td>{blank(ra.get("date"), 20)}</td>'
         f'<td>{blank(ra.get("next_review"), 20)}</td><td>{blank(H.get("date"), 20)}</td><td>{blank(pw, 20)}</td></tr></table>',
         "<h2>Event hazards</h2>",
         '<table width="100%" border="1" cellspacing="0" cellpadding="3">'
         f'<tr><th width="20%">{html.escape(C.get("hazard", "Hazard"))}</th><th width="9%">{html.escape(C.get("who", "Who is at risk?"))}</th>'
         f'<th>{html.escape(C.get("controls", "Controls"))}</th><th width="22%">{html.escape(C.get("changes", "What has changed?"))}</th></tr>']
    for z in base.get("hazards", []):
        note = ch.get(z["id"])
        o.append(f'<tr><td><b>{md(z["hazard"])}</b></td><td>{md(z.get("who", ""))}</td><td>{ul(z.get("controls"), pw)}</td>'
                 f'<td{" class=\"rr\"" if note else ""}>{md(note) if note else ""}</td></tr>')
    o.append("</table>")
    xs = h.get("road_crossings") or []; M = {m["id"]: m for m in h.get("marshals") or []}
    o.append("<h2>Significant road crossings: every one supervised by an adult</h2>")
    if xs:
        o.append('<p style="margin:0 0 1mm 0">Every place the route meets an A, B or main C road was found from OpenStreetMap and is listed here. '
                 'An adult sees every team across: the checkpoint leader where the crossing is at a checkpoint, otherwise a crossing marshal in Hi-Vis.</p>'
                 '<table width="100%" border="1" cellspacing="0" cellpadding="3"><tr><th width="28%">Road</th><th width="9%">Grid ref</th>'
                 '<th width="5%">km</th><th width="22%">Supervised by</th><th>Notes</th></tr>')
        for x in xs:
            s_ = x.get("supervised_by")
            who = (f"Crossing marshal <b>{s_}</b>" if s_ in M else f"<b>{s_}</b> checkpoint leader") if s_ else "No crossing: " + md(x.get("no_crossing", ""))
            note = x.get("note") or (M[s_].get("access") if s_ in M else "")
            o.append(f'<tr><td>{md(x["road"])}</td><td>{md(x["grid_ref"])}</td><td>{x["km"]:.1f}</td><td>{who}</td><td>{md(note)}</td></tr>')
        o.append("</table>")
    else:
        o.append("<p>The route does not cross or walk along any significant road.</p>")
    rr = ra.get("route_risks") or []
    o.append("<h2>Route-specific risks</h2>")
    if rr:
        o.append('<table width="100%" border="1" cellspacing="0" cellpadding="3">'
                 '<tr><th width="4%">Ref</th><th width="25%">Hazard and risks</th><th width="10%">Who is at risk?</th><th>Controls</th></tr>')
        for i, r in enumerate(rr, 1):
            o.append(f'<tr><td><b>R{i}</b></td><td>{md(r["hazard"])}</td><td>{md(r.get("who", "All participants"))}</td><td>{ul(r.get("controls"))}</td></tr>')
        o.append("</table>")
    else:
        o.append("<p>None recorded.</p>")
    o.append('<table width="100%" border="1" cellspacing="0" cellpadding="4" style="margin-top:3mm"><tr>'
             '<td width="34%" height="26"><b>Approved by (Leader in Charge)</b></td><td width="33%"><b>Signature</b></td><td><b>Date</b></td></tr></table>')
    return cellp("\n".join(o))

def build(h, hd, out_pdf, base=None, fs=8.6):
    base = base or load_base(hd)
    if base is None: return None
    css = CSS.format(fs=fs, h1=fs + 5, h2=fs + 1.6)
    doc = (f'<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><title>Risk assessment</title>'
           f'<style>{css}</style></head><body>\n{body(h, base)}\n</body></html>')
    tmp = tempfile.mkdtemp(prefix="hikedocs_ra_")
    try:
        p = os.path.join(tmp, "risk_assessment.html"); open(p, "w").write(doc)
        shutil.copy(soffice(p, tmp), out_pdf)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return pages(out_pdf)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("hike_dir"); ap.add_argument("--check", action="store_true")
    a = ap.parse_args(); hd = os.path.abspath(a.hike_dir)
    h = yaml.safe_load(open(os.path.join(hd, "hike.yaml"))); base = load_base(hd)
    err, warn = check(h, base)
    for x in err: print("ERROR:", x)
    for x in warn: print("WARN: ", x)
    if a.check or err or base is None: sys.exit(1 if err else 0)
    out = os.path.join(hd, f"{h['hike']['slug']}_risk_assessment.pdf")
    print("wrote", out, f"({build(h, hd, out, base)} pages)")

if __name__ == "__main__":
    main()
