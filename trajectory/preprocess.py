from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from shapely.geometry import LineString

from .constants import NO_FLY_ZONES
from .models import Coordinate, NoFlyZone
from .time_utils import parse_timestamp, within_range


def parse_geo_point(point_str: str) -> Tuple[float, float]:
    lat_str, lon_str = point_str.replace("geo:", "").split(",", 1)
    return float(lat_str), float(lon_str)


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


def apply_date_filters(
    coordinates: Sequence[Coordinate],
    start: Optional[datetime],
    end: Optional[datetime],
) -> List[Coordinate]:
    if start is None and end is None:
        return list(coordinates)
    return [coord for coord in coordinates if within_range(coord.timestamp, start, end)]


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


def haversine_vectorized(
    lat1: np.ndarray,
    lon1: np.ndarray,
    lat2: np.ndarray,
    lon2: np.ndarray,
) -> np.ndarray:
    lat1_rad = np.radians(lat1)
    lon1_rad = np.radians(lon1)
    lat2_rad = np.radians(lat2)
    lon2_rad = np.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2) ** 2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return 6371.0 * c


def build_segments(
    coordinates: Sequence[Coordinate],
    threshold_km: float,
) -> Tuple[List[LineString], List[List[Coordinate]], List[Tuple[Coordinate, Coordinate]]]:
    if len(coordinates) < 2:
        return [], [], []

    coord_list = list(coordinates)
    coords_array = np.array([coord.as_latlon for coord in coord_list])
    distances = haversine_vectorized(
        coords_array[:-1, 0],
        coords_array[:-1, 1],
        coords_array[1:, 0],
        coords_array[1:, 1],
    )
    break_indices = np.where(distances > threshold_km)[0]
    mask = np.insert(distances <= threshold_km, 0, True)

    segments_coords: List[List[Coordinate]] = []
    current_segment: List[Coordinate] = []
    flights: List[Tuple[Coordinate, Coordinate]] = []

    for keep, coord in zip(mask, coord_list):
        if keep:
            current_segment.append(coord)
        else:
            if len(current_segment) > 1:
                segments_coords.append(current_segment)
            current_segment = [coord]

    if len(current_segment) > 1:
        segments_coords.append(current_segment)

    def in_contiguous_us(coordinate: Coordinate) -> bool:
        return 24.5 <= coordinate.latitude <= 49.5 and -125.0 <= coordinate.longitude <= -66.0

    for idx in break_indices:
        if idx + 1 >= len(coord_list):
            continue
        origin = coord_list[idx]
        dest = coord_list[idx + 1]
        distance_km = distances[idx]
        threshold = 230.0 if in_contiguous_us(origin) and in_contiguous_us(dest) else 100.0
        if distance_km >= threshold:
            flights.append((origin, dest))

    segments = [LineString([coord.as_lonlat for coord in segment]) for segment in segments_coords]
    return segments, segments_coords, flights
