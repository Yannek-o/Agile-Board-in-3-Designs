"""Reusable backlog query helpers shared by backlog, sprint, board and reports."""

from django.db.models import (
    Case,
    Count,
    IntegerField,
    Q,
    QuerySet,
    Sum,
    Value,
    When,
)
from django.http import QueryDict
from django.db.models.functions import Coalesce

from apps.backlog.models import BacklogItem
from apps.core.numbers import percent

PRIORITY_ORDER = Case(
    When(priority=BacklogItem.Priority.CRITICAL, then=Value(0)),
    When(priority=BacklogItem.Priority.HIGH, then=Value(1)),
    When(priority=BacklogItem.Priority.MEDIUM, then=Value(2)),
    default=Value(3),
    output_field=IntegerField(),
)

FILTER_PARAMS = (
    "q", "type", "priority", "status", "assignee", "label", "epic", "release",
    "blocked",
)
SAVED_FILTER_PARAMS = (*FILTER_PARAMS, "sort", "archived")


def clean_filter_query(raw_query: str) -> str:
    """Keeps only known, non-empty filter parameters in their original order."""
    params = QueryDict(raw_query.lstrip("?"))
    kept = QueryDict(mutable=True)
    for name, values in params.lists():
        if name in SAVED_FILTER_PARAMS:
            kept.setlist(name, [value for value in values if value])
    return kept.urlencode()


def release_progress(project) -> list[dict]:
    """Items and story points per release, archived items excluded."""
    active = Q(items__archived_at__isnull=True)
    done = active & Q(items__status=BacklogItem.Status.DONE)
    releases = project.releases.annotate(
        item_count=Count("items", filter=active),
        done_count=Count("items", filter=done),
        total_points=Coalesce(Sum("items__story_points", filter=active), 0),
        done_points=Coalesce(Sum("items__story_points", filter=done), 0),
    )
    return [
        {
            "release": release,
            "items": release.item_count,
            "done_items": release.done_count,
            "open_items": release.item_count - release.done_count,
            "points": release.total_points,
            "done_points": release.done_points,
            "percent": percent(release.done_count, release.item_count),
        }
        for release in releases
    ]


def epic_progress(project) -> list[dict]:
    """Item count and story point progress per active epic (direct children)."""
    active = Q(children__archived_at__isnull=True)
    done = active & Q(children__status=BacklogItem.Status.DONE)
    epics = (
        project.items.active()
        .filter(item_type=BacklogItem.ItemType.EPIC)
        .annotate(
            item_count=Count("children", filter=active),
            done_count=Count("children", filter=done),
            total_points=Coalesce(Sum("children__story_points", filter=active), 0),
            done_points=Coalesce(Sum("children__story_points", filter=done), 0),
        )
        .order_by("backlog_rank", "number")
    )
    return [
        {
            "epic": epic,
            "items": epic.item_count,
            "done_items": epic.done_count,
            "total_points": epic.total_points,
            "done_points": epic.done_points,
            "open_points": epic.total_points - epic.done_points,
            "percent": percent(epic.done_points, epic.total_points),
        }
        for epic in epics
    ]


def apply_backlog_filters(queryset: QuerySet, params, project) -> QuerySet:
    """Applies whitelisted GET filters; unknown values are ignored."""
    search = params.get("q", "").strip()
    if search:
        search_filter = Q(title__icontains=search) | Q(
            description__icontains=search
        )
        prefix = f"{project.key}-"
        candidate = search.upper()
        if candidate.startswith(prefix) and candidate[len(prefix):].isdigit():
            search_filter = Q(number=int(candidate[len(prefix):]))
        elif search.isdigit():
            search_filter |= Q(number=int(search))
        queryset = queryset.filter(search_filter)
    choice_filters = {
        "type": ("item_type", BacklogItem.ItemType.values),
        "priority": ("priority", BacklogItem.Priority.values),
        "status": ("status", BacklogItem.Status.values),
    }
    for param, (field, allowed) in choice_filters.items():
        value = params.get(param, "")
        if value in allowed:
            queryset = queryset.filter(**{field: value})
    assignee = params.get("assignee", "")
    if assignee == "none":
        queryset = queryset.filter(assignee__isnull=True)
    elif assignee.isdigit():
        queryset = queryset.filter(assignee_id=int(assignee))
    label = params.get("label", "")
    if label.isdigit():
        queryset = queryset.filter(labels__id=int(label))
    epic = params.get("epic", "")
    if epic.isdigit():
        queryset = queryset.filter(
            Q(parent_id=int(epic)) | Q(parent__parent_id=int(epic))
        )
    release = params.get("release", "")
    if release.isdigit():
        queryset = queryset.filter(fix_version_id=int(release))
    if params.get("blocked") == "1":
        queryset = queryset.filter(is_blocked=True)
    return queryset
