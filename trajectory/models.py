from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence, Tuple


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
class RegionGroup:
    country_code: str
    country_label: str
    regions: Sequence[RegionVisit]


@dataclass(frozen=True)
class LocationStats:
    countries: Sequence[RegionVisit]
    us_states: Sequence[RegionVisit]
    region_groups: Sequence["RegionGroup"]


@dataclass(frozen=True)
class NoFlyZone:
    name: str
    min_lat: float
    min_lon: float
    max_lat: float
    max_lon: float

    def contains(self, latitude: float, longitude: float) -> bool:
        return self.min_lat <= latitude <= self.max_lat and self.min_lon <= longitude <= self.max_lon
