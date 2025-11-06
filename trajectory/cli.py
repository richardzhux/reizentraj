from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence, Tuple

from .coarsen import coarsen_coordinates
from .constants import DEFAULT_MAP_STYLE, DEFAULT_OUTPUT_DIR, MAP_STYLES
from .deckbuilder import build_deck_payload, build_flight_arcs, compute_initial_view_state
from .io import load_takeout_payload, resolve_input_path
from .models import LocationStats
from .preprocess import apply_date_filters, build_segments, extract_coordinates, filter_no_fly_zones
from .stats import compute_location_stats, compute_total_distance_km, print_stats
from .template.renderer import render_html
from .time_utils import format_timespan, parse_date_string


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
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
        default=None,
        help="HTML path for the generated explorer (default: named automatically based on privacy settings).",
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
        default=4.0,
        help="Initial zoom level for the map (default: 4).",
    )
    parser.add_argument(
        "--map-style",
        type=str,
        default=DEFAULT_MAP_STYLE,
        help="Basemap style (Voyager, Positron, Dark Matter) or a custom MapLibre style URL.",
    )
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="Skip interactive prompts (use CLI arguments or full data range).",
    )
    coarse_group = parser.add_mutually_exclusive_group()
    coarse_group.add_argument(
        "--coarsen",
        dest="coarsen",
        action="store_true",
        help="Apply privacy coarsening (daily curves with heavy smoothing) before rendering.",
    )
    coarse_group.add_argument(
        "--no-coarsen",
        dest="coarsen",
        action="store_false",
        help="Always keep precise points (skip privacy coarsening even if prompted).",
    )
    parser.set_defaults(coarsen=None)
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
    return parser.parse_args(argv)


def decide_no_fly_preference(args: argparse.Namespace, should_prompt: bool) -> bool:
    if args.exclude_no_fly_zones:
        return True
    if args.include_no_fly_zones:
        return False
    if not should_prompt:
        return False
    while True:
        answer = input("Exclude points in predefined no-fly zones? [Y/n]: ").strip().lower()
        if answer in {"y", "yes", ""}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Please enter 'y' or 'n'.")


def decide_coarsen_preference(args: argparse.Namespace, should_prompt: bool) -> bool:
    if args.coarsen is True:
        return True
    if args.coarsen is False:
        return False
    if not should_prompt:
        return False
    while True:
        answer = input(
            "Apply privacy coarsening (smooth daily curves instead of raw points)? [y/N]: "
        ).strip().lower()
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no", ""}:
            return False
        print("Please enter 'y' or 'n'.")


def prompt_date_range(
    existing_start: Optional[datetime],
    existing_end: Optional[datetime],
    earliest: datetime,
    latest: datetime,
) -> Tuple[datetime, datetime]:
    print(f"Available data spans {earliest.strftime('%Y-%m-%d')} to {latest.strftime('%Y-%m-%d')}.")

    def prompt_single(label: str, default: datetime) -> datetime:
        while True:
            raw = input(f"{label} date (YYYYMMDD) [press Enter for {default.strftime('%Y-%m-%d')}]: ").strip()
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


def normalise_map_style(style: str) -> str:
    style = style.strip()
    if not style:
        return DEFAULT_MAP_STYLE
    if style in MAP_STYLES:
        return style
    title_candidate = style.title()
    if title_candidate in MAP_STYLES:
        return title_candidate
    return style


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
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
    should_prompt = not args.no_prompt and sys.stdin.isatty()
    apply_coarsening = decide_coarsen_preference(args, should_prompt)
    if apply_coarsening and args.include_no_fly_zones:
        print(
            "Privacy coarsening always excludes predefined no-fly zones; ignoring --include-no-fly-zones."
        )
    exclude_no_fly_zones = True if apply_coarsening else decide_no_fly_preference(args, should_prompt)

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
            excluded_summary = ", ".join(f"{name}: {count}" for name, count in sorted(excluded_counts.items()))
            print(
                f"Excluded {sum(excluded_counts.values())} points inside protected areas ({excluded_summary})."
            )

    if apply_coarsening:
        before_count = len(coordinates)
        coordinates = coarsen_coordinates(coordinates)
        after_count = len(coordinates)
        print(
            f"Applied privacy coarsening: reduced {before_count} raw points to {after_count} daily smoothed points."
        )

    segments, segment_coords, flights = build_segments(coordinates, args.jump_threshold_km)
    if not segments:
        raise SystemExit("All segments were discarded. Try increasing --jump-threshold-km.")

    start_epoch = min(coord.timestamp.timestamp() for coord in coordinates)
    end_epoch = max(coord.timestamp.timestamp() for coord in coordinates)
    duration = max(end_epoch - start_epoch, 1.0)

    deck_data = build_deck_payload(segment_coords, start_epoch)
    initial_view_state = compute_initial_view_state(args.zoom)
    timeline = {
        "start": start_epoch,
        "end": end_epoch,
        "duration": duration,
    }

    stats = compute_location_stats(coordinates)
    stats_for_html = stats if stats else LocationStats(countries=[], us_states=[], region_groups=[])
    selected_map_style = normalise_map_style(args.map_style)
    timespan_text = format_timespan(duration)
    distance_km = compute_total_distance_km(coordinates, args.jump_threshold_km)
    flight_data = [] if apply_coarsening else build_flight_arcs(flights)

    html = render_html(
        deck_data,
        timeline,
        initial_view_state,
        stats_for_html,
        point_count=len(coordinates),
        map_style=selected_map_style,
        timespan=timespan_text,
        distance_km=round(distance_km),
        flights_data=flight_data,
        safe_mode=apply_coarsening,
    )

    print_stats(stats)

    if args.output is not None:
        output_path = args.output
    else:
        if apply_coarsening:
            filename = "trajectory_coarsen.html"
        elif exclude_no_fly_zones:
            filename = "trajectory_nfz.html"
        else:
            filename = "trajectory_full.html"
        output_path = DEFAULT_OUTPUT_DIR / filename

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"Saved deck.gl explorer to {output_path.resolve()}")
