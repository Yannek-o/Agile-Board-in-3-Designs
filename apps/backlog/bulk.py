"""Applies one change to many backlog items, item by item through the services."""

from dataclasses import dataclass, field

from django.core.exceptions import ValidationError

from apps.backlog.models import BacklogItem, Release
from apps.backlog.services import (
    ConcurrentModificationError,
    archive_item,
    update_backlog_item,
)

STATUS_ACTIONS = ("status",)
BACKLOG_ACTIONS = ("assignee", "priority", "sprint", "release", "archive")
BULK_ACTIONS = (*STATUS_ACTIONS, *BACKLOG_ACTIONS)
NONE_VALUE = "none"


class BulkActionError(ValueError):
    """The requested action or its value is invalid as a whole."""


@dataclass
class BulkResult:
    changed: int = 0
    failures: list[str] = field(default_factory=list)


def resolve_value(project, action: str, raw_value: str):
    """Turns the submitted value into the object the services expect."""
    from apps.sprints.models import Sprint

    if action == "archive":
        return None
    if action == "status":
        if raw_value not in BacklogItem.Status.values:
            raise BulkActionError("Ungültiger Status.")
        return raw_value
    if action == "priority":
        if raw_value not in BacklogItem.Priority.values:
            raise BulkActionError("Ungültige Priorität.")
        return raw_value
    if raw_value == NONE_VALUE:
        return None
    lookups = {
        "assignee": lambda: project.active_members().get(user_id=raw_value).user,
        "sprint": lambda: project.sprints.get(
            number=raw_value, status__in=Sprint.OPEN_STATUSES
        ),
        "release": lambda: project.releases.get(
            pk=raw_value, status=Release.Status.UNRELEASED
        ),
    }
    try:
        return lookups[action]()
    except (ValueError, KeyError, project.memberships.model.DoesNotExist,
            Sprint.DoesNotExist, Release.DoesNotExist) as error:
        raise BulkActionError("Ungültige Auswahl.") from error


def apply_bulk_action(items, action: str, value, actor) -> BulkResult:
    """Changes every item; failures are collected instead of aborting the rest."""
    from apps.sprints.services import SprintError, move_item_to_sprint

    if action not in BULK_ACTIONS:
        raise BulkActionError("Unbekannte Aktion.")
    result = BulkResult()
    for item in items:
        try:
            if action == "archive":
                archive_item(item, actor=actor)
            elif action == "sprint":
                move_item_to_sprint(item, value, actor=actor)
            else:
                field_name = "fix_version" if action == "release" else action
                update_backlog_item(
                    item, actor=actor, expected_version=None, **{field_name: value}
                )
        except ValidationError as error:
            result.failures.append(f"{item.key}: {' '.join(error.messages)}")
        except (SprintError, ConcurrentModificationError) as error:
            result.failures.append(f"{item.key}: {error}")
        else:
            result.changed += 1
    return result
