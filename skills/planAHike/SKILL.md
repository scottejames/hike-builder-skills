---
name: planAHike
description: Plan a scout checkpoint hike. Interviews the user, designs and checks a route against hike-kit/rules.md, proposes candidates for approval, and writes <workspace>/<slug>/hike.yaml for documentMyHike.
disable-model-invocation: true
---

# Plan a hike

Produce a `hike.yaml` that fully describes one approved hike. Every interview answer goes into `brief`, so the YAML alone can rebuild the documents. Work in the workspace, which is the current directory: it holds the `hike-kit/` link, `known-huts.yaml` and one folder per hike.

## 0. Load the rules

Read `hike-kit/rules.md`, `known-huts.yaml` (in the workspace; create it from `hike-kit/known-huts.example.yaml` if it's missing) and `hike-kit/hike-template.yaml`. The rules are the user's. Apply every one of them. A MUST rule can only be broken with the user's explicit OK, recorded in `brief.exceptions`.

## 1. Interview: ask everything up front

Use AskUserQuestion, at most 4 questions per call. Offer sensible options; the user can always type their own answer. Skip anything the user already told you.

- **Round 1:** area or start place; distance (offer the section's range from `section_defaults`); circular or linear; section (Scouts 10–14, Cubs, Explorers).
- **Round 2:** date and first start time (or "not fixed yet"); number of teams; start interval in minutes; toilet stop length (the default range is 0–30 min).
- **Round 3:** start/finish base (a known hut, a public car park, or no preference); toilet preference (public toilets, a named scout hut, or a café once confirmed); anything to include or avoid (viewpoints, roads, steep climbs); Street View photos yes or no. Say that Google bills each image, about 4 per location.
- If `known-huts.yaml` is empty and huts would help, ask whether the user has access to any huts in the area and add them to `known-huts.yaml` once confirmed.

Write the answers into a draft `brief` right away, so a crash loses nothing: `<slug>/hike.yaml` holding only `hike` and `brief`.

## 2. Gather facts about the area

1. Geocode the start: osm-nic `geocode`, or os-maps `search_os_place` for UK names. Confirm the grid ref with `python3 hike-kit/tools/osgb.py LAT,LON`.
2. Fetch the data: `python3 hike-kit/tools/osm_fetch.py --around LAT,LON --radius-km R --out <slug>/.osm`, where R is about 0.4 × the distance in km. It prints the bbox; record it as `route.osm_bbox` in `hike.yaml`, so the cache can always be rebuilt. Retries are built in. If it still fails, wait and rerun; never invent paths.
   - `.osm/` is a cache, not source material. It is re-fetched when it's missing, older than `osm_cache_max_age_days`, or covers a different bbox. If routing looks wrong or fails, re-fetch with `--refresh` before blaming the route.
3. Run `python3 hike-kit/tools/facilities.py <slug>/.osm --known-huts known-huts.yaml`. This lists toilets, scout huts, parking and ROAD ACCESS points.
4. Run osm-nic `find_nearby_pois` with `club=scout` near the start and the likely halfway point. OSM huts are only candidates; ask the user before relying on one.

**MCP notes:**
- Use osm-nic `route` with profile foot to cross-check.
- Use refconv for grid refs and Street View.
- Avoid openroute: one call returns about 25k tokens, and `search_pois` is broken.
- Avoid osm `get_route_directions`: it returns car routes, even for foot.

## 3. Design candidate routes

1. Pick the toilet checkpoint first. It must sit in `toilet_window_pct` of the distance, so for a circular route about half the distance away by path. Then pick a start/finish with parking, preferably a hut.
2. Build a loop: `python3 hike-kit/tools/plan_route.py <slug>/.osm "START@..;~shaping..;CP1@..;CP2@..;FINISH@.." --junctions`. Nothing is saved: the routing points are the source, and every tool re-routes from them. Use `~lat,lon` shaping points to push the line onto bridleways or away from the outward path.
3. Put checkpoints at ROAD ACCESS points, car parks or village streets. Aim for legs of 40–50 min at planning pace; location beats minutes.
4. Read the output and fix problems before you show anything:
   - road metres > 0 outside village lanes (rule 2)
   - bridleway share under 70% (rule 3)
   - a leg over the hard maximum (rule 10)
   - a snapping WARNING
   - LOST-RISK flags (rule 11). A REVISIT junction is a strong via-checkpoint candidate. It may be on foot only and shared, like Moon's Bottom (CP1/CP3) in the example.
5. Cross-check at least one leg with osm-nic `route` (profile foot). Note any difference above about 10%.
6. For each vehicle-access checkpoint, call refconv `streetview_coverage`. It's free, and it shows whether a photo exists and how old it is.

## 4. Preview first, then ask

The user can't judge a route from a table in chat. They need to see the map. **Don't ask any question about a route until its preview PDF is open in front of them.**

1. For each candidate (1 or 2 at most), write `<scratchpad>/candidate_<X>.yaml`, never in the hike folder. Include its `routing_points`. The format is in the docstring of `hike-kit/tools/preview.py`; `hike-kit/candidate-example.yaml` is an example. Include:
   - **checkpoints:** place, access (vehicle / foot / unknown), toilets, and a short note
   - **rule_breaches:** each one with the reason it can't be avoided
   - **lost_risk:** where teams could go wrong, and what covers it
   - **prewalk_checks:** everything not confirmed by data (toilet opening and public access, pavements, whether a lane is private, parking)
   - **options:** changes the user could ask for
2. Run `python3 hike-kit/tools/preview.py <slug> <scratchpad>/candidate_<X>.yaml --out <scratchpad>/preview_<X>.pdf --open`. That gives a 2-page PDF: page 1 is the summary, checkpoint table and lists; page 2 is the full-page map. Render page 1 with `pdftoppm` and Read it to check that it fits.
3. In chat, give one short paragraph per candidate and the PDF path. Then ask: approve, adjust (what to change), or try something else. Ask about the rule breaches at this point, since the user can now see them on the map.
4. **Pre-walk checks are never questions.** The user pre-walks every route, so anything that can't be confirmed from data goes into `prewalk_checks` and later into the leader pack as "check on the pre-walk". Don't ask the user to confirm toilets, pavements or private lanes during planning.
5. Iterate: re-route, regenerate the preview, open it again, until the user approves. Record each approved rule breach in `brief.exceptions`. Use the words "toilet" or "guide" in the exception text when it covers the toilet window or leg spacing, because `build_docs.py` reads those words. Copy the `prewalk_checks` into `route.verification`.

## 5. Write hike.yaml

Follow `hike-kit/hike-template.yaml`, with `hike-kit/examples/ditchling-stanmer.yaml` as the worked example. Apply the wording rules in `hike-kit/documentation-style.md` as you write.

- **Checkpoints:** take km, lat and lon from the `plan_route.py` output for the approved routing points, and grid refs from `osgb.py`, never by eye. Set `vehicle_access`, `toilets`, `shared_with` and `walk_in_min`.
- **Legs:**
  - Build the directions from the DECISION POINTS output: one row per real turn, numbered T1, T2 and so on along the route.
  - Copy each turn's lat/lon and grid ref exactly from that output.
  - Start each instruction with a verb, put turn and compass words in **CAPS**, and name what teams will see.
  - Write each road crossing as "**Cross <road> together**".
- **Leader notes:** add one entry per shared or foot-only checkpoint. For shared checkpoints, say how to tell the visits apart by arrival direction, and which grid ref to give.
- **Other sections:** fill in safety (name every road crossing), kit, emergency (nearest A&E), team-card safety in plain words, and `route.verification`. Mark anything unverified "check on the day".
- **Street View:** set `streetview.enabled` from the brief. If it's enabled, add one `locations` entry per distinct place, with `prefix` set and `date`/`source` left blank for documentMyHike to fill in.

## 6. Validate and hand over

Run `python3 hike-kit/tools/build_docs.py <slug> --check`. Fix every ERROR. Show the WARNs to the user and either fix them or record the user's OK as an exception.

## 7. Clean up

Always remove your working files before handing over, without being asked. Keep only material a person adjusts or reads; never keep anything that can be regenerated from `hike.yaml`. After planning, the hike folder holds only:
- `hike.yaml`, the single source
- `.osm/`, a disposable cache that is rebuilt from `route.osm_bbox`

Delete everything else you created while planning, wherever it is: candidate files, previews, saved router output, rendered images and notes in the scratchpad. Run `ls -A <slug>` to confirm.

**Done when:** `--check` prints CHECK OK, `hike.yaml` holds the full brief, the folder is clean, and you tell the user to run **/documentMyHike <slug>**.
