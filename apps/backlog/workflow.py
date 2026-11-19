"""Project-specific workflow rules for status transitions."""

from django.core.exceptions import ValidationError

from apps.backlog.models import BacklogItem
from apps.projects.models import ProjectMembership
from apps.projects.permissions import get_project_access

Status = BacklogItem.Status


def transition_error(item: BacklogItem, old: str, new: str, actor) -> str | None:
    """Reason why ``old`` → ``new`` is not allowed in the item's project."""
    project = item.project
    if old == new:
        return None
    if new == Status.IN_REVIEW and not project.use_review_column:
        return "Dieses Projekt verwendet keine Review-Spalte."
    if new != Status.DONE:
        return None
    done_label = project.status_label(Status.DONE)
    if project.require_review and old != Status.IN_REVIEW:
        review_label = project.status_label(Status.IN_REVIEW)
        return (
            f"Einträge kommen nur aus „{review_label}“ nach „{done_label}“ "
            "(Review-Pflicht)."
        )
    if project.done_requires_lead and actor is not None and not _may_finish(
        project, actor
    ):
        return (
            f"Nur die Projektleitung oder der Product Owner darf auf "
            f"„{done_label}“ setzen."
        )
    if project.done_requires_criteria and item.pk and item.acceptance_criteria.filter(
        is_met=False
    ).exists():
        return (
            f"Vor „{done_label}“ müssen alle Akzeptanzkriterien erfüllt sein."
        )
    return None


def _may_finish(project, actor) -> bool:
    access = get_project_access(actor, project)
    if access.can_manage_project:
        return True
    return (
        access.membership is not None
        and access.membership.scrum_role == ProjectMembership.ScrumRole.PRODUCT_OWNER
    )


def check_transition(item: BacklogItem, old: str, new: str, actor) -> None:
    error = transition_error(item, old, new, actor)
    if error:
        raise ValidationError({"status": error})
