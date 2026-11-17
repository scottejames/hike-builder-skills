# Hike documentation style

This file defines exactly what **documentMyHike** produces and how it's written. `tools/build_docs.py` builds the layout from `hike.yaml`. The wording rules below apply to every text field in `hike.yaml`. That covers checkpoint locations, access notes, leader notes and leg directions, so the wording is right before the build runs. Edit this file to change the documents. If you change the page structure, update `build_docs.py` to match.

## Outputs (in the hike folder)

| File | Contents | Pages |
|---|---|---|
| `<slug>_leader_pack.pdf` | The leader pack, described below | 5 (4 without Street View; +1 when leg directions need 2 pages) |
| `<slug>_team_card.pdf` | One card. Print one per team | 1 |
| `<slug>_risk_assessment.pdf` | Event risk assessment: the group's base hazards plus this route's own risks (needs `risk-assessment.yaml` in the workspace) | 3–4, landscape |
| `<slug>.gpx` | Route track, checkpoints and turn points, for OS Maps import | – |
| `<slug>_map.png` | Contour map with checkpoint and turn markers | – |
| `streetview/` | 4 Street View images per checkpoint location (N, E, S, W) | – |

## Leader pack, page by page

1. **Checkpoints.** The page has, in order:
   - **Title:** "Scout Hike: <name>".
   - **Summary line:** area · distance in km (and miles) · circular or linear · bridleway % · road statement · which CP has the toilets · OS map.
   - **Checkpoint table:** CP · Grid ref · Location · Access for leaders · Leg · Leg time · Running total · Give team. The toilet row is shaded yellow and shared checkpoints are shaded blue. A total row ends the table.
   - **Timing note:** one line explaining the pace and the climb allowance.
   - **Leader-note boxes:** one blue box for each shared or foot-only checkpoint.
   - **Road crossings box:** every significant road crossing with grid ref, km, who supervises it (checkpoint leader or marshal), the marshal's in-place time and parking (rule 23).
   - **Verification box:** one orange box saying how the route was checked and what still needs checking on the day.
2. **Leg directions.** One page if it fits at 8.2 pt or larger, otherwise two pages (the pack then has 6 pages). One table per leg, with columns Point · Grid ref · km · Instruction. Each leg heading reads "Leg n: FROM → TO · x.x km · nn min · effort".
3. **Map.** The full-page map, with a caption naming each marker.
4. **Safety, kit, emergency, opening and closing times, checkpoint log.** Two columns. Safety, kit and emergency go on the left. Opening and closing times and the log go on the right.
5. **Street View photos.** One row per location: 4 images, looking N, E, S and W, each row with a title and the capture date and source. This page is included only when `streetview.enabled` is true.

Each section must fit its pages. The build script shrinks the font, down to a 7.8 pt minimum, before it lets a section overflow, and it reports any section that still overflows.

## Risk assessment (landscape)

- **Source:** the workspace `risk-assessment.yaml` (the group's base event RA, private) merged with the hike's `risk_assessment:` section. Built by `tools/risk_assessment.py`, which `build_docs.py` calls.
- **Header:** title, a route summary line with the nearest A&E, and boxes for person doing the RA, date, next review, event date and pre-walk date (blank when not set, to fill in by hand).
- **Event hazards:** every base hazard with who is at risk and its controls. The fourth column holds this route's notes (`changes.<hazard id>`), shaded yellow, pointing to the route risks.
- **Route-specific risks:** numbered R1, R2 and so on: hazard, who is at risk, controls. Name the place, the leg and the checkpoint. Cover roads walked and crossed, water, railways, foot-only checkpoints, exposure, steep ground, livestock, distance, and anything on the pre-walk list that affects safety.
- **Sign-off:** Leader in Charge, signature and date.

## Team card (1 page)

- **Header:** title "<name>: Team card", with boxes for team name, team members and start time.
- **Start:** "START: <start name>, <grid ref>". This is the only route information on the card.
- **How it works:** "At each checkpoint the leader gives you the grid reference of the next one. Plot it, plan your route, then go."
- **Log table:** one row per checkpoint, with columns CP · Grid ref given to you · Time in · Time out · Leader initials. The rows are numbered but not named, so the card gives nothing away.
- **Kit list and safety rules:** in general terms, such as "you will cross roads: stop, gather, cross together".
- **Emergency:** 999, plus boxes for the leaders' phone numbers.
- **No map, route line, checkpoint names or directions.**

## Wording rules

- **Grid references:** always 6-figure, written `TQ 333 129` in bold monospace and never split across lines. A grid reference stands alone as an identifier; don't write "GR".
- **Distances:** km to 1 decimal place in tables. Summaries give km and miles, e.g. "9.4 km (5.9 miles)". Metres for anything under 1 km in directions, e.g. "about 150 m ahead".
- **Times:** leg times in whole minutes, e.g. "46 min". Running and planned times as h:mm offsets, e.g. "+0:46", or clock times once `teams.first_start` is set. Use the 24-hour clock.
- **Directions:** each instruction starts with a verb ("Turn", "Bear", "Follow", "Cross", "Take"). Turn words and compass words are in capitals and bold, e.g. **LEFT**, **RIGHT**, **STRAIGHT OVER**, **NORTH**. Name what teams will see: track type, woods, farm buildings, signs. Give one action per row, plus at most one "ignore side paths" note.
- **Road crossings:** always written as "**Cross <road name> together**", and repeated in the safety notes. At a significant road, say who supervises: "with marshal **M1**" or "watched by the CP3 leader".
- **Checkpoint location:** what the place is, plus the facilities there. Toilets in bold.
- **Access for leaders:** which road to arrive by and where to park. For a checkpoint reachable only on foot, start with "**On foot only:**" and give the walk-in distance and time from the nearest parking.
- **Uncertainty:** anything not confirmed by data or by the user ends with "check on the pre-walk". Every route is pre-walked, and the verification box lists these pre-walk checks. Never state opening hours, parking or gate details that haven't been verified.
- **Language:** British English, written plainly for adult leaders. Team cards are written for 10–14 year olds: short sentences, "you", no jargon.

## Colours and type

- **Body:** Liberation Sans 9.4 pt, which the build may shrink to 7.8 pt to fit. Headings are dark green, #2d5a27.
- **Shading:** toilet checkpoint #fff4c7 · shared or foot-only checkpoint #e8f0fb · verification box #fff7ed · total row #eeeeee.
- **Map markers:** start/finish green · toilet checkpoint orange · other checkpoints blue · crossing marshals purple (M1, M2 …) · turns white circles labelled T1, T2 and so on.
