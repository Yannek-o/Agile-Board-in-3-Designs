"""Sprint report: what was finished, what not, and how the scope changed."""

from apps.backlog.models import BacklogItem
from apps.core.numbers import percent
from apps.sprints.models import Sprint, SprintItem

Outcome = SprintItem.Outcome
NOT_COMPLETED_OUTCOMES = (Outcome.CARRIED_OVER, Outcome.RETURNED, Outcome.CANCELLED)


def _points(sprint: Sprint, entry: SprintItem) -> int:
    if not sprint.is_open and entry.points_at_close is not None:
        return entry.points_at_close
    return entry.item.story_points or 0


def _added_after_start(sprint: Sprint, entry: SprintItem) -> bool:
    return entry.added_at > sprint.started_at


def _is_completed(sprint: Sprint, entry: SprintItem) -> bool:
    if entry.outcome == Outcome.COMPLETED:
        return True
    return (
        sprint.is_open
        and entry.outcome == Outcome.OPEN
        and entry.item.status == BacklogItem.Status.DONE
    )


def _row(sprint: Sprint, entry: SprintItem) -> dict:
    return {
        "item": entry.item,
        "points": _points(sprint, entry),
        "outcome": entry.get_outcome_display(),
        "added_late": _added_after_start(sprint, entry),
    }


def sprint_report(sprint: Sprint) -> dict | None:
    """Groups the sprint entries; ``None`` until the sprint has been started."""
    if sprint.started_at is None:
        return None
    entries = list(
        sprint.entries.select_related("item", "item__project", "item__assignee")
        .order_by("added_at", "pk")
    )
    completed, not_completed, added, removed = [], [], [], []
    for entry in entries:
        row = _row(sprint, entry)
        if entry.outcome == Outcome.REMOVED:
            if entry.closed_at and entry.closed_at >= sprint.started_at:
                removed.append(row)
            continue
        if row["added_late"]:
            added.append(row)
        if _is_completed(sprint, entry):
            completed.append(row)
        elif entry.outcome in (Outcome.OPEN, *NOT_COMPLETED_OUTCOMES):
            not_completed.append(row)

    committed_at_start = sum(
        _points(sprint, entry)
        for entry in entries
        if not _added_after_start(sprint, entry)
    )
    added_points = sum(row["points"] for row in added)
    removed_points = sum(row["points"] for row in removed)
    completed_points = sum(row["points"] for row in completed)
    final_scope = committed_at_start + added_points - removed_points
    return {
        "completed": completed,
        "not_completed": not_completed,
        "added": added,
        "removed": removed,
        "summary": {
            "committed_at_start": committed_at_start,
            "added": added_points,
            "removed": removed_points,
            "final_scope": final_scope,
            "completed": completed_points,
            "percent": percent(completed_points, final_scope),
        },
    }
