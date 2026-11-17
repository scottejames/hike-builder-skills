#!/usr/bin/env python3
"""Write a hike's staffing sheet: <slug>_staffing.md, an editable Markdown table.

Usage:
  staffing.py HIKE_DIR        (build_docs.py also writes it on every build)

Roles come from hike.yaml, one person each:
  LIC     Leader in charge
  BOOK    Booking-in leader: runs the START, then books teams in at the finish
  FIN     Finish leader
  CPn     one checkpoint leader per checkpoint (a shared checkpoint, e.g. CP1/CP3, is one person)
  Mn      one crossing marshal per significant road crossing (rule 23)
In-place and until times use the same timings as the leader pack's opening times.

The sheet is yours to edit. Fill in the Name, Mobile and Notes columns, and write anything
else under "## Planning notes". A rebuild regenerates the roles, places and times, but keeps
Name, Mobile and Notes (matched by the ID column) and the planning notes. If a role
disappears after a route change, its details move to "## Removed roles" so nothing is lost.

The .md stays the only local copy. publish_site.py renders it to PDF (to_pdf) for the website.
"""
import sys; sys.dont_write_bytecode = True  # no __pycache__ next to the tools
import os, re
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

KEEP = ("Name", "Mobile", "Notes")
COLS = ("ID", "Role", "Location", "Grid ref", "In place by", "Until") + KEEP
NOTES_H = "## Planning notes"
REMOVED_H = "## Removed roles"

def path(hd, slug):
    return os.path.join(hd, f"{slug}_staffing.md")

def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]

def parse(p):
    """Return (rows, header, notes): rows maps role ID -> dict of every column in the table."""
    rows, notes, header = {}, "", None
    if not os.path.exists(p): return rows, header, notes
    txt = open(p).read()
    if NOTES_H in txt:
        notes = txt.split(NOTES_H, 1)[1]
        notes = notes.split(REMOVED_H, 1)[0].strip("\n")
    for line in txt.split(NOTES_H, 1)[0].splitlines():
        if not line.lstrip().startswith("|"): continue
        c = _cells(line)
        if header is None and "ID" in c: header = c; continue
        if header and not set("".join(c)) <= set("-: ") and len(c) == len(header):
            r = dict(zip(header, c))
            if r.get("ID"): rows[r["ID"]] = r
    if REMOVED_H in txt:   # keep earlier removed roles too
        for line in txt.split(REMOVED_H, 1)[1].splitlines():
            m = re.match(r"- \*\*(.+?)\*\* \((.*?)\): (.*)", line.strip())
            if m: rows.setdefault("removed:" + m.group(1), {"ID": m.group(1), "Role": m.group(2), "Name": m.group(3), "_removed": True})
    return rows, header, notes

def names(hd, slug):
    """Role ID -> 'Name, mobile' for anyone filled in (used in the leader pack's checkpoint log)."""
    rows, _, _ = parse(path(hd, slug))
    return {k: ", ".join(x for x in (r.get("Name"), r.get("Mobile")) if x) for k, r in rows.items()
            if r.get("Name") and not r.get("_removed")}

def roles(h, E, T, MT, hm):
    """Staff roles in the order people are deployed."""
    start = (E["teams"] or {}).get("first_start")
    cps = h["checkpoints"]; S, F = cps[0], cps[-1]; by = {r["id"]: r for r in T}
    t = lambda r, k: hm(r[k], start) if r and k in r else ""
    until = lambda r: t(r, "close") or "last team through"
    same = S["grid_ref"] == F["grid_ref"]
    count, iv = (E["teams"] or {}).get("count"), (E["teams"] or {}).get("start_interval_min") or 0
    last_start = hm((count - 1) * iv, start) if count else "last team starts"
    out = [
        dict(ID="LIC", Role="Leader in charge", Location=f"Event base: {S['name']}" + ("" if same else f", then {F['name']}"),
             **{"Grid ref": S["grid_ref"], "In place by": t(by["START"], "open"), "Until": "all teams finished"}),
        dict(ID="BOOK", Role="Booking-in leader: runs the START, then books teams in at the finish",
             Location=S["name"] + (" (start and finish)" if same else f", then {F['name']}"),
             **{"Grid ref": S["grid_ref"], "In place by": t(by["START"], "open"),
                "Until": f"START until {last_start}; FINISH from {t(by['FINISH'], 'open')} until {until(by['FINISH'])}"}),
        dict(ID="FIN", Role="Finish leader", Location=F["name"],
             **{"Grid ref": F["grid_ref"], "In place by": t(by["FINISH"], "open"), "Until": until(by["FINISH"])}),
    ]
    seen = set()
    for c in cps[1:-1]:
        if c["id"] in seen: continue
        ids = [c["id"]] + ([c["shared_with"]] if c.get("shared_with") else []); seen.update(ids)
        r = by[c["id"]]; walk = f" (walk in {c['walk_in_min']} min)" if c.get("walk_in_min") else ""
        out.append(dict(ID="/".join(ids), Role="Checkpoint leader" + (" (toilet stop)" if c.get("toilets") else "") + walk,
                        Location=c["name"], **{"Grid ref": c["grid_ref"], "In place by": t(r, "open"),
                                               "Until": until(by[ids[-1]]) if len(ids) > 1 else until(r)}))
    Mx = {r["id"]: r for r in MT}
    for m in h.get("marshals") or []:
        r = Mx.get(m["id"])
        out.append(dict(ID=m["id"], Role="Crossing marshal", Location=m["name"],
                        **{"Grid ref": m["grid_ref"], "In place by": t(r, "open"), "Until": until(r)}))
    return out

def write(h, hd, E, T, MT, hm):
    """(Re)write the sheet, keeping what people typed. Returns (path, people, filled)."""
    slug = h["hike"]["slug"]; p = path(hd, slug)
    old, _, notes = parse(p)
    R = roles(h, E, T, MT, hm)
    for r in R:
        o = old.pop(r["ID"], {})
        for k in KEEP: r[k] = o.get(k, "")
    gone = [o for o in old.values() if any(o.get(k) for k in KEEP)]
    clean = lambda v: str(v).replace("|", "/").replace("\n", " ")
    H = h["hike"]; ts = E["teams"] or {}
    n_cp = sum(1 for r in R if r["ID"].startswith("CP")); n_m = sum(1 for r in R if r["ID"].startswith("M"))
    lines = [f"# Staffing: {H['name']}", "",
             f"Date: {H.get('date') or 'not set'} · Teams: {ts.get('count') or 'not set'}, starting every {ts.get('start_interval_min', 0)} min"
             f" from {ts.get('first_start') or 'the first start (times below are offsets)'}", "",
             f"**{len(R)} people needed:** leader in charge, booking-in leader (also runs the start), finish leader, "
             f"{n_cp} checkpoint leader{'s' if n_cp != 1 else ''} and {n_m} crossing marshal{'s' if n_m != 1 else ''} (rule 23).", "",
             "Fill in **Name**, **Mobile** and **Notes**. Rebuilding the hike keeps them (matched by ID) and refreshes the other columns.", "",
             "| " + " | ".join(COLS) + " |", "|" + "|".join("---" for _ in COLS) + "|"]
    lines += ["| " + " | ".join(clean(r.get(k, "")) for k in COLS) + " |" for r in R]
    lines += ["", NOTES_H, notes.strip("\n") if notes.strip() else "\n(Anything else for planning: vehicles, kit, radios, who brings the signs.)", ""]
    if gone:
        lines += [REMOVED_H, "These roles are no longer on the route. Move the people to a new role or delete these lines.", ""]
        lines += [f"- **{o['ID']}** ({o.get('Role', '')}): " + ", ".join(o[k] for k in KEEP if o.get(k)) for o in gone] + [""]
    open(p, "w").write("\n".join(lines))
    return p, len(R), sum(1 for r in R if r["Name"])

PDF_CSS = """
  @page { size: A4 landscape; margin: 10mm; }
  body { font-family: "Liberation Sans", Arial, sans-serif; font-size: 9pt; color: #111; margin: 0; }
  h1, h2 { font-family: "Liberation Sans", Arial, sans-serif; }
  h1 { font-size: 15pt; margin: 0 0 1mm 0; }
  h2 { font-size: 11pt; margin: 4mm 0 1.5mm 0; color: #2d5a27; border-bottom: 1.5px solid #2d5a27; }
  p { margin: 0 0 1.5mm 0; }
  table { border-collapse: collapse; }
  tr { page-break-inside: avoid; }
  th, td { vertical-align: top; text-align: left; font-size: 9pt; }
  th { background: #e4ecdf; }
  .gr { font-family: "Liberation Mono", monospace; font-weight: bold; white-space: nowrap; }
"""
WIDTHS = {"ID": "6%", "Role": "17%", "Location": "17%", "Grid ref": "8%", "In place by": "6%", "Until": "13%",
          "Name": "12%", "Mobile": "10%"}

def to_pdf(md_path, out_pdf):
    """Render the Markdown sheet as a landscape A4 PDF (for the website; nothing is written next to the .md)."""
    import html, shutil, tempfile
    from build_docs import md, cellp, soffice
    o, table, ul = [], [], False
    def flush():
        nonlocal table
        if not table: return
        hdr, body = table[0], [r for r in table[1:] if not set("".join(r)) <= set("-: ")]
        o.append('<table width="100%" border="1" cellspacing="0" cellpadding="3"><tr>'
                 + "".join(f'<th width="{WIDTHS.get(c, "")}">{html.escape(c)}</th>' for c in hdr) + "</tr>"
                 + "".join('<tr>' + "".join(f'<td height="24">{md(c)}</td>' for c in r) + "</tr>" for r in body) + "</table>")
        table = []
    for line in open(md_path).read().splitlines():
        t = line.strip()
        if t.startswith("|"): table.append(_cells(t)); continue
        flush()
        if ul and not t.startswith("- "): o.append("</ul>"); ul = False
        if t.startswith("# "): o.append(f"<h1>{md(t[2:])}</h1>")
        elif t.startswith("## "): o.append(f"<h2>{md(t[3:])}</h2>")
        elif t.startswith("- "):
            if not ul: o.append("<ul>"); ul = True
            o.append(f"<li>{md(t[2:])}</li>")
        elif t: o.append(f"<p>{md(t)}</p>")
    flush()
    if ul: o.append("</ul>")
    doc = (f'<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><title>Staffing</title><style>{PDF_CSS}</style>'
           f'</head><body>\n{cellp(chr(10).join(o))}\n</body></html>')
    tmp = tempfile.mkdtemp(prefix="hikedocs_staff_")
    try:
        h = os.path.join(tmp, "staffing.html"); open(h, "w").write(doc)
        shutil.copy(soffice(h, tmp), out_pdf)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out_pdf

def main():
    import build_docs as B
    hd = os.path.abspath(sys.argv[1]); h = yaml.safe_load(open(os.path.join(hd, "hike.yaml")))
    E = B.merged(h, B.load_settings())
    p, n, f = write(h, hd, E, B.timings(h, E), B.marshal_timings(h, E), B.hm)
    print("wrote", p, f"({n} people, {f} named)")

if __name__ == "__main__":
    main()
