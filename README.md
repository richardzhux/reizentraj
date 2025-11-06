# reizentraj

Interactive trajectory tools for visualising Google Takeout location history.
The name “reizentraj” nods to my Dutch lessons with a beloved Northwestern professor—combining *reizen* (“to travel”) with “trajectory.”

## What’s Included
- `trajectory.py` / `python -m trajectory.cli` builds the deck.gl + MapLibre explorer with the full control surface: animated playback, exploration mode, draggable control panel, rainbow palette, basemap chooser, and the ✈️ flight overlay.
- `folium_trajectory.py` provides the lightweight Leaflet renderer. It shares the same CLI switches but skips the richer WebGL UI and flight arcs.
- `legacy_analysis.py` preserves earlier heatmaps, visited-state counters, and distance summaries. It is kept for reproducibility and is not actively maintained.

## Requirements
- Python 3.9 or newer
- Python packages: `folium`, `numpy`, `shapely`
- Optional packages (unlock travel stats in `trajectory.py`): `reverse_geocoder`, `pycountry`
- Optional (only for `legacy_analysis.py`): `geopandas`, `geopy`, and access to the shapefiles referenced inside the script

Install the core dependencies with:

```bash
python3 -m pip install folium numpy shapely
```

Install the optional travel-stat libraries when you want automatic country and US state summaries:

```bash
python3 -m pip install reverse_geocoder pycountry
```

## Preparing Google Takeout Data
1. Request your **Location History** archive from [Google Takeout](https://takeout.google.com/).
2. Extract the downloaded archive.
3. Note the path to the JSON file you plan to analyse (for example `Location History (Timeline)/Records.json`).

## Run the Deck Explorer
Generate an interactive trajectory explorer by pointing the script at your Takeout JSON file:

```bash
python3 trajectory.py --input "/path/to/Takeout/Records.json"
```

If you omit `--input`, the script offers the bundled `nov5.json` or prompts for your own export. A date-range prompt appears next; press **Enter** to accept the detected bounds or pre-fill them with `--start-date` / `--end-date`. Add `--no-prompt` whenever you want a fully non-interactive run.

Common CLI options (available in both deck.gl and Folium builds):
- `--output`: destination HTML file. Defaults to `trajectory_map.html`.
- `--start-date` / `--end-date`: limit the window (`YYYY-MM-DD` or `YYYYMMDD`). Works with interactivity disabled.
- `--jump-threshold-km`: treat any single hop longer than this as a discontinuity (default `50` km). See “Flight mode explained” for how this connects to flight detection.
- `--zoom`: initial zoom (deck.gl default `4`, Folium default `6`).
- `--map-style`: `Voyager`, `Positron`, `Dark Matter`, or a custom MapLibre style URL.
- `--exclude-no-fly-zones` / `--include-no-fly-zones`: bypass the prompt and force either behaviour.
- `--no-prompt`: accept all defaults and rely on CLI arguments.

Example with filtering and a tighter jump threshold:

```bash
python3 trajectory.py \
  --input "/path/to/Takeout/Records.json" \
  --start-date 2023-01-01 \
  --end-date 2023-12-31 \
  --jump-threshold-km 35 \
  --output reports/trajectory_2023.html
```

Open the generated HTML in your browser to play with the explorer.

## Deck Explorer Control Surface
Every control lives in the floating “Trajectory explorer” panel (drag it anywhere on screen or press **Minimize** to collapse it into a single button).

- `Play` (primary button): starts or pauses time animation. While playing, the timeline moves continuously; pause to inspect a moment.
- `Explore` (ghost button): switches to exploration mode. The trail becomes cumulative, always showing everything you have visited up to the current time. Turn it off to go back to a fading “recent history” view.
- Timestamp pill (`YYYY-MM-DD HH:MM:SS` input): reflects the active position. Type any timestamp within the dataset and press **Enter** to jump precisely; it snaps to the closest raw point.
- `Playback speed` select: chooses how quickly the timeline advances (1, 5, 10, 20, 50, 100, 500, or 1000 minutes of travel per real second). Use it to slow a dense city day or fast-forward through highway stretches.
- `🌈 Palette` toggle: swaps the default blue trail for a rainbow gradient. Rainbow mode colours older points warm and newer points cool, and the timeline slider picks up the same gradient for orientation.
- `Basemap` select: switches between the MapTiler Voyager, Positron, and Dark Matter styles (or your custom URL when provided on the CLI).
- `✈️ Flights` toggle: reveals long-haul hops as great-circle arcs. The button glows when active. See the detailed logic below, but in practice you can leave it off for road trips and turn it on when the path jumps continents.
- Timeline slider: scrub through the full time range. The handle shows your current position; drag to browse or to set the starting moment before you press **Play**.
- `Trail length` slider (1–48 hours): controls how much history remains visible behind the pig-head marker while exploration mode is off. Exploration mode ignores this slider and keeps the entire cumulative trail.
- Stat line: quick counts for countries, US states, custom regions, total points, temporal span (`T-Span`), and rendered distance (`D-Span`). These update immediately after the map loads.
- `Minimize` / `Trajectory explorer` buttons: collapse the panel to reclaim map space. Both the expanded panel and the collapsed button can be dragged; the position persists while the page is open.

Suggested workflow: scrub to your start moment, set the trail length (e.g. 6 hours), pick a palette, and hit **Play**. Adjust speed on the fly, toggle **Explore** when you want to see cumulative coverage, and switch basemaps or flights as needed.

## Flight Mode Explained
Flight detection is a three-stage process designed to keep the driving/cycling trail clean while still exposing inter-city leaps.

1. **Jump threshold (default 50 km):** As the coordinates load, every consecutive pair is measured. Any hop longer than the `--jump-threshold-km` value ends the active ground segment. Those oversized hops are not drawn as part of the drivable trail, and they do not contribute to `D-Span`. You can tighten or loosen this behaviour from the CLI.
2. **Candidate flights (≥100 km or ≥230 km):** Each discarded hop is reconsidered as a potential flight. If both endpoints fall inside the contiguous United States (24.5–49.5° N, −125 to −66° E), the hop needs to be at least **230 km** before it is labelled a flight. Elsewhere in the world the bar is **100 km**. These dual thresholds prevent fast intracity trips or regional trains from being misclassified while still surfacing medium-haul flights.
3. **UI overlay:** When you click the `✈️ Flights` toggle, every confirmed flight is rendered as a deck.gl `ArcLayer`. The arcs share the same timestamp domain, so they originate and land at the correct instants. You can keep the toggle off for pure surface travel or turn it on to contextualise the gaps between separated ground segments.

Because flights are treated as discontinuities, their distances remain excluded from the `D-Span` stat and from the visible Trips layer; they exist solely in the optional overlay. Adjusting `--jump-threshold-km` directly affects which hops are eligible. For example, setting it to `80` km may keep a long ferry ride inside the continuous trail and thus out of the flights overlay, whereas lowering it to `25` km will fragment dense downtown coverage but surface only the largest leaps as flights.

## Working with the Folium Variant
Run the pared-back Folium build whenever you want the lightweight Leaflet output instead of deck.gl:

```bash
python3 folium_trajectory.py --input "/path/to/Takeout/Records.json"
```

Both scripts accept identical CLI options; the only difference is the renderer. The Folium map keeps the standard Leaflet sidebar and TimestampedGeoJson control set, and it does not include the deck.gl control panel or flight overlay.

## Hosting & Extensibility
- The deck.gl explorer writes a single self-contained HTML file. Open it locally in any modern browser or serve it from static hosting.
- Streamlit users can embed the explorer with `streamlit.components.v1.html(output_html, height=...)`, or expose the JSON upload step in Streamlit and regenerate the HTML on the fly.
- Because the UI runs entirely in the browser, you can swap MapLibre styles, recolour the trips, add per-country annotations, or extend the JavaScript block inside `trajectory.py` with additional layers (waypoints, heatmaps, flight duration labels, etc.).

## Legacy Script
`legacy_analysis.py` contains the older exploratory notebooks (heatmaps, visited state trackers, distance summaries). The code is preserved for reproducibility but is no longer cleaned up or parameterised. Expect to adjust the hard-coded file paths before running those sections.

## Contributing
Issues and pull requests are welcome. Please prefer updates to the modern `trajectory` package and keep the legacy script intact unless you are fixing a clear bug. Feel free to add automated tests or linting configurations that fit your workflow.
