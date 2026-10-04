"""Timestamp regex fragments shared by all layouts (docs/09, section 3.1).

Every logcat time modifier (year, usec/nsec, epoch, monotonic, zone) is
covered by one combined fragment, so each header layout is written once.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from ..model.entry import TimeKind

_FRAC = r"\.\d{3,9}"
YMD = rf"\d{{4}}-\d\d-\d\d\s+\d\d:\d\d:\d\d{_FRAC}"
MMDD = rf"\d\d-\d\d\s+\d\d:\d\d:\d\d{_FRAC}"
SECONDS = rf"\d+{_FRAC}"  # epoch or monotonic, told apart by magnitude
ZONE = r"(?:\s+(?:[+-]\d{4}|[A-Z]{3,5}))?"

# Named group `ts`; the time zone (if any) is part of the captured text.
TS = rf"(?P<ts>(?:{YMD}|{MMDD}|{SECONDS}){ZONE})"

_ZONE_RE = re.compile(r"\s+([+-]\d{4}|[A-Z]{3,5})$")
_EPOCH_MIN_DIGITS = 9  # 1e9 seconds is 2001; monotonic uptimes stay far below


def classify(ts: str) -> TimeKind:
    """Kind of a timestamp captured by `TS` (cheap: runs once per line)."""
    if len(ts) > 4 and ts[4] == "-":
        return TimeKind.WALL
    if len(ts) > 2 and ts[2] == "-":
        return TimeKind.WALL_NO_YEAR
    dot = ts.find(".")
    if dot >= _EPOCH_MIN_DIGITS:
        return TimeKind.EPOCH
    return TimeKind.MONOTONIC if dot > 0 else TimeKind.NONE


def fraction_digits(ts: str) -> int:
    dot = ts.find(".")
    if dot < 0:
        return 0
    end = dot + 1
    while end < len(ts) and ts[end].isdigit():
        end += 1
    return end - dot - 1


def has_zone(ts: str) -> bool:
    return _ZONE_RE.search(ts) is not None


def to_seconds(ts: str, kind: TimeKind, default_year: int | None = None) -> float | None:
    """Best-effort conversion to seconds (epoch for wall clocks, uptime for
    monotonic). Used for sorting/merging, never for display."""
    text = ts.strip()
    try:
        if kind in (TimeKind.EPOCH, TimeKind.MONOTONIC):
            return float(text.split()[0])
        if kind not in (TimeKind.WALL, TimeKind.WALL_NO_YEAR):
            return None
        tz = timezone.utc
        m = _ZONE_RE.search(text)
        if m:
            text = text[: m.start()]
            zone = m.group(1)
            if zone[0] in "+-":
                sign = 1 if zone[0] == "+" else -1
                tz = timezone(sign * timedelta(hours=int(zone[1:3]), minutes=int(zone[3:5])))
        date_part, time_part = text.split()
        if kind is TimeKind.WALL_NO_YEAR:
            year = default_year or datetime.now().year
            date_part = f"{year}-{date_part}"
        hms, frac = time_part.split(".")
        dt = datetime.strptime(f"{date_part} {hms}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)
        return dt.timestamp() + int(frac) / 10 ** len(frac)
    except ValueError:
        return None
