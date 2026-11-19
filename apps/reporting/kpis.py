"""Dashboard key figure tiles: daily snapshots, trend and sparkline."""

from dataclasses import dataclass
from datetime import date, timedelta

from django.utils import timezone

from apps.reporting.models import DashboardSnapshot

SNAPSHOT_RETENTION_DAYS = 60
SPARKLINE_DAYS = 14
TREND_DAYS = 7
SPARKLINE_WIDTH = 100
SPARKLINE_HEIGHT = 28
SPARKLINE_PADDING = 2

NEUTRAL = "neutral"
HIGHER_IS_BETTER = "higher_is_better"
LOWER_IS_BETTER = "lower_is_better"


@dataclass(frozen=True)
class KpiDefinition:
    key: str
    label: str
    icon: str
    polarity: str


KPI_DEFINITIONS = (
    KpiDefinition("active_projects", "Aktive Projekte", "projects", NEUTRAL),
    KpiDefinition("my_open_items", "Meine offenen Aufgaben", "tasks", NEUTRAL),
    KpiDefinition("running_sprints", "Laufende Sprints", "sprints", NEUTRAL),
    KpiDefinition("sprint_done", "Im Sprint erledigt", "done", HIGHER_IS_BETTER),
    KpiDefinition(
        "high_priority_open", "Hohe Priorität offen", "priority", LOWER_IS_BETTER
    ),
    KpiDefinition("blocked_items", "Blockiert", "blocked", LOWER_IS_BETTER),
)
SNAPSHOT_KEYS = tuple(definition.key for definition in KPI_DEFINITIONS) + (
    "sprint_total",
)


def record_dashboard_snapshot(user, metrics: dict, today: date | None = None) -> None:
    today = today or timezone.localdate()
    values = {key: int(metrics.get(key) or 0) for key in SNAPSHOT_KEYS}
    DashboardSnapshot.objects.update_or_create(
        user=user, day=today, defaults={"metrics": values}
    )
    DashboardSnapshot.objects.filter(
        user=user, day__lt=today - timedelta(days=SNAPSHOT_RETENTION_DAYS)
    ).delete()


def kpi_tiles(user, metrics: dict, today: date | None = None) -> list[dict]:
    today = today or timezone.localdate()
    history = list(
        DashboardSnapshot.objects.filter(user=user, day__lt=today).order_by("day")
    )
    return [
        _tile(definition, metrics, history, today) for definition in KPI_DEFINITIONS
    ]


def _tile(definition: KpiDefinition, metrics: dict, history: list, today: date):
    current = int(metrics.get(definition.key) or 0)
    series = [
        (snapshot.day, int(snapshot.metrics.get(definition.key) or 0))
        for snapshot in history
        if definition.key in snapshot.metrics
    ]
    return {
        "key": definition.key,
        "label": definition.label,
        "icon": definition.icon,
        "value": _display_value(definition.key, metrics),
        "signal": _signal(definition.key, metrics),
        "trend": _trend(definition.polarity, current, series, today),
        "sparkline": _sparkline(series + [(today, current)], today),
    }


def _display_value(key: str, metrics: dict) -> str:
    value = int(metrics.get(key) or 0)
    if key == "sprint_done":
        return f"{value} / {int(metrics.get('sprint_total') or 0)}"
    return str(value)


def _signal(key: str, metrics: dict) -> str | None:
    if key == "blocked_items" and metrics.get("blocked_items"):
        return "danger"
    if key == "high_priority_open" and metrics.get("high_priority_open"):
        return "warning"
    total = metrics.get("sprint_total") or 0
    if key == "sprint_done" and total and metrics.get("sprint_done") == total:
        return "success"
    return None


def _trend(polarity: str, current: int, series: list, today: date) -> dict | None:
    """Change against the value one week ago, or the oldest known value."""
    if not series:
        return None
    week_ago = today - timedelta(days=TREND_DAYS)
    older = [entry for entry in series if entry[0] <= week_ago]
    since, previous = older[-1] if older else series[0]
    delta = current - previous
    return {
        "delta": delta,
        "display": _signed(delta),
        "since": since,
        "tone": _tone(polarity, delta),
    }


def _signed(delta: int) -> str:
    if delta > 0:
        return f"+{delta}"
    if delta < 0:
        return f"\u2212{abs(delta)}"
    return "\u00b10"


def _tone(polarity: str, delta: int) -> str:
    if delta == 0 or polarity == NEUTRAL:
        return NEUTRAL
    improved = (delta > 0) == (polarity == HIGHER_IS_BETTER)
    return "success" if improved else "danger"


def _sparkline(series: list, today: date) -> dict | None:
    first_day = today - timedelta(days=SPARKLINE_DAYS - 1)
    window = [(day, value) for day, value in series if day >= first_day]
    if len(window) < 2:
        return None
    values = [value for _, value in window]
    low, high = min(values), max(values)
    usable = SPARKLINE_HEIGHT - 2 * SPARKLINE_PADDING

    def x(day: date) -> float:
        return (day - first_day).days / (SPARKLINE_DAYS - 1) * SPARKLINE_WIDTH

    def y(value: int) -> float:
        share = 0.5 if high == low else (value - low) / (high - low)
        return SPARKLINE_PADDING + (1 - share) * usable

    coordinates = [(f"{x(day):.1f}", f"{y(value):.1f}") for day, value in window]
    points = " ".join(f"{cx},{cy}" for cx, cy in coordinates)
    last_x, last_y = coordinates[-1]
    return {
        "points": points,
        "area": f"{coordinates[0][0]},{SPARKLINE_HEIGHT} {points} "
        f"{last_x},{SPARKLINE_HEIGHT}",
        "last_x": last_x,
        "last_y": last_y,
    }
