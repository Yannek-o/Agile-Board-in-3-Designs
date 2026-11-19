"""Sprint burndown reconstructed from the status history.

No daily snapshot job is needed: for every day of the sprint the remaining
story points are derived from the ``status`` entries of the activity log and
from the time each item joined the sprint.
"""

from collections import defaultdict
from datetime import date, timedelta
from math import ceil

from django.utils import timezone

from apps.activity.models import ActivityEvent
from apps.backlog.models import BacklogItem
from apps.sprints.models import Sprint

DONE_LABEL = BacklogItem.Status.DONE.label

CHART_WIDTH = 1000
CHART_HEIGHT = 260
CHART_PADDING = {"left": 40, "right": 20, "top": 16, "bottom": 30}
GRID_STEPS = 4
MAX_DAY_LABELS = 7


def done_at_end_of(day: date, events: list, current_status: str) -> bool:
    last_before = None
    for event in events:
        if timezone.localdate(event.created_at) <= day:
            last_before = event
        else:
            break
    if last_before is not None:
        return last_before.new_value == DONE_LABEL
    if events:
        return events[0].old_value == DONE_LABEL
    return current_status == BacklogItem.Status.DONE


def entry_points(sprint: Sprint, entry) -> int:
    if not sprint.is_open and entry.points_at_close is not None:
        return entry.points_at_close
    return entry.item.story_points or 0


def entry_start_day(sprint: Sprint, entry) -> date:
    if sprint.started_at and entry.added_at <= sprint.started_at:
        return sprint.start_date
    return max(timezone.localdate(entry.added_at), sprint.start_date)


def sprint_burndown(sprint: Sprint, today: date | None = None) -> dict | None:
    if sprint.started_at is None:
        return None
    today = today or timezone.localdate()
    last_day = min(today, sprint.end_date)
    if sprint.closed_at:
        last_day = min(last_day, timezone.localdate(sprint.closed_at))

    entries = list(sprint.committed_entries().select_related("item"))
    events_by_item = defaultdict(list)
    for event in ActivityEvent.objects.filter(
        item_id__in=[entry.item_id for entry in entries],
        action=ActivityEvent.Action.STATUS_CHANGED,
        field="status",
    ).order_by("created_at", "pk"):
        events_by_item[event.item_id].append(event)

    days = [
        sprint.start_date + timedelta(days=offset)
        for offset in range((sprint.end_date - sprint.start_date).days + 1)
    ]
    initial_scope = sum(
        entry_points(sprint, entry)
        for entry in entries
        if entry_start_day(sprint, entry) <= sprint.start_date
    )
    rows = []
    for index, day in enumerate(days):
        ideal = initial_scope * (1 - index / max(len(days) - 1, 1))
        remaining = None
        if day <= last_day:
            remaining = 0
            for entry in entries:
                if entry_start_day(sprint, entry) > day:
                    continue
                status_at_close = entry.status_at_close or entry.item.status
                done = done_at_end_of(
                    day, events_by_item[entry.item_id], status_at_close
                )
                if not done:
                    remaining += entry_points(sprint, entry)
        rows.append({"day": day, "ideal": round(ideal, 1), "remaining": remaining})
    today_index = None
    if sprint.is_open and sprint.start_date <= today <= sprint.end_date:
        today_index = (today - sprint.start_date).days
    return {
        "rows": rows,
        "initial_scope": initial_scope,
        **_chart(rows, today_index),
    }


def nice_step(raw_step: float) -> int:
    """Smallest 1/2/5·10^n step that is at least ``raw_step``."""
    magnitude = 1
    while True:
        for factor in (1, 2, 5):
            if factor * magnitude >= raw_step:
                return factor * magnitude
        magnitude *= 10


def day_label_indexes(count: int) -> set[int]:
    every = max(ceil(count / MAX_DAY_LABELS), 1)
    indexes = {index for index in range(0, count, every)}
    last = count - 1
    indexes = {index for index in indexes if last - index >= every / 2}
    indexes.add(last)
    return indexes


def _chart(rows: list[dict], today_index: int | None = None) -> dict:
    highest = max(
        [row["ideal"] for row in rows]
        + [row["remaining"] or 0 for row in rows]
        + [1]
    )
    step = nice_step(highest / GRID_STEPS)
    max_value = step * ceil(highest / step)
    plot_width = CHART_WIDTH - CHART_PADDING["left"] - CHART_PADDING["right"]
    plot_height = CHART_HEIGHT - CHART_PADDING["top"] - CHART_PADDING["bottom"]
    day_step = plot_width / max(len(rows) - 1, 1)
    plot_bottom = CHART_HEIGHT - CHART_PADDING["bottom"]

    def x(index: int) -> float:
        return round(CHART_PADDING["left"] + index * day_step, 1)

    def y(value: float) -> float:
        return round(
            CHART_PADDING["top"] + plot_height * (1 - value / max_value), 1
        )

    ideal = " ".join(f"{x(i)},{y(row['ideal'])}" for i, row in enumerate(rows))
    day_points = [
        {
            "x": x(i),
            "y": y(row["remaining"]),
            "day": row["day"],
            "remaining": row["remaining"],
            "ideal": row["ideal"],
        }
        for i, row in enumerate(rows)
        if row["remaining"] is not None
    ]
    actual_points = " ".join(f"{p['x']},{p['y']}" for p in day_points)
    area_points = ""
    if day_points:
        area_points = (
            f"{day_points[0]['x']},{plot_bottom} {actual_points} "
            f"{day_points[-1]['x']},{plot_bottom}"
        )
    plan_delta = None
    if day_points:
        plan_delta = round(day_points[-1]["remaining"] - day_points[-1]["ideal"], 1)
    label_indexes = day_label_indexes(len(rows))
    return {
        "width": CHART_WIDTH,
        "height": CHART_HEIGHT,
        "max_value": max_value,
        "plan_delta_abs": abs(plan_delta) if plan_delta is not None else None,
        "gridlines": [
            {"value": value, "y": y(value)}
            for value in range(0, max_value + 1, step)
        ],
        "day_ticks": [
            {"x": x(i), "day": row["day"], "labeled": i in label_indexes}
            for i, row in enumerate(rows)
        ],
        "ideal_points": ideal,
        "actual_points": actual_points,
        "area_points": area_points,
        "day_points": day_points,
        "plan_delta": plan_delta,
        "today_x": x(today_index) if today_index is not None else None,
        "plot_left": CHART_PADDING["left"],
        "plot_right": CHART_WIDTH - CHART_PADDING["right"],
        "plot_top": CHART_PADDING["top"],
        "plot_bottom": plot_bottom,
        "label_y": CHART_HEIGHT - 8,
    }
