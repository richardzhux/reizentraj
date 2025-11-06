from __future__ import annotations

from typing import List, Sequence

from .models import Coordinate


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
    zoom: float,
) -> dict:
    return {
        "longitude": -98.5795,
        "latitude": 39.8283,
        "zoom": float(zoom),
        "pitch": 0,
        "bearing": 0,
    }

