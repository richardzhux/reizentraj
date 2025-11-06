from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable, Optional

from .constants import DEFAULT_INPUT_FILE


def load_takeout_payload(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict) and "locations" in payload:
        yield from payload["locations"]
        return
    if isinstance(payload, dict) and "timelinePath" in payload:
        yield payload
        return
    if isinstance(payload, list):
        yield from payload
        return
    raise ValueError(f"Unrecognised Google Takeout payload structure in {path}")


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

    raise SystemExit("No input file provided. Supply --input or place nov5.json alongside the script.")
