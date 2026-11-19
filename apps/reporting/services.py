"""Read-only aggregations for the dashboard and project reports."""

from collections import defaultdict
from itertools import chain

from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.backlog.models import BacklogItem
from apps.backlog.queries import PRIORITY_ORDER
from apps.core.numbers import percent
from apps.projects.models import Project
from apps.projects.permissions import visible_projects
from apps.reporting.burndown import sprint_burndown
from apps.reporting.charts import cumulative_flow, sprint_burnup, velocity_chart
from apps.sprints.models import Sprint, SprintItem

METRIC_DETAIL_LIMIT = 25


def sprint_progress(sprint: Sprint) -> dict:
    counts = sprint.open_items().aggregate(
        total=Count("id"), done=Count("id", filter=Q(status=BacklogItem.Status.DONE))
    )
    return {
        "sprint": sprint,
        "total": counts["total"],
        "done": counts["done"],
        "percent": percent(counts["done"], counts["total"]),
    }


def _points_per_sprint_and_status(sprints: list[Sprint]) -> dict:
    """Open sprints use live item values, closed sprints the completion snapshot."""
    open_ids = [sprint.pk for sprint in sprints if sprint.is_open]
    closed_ids = [sprint.pk for sprint in sprints if not sprint.is_open]
    open_rows = (
        SprintItem.objects.filter(
            sprint_id__in=open_ids, outcome=SprintItem.Outcome.OPEN
        )
        .order_by()
        .values_list("sprint_id", "item__status")
        .annotate(points=Sum("item__story_points"))
    )
    closed_rows = (
        SprintItem.objects.filter(sprint_id__in=closed_ids)
        .exclude(outcome=SprintItem.Outcome.REMOVED)
        .order_by()
        .values_list("sprint_id", "status_at_close")
        .annotate(points=Sum("points_at_close"))
    )
    points = defaultdict(dict)
    for sprint_id, status, status_points in chain(open_rows, closed_rows):
        points[sprint_id][status] = status_points or 0
    return points


def sprint_point_breakdowns(sprints) -> dict[int, dict]:
    sprints = list(sprints)
    points = _points_per_sprint_and_status(sprints)
    today = timezone.localdate()
    breakdowns = {}
    for sprint in sprints:
        by_status = points[sprint.pk]
        segments = [
            {"status": status, "label": label, "points": by_status[status]}
            for status, label in BacklogItem.Status.choices
            if by_status.get(status)
        ]
        total = sum(segment["points"] for segment in segments)
        done = by_status.get(BacklogItem.Status.DONE, 0)
        is_active = sprint.status == Sprint.Status.ACTIVE
        breakdowns[sprint.pk] = {
            "segments": segments,
            "total": total,
            "done": done,
            "percent": percent(done, total),
            "days_left": max((sprint.end_date - today).days, 0) if is_active else None,
        }
    return breakdowns


def dashboard_data(user) -> dict:
    projects = visible_projects(user).not_archived()
    open_items = BacklogItem.objects.open().filter(project__in=projects)
    my_open_items = open_items.filter(assignee=user)
    active_sprints = Sprint.objects.filter(
        project__in=projects, status=Sprint.Status.ACTIVE
    ).select_related("project")
    sprint_items = BacklogItem.objects.active().filter(
        sprint_entries__outcome=SprintItem.Outcome.OPEN,
        sprint_entries__sprint__in=active_sprints,
    )
    sprint_counts = sprint_items.aggregate(
        total=Count("id"), done=Count("id", filter=Q(status=BacklogItem.Status.DONE))
    )
    active_projects = projects.filter(status=Project.Status.ACTIVE)
    high_priority_open = open_items.filter(priority__in=BacklogItem.HIGH_PRIORITIES)
    blocked_items = open_items.filter(is_blocked=True)
    sprint_done = sprint_items.filter(status=BacklogItem.Status.DONE)
    return {
        "metrics": {
            "active_projects": active_projects.count(),
            "running_sprints": active_sprints.count(),
            "my_open_items": my_open_items.count(),
            "high_priority_open": high_priority_open.count(),
            "blocked_items": blocked_items.count(),
            "sprint_done": sprint_counts["done"],
            "sprint_total": sprint_counts["total"],
        },
        "metric_details": {
            "active_projects": active_projects.order_by("name"),
            "my_open_items": my_open_items.select_related("project")
            .annotate(priority_order=PRIORITY_ORDER)
            .order_by("priority_order", "due_date", "backlog_rank")[
                :METRIC_DETAIL_LIMIT
            ],
            "high_priority_open": high_priority_open.select_related(
                "project", "assignee"
            ).order_by("project__key", "number")[:METRIC_DETAIL_LIMIT],
            "blocked_items": blocked_items.select_related(
                "project", "assignee"
            ).order_by("project__key", "number")[:METRIC_DETAIL_LIMIT],
            "sprint_done": sprint_done.select_related("project", "assignee")
            .order_by("project__key", "number")[:METRIC_DETAIL_LIMIT],
        },
        "my_next_items": my_open_items.select_related("project")
        .annotate(priority_order=PRIORITY_ORDER)
        .order_by("priority_order", "due_date", "backlog_rank")[:8],
        "active_sprints": [sprint_progress(sprint) for sprint in active_sprints],
        "recent_items": BacklogItem.objects.active()
        .filter(project__in=projects)
        .select_related("project", "assignee")
        .order_by("-updated_at")[:8],
        "projects": projects.order_by("name")[:6],
    }


VELOCITY_SPRINTS = 3
# Planning more than this factor above the velocity triggers the warning.
CAPACITY_TOLERANCE = 1.15


def average_velocity(completed_points_newest_first: list[int]) -> float | None:
    recent = completed_points_newest_first[:VELOCITY_SPRINTS]
    return round(sum(recent) / len(recent), 1) if recent else None


def sprint_capacity(sprint: Sprint) -> dict:
    """Planned story points of an open sprint compared to the recent velocity."""
    previous = list(
        sprint.project.sprints.filter(
            status=Sprint.Status.COMPLETED, number__lt=sprint.number
        ).order_by("-number")[:VELOCITY_SPRINTS]
    )
    velocity = average_velocity([done.completed_points() for done in previous])
    planned = sprint.committed_points()
    return {
        "planned": planned,
        "velocity": velocity,
        "sprints": len(previous),
        "over": velocity is not None and planned > velocity * CAPACITY_TOLERANCE,
    }


def project_report(project: Project) -> dict:
    items = BacklogItem.objects.active().filter(project=project)
    status_counts = dict(
        items.values_list("status").annotate(count=Count("id")).order_by()
    )
    type_counts = dict(
        items.values_list("item_type").annotate(count=Count("id")).order_by()
    )
    closed_sprints = list(
        project.sprints.filter(status=Sprint.Status.COMPLETED).order_by("-number")
    )
    sprint_rows = [
        {
            "sprint": sprint,
            "committed": sprint.committed_points(),
            "completed": sprint.completed_points(),
            "items": sprint.committed_entries().count(),
            "items_done": sprint.entries.filter(
                outcome=SprintItem.Outcome.COMPLETED
            ).count(),
        }
        for sprint in closed_sprints
    ]
    for row in sprint_rows:
        row["percent"] = percent(row["completed"], row["committed"])
    velocity = average_velocity([row["completed"] for row in sprint_rows])
    workload = (
        items.exclude(status=BacklogItem.Status.DONE)
        .values("assignee__username", "assignee__first_name", "assignee__last_name")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    active_sprint = project.sprints.filter(status=Sprint.Status.ACTIVE).first()
    burndown_sprint = active_sprint or (closed_sprints[0] if closed_sprints else None)
    total = items.count()
    return {
        "burndown": sprint_burndown(burndown_sprint) if burndown_sprint else None,
        "burnup": sprint_burnup(burndown_sprint) if burndown_sprint else None,
        "velocity_data": velocity_chart(project),
        "flow": cumulative_flow(project),
        "burndown_sprint": burndown_sprint,
        "status_rows": [
            {
                "label": label,
                "count": status_counts.get(value, 0),
                "percent": percent(status_counts.get(value, 0), total),
            }
            for value, label in BacklogItem.Status.choices
        ],
        "type_rows": [
            {"label": label, "count": type_counts.get(value, 0)}
            for value, label in BacklogItem.ItemType.choices
        ],
        "item_total": total,
        "sprint_rows": sprint_rows,
        "velocity": velocity,
        "workload": workload,
        "active_progress": sprint_progress(active_sprint) if active_sprint else None,
        "blocked_count": items.filter(is_blocked=True).count(),
    }
