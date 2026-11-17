#!/usr/bin/env python3
"""Render a route map PNG on OpenTopoMap (contours) with checkpoint and turn markers.

CLI (quick look):        render_map.py OSM_DIR "START@lat,lon;...;FINISH@lat,lon" out.png
Library (documentation): render(track, markers, out_png)
  markers: list of dicts {label, lat, lon, kind}; kind in start|finish|cp|toilet|turn
Markers sharing a location are merged ("CP1/3", "S/F"). Tiles are cached in
hike-kit/.tilecache and requested with a User-Agent (OpenTopoMap usage policy).
"""
import sys; sys.dont_write_bytecode = True  # no __pycache__ next to the tools
import io, json, math, os, sys, urllib.request
from PIL import Image, ImageDraw, ImageFont

Z = 15
CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".tilecache")
def font_file(bold=False):
    """Locate Liberation Sans (or a close fallback) on Linux or macOS via fontconfig."""
    import subprocess
    pat = "Liberation Sans:bold" if bold else "Liberation Sans"
    try:
        return subprocess.run(["fc-match", "-f", "%{file}", pat], capture_output=True, text=True).stdout.strip() or "DejaVuSans.ttf"
    except FileNotFoundError:
        return "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf"

FB = font_file(True)
FR = font_file(False)
UA = "hikeBuilder/1.0 (scout hike planning; low volume)"

def _px(lat, lon):
    n = 2**Z*256
    return (lon+180)/360*n, (1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n

def _font(path, size):
    try: return ImageFont.truetype(path, size)
    except OSError: return ImageFont.load_default()

def _tile(tx, ty):
    os.makedirs(CACHE, exist_ok=True)
    f = f"{CACHE}/{Z}_{tx}_{ty}.png"
    if not os.path.exists(f):
        req = urllib.request.Request(f"https://{'abc'[(tx+ty)%3]}.tile.opentopomap.org/{Z}/{tx}/{ty}.png", headers={"User-Agent": UA})
        open(f, "wb").write(urllib.request.urlopen(req, timeout=60).read())
    return Image.open(f).convert("RGB")

def render(track, markers, out, pad=90, scale=2):
    xs, ys = zip(*[_px(a, b) for a, b in track])
    x0, x1, y0, y1 = min(xs)-pad, max(xs)+pad, min(ys)-pad, max(ys)+pad
    tx0, tx1, ty0, ty1 = int(x0//256), int(x1//256), int(y0//256), int(y1//256)
    big = Image.new("RGB", ((tx1-tx0+1)*256, (ty1-ty0+1)*256), "white")
    for tx in range(tx0, tx1+1):
        for ty in range(ty0, ty1+1):
            big.paste(_tile(tx, ty), ((tx-tx0)*256, (ty-ty0)*256))
    img = big.crop((int(x0-tx0*256), int(y0-ty0*256), int(x1-tx0*256), int(y1-ty0*256)))
    img = img.resize((img.width*scale, img.height*scale), Image.LANCZOS)
    d = ImageDraw.Draw(img, "RGBA")
    P = lambda la, lo: ((_px(la, lo)[0]-x0)*scale, (_px(la, lo)[1]-y0)*scale)
    pts = [P(a, b) for a, b in track]
    d.line(pts, fill=(255, 255, 255, 200), width=14, joint="curve")
    d.line(pts, fill=(200, 20, 60, 255), width=8, joint="curve")
    cum = [0]
    for a, b in zip(pts, pts[1:]): cum.append(cum[-1]+math.dist(a, b))
    for k in range(1, 15):  # direction arrows
        i = min(range(len(pts)-1), key=lambda i: abs(cum[i]-k*cum[-1]/15)); a, b = pts[i], pts[min(i+3, len(pts)-1)]
        ang = math.atan2(b[1]-a[1], b[0]-a[0]); cx, cy = a; L = 16
        d.polygon([(cx+L*math.cos(ang+o), cy+L*math.sin(ang+o)) for o in (0, 2.5, -2.5)], fill="white", outline=(120, 0, 30))
    # merge markers at the same spot
    merged = []
    for m in markers:
        for g in merged:
            if g["kind"] != "turn" and m["kind"] != "turn" and abs(g["lat"]-m["lat"]) < 2e-4 and abs(g["lon"]-m["lon"]) < 3e-4:
                g["labels"].append(m["label"]); g["kinds"].add(m["kind"]); break
        else:
            merged.append(dict(m, labels=[m["label"]], kinds={m["kind"]}))
    for g in sorted(merged, key=lambda g: g["kind"] != "turn"):
        cx, cy = P(g["lat"], g["lon"])
        if g["kind"] == "turn":
            r = 17; d.ellipse((cx-r, cy-r, cx+r, cy+r), fill="white", outline=(20, 20, 20), width=3)
            d.text((cx, cy), g["label"], fill="black", font=_font(FB, 15 if len(g["label"]) > 2 else 18), anchor="mm"); continue
        labs = g["labels"]
        if {"start", "finish"} <= g["kinds"]: lab = "S/F"
        elif all(l.startswith("CP") for l in labs) and len(labs) > 1: lab = "CP" + "/".join(l[2:] for l in labs)
        else: lab = "/".join(labs)
        col = (30, 110, 40) if g["kinds"] & {"start", "finish"} else (230, 140, 0) if "toilet" in g["kinds"] \
            else (120, 40, 160) if g["kinds"] == {"marshal"} else (20, 60, 140)
        w = 26 + len(lab)*17
        d.rounded_rectangle((cx-w/2, cy-26, cx+w/2, cy+26), radius=14, fill=col, outline="white", width=4)
        d.text((cx, cy), lab, fill="white", font=_font(FB, 28), anchor="mm")
    W, H = img.size
    d.rectangle((W-90, 20, W-20, 120), fill=(255, 255, 255, 220))
    d.polygon([(W-55, 32), (W-75, 90), (W-55, 78), (W-35, 90)], fill="black")
    d.text((W-55, 108), "N", fill="black", font=_font(FB, 30), anchor="mm")
    mpp = 156543.03*math.cos(math.radians(track[0][0]))/2**Z/scale; L = 1000/mpp
    d.rectangle((20, H-80, 60+L, H-20), fill=(255, 255, 255, 220))
    d.rectangle((30, H-45, 30+L, H-35), fill="black"); d.rectangle((30+L/2, H-45, 30+L, H-35), fill="white", outline="black")
    d.text((30, H-60), "0", fill="black", font=_font(FR, 20), anchor="mm"); d.text((30+L, H-60), "1 km", fill="black", font=_font(FR, 20), anchor="mm")
    d.text((W-10, H-8), "Map © OpenStreetMap contributors, SRTM | style © OpenTopoMap (CC-BY-SA)", fill="black", font=_font(FR, 20), anchor="rd")
    img.save(out)
    return img.size

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from plan_route import route
    t = route(sys.argv[1], sys.argv[2])
    cps = t["checkpoints"]
    ms = [dict(label=c["label"], lat=c["lat"], lon=c["lon"],
               kind="start" if i == 0 else "finish" if i == len(cps)-1 else "cp") for i, c in enumerate(cps)]
    print(render([tuple(p) for p in t["track"]], ms, sys.argv[3]))
