# Hike planning rules

Edit this file to change how hikes are planned and checked. **planAHike** applies every rule when it designs a route. **documentMyHike** re-checks the measurable ones and warns about breaches in the leader pack.

Rules marked **MUST** block a plan. Breaking one needs your explicit OK, and that OK is recorded in the YAML under `brief.exceptions`. Rules marked **SHOULD** are strong preferences: the planner explains any breach when it proposes the route.

## Settings (read by the scripts)

The scripts read the numbers in the block below. Per-hike values in `hike.yaml` override them.

```yaml
pace:
  planning_kmh: 4          # timing used for leg times on every document
  fastest_kmh: 5           # earliest-arrival prediction (checkpoint opening)
  slowest_kmh: 3           # latest-arrival prediction (checkpoint closing)
leg_target_min: [40, 50]   # guide spacing between checkpoints at planning pace
leg_hard_max_min: 65       # any leg longer than this needs a via checkpoint or your OK
toilet_window_pct: [35, 65]  # the toilet checkpoint must fall in this % of total distance
open_before_first_min: 30  # open each checkpoint this long before the fastest team could arrive
close_after_last_min: 15   # close this long after the slowest, last-starting team is due
toilet_stop_min: {min: 0, max: 30}  # shortest / longest stop a team makes at the toilet CP
distance_tolerance_pct: 10 # route length may differ from the request by this much
osm_cache_max_age_days: 90 # re-fetch a hike's OpenStreetMap cache when older than this
significant_road_classes: [trunk, primary, secondary, tertiary]  # OSM highway classes that count as a significant road (rule 23)
crossing_cover_m: 100      # a checkpoint leader or marshal supervises a crossing only within this distance of it
section_defaults:
  Scouts:    {planning_kmh: 4,   fastest_kmh: 5,   slowest_kmh: 3,   distance_km: [6, 12]}
  Cubs:      {planning_kmh: 3,   fastest_kmh: 4,   slowest_kmh: 2.5, distance_km: [4, 8]}
  Explorers: {planning_kmh: 4.5, fastest_kmh: 6,   slowest_kmh: 3.5, distance_km: [10, 20]}
```

## Route

1. **MUST: toilet at halfway.** A checkpoint with toilets the teams can use falls inside `toilet_window_pct` of the total distance. Valid toilets are public toilets, a scout hut you have access to, or a café or pub you have confirmed will let teams use them. Record the source of the toilet in the checkpoint's `location`.
2. **MUST: no walking along roads.** Teams walk on bridleways, byways, tracks and paths. Road crossings are allowed, and each one is named in the leg directions with "cross … together". Significant road crossings also need an adult supervising (rule 23). The only on-road walking allowed is a short lane through a village or estate (up to about 500 m in total), and the summary states it.
3. **SHOULD: prefer bridleways.** Aim for 70% or more of the distance on bridleway or byway. They are wider, better signed and easier to follow than footpaths.
4. **SHOULD: obvious paths.** Choose the line with the fewest decision points. A main track with side paths is better than a web of small paths.
5. **SHOULD: a circular route** that starts and finishes at the same place with parking, unless the brief asks for a linear route.
6. **SHOULD: avoid repeating the same path.** Crossing your own route is fine.
7. Distance stays within `distance_tolerance_pct` of the requested distance.

## Road crossings

23. **MUST: every significant road crossing has its own crossing marshal.** A significant road is any road in `significant_road_classes` (A roads, B roads and the main C roads), plus any other road you add after the pre-walk. Wherever the route crosses, joins or walks along one, a dedicated adult marshal (M1, M2 …) stands within `crossing_cover_m` of the crossing and sees teams across. A checkpoint leader does not double up as the marshal, even when the crossing is at their checkpoint.
    - `build_docs.py --check` finds every contact with a significant road from the map data. Each one needs a `road_crossings` entry naming its marshal, or, where teams stay on a pavement and never cross, a `no_crossing` reason to confirm on the pre-walk.
    - Every marshal is one person on the staffing sheet, so prefer routes that cross fewer significant roads. Marshals get in-place times and map markers, like checkpoints.
    - The risk assessment lists every crossing and who supervises it.

## Checkpoints

8. **MUST: 6-figure grid references.** Every checkpoint, turn point and start or finish is given as a 6-figure OS grid reference in the form `TQ 333 129`, with letters, space, 3 digits, space, 3 digits. Compute it from coordinates with `tools/osgb.py` or the refconv MCP. Never estimate one by eye.
9. **SHOULD: vehicle access.** Each checkpoint sits where a leader can drive and park: a car park, a village street, or a bridleway that meets a public road (see `facilities.py`, ROAD ACCESS). If a checkpoint is on foot only, its `access` field says how far the walk is and from where.
10. **SHOULD: spacing.** Legs fall in `leg_target_min` at planning pace. Treat this as a guide: the location matters more than the minutes. Any leg over `leg_hard_max_min` needs a via checkpoint or your OK.
11. **SHOULD: via checkpoints where teams could get lost.** Review the LOST-RISK output from `plan_route.py --junctions`. Consider a via checkpoint (it may be on foot only) at:
    - a junction the route passes twice, where teams must leave a different way each time
    - a leg with 5 or more turns
    - sharp turns, or legs mostly on unsigned paths
    - a junction where several similar tracks meet
12. **Shared checkpoints.** One leader may cover a location the route visits twice. Those checkpoints get separate IDs (for example CP1 and CP3) and `shared_with`. Their `leader_notes` explain how to tell the visits apart, by arrival direction and which grid reference to hand out.
13. **Next grid reference.** Each checkpoint gives teams the grid reference of the next checkpoint only. The team card shows only the start.

## Resources

14. **Scout huts** are first-choice resources for the start/finish (parking, shelter, toilets), the toilet checkpoint, and vehicle-accessible checkpoints. Check `known-huts.yaml` (in your workspace) first: those are huts you have access to. Huts found in OpenStreetMap (`club=scout`) are only candidates until you confirm access, and the planner asks you before relying on one.
15. Café and pub toilets count only if you confirm that teams can use them.

## Timing

16. Opening time is the earliest the fastest team could arrive (first team, `fastest_kmh`, shortest toilet stop) minus `open_before_first_min`.
17. Closing time is when the slowest team is due (last team to start, `slowest_kmh`, longest toilet stop) plus `close_after_last_min`.
18. A checkpoint that can only be reached on foot needs its leader to leave early enough to walk in. The leader notes give the walk-in time.

## Data and tools

19. Facts come from data: OSM (via `osm_fetch.py` or the MCPs), Street View, or you. Anything unverified (parking, toilet opening hours and public access, pavements, private lanes, gates) goes on the **pre-walk check list**. Every route is pre-walked, so the planner records these items rather than asking about them. The leader pack marks them "check on the pre-walk".
21. **Preview before decisions.** No route question is asked until the user has the route preview PDF open, with the map, checkpoint table, rule breaches and pre-walk checks (`tools/preview.py`).
20. Plans must be cross-checked: at least one leg is compared with an independent router (osm-nic `route` with profile foot). Every location with vehicle access is checked on Street View before you sign off.
22. **Clean up.** After planning or documenting, remove every temporary file: trial tracks, candidate files, previews, scratch renders and fetched Street View originals. Keep only material a person adjusts or reads; never store anything that can be regenerated from `hike.yaml`, such as the route line. A hike folder holds only `hike.yaml`, `streetview/`, the `.osm/` cache and the final outputs.
