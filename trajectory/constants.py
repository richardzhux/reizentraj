from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, Sequence

from .models import NoFlyZone

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_PATH = (BASE_DIR / "trajectory_deck.html").resolve()
DEFAULT_OUTPUT_DIR = DEFAULT_OUTPUT_PATH.parent
DEFAULT_OUTPUT_NAME = str(DEFAULT_OUTPUT_PATH)
DEFAULT_INPUT_FILE = BASE_DIR / "nov5.json"
DEFAULT_MAP_STYLE = "Voyager"

MAP_STYLES: Dict[str, str] = {
    "Voyager": "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json",
    "Positron": "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
    "Dark Matter": "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
}

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

LOCAL_TZ = datetime.now().astimezone().tzinfo
