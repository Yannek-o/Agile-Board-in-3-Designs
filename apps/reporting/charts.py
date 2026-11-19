"""Velocity, burnup and cumulative flow charts rendered as server-side SVG.

Like the burndown, all values are reconstructed from existing data (sprint
entries and the status history), so no snapshot job is required.
"""

from collections import defaultdict
from datetime import date, timedelta
from math import ceil

from django.utils import timezone

from apps.activity.models import ActivityEvent
from apps.backlog.models import BacklogItem
from apps.core.numbers import percent
from apps.reporting.burndown import (
    CHART_HEIGHT,
    CHART_PADDING,
    CHART_WIDTH,
    GRID_STEPS,
    done_at_end_of,
    entry_points,
    entry_start_day,
    day_label_indexes,
    nice_step,
)
from apps.sprints.models import Sprint

VELOCITY_SPRINTS = 8
CFD_DAYS = 30
MIN_CFD_DAYS = 7
STATUS_BY_LABEL = {label: value for value, label in BacklogItem.Status.choices}
# Stacking order of the cumulative flow bands from bottom to top.
CFD_STACK = ("done", "in_review", "in_progress", "todo")


class ChartFrame:
    """Shared axes: value scale with tidy grid steps and evenly spaced columns."""

    def __init__(self, highest: float, columns: int):
        self.step = nice_step(max(highest, 1) / GRID_STEPS)
        self.max_value = self.step * ceil(max(highest, 1) / self.step)
        self.columns = columns
        self.plot_left = CHART_PADDING["left"]
        self.plot_right = CHART_WIDTH - CHART_PADDING["right"]
        self.plot_top = CHART_PADDING["top"]
        self.plot_bottom = CHART_HEIGHT - CHART_PADDING["bottom"]
        self.plot_width = self.plot_right - self.plot_left
        self.plot_height = self.plot_bottom - self.plot_top

    def x(self, index: int) -> float:
        step = self.plot_width / max(self.columns - 1, 1)
        return round(self.plot_left + index * step, 1)

    def y(self, value: float) -> float:
        return round(self.plot_top + self.plot_height * (1 - value / self.max_value), 1)

    def height(self, value: float) -> float:
        return round(self.plot_height * value / self.max_value, 1)

    def context(self) -> dict:
        return {
            "width": CHART_WIDTH,
            "height": CHART_HEIGHT,
            "plot_left": self.plot_left,
            "plot_right": self.plot_right,
            "plot_top": self.plot_top,
            "plot_bottom": self.plot_bottom,
            "label_y": CHART_HEIGHT - 8,
            "gridlines": [
                {"value": value, "y": self.y(value)}
                for value in range(0, self.max_value + 1, self.step)
            ],
        }

    def day_ticks(self, days: list[date]) -> list[dict]:
        labeled = day_label_indexes(len(days))
        return [
            {"x": self.x(index), "day": day, "labeled": index in labeled}
            for index, day in enumerate(days)
        ]


def velocity_chart(project) -> dict | None:
    """Committed vs. completed story points of the last completed sprints."""
    sprints = list(
        project.sprints.filter(status=Sprint.Status.COMPLETED).order_by("-number")[
            :VELOCITY_SPRINTS
        ]
    )
    if not sprints:
        return None
    sprints.reverse()
    values = [
        {
            "sprint": sprint,
            "committed": sprint.committed_points(),
            "completed": sprint.completed_points(),
        }
        for sprint in sprints
    ]
    average = round(sum(row["completed"] for row in values) / len(values), 1)
    frame = ChartFrame(max(max(row["committed"] for row in values), 1), len(values))
    slot = frame.plot_width / len(values)
    bar_width = round(min(slot * 0.32, 48), 1)
    bars = []
    for index, row in enumerate(values):
        center = frame.plot_left + slot * (index + 0.5)
        bars.append(
            {
                **row,
                "label": row["sprint"].label,
                "center": round(center, 1),
                "committed_x": round(center - bar_width - 2, 1),
                "completed_x": round(center + 2, 1),
                "bar_width": bar_width,
                "committed_y": frame.y(row["committed"]),
                "committed_height": frame.height(row["committed"]),
                "completed_y": frame.y(row["completed"]),
                "completed_height": frame.height(row["completed"]),
                "percent": percent(row["completed"], row["committed"]),
            }
        )
    return {
        **frame.context(),
        "bars": bars,
        "average": average,
        "average_y": frame.y(average),
    }


def _status_events(item_ids) -> dict[int, list]:
    events = defaultdict(list)
    for event in ActivityEvent.objects.filter(
        item_id__in=item_ids,
        action=ActivityEvent.Action.STATUS_CHANGED,
        field="status",
    ).order_by("created_at", "pk"):
        events[event.item_id].append(event)
    return events


def sprint_burnup(sprint: Sprint, today: date | None = None) -> dict | None:
    """Scope line and completed line per sprint day."""
    if sprint.started_at is None:
        return None
    today = today or timezone.localdate()
    last_day = min(today, sprint.end_date)
    if sprint.closed_at:
        last_day = min(last_day, timezone.localdate(sprint.closed_at))
    entries = list(sprint.committed_entries().select_related("item"))
    events = _status_events([entry.item_id for entry in entries])
    days = [
        sprint.start_date + timedelta(days=offset)
        for offset in range((sprint.end_date - sprint.start_date).days + 1)
    ]
    rows = []
    for day in days:
        if day > last_day:
            rows.append({"day": day, "scope": None, "done": None})
            continue
        scope = done = 0
        for entry in entries:
            if entry_start_day(sprint, entry) > day:
                continue
            points = entry_points(sprint, entry)
            scope += points
            current = entry.status_at_close or entry.item.status
            if done_at_end_of(day, events[entry.item_id], current):
                done += points
        rows.append({"day": day, "scope": scope, "done": done})
    known = [row for row in rows if row["scope"] is not None]
    frame = ChartFrame(max([row["scope"] for row in known] + [1]), len(days))

    def line(key: str) -> str:
        return " ".join(
            f"{frame.x(index)},{frame.y(row[key])}"
            for index, row in enumerate(rows)
            if row[key] is not None
        )

    return {
        **frame.context(),
        "rows": rows,
        "day_ticks": frame.day_ticks(days),
        "scope_points": line("scope"),
        "done_points": line("done"),
    }


def _status_at_end_of(day: date, events: list, current: str) -> str:
    last_before = None
    for event in events:
        if timezone.localdate(event.created_at) <= day:
            last_before = event
        else:
            break
    if last_before is not None:
        return STATUS_BY_LABEL.get(last_before.new_value, current)
    if events:
        return STATUS_BY_LABEL.get(events[0].old_value, current)
    return current


def cumulative_flow(project, days: int = CFD_DAYS, today: date | None = None) -> dict:
    """Number of active items per status at the end of each of the last days.

    Young projects are shown from their first item on (at least a week), so
    the chart is not dominated by empty days.
    """
    today = today or timezone.localdate()
    items = list(
        BacklogItem.objects.active()
        .filter(project=project)
        .only("id", "status", "created_at")
    )
    if items:
        first_day = min(timezone.localdate(item.created_at) for item in items)
        age = (today - first_day).days + 1
        days = min(days, max(age, MIN_CFD_DAYS))
    day_list = [today - timedelta(days=offset) for offset in range(days - 1, -1, -1)]
    events = _status_events([item.pk for item in items])
    rows = []
    for day in day_list:
        counts = {status: 0 for status in BacklogItem.Status.values}
        for item in items:
            if timezone.localdate(item.created_at) > day:
                continue
            counts[_status_at_end_of(day, events[item.pk], item.status)] += 1
        rows.append({"day": day, "counts": counts, "total": sum(counts.values())})
    frame = ChartFrame(max([row["total"] for row in rows] + [1]), len(day_list))
    labels = dict(BacklogItem.Status.choices)
    bands = []
    lower = [0] * len(rows)
    for status in CFD_STACK:
        upper = [base + row["counts"][status] for base, row in zip(lower, rows)]
        top = [f"{frame.x(i)},{frame.y(value)}" for i, value in enumerate(upper)]
        bottom = [
            f"{frame.x(i)},{frame.y(value)}"
            for i, value in reversed(list(enumerate(lower)))
        ]
        bands.append(
            {
                "status": status,
                "label": labels[status],
                "points": " ".join(top + bottom),
                "latest": rows[-1]["counts"][status] if rows else 0,
            }
        )
        lower = upper
    return {
        **frame.context(),
        "rows": rows,
        "bands": bands,
        "day_ticks": frame.day_ticks(day_list),
    }
