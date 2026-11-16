# Hike kit

The tools, rules and templates behind the **/planAHike** and **/documentMyHike** skills. For installation and the MCP servers they need, see the [project README](../README.md).

- **/planAHike** interviews you, designs and checks a route, shows you a route preview, then writes `<workspace>/<slug>/hike.yaml`.
- **/documentMyHike** reads a `hike.yaml` and builds the leader pack PDF, the team card, a GPX file, the map and, if enabled, Street View photos.

## Files you edit

| File | What it controls |
|---|---|
| `rules.md` | Planning rules (MUST / SHOULD) and the numbers the scripts use: paces, leg times, toilet window, opening and closing margins |
| `documentation-style.md` | Exactly what the documents contain and how they're worded |
| `<workspace>/known-huts.yaml` | Scout huts you have access to (started from `known-huts.example.yaml`; kept out of the repo) |
| `hike-template.yaml` | The `hike.yaml` format, annotated |

## Tools (`tools/`)

| Script | Purpose |
|---|---|
| `osm_fetch.py --around LAT,LON --radius-km 4 --out DIR/.osm [--refresh]` | Fills the OSM cache from Overpass, with mirrors and retries. It re-fetches when the cache is missing, stale, or covers a different area |
| `facilities.py DIR/.osm` | Lists scout huts, toilets, parking, cafés and water, plus points where bridleways meet roads, with grid refs |
| `plan_route.py DIR/.osm "START@..;CP1@..;FINISH@.." --junctions` | Bridleway-preferring router. Reports legs, surfaces, decision points and lost-risk. Saves nothing |
| `render_map.py DIR/.osm "points" out.png` | Quick contour map of a set of routing points |
| `preview.py DIR candidate.yaml --open` | 2-page route preview PDF (table, breaches, pre-walk checks, map) shown before any route decision |
| `osgb.py LAT,LON` | 6-figure OS grid reference |
| `build_docs.py DIR [--check] [--refresh-osm]` | Re-routes from `hike.yaml`, validates it, and builds all outputs |
| `bin/with-env.sh ENV_FILE CMD...` | Starts an MCP server with keys from your workspace `.env` (see `env.example`) |

## Rebuilding a hike by hand

```
python3 hike-kit/tools/build_docs.py <slug> --check
python3 hike-kit/tools/build_docs.py <slug>
```

Map tiles are cached in `hike-kit/.tilecache/`. The cache is safe to delete.

## Worked example

`examples/ditchling-stanmer.yaml` is a complete 9.4 km hike on the South Downs. To build it, copy it to `<workspace>/ditchling-stanmer/hike.yaml` and run `build_docs.py ditchling-stanmer`. The OSM cache is fetched automatically. Street View is enabled in the example, so either fetch the photos with /documentMyHike or set `streetview.enabled: false`.

## What lives in a hike folder

Keep only material a person adjusts or reads:
- **`hike.yaml`:** the single source. The route line is re-routed from `route.routing_points` on every run and is never stored.
- **`streetview/`:** fetched photos, which cost money to re-fetch.
- **`.osm/`:** a disposable OpenStreetMap cache, re-fetched from `route.osm_bbox` when it's missing, older than `osm_cache_max_age_days`, or covers a different area.
- **Outputs:** the leader pack PDF, the team card PDF, the GPX file and the map PNG.

