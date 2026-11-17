# hikeBuilder

Claude Code skills for planning a **scout checkpoint hike** in Great Britain and producing its paperwork.

- **`/planAHike`** asks you about the area, distance, section, teams and toilet stop. It then designs a route on bridleways using OpenStreetMap data, checks it against your editable planning rules, and opens a **route preview PDF** (map, checkpoint table, rule breaches, pre-walk checks) for you to approve. The approved hike is saved as a single `hike.yaml`.
- **`/documentMyHike`** turns that `hike.yaml` into:
  - **a leader pack PDF:** checkpoint table with 6-figure grid refs, leg-by-leg directions, a contour map, opening and closing times for staggered starts, safety and kit notes, and Street View photos of each checkpoint
  - **a one-page team card**
  - **an event risk assessment PDF**: your group's base risk assessment (kept privately in the workspace as `risk-assessment.yaml`) plus the hazards unique to the route
  - **a GPX file** for OS Maps
- **`/publishHikes`** (optional) publishes every documented hike to a small password-protected website on AWS Amplify Hosting, so other leaders can view the routes and download the packs. It needs the AWS CLI and a one-off setup described in [`skills/publishHikes/SKILL.md`](skills/publishHikes/SKILL.md).

The planning rules include toilets at halfway, no walking along roads, bridleways preferred, checkpoints a leader can drive to, and extra checkpoints where teams could get lost. They live in [`hike-kit/rules.md`](hike-kit/rules.md). The wording and layout of the documents is set in [`hike-kit/documentation-style.md`](hike-kit/documentation-style.md). Both files are yours to edit.

## How it fits together

```
hikeBuilder/            <- this repo (public)
  skills/planAHike/  skills/documentMyHike/  skills/publishHikes/
  hike-kit/             tools, rules, style spec, templates, worked example
  install.sh

~/hiking/               <- your workspace (private, never pushed)
  .claude/skills/*  -> symlinks to hikeBuilder/skills/*
  hike-kit          -> symlink to hikeBuilder/hike-kit
  .env                  your API keys (mode 600)
  known-huts.yaml       scout huts you can use
  <hike-name>/          one folder per hike: hike.yaml + its PDFs, GPX, map, photos
```

Your keys, huts and hikes stay in the workspace. A `git pull` in this repo updates every workspace linked to it.

## Install

### 1. System requirements

- [Claude Code](https://claude.com/claude-code)
- Python 3 with **PyYAML** and **Pillow**
- **LibreOffice** (`soffice`), used headless to make the PDFs
- **poppler-utils** (`pdfunite`, `pdfseparate`, `pdftotext`, `pdfinfo`)
- **fontconfig** and the **Liberation Sans** font

| Platform | Install command |
|---|---|
| Fedora | `sudo dnf install python3-pyyaml python3-pillow libreoffice-writer poppler-utils liberation-sans-fonts fontconfig` |
| Debian / Ubuntu | `sudo apt install python3-yaml python3-pil libreoffice-writer poppler-utils fonts-liberation fontconfig` |
| macOS (Homebrew) | `brew install poppler fontconfig && brew install --cask libreoffice font-liberation && pip3 install pyyaml pillow` |

### 2. Clone and link into a workspace

```sh
git clone https://github.com/scottejames/hike-builder-skills.git ~/projects/hikeBuilder
~/projects/hikeBuilder/install.sh ~/hiking     # the workspace folder; created if missing
```

`install.sh` links the skills and kit into the workspace and creates your private `.env` and `known-huts.yaml`. It also checks the requirements. Run it again at any time; it never overwrites your own files.

### 3. Add your API keys

Edit `~/hiking/.env`. This is the only place keys are kept.

| Key | Needed for | Get one |
|---|---|---|
| `GOOGLE_MAPS_API_KEY` | Street View photos and coverage checks (refconv) | Google Cloud console: enable **Street View Static API**. Images are billed per request; the coverage check is free |
| `OS_API_KEY` | UK place search (os-maps, optional) | [OS Data Hub](https://osdatahub.os.uk/) (OS Names API) |

### 4. Install the MCP servers

Claude Code calls the servers by name, so **register them with exactly the names shown**. Servers that need keys are started through `hike-kit/bin/with-env.sh`, which loads `~/hiking/.env`. Keys never go into `~/.claude.json` or into the server's own folder.

#### Required

| Name to register | Repository | Used for | API key |
|---|---|---|---|
| `osm-nic` | [github.com/ni-c/osm-mcp](https://github.com/ni-c/osm-mcp) | Geocoding the start, scout huts near the route (`club=scout`), reverse geocoding, and walking-route cross-checks | none |
| `refconv` | [github.com/scottejames/RefConvMCP](https://github.com/scottejames/RefConvMCP) | OS grid reference conversion, Street View coverage checks and photos | `GOOGLE_MAPS_API_KEY` |

```sh
# osm-nic (published on npm)
claude mcp add -s user osm-nic -- npx -y osm-mcp

# refconv: clone it and follow its README to install (uv), but skip its .env step
git clone https://github.com/scottejames/RefConvMCP.git ~/projects/mcp/RefConvMCP
claude mcp add -s user refconv -- ~/hiking/hike-kit/bin/with-env.sh ~/hiking/.env ~/projects/mcp/RefConvMCP/run.sh
```

#### Optional

| Name to register | Repository | Used for | API key |
|---|---|---|---|
| `os-maps` | [github.com/mgrinstein/os-maps-mcp](https://github.com/mgrinstein/os-maps-mcp) | Ordnance Survey place-name search for UK villages, farms and hills | `OS_API_KEY` |

```sh
git clone https://github.com/mgrinstein/os-maps-mcp.git ~/projects/mcp/os-maps-mcp
# install its dependencies into ~/projects/mcp/os-maps-mcp/.venv as its README describes, then:
claude mcp add -s user os-maps -- ~/hiking/hike-kit/bin/with-env.sh ~/hiking/.env \
    ~/projects/mcp/os-maps-mcp/.venv/bin/python ~/projects/mcp/os-maps-mcp/server.py
```

#### Not needed

These were tried during development. The skills don't depend on them:

- **[vemonet/openroute-mcp](https://github.com/vemonet/openroute-mcp):** foot-hiking routing works, but each call returns about 25k tokens and `search_pois` fails. The kit's own router replaces it.
- **[jagan-shanmugam/open-streetmap-mcp](https://github.com/jagan-shanmugam/open-streetmap-mcp):** its OSRM "foot" routing returns car routes. Its Overpass calls also fail with HTTP 406 because they send no User-Agent.

Run `claude mcp list` to check that the servers show **Connected**.

### 5. Use it

```sh
cd ~/hiking && claude
> /planAHike
> /documentMyHike <hike-name>
> /publishHikes                # optional: update the leaders' website
```

To try the worked example, copy `hike-kit/examples/ditchling-stanmer.yaml` to `~/hiking/ditchling-stanmer/hike.yaml` and run `/documentMyHike ditchling-stanmer`.

## Data sources and licences

- **Paths and facilities:** © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors (ODbL), downloaded from the public Overpass API. Downloads are cached per hike and limited to occasional requests; please keep it that way.
- **Map tiles:** © [OpenTopoMap](https://opentopomap.org) (CC-BY-SA), cached locally under `hike-kit/.tilecache/`. Follow their tile usage policy.
- **Street View images:** © Google and photo contributors, fetched with your own key under Google's terms. They stay in your workspace and are not part of this repo.
- **Data accuracy:** routes and facilities come from community data. **Pre-walk every route.** The leader pack lists everything that still needs checking on the pre-walk.

## Licence

[MIT](LICENSE). The licence covers the code and documents in this repo. The map, OpenStreetMap and Street View data the tools download stay under their own licences (see above).
