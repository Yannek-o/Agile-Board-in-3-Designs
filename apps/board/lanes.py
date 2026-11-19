"""Swimlanes and quick filters for the sprint board."""

from datetime import timedelta
from urllib.parse import urlencode

from django.db.models import QuerySet
from django.utils import timezone

from apps.backlog.models import BacklogItem

Status = BacklogItem.Status
Priority = BacklogItem.Priority

QUICK_FILTERS = {
    "mine": "Nur meine",
    "recent": "Zuletzt geändert",
    "overdue": "Überfällig",
}
SWIMLANES = {
    "none": "Keine",
    "assignee": "Bearbeiter",
    "epic": "Epic",
    "priority": "Priorität",
}
PRIORITY_RANK = {
    Priority.CRITICAL: 0, Priority.HIGH: 1, Priority.MEDIUM: 2, Priority.LOW: 3,
}
RECENT_WINDOW = timedelta(hours=24)


def active_quick_filters(params) -> list[str]:
    return [key for key in params.getlist("quick") if key in QUICK_FILTERS]


def selected_swimlane(params) -> str:
    value = params.get("swimlane", "none")
    return value if value in SWIMLANES else "none"


def apply_quick_filters(queryset: QuerySet, keys: list[str], user) -> QuerySet:
    if "mine" in keys:
        queryset = queryset.filter(assignee=user)
    if "recent" in keys:
        queryset = queryset.filter(updated_at__gte=timezone.now() - RECENT_WINDOW)
    if "overdue" in keys:
        queryset = queryset.filter(due_date__lt=timezone.localdate()).exclude(
            status=Status.DONE
        )
    return queryset


def wip_status_info(items: list, project) -> dict[str, dict]:
    """Board-wide card count and WIP limit per status, independent of lanes."""
    info = {}
    for value, _ in Status.choices:
        total = sum(1 for item in items if item.status == value)
        limit = project.wip_limit_for(value)
        info[value] = {
            "status_total": total,
            "wip_limit": limit,
            "over_limit": bool(limit and total > limit),
        }
    return info


def board_statuses(project, items: list) -> list[tuple[str, str]]:
    """Columns of the board; a disabled review column stays while it has cards."""
    in_review = any(item.status == Status.IN_REVIEW for item in items)
    return [
        (value, project.status_label(value))
        for value in Status.values
        if value != Status.IN_REVIEW or project.use_review_column or in_review
    ]


def build_columns(
    items: list, wip_info: dict | None = None, statuses: list | None = None
) -> list[dict]:
    wip_info = wip_info or {}
    return [
        {
            "status": value,
            "label": label,
            "items": [item for item in items if item.status == value],
            **wip_info.get(
                value,
                {"status_total": None, "wip_limit": None, "over_limit": False},
            ),
        }
        for value, label in (statuses or Status.choices)
    ]


def _lane_key(item, swimlane: str):
    if swimlane == "assignee":
        if item.assignee is None:
            return (1, ""), "Nicht zugewiesen"
        name = item.assignee.display_name
        return (0, name.lower()), name
    if swimlane == "epic":
        epic = item.epic
        if epic is None:
            return (1, 0), "Ohne Epic"
        return (0, epic.number), epic.title
    return (PRIORITY_RANK.get(item.priority, 9), ""), item.get_priority_display()


def build_lanes(
    items: list,
    swimlane: str,
    wip_info: dict | None = None,
    statuses: list | None = None,
) -> list[dict]:
    """Groups items into lanes; without swimlanes one unlabeled lane remains."""
    if swimlane == "none":
        return [{"key": "all", "label": None, "items": items,
                 "columns": build_columns(items, wip_info, statuses)}]
    groups: dict = {}
    for item in items:
        sort_key, label = _lane_key(item, swimlane)
        groups.setdefault(sort_key, {"label": label, "items": []})
        groups[sort_key]["items"].append(item)
    return [
        {
            "key": f"lane-{index}",
            "label": group["label"],
            "items": group["items"],
            "columns": build_columns(group["items"], wip_info, statuses),
        }
        for index, (_, group) in enumerate(sorted(groups.items()))
    ]


def _url_with(params, **changes) -> str:
    query = params.copy()
    for key, values in changes.items():
        query.setlist(key, values)
    return "?" + urlencode(
        [(key, value) for key in query for value in query.getlist(key) if value]
    )


def quick_filter_chips(params, active: list[str]) -> list[dict]:
    chips = []
    for key, label in QUICK_FILTERS.items():
        toggled = [k for k in active if k != key] if key in active else active + [key]
        chips.append(
            {
                "key": key,
                "label": label,
                "active": key in active,
                "url": _url_with(params, quick=toggled),
            }
        )
    return chips


def swimlane_options(params, current: str) -> list[dict]:
    return [
        {
            "key": key,
            "label": label,
            "active": key == current,
            "url": _url_with(params, swimlane=[] if key == "none" else [key]),
        }
        for key, label in SWIMLANES.items()
    ]
