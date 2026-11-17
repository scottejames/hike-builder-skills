---
name: documentMyHike
description: Build the documentation for a planned scout hike from <workspace>/<slug>/hike.yaml - leader pack PDF, team card, GPX, map and optional Street View photos - following hike-kit/documentation-style.md.
argument-hint: "<hike folder, e.g. ditchling-stanmer>"
disable-model-invocation: true
---

# Document a hike

Turn `$ARGUMENTS/hike.yaml` (in the workspace, the current directory) into the outputs listed in `hike-kit/documentation-style.md`. The YAML is the single source of truth. Change content in the YAML, never in generated files, so a rebuild reproduces it. If no folder is given, list the folders in the workspace that contain `hike.yaml` and ask which one.

## 1. Load

Read `hike-kit/documentation-style.md`, which is the specification for every page, and the hike's `hike.yaml`.

## 2. Check

Run `python3 hike-kit/tools/build_docs.py <slug> --check`.

- **ERRORs:** fix them in `hike.yaml`. A grid ref mismatch means the coordinates or the ref are wrong, so recompute with `hike-kit/tools/osgb.py`. The route line is never stored: `build_docs.py` re-routes from `route.routing_points` on the `.osm/` cache every run, and refreshes the cache when it's stale or missing. If the check reports that a checkpoint's km has changed, the OSM data or the routing points changed. Rerun `plan_route.py --junctions`, review the line with the user, and update the km and directions in `hike.yaml`. Use `--refresh-osm` to force a fresh download.
- **MUST breaches** that aren't in `brief.exceptions`: stop and ask the user.
- **Road crossings (rule 23):** `--check` fails for any significant road contact without a `road_crossings` entry, or whose supervisor is too far away. Fix it by covering the crossing with a checkpoint or adding a marshal, and ask the user if it changes the route or staffing. Make sure the RA's traffic notes and route risks name who supervises each crossing.
- **Risk assessment:** if the workspace has `risk-assessment.yaml`, the hike needs a `risk_assessment:` section (see `hike-kit/hike-template.yaml`). Review the route for hazards unique to it: roads walked and crossed, rivers and ponds, railways, foot-only or shared checkpoints, exposed or steep ground, mud and flooding, livestock, bikes and horses, long distance, busy checkpoint sites, and anything on the pre-walk list that affects safety. Write each one as a `route_risks` entry naming the place, and point the matching base hazard to it with `changes.<id>`. Leave assessor and dates null unless the user gives them.
- **Wording review:** read every text field against the wording rules: verbs first, **CAPS** turn words, "Cross … together", "**On foot only:**", "check on the day" for anything unverified, and British English. Fix the YAML where needed.

## 3. Street View, only if `streetview.enabled` is true

Each location needs 4 images in `<slug>/streetview/` named `<prefix>_h000.jpg`, `_h090`, `_h180` and `_h270`. Skip any location whose images already exist; each image is billed by Google.

1. Run refconv `streetview_coverage` on `grid_ref_used`. It's free. Note the panorama date and whether it's an official Google capture or a user photo.
2. For a vehicle checkpoint, make sure the panorama is on the road and not in nearby woods. If the coverage location is off the road, pass a 10-figure ref for the exact roadside spot. Convert the road point with refconv `latlon_to_gridref`.
3. Fetch the images with refconv `streetview_from_gridref` at headings 0, 90, 180 and 270. The files land in refconv's output folder (`REFCONV_OUTPUT_DIR`); the tool's `Saved:` line gives each path. Copy them to `<slug>/streetview/` under the names above.
4. Look at each image. Write `date` (YYYY-MM), `source` ("Google" or "user photo © <name>") and a short `caption` saying what leaders will see (parking, gate, sign) into the YAML.
5. If there's no coverage, tell the user, and remove that location or set `enabled: false`.

## 4. Build

Run `python3 hike-kit/tools/build_docs.py <slug>`. It writes the map, GPX, leader pack PDF and team card PDF. Read its output:

- **"OVERFLOW" for a section:** shorten that section's text in the YAML and rebuild. Don't add pages.
- **Wrong page count:** the leader pack should have 5 pages, or 4 without Street View.

## 5. Look at every page

Render the pages with `pdftoppm -r 70 -png <pdf> <scratchpad>/pg`, then Read each image and check it against `documentation-style.md`:

- **Page 1:** the summary line; the toilet row in yellow; shared and foot-only rows in blue; a total row; leader-note boxes; an orange verification box.
- **Page 2:** one table per leg; no table split badly across the page.
- **Page 3:** the map shows every T-point and checkpoint, the markers are legible, and the caption is complete.
- **Page 4:** opening times present, with closing times when `teams.count` is set; the checkpoint log.
- **Page 5:** four images per location, each with date and source.
- **Team card:** the start grid ref only; numbered rows with no checkpoint names; 1 page.
- **Staffing sheet** (`<slug>_staffing.md`): one row each for LIC, BOOK, FIN, every checkpoint (a shared CP is one row) and every crossing marshal; in-place times match page 4. The build keeps any Name, Mobile and Notes the user typed. Never overwrite or blank them by hand.
- **Risk assessment:** landscape; header boxes; route notes shaded in the 4th column; every route risk numbered R1, R2 …; sign-off box.
- **Everywhere:** grid refs in bold monospace and never wrapped.

Fix any problem through the YAML, or in `build_docs.py` if it's a layout bug, and rebuild.

## 6. Clean up

Always remove temporary files without being asked:
- page renders and test files in the scratchpad
- Street View originals in the RefConvMCP output folder
- any stray `/tmp/hikedocs_*` or `/tmp/preview_*` folders

Keep only material a person adjusts or reads; never keep anything that can be regenerated from `hike.yaml`. The hike folder holds only:
- `hike.yaml`, the source
- `streetview/`, photos that cost money to re-fetch
- `.osm/`, a disposable cache
- the outputs people read: leader pack PDF, team card PDF, risk assessment PDF, GPX, and map PNG
- `<slug>_staffing.md`, the staffing sheet. It's generated, but the user edits it (names, mobiles, notes), so it is source too: never delete it

Run `ls -A <slug>` to confirm.

## 7. Report

**Done when:** every page passes step 5 and step 6 is done. Tell the user:

- the file paths
- the page counts
- the opening times (and closing times, if set)
- the staffing headcount, and that names go in `<slug>_staffing.md` (kept on every rebuild)
- any remaining WARNs or "check on the day" items
- the number of Street View images fetched (they're billed)

Suggest checking the line on OS Maps by importing the GPX.
