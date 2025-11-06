from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional, Sequence, Tuple
import numpy as np

from .models import Coordinate, LocationStats, RegionVisit
from .preprocess import haversine_vectorized
from .time_utils import isoformat_local

try:
    import reverse_geocoder  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    reverse_geocoder = None

try:
    import pycountry  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    pycountry = None


def compute_total_distance_km(coordinates: Sequence[Coordinate], threshold_km: float) -> float:
    if len(coordinates) < 2:
        return 0.0
    coords_array = np.array([coord.as_latlon for coord in coordinates])
    distances = haversine_vectorized(
        coords_array[:-1, 0],
        coords_array[:-1, 1],
        coords_array[1:, 0],
        coords_array[1:, 1],
    )
    valid = distances <= threshold_km
    return float(distances[valid].sum())


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

    cache: Dict[Tuple[float, float], dict] = {}
    country_last_seen: Dict[str, datetime] = {}
    state_last_seen: Dict[str, datetime] = {}

    for coordinate in coordinates:
        key = (round(coordinate.latitude, 4), round(coordinate.longitude, 4))
        if key not in cache:
            lookup = reverse_geocoder.search([coordinate.as_latlon], mode=1, verbose=False)
            if not lookup:
                continue
            cache[key] = lookup[0]
        result = cache[key]

        country_code = result.get("cc", "").upper()
        if country_code:
            previous = country_last_seen.get(country_code)
            if not previous or coordinate.timestamp > previous:
                country_last_seen[country_code] = coordinate.timestamp

        state_code = result.get("admin1", "")
        if state_code:
            previous_state = state_last_seen.get(state_code)
            if not previous_state or coordinate.timestamp > previous_state:
                state_last_seen[state_code] = coordinate.timestamp

    countries = [
        RegionVisit(identifier=code, label=lookup_country_name(code), last_seen=last_seen)
        for code, last_seen in sorted(country_last_seen.items(), key=lambda item: item[1], reverse=True)
    ]
    states = [
        RegionVisit(identifier=code, label=code, last_seen=last_seen)
        for code, last_seen in sorted(state_last_seen.items(), key=lambda item: item[1], reverse=True)
    ]

    return LocationStats(countries=countries, us_states=states)


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
