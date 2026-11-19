"""Sprint lifecycle rules: planning, start, completion and cancellation."""

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.activity.models import ActivityEvent
from apps.activity.services import record_event
from apps.backlog.models import BacklogItem
from apps.notifications.services import notify_sprint_event
from apps.projects.models import Project
from apps.sprints.models import RETRO_FIELDS, Sprint, SprintItem

Outcome = SprintItem.Outcome


class SprintError(Exception):
    """A sprint operation violates a business rule."""


def create_sprint(project: Project, actor=None, **fields) -> Sprint:
    with transaction.atomic():
        locked_project = Project.objects.select_for_update().get(pk=project.pk)
        number = locked_project.next_sprint_number
        sprint = Sprint(project=project, number=number, **fields)
        sprint.full_clean()
        sprint.save()
        locked_project.next_sprint_number = number + 1
        locked_project.save(update_fields=["next_sprint_number"])
        record_event(
            project, ActivityEvent.Action.SPRINT_CREATED, actor=actor,
            sprint=sprint, message=f"{sprint.label} angelegt",
        )
    return sprint


def _lock_sprint(sprint: Sprint) -> Sprint:
    return Sprint.objects.select_for_update().select_related("project").get(
        pk=sprint.pk
    )


def _require_open(sprint: Sprint) -> None:
    if not sprint.is_open:
        raise SprintError(
            f"{sprint.label} ist {sprint.get_status_display().lower()} "
            "und kann nicht mehr geändert werden."
        )


def add_item_to_sprint(sprint: Sprint, item: BacklogItem, actor) -> SprintItem:
    with transaction.atomic():
        sprint = _lock_sprint(sprint)
        _require_open(sprint)
        item = BacklogItem.objects.select_for_update().get(pk=item.pk)
        if item.project_id != sprint.project_id:
            raise SprintError("Der Eintrag gehört zu einem anderen Projekt.")
        if item.archived_at is not None:
            raise SprintError("Archivierte Einträge können nicht eingeplant werden.")
        if item.status == BacklogItem.Status.DONE:
            raise SprintError("Erledigte Einträge können nicht eingeplant werden.")
        if item.item_type == BacklogItem.ItemType.EPIC:
            raise SprintError(
                "Epics werden nicht eingeplant – "
                "bitte die zugehörigen Stories einplanen."
            )
        already_planned = SprintItem.objects.filter(
            item=item, outcome=Outcome.OPEN, sprint__status__in=Sprint.OPEN_STATUSES
        ).select_related("sprint").first()
        if already_planned:
            raise SprintError(
                f"{item.key} ist bereits in {already_planned.sprint.label} eingeplant."
            )
        entry, created = SprintItem.objects.get_or_create(
            sprint=sprint, item=item, defaults={"added_by": actor}
        )
        if not created:
            entry.outcome = Outcome.OPEN
            entry.closed_at = None
            entry.added_by = actor
            entry.save(update_fields=["outcome", "closed_at", "added_by"])
        record_event(
            sprint.project, ActivityEvent.Action.SPRINT_ITEM_ADDED, actor=actor,
            item=item, sprint=sprint, message=f"{item.key} → {sprint.label}",
        )
    return entry


def remove_item_from_sprint(sprint: Sprint, item: BacklogItem, actor) -> None:
    with transaction.atomic():
        sprint = _lock_sprint(sprint)
        _require_open(sprint)
        entry = SprintItem.objects.filter(
            sprint=sprint, item=item, outcome=Outcome.OPEN
        ).first()
        if entry is None:
            raise SprintError(f"{item.key} ist nicht in {sprint.label} eingeplant.")
        entry.outcome = Outcome.REMOVED
        entry.closed_at = timezone.now()
        entry.save(update_fields=["outcome", "closed_at"])
        record_event(
            sprint.project, ActivityEvent.Action.SPRINT_ITEM_REMOVED, actor=actor,
            item=item, sprint=sprint, message=f"{item.key} aus {sprint.label}",
        )


def move_item_to_sprint(item: BacklogItem, target: Sprint | None, actor) -> None:
    """Moves an item into ``target`` or, with ``None``, back to the backlog."""
    current_entry = SprintItem.objects.filter(
        item=item, outcome=Outcome.OPEN, sprint__status__in=Sprint.OPEN_STATUSES
    ).select_related("sprint").first()
    current = current_entry.sprint if current_entry else None
    if (current and current.pk) == (target and target.pk):
        return
    with transaction.atomic():
        if current is not None:
            remove_item_from_sprint(current, item, actor=actor)
        if target is not None:
            add_item_to_sprint(target, item, actor=actor)


def start_sprint(sprint: Sprint, actor) -> Sprint:
    with transaction.atomic():
        sprint = _lock_sprint(sprint)
        if sprint.status != Sprint.Status.PLANNED:
            raise SprintError("Nur geplante Sprints können gestartet werden.")
        if not sprint.goal.strip():
            raise SprintError("Vor dem Start muss ein Sprint-Ziel festgelegt werden.")
        if Sprint.objects.filter(
            project_id=sprint.project_id, status=Sprint.Status.ACTIVE
        ).exists():
            raise SprintError("In diesem Projekt läuft bereits ein Sprint.")
        sprint.status = Sprint.Status.ACTIVE
        sprint.started_at = timezone.now()
        try:
            with transaction.atomic():
                sprint.save(update_fields=["status", "started_at", "updated_at"])
        except IntegrityError as error:
            raise SprintError("In diesem Projekt läuft bereits ein Sprint.") from error
        record_event(
            sprint.project, ActivityEvent.Action.SPRINT_STARTED, actor=actor,
            sprint=sprint, message=f"{sprint.label} gestartet",
        )
        notify_sprint_event(sprint, actor, "started")
    return sprint


def _close_entries(sprint: Sprint, now) -> list[SprintItem]:
    entries = list(
        sprint.entries.filter(outcome=Outcome.OPEN)
        .select_related("item")
        .select_for_update()
    )
    for entry in entries:
        entry.closed_at = now
        entry.status_at_close = entry.item.status
        entry.points_at_close = entry.item.story_points
    return entries


def complete_sprint(
    sprint: Sprint,
    actor,
    carry_over_to: Sprint | None = None,
    review_notes: str = "",
) -> Sprint:
    with transaction.atomic():
        sprint = _lock_sprint(sprint)
        if sprint.status != Sprint.Status.ACTIVE:
            raise SprintError("Nur aktive Sprints können abgeschlossen werden.")
        if carry_over_to is not None:
            carry_over_to = _lock_sprint(carry_over_to)
            if (
                carry_over_to.project_id != sprint.project_id
                or carry_over_to.status != Sprint.Status.PLANNED
            ):
                raise SprintError(
                    "Offene Arbeit kann nur in einen geplanten Sprint desselben "
                    "Projekts übernommen werden."
                )

        now = timezone.now()
        entries = _close_entries(sprint, now)
        unfinished = []
        for entry in entries:
            if entry.item.status == BacklogItem.Status.DONE:
                entry.outcome = Outcome.COMPLETED
            elif carry_over_to is not None:
                entry.outcome = Outcome.CARRIED_OVER
                unfinished.append(entry.item)
            else:
                entry.outcome = Outcome.RETURNED
        SprintItem.objects.bulk_update(
            entries, ["outcome", "closed_at", "status_at_close", "points_at_close"]
        )

        sprint.status = Sprint.Status.COMPLETED
        sprint.closed_at = now
        sprint.completed_by = actor
        sprint.review_notes = review_notes
        sprint.save()

        for item in unfinished:
            add_item_to_sprint(carry_over_to, item, actor=actor)

        done_count = sum(1 for entry in entries if entry.outcome == Outcome.COMPLETED)
        target = f", offene Arbeit → {carry_over_to.label}" if carry_over_to else ""
        record_event(
            sprint.project, ActivityEvent.Action.SPRINT_COMPLETED, actor=actor,
            sprint=sprint,
            message=f"{sprint.label}: {done_count}/{len(entries)} erledigt{target}",
        )
        notify_sprint_event(sprint, actor, "completed")
    return sprint


def cancel_sprint(sprint: Sprint, actor) -> Sprint:
    with transaction.atomic():
        sprint = _lock_sprint(sprint)
        _require_open(sprint)
        now = timezone.now()
        entries = _close_entries(sprint, now)
        for entry in entries:
            entry.outcome = Outcome.CANCELLED
        SprintItem.objects.bulk_update(
            entries, ["outcome", "closed_at", "status_at_close", "points_at_close"]
        )
        sprint.status = Sprint.Status.CANCELLED
        sprint.closed_at = now
        sprint.completed_by = actor
        sprint.save()
        record_event(
            sprint.project, ActivityEvent.Action.SPRINT_CANCELLED, actor=actor,
            sprint=sprint, message=f"{sprint.label} abgebrochen",
        )
    return sprint


def update_sprint(sprint: Sprint, actor, **fields) -> Sprint:
    with transaction.atomic():
        sprint = _lock_sprint(sprint)
        _require_open(sprint)
        for field, value in fields.items():
            setattr(sprint, field, value)
        sprint.full_clean()
        sprint.save()
        record_event(
            sprint.project, ActivityEvent.Action.SPRINT_UPDATED, actor=actor,
            sprint=sprint, message=f"{sprint.label} geändert",
        )
    return sprint


def save_retrospective(sprint: Sprint, actor, **retro) -> Sprint:
    """The retrospective happens after the sprint, so only closed sprints qualify."""
    unknown = set(retro) - set(RETRO_FIELDS)
    if unknown:
        raise ValueError(f"Unbekannte Felder: {', '.join(sorted(unknown))}")
    with transaction.atomic():
        sprint = _lock_sprint(sprint)
        if sprint.status != Sprint.Status.COMPLETED:
            raise SprintError(
                "Die Retrospektive wird nach dem Abschluss des Sprints festgehalten."
            )
        for field, value in retro.items():
            setattr(sprint, field, value.strip())
        sprint.save(update_fields=[*retro, "updated_at"])
        record_event(
            sprint.project, ActivityEvent.Action.SPRINT_UPDATED, actor=actor,
            sprint=sprint, message=f"Retrospektive zu {sprint.label} gespeichert",
        )
    return sprint


def last_sprint_with_retro_actions(sprint: Sprint) -> Sprint | None:
    """Latest completed sprint before ``sprint`` that recorded retro actions."""
    return (
        Sprint.objects.filter(
            project_id=sprint.project_id,
            status=Sprint.Status.COMPLETED,
            number__lt=sprint.number,
        )
        .exclude(retro_actions="")
        .order_by("-number")
        .first()
    )
