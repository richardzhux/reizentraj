import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from string import Template
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from shapely.geometry import LineString
from shapely.ops import unary_union

try:
    import reverse_geocoder  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    reverse_geocoder = None

try:
    import pycountry  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    pycountry = None


DEFAULT_OUTPUT_NAME = "trajectory_deck.html"
DEFAULT_INPUT_FILE = Path(__file__).resolve().parent / "nov5.json"
DEFAULT_MAP_STYLE = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"


LOCAL_TZ = datetime.now().astimezone().tzinfo


@dataclass(frozen=True)
class Coordinate:
    latitude: float
    longitude: float
    timestamp: datetime

    @property
    def as_latlon(self) -> Tuple[float, float]:
        return (self.latitude, self.longitude)

    @property
    def as_lonlat(self) -> Tuple[float, float]:
        return (self.longitude, self.latitude)


@dataclass(frozen=True)
class RegionVisit:
    identifier: str
    label: str
    last_seen: datetime


@dataclass(frozen=True)
class LocationStats:
    countries: Sequence[RegionVisit]
    us_states: Sequence[RegionVisit]


@dataclass(frozen=True)
class NoFlyZone:
    name: str
    min_lat: float
    min_lon: float
    max_lat: float
    max_lon: float

    def contains(self, latitude: float, longitude: float) -> bool:
        return self.min_lat <= latitude <= self.max_lat and self.min_lon <= longitude <= self.max_lon


NO_FLY_ZONES: Sequence[NoFlyZone] = (
    NoFlyZone(
        name="Chicago & Evanston",
        min_lat=41.6,
        max_lat=42.1,
        min_lon=-87.95,
        max_lon=-87.5,
    ),
    NoFlyZone(
        name="Beijing",
        min_lat=39.4,
        max_lat=40.3,
        min_lon=115.5,
        max_lon=117.5,
    ),
)


HTML_TEMPLATE = Template(
    """<!DOCTYPE html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Trajectory Explorer</title>
    <link rel=\"stylesheet\" href=\"https://unpkg.com/maplibre-gl@2.4.0/dist/maplibre-gl.css\" />
    <style>
      :root {
        color-scheme: light dark;
      }
      body {
        margin: 0;
        padding: 0;
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: #0f172a;
        color: #e2e8f0;
      }
      #controls {
        position: absolute;
        z-index: 10;
        top: 16px;
        left: 50%;
        transform: translateX(-50%);
        background: rgba(15, 23, 42, 0.85);
        backdrop-filter: blur(8px);
        border-radius: 12px;
        box-shadow: 0 12px 30px rgba(15, 23, 42, 0.45);
        padding: 18px 22px;
        width: min(720px, 94vw);
      }
      #controls h1 {
        font-size: 1.15rem;
        margin: 0 0 12px;
        letter-spacing: 0.02em;
      }
      #controls section {
        display: flex;
        flex-wrap: wrap;
        gap: 12px 18px;
        align-items: center;
        margin-bottom: 12px;
      }
      #controls label {
        font-size: 0.85rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.08em;
      }
      #controls input[type=\"range\"] {
        flex: 1 1 220px;
      }
      #controls button,
      #controls select {
        font-size: 0.9rem;
        border-radius: 999px;
        border: none;
        padding: 8px 18px;
        font-weight: 600;
        cursor: pointer;
        transition: transform 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
      }
      #controls button.primary {
        background: linear-gradient(135deg, #38bdf8, #6366f1);
        color: #0f172a;
        box-shadow: 0 8px 20px rgba(56, 189, 248, 0.35);
      }
      #controls button.primary:hover {
        transform: translateY(-1px);
        box-shadow: 0 16px 32px rgba(99, 102, 241, 0.45);
      }
      #controls button.ghost {
        background: rgba(148, 163, 184, 0.12);
        color: #e2e8f0;
      }
      #controls button.ghost.active {
        background: rgba(244, 114, 182, 0.3);
        color: #fdf2f8;
        box-shadow: inset 0 0 8px rgba(244, 114, 182, 0.35);
      }
      #controls button.ghost:hover {
        transform: translateY(-1px);
      }
      #controls .statline {
        margin-top: 8px;
        font-size: 0.85rem;
        opacity: 0.85;
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
      }
      #deck-container {
        position: absolute;
        inset: 0;
      }
      #time-label {
        font-feature-settings: "tnum";
        font-variant-numeric: tabular-nums;
        padding: 6px 12px;
        border-radius: 999px;
        background: rgba(148, 163, 184, 0.16);
      }
      @media (max-width: 640px) {
        #controls {
          top: 8px;
          padding: 14px;
          border-radius: 10px;
        }
        #controls section {
          gap: 10px 12px;
        }
      }
    </style>
  </head>
  <body>
    <div id=\"controls\">
      <h1>Trajectory explorer</h1>
      <section>
        <button id=\"play-toggle\" class=\"primary\" type=\"button\">Play</button>
        <button id=\"exploration-toggle\" class=\"ghost\" type=\"button\">Exploration mode</button>
        <label for=\"time-slider\">Timeline</label>
        <input id=\"time-slider\" type=\"range\" min=\"0\" max=\"1\" step=\"60\" value=\"0\" />
        <span id=\"time-label\"></span>
      </section>
      <section>
        <label for=\"trail-slider\">Trail length (hours)</label>
        <input id=\"trail-slider\" type=\"range\" min=\"1\" max=\"48\" step=\"1\" value=\"1\" />
        <label for=\"speed-select\">Playback speed</label>
        <select id=\"speed-select\">
          <option value=\"300\">5x</option>
          <option value=\"120\">2x</option>
          <option value=\"60\" selected>1x</option>
          <option value=\"30\">0.5x</option>
        </select>
      </section>
      <div class=\"statline\">
        <div>${country_count} countries</div>
        <div>${state_count} US states</div>
        <div>Points: ${point_count}</div>
      </div>
    </div>
    <div id=\"deck-container\"></div>

    <script src=\"https://unpkg.com/maplibre-gl@2.4.0/dist/maplibre-gl.js\"></script>
    <script src=\"https://unpkg.com/deck.gl@8.9.27/dist.min.js\"></script>
    <script src=\"https://unpkg.com/@deck.gl/mapbox@8.9.27/dist.min.js\"></script>
    <script>
      const tripsData = ${deck_data};
      const timeline = ${timeline};
      const initialViewState = ${initial_view_state};
      const mapStyle = "${map_style}";

      const state = {
        currentTime: 0,
        playing: false,
        exploration: false,
        trailLength: 3600,
        lastFrameTs: null,
        speedFactor: 60, // seconds per real second
      };

      const slider = document.getElementById('time-slider');
      const trailSlider = document.getElementById('trail-slider');
      const label = document.getElementById('time-label');
      const playToggle = document.getElementById('play-toggle');
      const explorationToggle = document.getElementById('exploration-toggle');
      const speedSelect = document.getElementById('speed-select');

      slider.max = timeline.duration;
      slider.step = Math.max(60, Math.floor(timeline.duration / 1000));
      slider.value = 0;
      trailSlider.value = 1;
      label.textContent = formatTime(timeline.start + state.currentTime);

      const deckgl = new deck.DeckGL({
        container: 'deck-container',
        map: maplibregl,
        mapStyle,
        controller: true,
        initialViewState,
        layers: createLayers(),
      });

      function formatTime(epochSeconds) {
        const dt = new Date(epochSeconds * 1000);
        return dt.toISOString().replace('T', ' ').substring(0, 19);
      }

      function formatHours(seconds) {
        return (seconds / 3600).toFixed(1);
      }

      function getLatestPosition(currentTime) {
        let best = null;
        let bestTime = -Infinity;
        for (const trip of tripsData) {
          const { timestamps, path } = trip;
          for (let i = 0; i < timestamps.length; i += 1) {
            const ts = timestamps[i];
            if (ts <= currentTime && ts > bestTime) {
              bestTime = ts;
              best = path[i];
            } else if (ts > currentTime) {
              break;
            }
          }
        }
        return best;
      }

      function createLayers() {
        const trailLength = state.exploration ? timeline.duration : state.trailLength;
        const tripsLayer = new deck.TripsLayer({
          id: 'trips',
          data: tripsData,
          getPath: (d) => d.path,
          getTimestamps: (d) => d.timestamps,
          getColor: (d) => d.color,
          opacity: 0.85,
          widthMinPixels: 4,
          rounded: true,
          fadeTrail: true,
          trailLength,
          currentTime: state.currentTime,
          shadowEnabled: false,
        });

        const headPosition = getLatestPosition(state.currentTime);
        const pigLayer = new deck.TextLayer({
          id: 'pig-head',
          data: headPosition ? [{ position: headPosition, text: '🐷' }] : [],
          getPosition: (d) => d.position,
          getText: (d) => d.text,
          getSize: () => 32,
          sizeUnits: 'pixels',
          getColor: () => [252, 211, 77],
          billboard: true,
          fontFamily: "'Apple Color Emoji','Segoe UI Emoji','Noto Color Emoji',sans-serif",
        });

        return [tripsLayer, pigLayer];
      }

      function render() {
        deckgl.setProps({ layers: createLayers() });
        slider.value = state.currentTime;
        label.textContent = formatTime(timeline.start + state.currentTime);
        trailSlider.disabled = state.exploration;
        explorationToggle.classList.toggle('active', state.exploration);
        explorationToggle.setAttribute('aria-pressed', state.exploration ? 'true' : 'false');
      }

      function stepAnimation(timestamp) {
        if (!state.playing) {
          state.lastFrameTs = null;
          return;
        }
        if (state.lastFrameTs == null) {
          state.lastFrameTs = timestamp;
          requestAnimationFrame(stepAnimation);
          return;
        }
        const delta = (timestamp - state.lastFrameTs) / 1000;
        state.lastFrameTs = timestamp;
        state.currentTime += delta * state.speedFactor;
        if (state.currentTime > timeline.duration) {
          state.currentTime = timeline.duration;
          state.playing = false;
          playToggle.textContent = 'Play';
        }
        render();
        if (state.playing) {
          requestAnimationFrame(stepAnimation);
        }
      }

      playToggle.addEventListener('click', () => {
        state.playing = !state.playing;
        playToggle.textContent = state.playing ? 'Pause' : 'Play';
        state.lastFrameTs = null;
        if (state.playing) {
          requestAnimationFrame(stepAnimation);
        }
      });

      slider.addEventListener('input', (event) => {
        state.currentTime = Number(event.target.value);
        render();
      });

      trailSlider.addEventListener('input', (event) => {
        const hours = Number(event.target.value);
        state.trailLength = Math.max(3600, hours * 3600);
        render();
      });

      speedSelect.addEventListener('change', (event) => {
        state.speedFactor = Number(event.target.value);
      });

      explorationToggle.addEventListener('click', () => {
        state.exploration = !state.exploration;
        if (state.exploration) {
          state.trailLength = timeline.duration;
        }
        render();
      });

      render();
    </script>
  </body>
</html>
"""
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a deck.gl + MapLibre trajectory explorer from Google Takeout exports."
    )
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        default=None,
        help="Path to the Google Takeout JSON file (Records.json or semantic location history).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path(DEFAULT_OUTPUT_NAME),
        help=f"HTML path for the generated explorer (default: {DEFAULT_OUTPUT_NAME}).",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Filter records on or after this date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="Filter records on or before this date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--jump-threshold-km",
        type=float,
        default=50.0,
        help="Ignore hops larger than this many kilometres (default: 50).",
    )
    parser.add_argument(
        "--zoom",
        type=float,
        default=6.0,
        help="Initial zoom level for the map (default: 6).",
    )
    parser.add_argument(
        "--map-style",
        type=str,
        default=DEFAULT_MAP_STYLE,
        help="MapLibre style URL to use for the basemap.",
    )
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="Skip interactive prompts (use CLI arguments or full data range).",
    )
    no_fly_group = parser.add_mutually_exclusive_group()
    no_fly_group.add_argument(
        "--exclude-no-fly-zones",
        action="store_true",
        help="Always remove coordinates in predefined no-fly zones before building maps or stats.",
    )
    no_fly_group.add_argument(
        "--include-no-fly-zones",
        action="store_true",
        help="Always keep coordinates from predefined no-fly zones (skip any interactive prompt).",
    )
    return parser.parse_args()


def load_takeout_payload(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict) and "locations" in payload:
        return payload["locations"]
    if isinstance(payload, dict) and "timelinePath" in payload:
        return [payload]
    if isinstance(payload, list):
        return payload
    raise ValueError(f"Unrecognised Google Takeout payload structure in {path}")


def parse_timestamp(raw: str) -> datetime:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return datetime.fromtimestamp(int(raw) / 1000).astimezone()


def extract_coordinates(payload: Iterable[dict]) -> List[Coordinate]:
    records: List[Coordinate] = []
    for entry in payload:
        if "latitudeE7" in entry and "longitudeE7" in entry:
            raw_ts = entry.get("timestamp") or entry.get("timestampMs")
            if not raw_ts:
                continue
            timestamp = parse_timestamp(raw_ts)
            records.append(
                Coordinate(
                    latitude=entry["latitudeE7"] / 1e7,
                    longitude=entry["longitudeE7"] / 1e7,
                    timestamp=timestamp,
                )
            )
        elif "timelinePath" in entry:
            raw_ts = entry.get("startTime")
            if not raw_ts:
                continue
            timestamp = parse_timestamp(raw_ts)
            for point in entry["timelinePath"]:
                location = point.get("point")
                if not location:
                    continue
                lat, lon = parse_geo_point(location)
                records.append(Coordinate(latitude=lat, longitude=lon, timestamp=timestamp))
        elif "visit" in entry and "topCandidate" in entry["visit"]:
            raw_ts = entry.get("startTime")
            if not raw_ts:
                continue
            timestamp = parse_timestamp(raw_ts)
            location = entry["visit"]["topCandidate"].get("placeLocation")
            if not location:
                continue
            lat, lon = parse_geo_point(location)
            records.append(Coordinate(latitude=lat, longitude=lon, timestamp=timestamp))
    return sorted(records, key=lambda coord: coord.timestamp)


def within_range(ts: datetime, start: Optional[datetime], end: Optional[datetime]) -> bool:
    if start and ts < start:
        return False
    if end and ts > end:
        return False
    return True


def apply_date_filters(
    coordinates: Sequence[Coordinate],
    start: Optional[datetime],
    end: Optional[datetime],
) -> List[Coordinate]:
    if start is None and end is None:
        return list(coordinates)
    return [coord for coord in coordinates if within_range(coord.timestamp, start, end)]


def parse_date_string(date_str: str) -> datetime:
    cleaned = date_str.strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            naive = datetime.strptime(cleaned, fmt)
            return naive.replace(tzinfo=LOCAL_TZ)
        except ValueError:
            continue
    raise ValueError(f"Invalid date format '{date_str}'. Use YYYYMMDD or YYYY-MM-DD.")


def parse_geo_point(point_str: str) -> Tuple[float, float]:
    lat_str, lon_str = point_str.replace("geo:", "").split(",", 1)
    return float(lat_str), float(lon_str)


def locate_no_fly_zone(coordinate: Coordinate) -> Optional[NoFlyZone]:
    for zone in NO_FLY_ZONES:
        if zone.contains(coordinate.latitude, coordinate.longitude):
            return zone
    return None


def filter_no_fly_zones(coordinates: Sequence[Coordinate]) -> Tuple[List[Coordinate], Dict[str, int]]:
    filtered: List[Coordinate] = []
    excluded_counts: Dict[str, int] = {}

    for coordinate in coordinates:
        zone = locate_no_fly_zone(coordinate)
        if zone:
            excluded_counts[zone.name] = excluded_counts.get(zone.name, 0) + 1
            continue
        filtered.append(coordinate)

    return filtered, excluded_counts


def resolve_input_path(candidate: Optional[Path]) -> Path:
    if candidate:
        expanded = candidate.expanduser()
        if expanded.exists():
            return expanded
        raise SystemExit(f"Input file not found: {expanded}")

    default_file = DEFAULT_INPUT_FILE

    if sys.stdin.isatty():
        prompt = (
            f"Path to Google Takeout JSON [default: {default_file.resolve()}]: "
            if default_file.exists()
            else "Path to Google Takeout JSON: "
        )
        while True:
            raw = input(prompt).strip()
            if raw:
                proposed = Path(raw).expanduser()
                if proposed.exists():
                    return proposed
                print(f"File not found at {proposed}. Please try again.")
                continue
            if default_file.exists():
                print(f"Using default file {default_file.resolve()}")
                return default_file
            print("Please provide a valid path to the Takeout JSON file.")

    if default_file.exists():
        return default_file

    raise SystemExit(
        "No input file provided. Supply --input or place nov5.json alongside the script."
    )


def build_segments(
    coordinates: Sequence[Coordinate],
    threshold_km: float,
) -> Tuple[List[LineString], List[List[Coordinate]]]:
    if len(coordinates) < 2:
        return [], []

    coords_array = np.array([coord.as_latlon for coord in coordinates])
    distances = haversine_vectorized(
        coords_array[:-1, 0],
        coords_array[:-1, 1],
        coords_array[1:, 0],
        coords_array[1:, 1],
    )
    mask = np.insert(distances <= threshold_km, 0, True)

    segments_coords: List[List[Coordinate]] = []
    current_segment: List[Coordinate] = []

    for keep, coord in zip(mask, coordinates):
        if keep:
            current_segment.append(coord)
        else:
            if len(current_segment) > 1:
                segments_coords.append(current_segment)
            current_segment = [coord]

    if len(current_segment) > 1:
        segments_coords.append(current_segment)

    segments = [
        LineString([coord.as_lonlat for coord in segment]) for segment in segments_coords
    ]
    return segments, segments_coords


def haversine_vectorized(
    lat1: np.ndarray,
    lon1: np.ndarray,
    lat2: np.ndarray,
    lon2: np.ndarray,
) -> np.ndarray:
    radius = 6371.0
    lat1_rad, lon1_rad = np.radians(lat1), np.radians(lon1)
    lat2_rad, lon2_rad = np.radians(lat2), np.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2) ** 2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return radius * c


def lookup_country_name(iso_code: str) -> str:
    if not iso_code:
        return "Unknown"
    if pycountry:
        match = pycountry.countries.get(alpha_2=iso_code.upper())
        if match:
            return getattr(match, "common_name", match.name)
    return iso_code.upper()


def compute_location_stats(coordinates: Sequence[Coordinate]) -> Optional[LocationStats]:
    if not reverse_geocoder:
        return None

    cache: dict[Tuple[float, float], dict] = {}
    country_last_seen: dict[str, datetime] = {}
    state_last_seen: dict[str, datetime] = {}

    for coordinate in coordinates:
        key = (round(coordinate.latitude, 4), round(coordinate.longitude, 4))
        if key not in cache:
            lookup = reverse_geocoder.search(
                [coordinate.as_latlon], mode=1, verbose=False
            )
            if not lookup:
                continue
            cache[key] = lookup[0]
        result = cache[key]

        country_code = result.get("cc", "").upper()
        if country_code:
            previous = country_last_seen.get(country_code)
            if not previous or coordinate.timestamp > previous:
                country_last_seen[country_code] = coordinate.timestamp

        if country_code == "US":
            state_label = result.get("admin1")
            if state_label:
                previous_state = state_last_seen.get(state_label)
                if not previous_state or coordinate.timestamp > previous_state:
                    state_last_seen[state_label] = coordinate.timestamp

    if not country_last_seen:
        return None

    countries = [
        RegionVisit(
            identifier=code,
            label=lookup_country_name(code),
            last_seen=country_last_seen[code],
        )
        for code in country_last_seen
    ]
    countries.sort(key=lambda visit: (visit.label, visit.identifier))

    states = [
        RegionVisit(identifier=label, label=label, last_seen=state_last_seen[label])
        for label in state_last_seen
    ]
    states.sort(key=lambda visit: visit.label)

    return LocationStats(countries=countries, us_states=states)


def decide_no_fly_preference(args: argparse.Namespace) -> bool:
    if args.exclude_no_fly_zones:
        return True
    if args.include_no_fly_zones:
        return False
    if args.no_prompt or not sys.stdin.isatty():
        return False

    prompt = "Exclude no-fly zones (Chicago/Evanston and Beijing) from the map? [y/N]: "
    while True:
        raw = input(prompt).strip().lower()
        if not raw:
            return False
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("Please answer with 'y' or 'n'.")


def isoformat_local(dt: datetime) -> str:
    return dt.astimezone(LOCAL_TZ).strftime("%Y-%m-%d")


def build_deck_payload(
    segment_coords: Sequence[Sequence[Coordinate]],
    start_epoch: float,
) -> List[dict]:
    trips: List[dict] = []
    for index, segment in enumerate(segment_coords):
        if len(segment) < 2:
            continue
        path = [[coord.longitude, coord.latitude] for coord in segment]
        timestamps = [(coord.timestamp.timestamp() - start_epoch) for coord in segment]
        trips.append(
            {
                "id": index,
                "path": path,
                "timestamps": timestamps,
                "color": [55, 114, 255],
            }
        )
    return trips


def compute_initial_view_state(
    coordinates: Sequence[Coordinate],
    zoom: float,
) -> dict:
    if not coordinates:
        return {"longitude": 0, "latitude": 0, "zoom": zoom, "pitch": 45, "bearing": 0}
    lats = [coord.latitude for coord in coordinates]
    lons = [coord.longitude for coord in coordinates]
    return {
        "longitude": float(np.mean(lons)),
        "latitude": float(np.mean(lats)),
        "zoom": float(zoom),
        "pitch": 45,
        "bearing": 0,
    }


def render_html(
    data: List[dict],
    timeline: dict,
    initial_view_state: dict,
    stats: LocationStats,
    point_count: int,
    map_style: str,
) -> str:
    return HTML_TEMPLATE.substitute(
        deck_data=json.dumps(data, ensure_ascii=False),
        timeline=json.dumps(timeline, ensure_ascii=False),
        initial_view_state=json.dumps(initial_view_state, ensure_ascii=False),
        country_count=len(stats.countries) if stats else 0,
        state_count=len(stats.us_states) if stats else 0,
        point_count=point_count,
        map_style=map_style,
    )


def print_stats(stats: Optional[LocationStats]) -> None:
    if not stats:
        if reverse_geocoder is None:
            print(
                "\nTravel stats unavailable: install optional dependency 'reverse_geocoder' "
                "(and 'pycountry' for names) to enable them."
            )
        return

    print("\nTravel Stats")
    print("------------")
    print(f"Visited countries: {len(stats.countries)}")
    for visit in stats.countries:
        print(f"  - {visit.label} ({visit.identifier}) — last entry {isoformat_local(visit.last_seen)}")
    if stats.us_states:
        print(f"\nVisited US states: {len(stats.us_states)}")
        for visit in stats.us_states:
            print(f"  - {visit.label} — last entry {isoformat_local(visit.last_seen)}")


def prompt_date_range(
    existing_start: Optional[datetime],
    existing_end: Optional[datetime],
    earliest: datetime,
    latest: datetime,
) -> Tuple[datetime, datetime]:
    print(
        f"Available data spans {earliest.strftime('%Y-%m-%d')} "
        f"to {latest.strftime('%Y-%m-%d')}."
    )

    def prompt_single(label: str, default: datetime) -> datetime:
        while True:
            raw = input(
                f"{label} date (YYYYMMDD) "
                f"[press Enter for {default.strftime('%Y-%m-%d')}]: "
            ).strip()
            if not raw:
                return default
            try:
                return parse_date_string(raw)
            except ValueError as exc:
                print(exc)

    start_default = existing_start or earliest
    end_default = existing_end or latest

    while True:
        start = prompt_single("Start", start_default)
        end = prompt_single("End", end_default)
        if start <= end:
            return start, end
        print("Start date must be on or before the end date. Please try again.")


def main() -> None:
    args = parse_args()
    input_path = resolve_input_path(args.input)
    entries = list(load_takeout_payload(input_path))
    if not entries:
        raise SystemExit("No location entries found in the supplied file.")

    all_coordinates = extract_coordinates(entries)
    if not all_coordinates:
        raise SystemExit("No location records could be parsed from the supplied file.")

    earliest = all_coordinates[0].timestamp
    latest = all_coordinates[-1].timestamp

    start = parse_date_string(args.start_date) if args.start_date else None
    end = parse_date_string(args.end_date) if args.end_date else None
    exclude_no_fly_zones = decide_no_fly_preference(args)

    should_prompt = not args.no_prompt and sys.stdin.isatty()
    if should_prompt:
        start, end = prompt_date_range(start, end, earliest, latest)

    coordinates = apply_date_filters(all_coordinates, start, end)
    if not coordinates:
        raise SystemExit("No location records matched the specified filters.")

    if exclude_no_fly_zones:
        coordinates, excluded_counts = filter_no_fly_zones(coordinates)
        if not coordinates:
            raise SystemExit(
                "All records were removed by the no-fly zone filters. "
                "Retry without --exclude-no-fly-zones or adjust your data range."
            )
        if excluded_counts:
            excluded_summary = ", ".join(
                f"{name}: {count}" for name, count in sorted(excluded_counts.items())
            )
            print(
                f"Excluded {sum(excluded_counts.values())} points "
                f"inside protected areas ({excluded_summary})."
            )

    segments, segment_coords = build_segments(coordinates, args.jump_threshold_km)
    if not segments:
        raise SystemExit("All segments were discarded. Try increasing --jump-threshold-km.")

    start_epoch = min(coord.timestamp.timestamp() for coord in coordinates)
    end_epoch = max(coord.timestamp.timestamp() for coord in coordinates)
    duration = max(end_epoch - start_epoch, 1.0)

    deck_data = build_deck_payload(segment_coords, start_epoch)
    initial_view_state = compute_initial_view_state(coordinates, args.zoom)
    timeline = {
        "start": start_epoch,
        "end": end_epoch,
        "duration": duration,
    }

    stats = compute_location_stats(coordinates)
    stats_for_html = stats if stats else LocationStats(countries=[], us_states=[])
    html = render_html(
        deck_data,
        timeline,
        initial_view_state,
        stats_for_html,
        point_count=len(coordinates),
        map_style=args.map_style,
    )

    print_stats(stats)

    output_path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"Saved deck.gl explorer to {output_path.resolve()}")


if __name__ == "__main__":
    main()
