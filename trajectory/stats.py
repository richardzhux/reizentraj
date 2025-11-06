from __future__ import annotations

from datetime import datetime
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .models import Coordinate, LocationStats, RegionGroup, RegionVisit
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


US_STATE_ALIASES = {
    "alabama": "Alabama",
    "alaska": "Alaska",
    "arizona": "Arizona",
    "arkansas": "Arkansas",
    "california": "California",
    "colorado": "Colorado",
    "connecticut": "Connecticut",
    "delaware": "Delaware",
    "district of columbia": "District of Columbia",
    "washington, d.c.": "District of Columbia",
    "washington d.c.": "District of Columbia",
    "washington, dc": "District of Columbia",
    "washington dc": "District of Columbia",
    "dc": "District of Columbia",
    "florida": "Florida",
    "georgia": "Georgia",
    "hawaii": "Hawaii",
    "idaho": "Idaho",
    "illinois": "Illinois",
    "indiana": "Indiana",
    "iowa": "Iowa",
    "kansas": "Kansas",
    "kentucky": "Kentucky",
    "louisiana": "Louisiana",
    "maine": "Maine",
    "maryland": "Maryland",
    "massachusetts": "Massachusetts",
    "michigan": "Michigan",
    "minnesota": "Minnesota",
    "mississippi": "Mississippi",
    "missouri": "Missouri",
    "montana": "Montana",
    "nebraska": "Nebraska",
    "nevada": "Nevada",
    "new hampshire": "New Hampshire",
    "new jersey": "New Jersey",
    "new mexico": "New Mexico",
    "new york": "New York",
    "north carolina": "North Carolina",
    "north dakota": "North Dakota",
    "ohio": "Ohio",
    "oklahoma": "Oklahoma",
    "oregon": "Oregon",
    "pennsylvania": "Pennsylvania",
    "rhode island": "Rhode Island",
    "south carolina": "South Carolina",
    "south dakota": "South Dakota",
    "tennessee": "Tennessee",
    "texas": "Texas",
    "utah": "Utah",
    "vermont": "Vermont",
    "virginia": "Virginia",
    "washington": "Washington",
    "west virginia": "West Virginia",
    "wisconsin": "Wisconsin",
    "wyoming": "Wyoming",
}


def compute_location_stats(coordinates: Sequence[Coordinate]) -> Optional[LocationStats]:
    if not reverse_geocoder:
        return None

    cache: Dict[Tuple[float, float], dict] = {}
    country_last_seen: Dict[str, datetime] = {}
    us_state_last_seen: Dict[str, datetime] = {}
    regions_last_seen: Dict[str, Dict[str, datetime]] = {}

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

        admin1 = result.get("admin1", "").strip()
        if not admin1:
            continue

        admin1_normalized = admin1.lower()
        canonical_state = US_STATE_ALIASES.get(admin1_normalized)

        if country_code == "US" and canonical_state:
            prev_state = us_state_last_seen.get(canonical_state)
            if not prev_state or coordinate.timestamp > prev_state:
                us_state_last_seen[canonical_state] = coordinate.timestamp
            continue

        if country_code:
            per_country = regions_last_seen.setdefault(country_code, {})
            prev_region = per_country.get(admin1)
            if not prev_region or coordinate.timestamp > prev_region:
                per_country[admin1] = coordinate.timestamp

    countries = [
        RegionVisit(identifier=code, label=lookup_country_name(code), last_seen=last_seen)
        for code, last_seen in sorted(country_last_seen.items(), key=lambda item: item[1], reverse=True)
    ]

    us_states = [
        RegionVisit(identifier=state, label=state, last_seen=last_seen)
        for state, last_seen in sorted(us_state_last_seen.items(), key=lambda item: item[1], reverse=True)
    ]

    region_groups: list[RegionGroup] = []
    for country_code, regions in regions_last_seen.items():
        if country_code == "US":
            # already captured as states; skip duplicates
            continue
        visits = [
            RegionVisit(identifier=f"{country_code}-{name}", label=name, last_seen=last_seen)
            for name, last_seen in sorted(regions.items(), key=lambda item: item[1], reverse=True)
        ]
        if visits:
            region_groups.append(
                RegionGroup(
                    country_code=country_code,
                    country_label=lookup_country_name(country_code),
                    regions=visits,
                )
            )

    region_groups.sort(
        key=lambda group: group.regions[0].last_seen if group.regions else datetime.min,
        reverse=True,
    )

    return LocationStats(countries=countries, us_states=us_states, region_groups=region_groups)


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
    if stats.region_groups:
        print("\nRegions by country:")
        for group in stats.region_groups:
            print(f"  {group.country_label} ({group.country_code}) — {len(group.regions)} region(s)")
            for visit in group.regions:
                print(f"    - {visit.label} — last entry {isoformat_local(visit.last_seen)}")
