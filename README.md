# reizentraj

Interactive trajectory tools for visualising Google Takeout location history.
The name “reizentraj” nods to my Dutch lessons with a beloved Northwestern professor—combining *reizen* (“to travel”) with “trajectory.”

## Overview
- `trajectory.py` builds a high-performance deck.gl + MapLibre explorer. It renders animated trips with a timeline slider, play/pause controls, exploration (cumulative) mode, and the signature pig-head marker. Use it when you want the richer UI and WebGL rendering.
- `folium_trajectory.py` keeps the classic Folium map flow: simple HTML output with the standard Leaflet controls. By default it offers to strip coordinates in protected regions (Chicago/Evanston and metropolitan Beijing); override the prompt with `--exclude-no-fly-zones` or `--include-no-fly-zones`.
- `legacy_analysis.py` preserves earlier exploratory routines (heatmaps, visited-state counters, distance summaries). It is kept for reference and is not actively maintained.

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

## Usage
Generate an interactive trajectory explorer by pointing the script at your Takeout JSON file:

```bash
python3 trajectory.py --input "/path/to/Takeout/Records.json"
```

The script inspects the data range and, by default, prompts for a start and end date in `YYYYMMDD` format. Press Enter to accept the earliest or latest available date. Set `--no-prompt` to disable the interactive questions (handy for automation).
If you run the script without `--input`, it will offer to use the bundled `nov5.json` file (or prompt interactively for a path if you prefer another export).

Key options (`trajectory.py` and `folium_trajectory.py` share the same CLI):
- `--output`: HTML destination for the map (`trajectory_map.html` by default).
- `--start-date` / `--end-date`: pre-fill the interactive prompt or set the range directly (`YYYY-MM-DD` or `YYYYMMDD`).
- `--jump-threshold-km`: discard point-to-point hops above this distance (defaults to 50 km).
- `--zoom`: initial zoom level for the map (deck.gl defaults to 4 for continental US coverage; the Folium build keeps its original default of 6).
- `--map-style`: choose `Voyager`, `Positron`, `Dark Matter`, or supply a custom MapLibre style URL.
- `--exclude-no-fly-zones`: force removal of the protected regions without prompting.
- `--include-no-fly-zones`: keep the protected regions without prompting.
- `--no-prompt`: skip all interactive prompts (date range and no-fly zones) and rely entirely on CLI values.

Example with filtering:

```bash
python3 trajectory.py \
  --input "/path/to/Takeout/Records.json" \
  --start-date 2023-01-01 \
  --end-date 2023-12-31 \
  --jump-threshold-km 35 \
  --output reports/trajectory_2023.html
```

Open the generated HTML file in your browser to explore the interactive map. The deck.gl build comes with:
- A full-width timeline slider, play/pause control, and new playback presets ranging from 1 to 1000 minutes of travel per real second.
- The timestamp pill is editable—enter any `YYYY-MM-DD HH:MM:SS` within the data range to jump directly.
- A basemap selector (Voyager, Positron, Dark Matter) beside the speed control.
- A pig-head marker that hugs the active position along the path.
- An **Exploration mode** toggle that draws the travelled route cumulatively as you scrub the timeline.
- Adjustable trail length (in hours) when Exploration mode is off.
- A palette toggle switches between the classic blue trip style and a rainbow gradient that colors older points warm (reds) and newer points cool (purples); the timeline slider reflects the chosen palette.
- Stats include `T-Span` (temporal coverage) and `D-Span` (total kilometres travelled) for quick reporting. `D-Span` only sums distances that actually render on the map. Example edge cases:
  - Points inside configured no-fly zones (e.g., Northwestern campus) are removed entirely, so the mileage excludes time spent there; you’ll see the segment resume at the edge of the box.
  - Any hop longer than the jump threshold (50 km by default) is discarded—long-haul flights appear as disconnected points, and their distance is not counted.
  - GPS gaps that produce missing points simply break the segment; only the legs with valid data contribute to the total.

When the optional dependencies are installed, the script prints a travel summary after building the map. The summary lists the number of visited countries, their last recorded entry dates, and—if applicable—the count of US states plus their last entry dates.

Apply the built-in no-fly filtering whenever you share maps or stats more broadly:

```bash
python3 trajectory.py --exclude-no-fly-zones
```

Just like any other run, omitting `--input` falls back to `nov5.json` or prompts for a file path when you are running interactively.

Use `--include-no-fly-zones` when scripting and you want to bypass the question while keeping those points.

## Working with the Folium variant
Run the pared-back Folium build whenever you want the lightweight Leaflet output instead of deck.gl:

```bash
python3 folium_trajectory.py --input "/path/to/Takeout/Records.json"
```

Both scripts accept identical CLI options; the only difference is the renderer. The Folium map keeps the standard Leaflet sidebar and TimestampedGeoJson control set.

## Hosting & Extensibility
- The deck.gl explorer writes a single self-contained HTML file. Open it locally in any modern browser or serve it from static hosting.
- Streamlit users can embed the explorer with `streamlit.components.v1.html(output_html, height=...)`, or expose the JSON upload step in Streamlit and regenerate the HTML on the fly.
- Because the UI runs entirely in the browser, you can swap MapLibre styles, recolour the trips, or add additional layers (waypoints, heatmaps) by extending the JavaScript block inside `trajectory.py`.

## Legacy Script
`legacy_analysis.py` contains a collection of experimental analyses (heatmaps, visited state trackers, distance summaries). The code is preserved for reproducibility but is no longer cleaned up or parameterised. Expect to adjust the hard-coded file paths before running those sections.

## Contributing
Issues and pull requests are welcome. Please prefer updates to `trajectory.py` and keep the legacy script intact unless you are fixing a clear bug. Feel free to add automated tests or linting configurations that fit your workflow.
