from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from .constants import LOCAL_TZ


def parse_timestamp(raw: str) -> datetime:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return datetime.fromtimestamp(int(raw) / 1000).astimezone()


def parse_date_string(date_str: str) -> datetime:
    cleaned = date_str.strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=LOCAL_TZ)
        except ValueError:
            continue
    raise ValueError(f"Invalid date format '{date_str}'. Use YYYYMMDD or YYYY-MM-DD.")


def within_range(ts: datetime, start: Optional[datetime], end: Optional[datetime]) -> bool:
    if start and ts < start:
        return False
    if end and ts > end:
        return False
    return True


def format_timespan(seconds: float) -> str:
    if seconds <= 0:
        return "0 days"
    total_days = int(seconds // 86400)
    years, rem_days = divmod(total_days, 365)
    months, days = divmod(rem_days, 30)
    parts: List[str] = []
    if years:
        parts.append(f"{years} year{'s' if years != 1 else ''}")
    if months:
        parts.append(f"{months} month{'s' if months != 1 else ''}")
    if days or not parts:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    return ", ".join(parts)


def isoformat_local(dt: datetime) -> str:
    return dt.astimezone(LOCAL_TZ).strftime("%Y-%m-%d")
