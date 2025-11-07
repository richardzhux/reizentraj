from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Sequence

import numpy as np

from .constants import LOCAL_TZ
from .models import Coordinate


def _mean_lat_lon(coordinates: Sequence[Coordinate]) -> tuple[float, float]:
    latitudes = [coord.latitude for coord in coordinates]
    longitudes = [coord.longitude for coord in coordinates]
    return float(np.mean(latitudes)), float(np.mean(longitudes))


def _generate_anchor_points(
    coordinates: Sequence[Coordinate],
    window_size: int,
) -> List[tuple[float, float]]:
    anchors: List[tuple[float, float]] = []
    for index in range(0, len(coordinates), window_size):
        window = coordinates[index : index + window_size]
        anchors.append(_mean_lat_lon(window))
    return anchors


def _evaluate_curve(
    anchors: Sequence[tuple[float, float]],
    min_samples: int,
) -> np.ndarray:
    anchor_count = len(anchors)
    if anchor_count == 1:
        return np.array([[anchors[0][0], anchors[0][1]]])

    anchor_positions = np.linspace(0.0, 1.0, anchor_count)
    sample_count = max(min_samples, anchor_count)
    sample_positions = np.linspace(0.0, 1.0, sample_count)

    latitudes = np.array([value[0] for value in anchors])
    longitudes = np.array([value[1] for value in anchors])

    if anchor_count >= 3:
        degree = min(3, anchor_count - 1)
        lat_coeffs = np.polyfit(anchor_positions, latitudes, degree)
        lon_coeffs = np.polyfit(anchor_positions, longitudes, degree)
        latitudes = np.polyval(lat_coeffs, sample_positions)
        longitudes = np.polyval(lon_coeffs, sample_positions)
    else:
        latitudes = np.interp(sample_positions, anchor_positions, latitudes)
        longitudes = np.interp(sample_positions, anchor_positions, longitudes)

    return np.stack((latitudes, longitudes), axis=1)


def _midday_timestamp(day: date) -> datetime:
    start = datetime.combine(day, time(), tzinfo=LOCAL_TZ)
    return start + timedelta(hours=12)


def _coarsen_single_day(
    day: date,
    coordinates: Sequence[Coordinate],
    window_size: int,
    min_samples: int,
) -> List[Coordinate]:
    sorted_coords = sorted(coordinates, key=lambda coord: coord.timestamp)
    anchors = _generate_anchor_points(sorted_coords, window_size)
    curve_points = _evaluate_curve(anchors, min_samples)
    timestamp = _midday_timestamp(day)
    return [
        Coordinate(latitude=float(lat), longitude=float(lon), timestamp=timestamp)
        for lat, lon in curve_points
    ]


def _haversine_distance_km(coord_a: Coordinate, coord_b: Coordinate) -> float:
    lat1 = np.radians(coord_a.latitude)
    lon1 = np.radians(coord_a.longitude)
    lat2 = np.radians(coord_b.latitude)
    lon2 = np.radians(coord_b.longitude)

    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return float(6371.0 * c)


def _build_bridge(
    start: Coordinate,
    end: Coordinate,
    segments: int = 6,
) -> List[Coordinate]:
    if segments < 2:
        return []
    bridge: List[Coordinate] = []
    for index in range(1, segments):
        t = index / segments
        lat = start.latitude + (end.latitude - start.latitude) * t
        lon = start.longitude + (end.longitude - start.longitude) * t
        bridge.append(Coordinate(latitude=lat, longitude=lon, timestamp=end.timestamp))
    return bridge


def coarsen_coordinates(
    coordinates: Sequence[Coordinate],
    window_size: int = 5,
    min_samples: int = 10,
    bridge_threshold_km: float = 150.0,
) -> List[Coordinate]:
    if len(coordinates) <= 1:
        return list(coordinates)

    daily_groups: Dict[date, List[Coordinate]] = defaultdict(list)
    for coordinate in coordinates:
        local_day = coordinate.timestamp.astimezone(LOCAL_TZ).date()
        daily_groups[local_day].append(coordinate)

    coarsened: List[Coordinate] = []
    previous_tail: Coordinate | None = None

    for day in sorted(daily_groups):
        day_points = _coarsen_single_day(day, daily_groups[day], window_size, min_samples)
        if not day_points:
            continue
        if previous_tail:
            distance = _haversine_distance_km(previous_tail, day_points[0])
            if distance <= bridge_threshold_km:
                coarsened.extend(_build_bridge(previous_tail, day_points[0]))
        coarsened.extend(day_points)
        previous_tail = day_points[-1]

    return coarsened
