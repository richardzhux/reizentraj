import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import folium
import numpy as np
from folium.plugins import TimestampedGeoJson
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


DEFAULT_OUTPUT_NAME = "trajectory_map.html"
DEFAULT_INPUT_FILE = Path(__file__).resolve().parent / "nov5.json"


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an interactive trajectory map from Google Takeout exports."
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
        help=f"HTML path for the generated map (default: {DEFAULT_OUTPUT_NAME}).",
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
        type=int,
        default=6,
        help="Initial zoom level for the folium map (default: 6).",
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


def build_map(
    segments: Sequence[LineString],
    segment_coordinates: Sequence[Sequence[Coordinate]],
    zoom: int,
) -> folium.Map:
    if not segments:
        raise ValueError("No continuous trajectory segments remain after filtering.")

    centroid = unary_union(segments).centroid
    fmap = folium.Map(location=[centroid.y, centroid.x], zoom_start=zoom, tiles="OpenStreetMap")

    for segment in segments:
        folium.GeoJson(segment.__geo_interface__).add_to(fmap)

    time_geojson = build_time_geojson(segment_coordinates)
    if time_geojson["features"]:
        TimestampedGeoJson(
            time_geojson,
            period="PT1H",
            duration="PT1H",
            add_last_point=True,
            loop=False,
            auto_play=False,
            loop_button=True,
            time_slider_drag_update=True,
        ).add_to(fmap)

    return fmap


def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    return parse_date_string(date_str)


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


def build_time_geojson(
    segment_coordinates: Sequence[Sequence[Coordinate]],
) -> dict:
    features: List[dict] = []

    for segment in segment_coordinates:
        if len(segment) < 2:
            continue
        times = [coord.timestamp.isoformat() for coord in segment]
        geometry = [[coord.longitude, coord.latitude] for coord in segment]
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": geometry},
                "properties": {
                    "times": times,
                    "style": {"color": "#3772ff", "weight": 3},
                    "popup": segment[0].timestamp.strftime("%Y-%m-%d %H:%M"),
                },
            }
        )

    return {"type": "FeatureCollection", "features": features}


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


def format_visit_summary(visit: RegionVisit) -> str:
    date_str = visit.last_seen.astimezone(LOCAL_TZ).strftime("%Y-%m-%d")
    return f"{visit.label} ({visit.identifier}) — last entry {date_str}"


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

    start = parse_date(args.start_date)
    end = parse_date(args.end_date)
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

    fmap = build_map(segments, segment_coords, args.zoom)

    stats = compute_location_stats(coordinates)
    if stats:
        print("\nTravel Stats")
        print("------------")
        print(f"Visited countries: {len(stats.countries)}")
        for visit in stats.countries:
            print(f"  - {format_visit_summary(visit)}")
        if stats.us_states:
            print(f"\nVisited US states: {len(stats.us_states)}")
            for visit in stats.us_states:
                print(f"  - {format_visit_summary(visit)}")
    elif reverse_geocoder is None:
        print(
            "\nTravel stats unavailable: install optional dependency "
            "'reverse_geocoder' (and 'pycountry' for names) to enable them."
        )

    output_path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(output_path))
    print(f"Saved interactive map to {output_path.resolve()}")


if __name__ == "__main__":
    main()
