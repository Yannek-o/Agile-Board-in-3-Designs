"""Parsing and formatting of work durations in the Jira style (1d 2h 30m).

One working day counts as eight hours. A bare number means minutes.
"""

import re

from django.core.exceptions import ValidationError

MINUTES_PER_HOUR = 60
MINUTES_PER_DAY = 8 * MINUTES_PER_HOUR
UNIT_MINUTES = {"d": MINUTES_PER_DAY, "h": MINUTES_PER_HOUR, "m": 1}
DURATION_PART = re.compile(r"(\d+(?:[.,]\d+)?)\s*(d|h|min|m)?", re.IGNORECASE)
INVALID_DURATION = (
    "Bitte eine Dauer wie „1h 30m“, „2h“, „45m“ oder „1d“ angeben."
)


def parse_duration(text: str) -> int:
    """Returns the duration in whole minutes; raises ValidationError otherwise."""
    cleaned = (text or "").strip().lower()
    if not cleaned:
        raise ValidationError(INVALID_DURATION)
    total = 0.0
    position = 0
    previous_unit = None
    for match in DURATION_PART.finditer(cleaned):
        if cleaned[position:match.start()].strip():
            raise ValidationError(INVALID_DURATION)
        value = float(match.group(1).replace(",", "."))
        unit = (match.group(2) or "").replace("min", "m")
        if not unit:
            # "2h15" means 2 h 15 min; a lone number means minutes.
            unit = "m" if previous_unit in (None, "h") else None
            if unit is None:
                raise ValidationError(INVALID_DURATION)
        total += value * UNIT_MINUTES[unit]
        previous_unit = unit
        position = match.end()
    if cleaned[position:].strip() or position == 0:
        raise ValidationError(INVALID_DURATION)
    minutes = round(total)
    if minutes <= 0:
        raise ValidationError("Die Dauer muss größer als null sein.")
    return minutes


def format_minutes(minutes: int | None) -> str:
    if minutes is None:
        return "–"
    if minutes == 0:
        return "0m"
    days, rest = divmod(minutes, MINUTES_PER_DAY)
    hours, mins = divmod(rest, MINUTES_PER_HOUR)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if mins:
        parts.append(f"{mins}m")
    return " ".join(parts)
