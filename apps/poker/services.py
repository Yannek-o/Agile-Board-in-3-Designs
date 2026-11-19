"""Planning poker: start, vote, reveal, re-vote and accept an estimate."""

from statistics import mean

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.backlog.services import update_backlog_item
from apps.poker.models import DECK, NUMERIC_CARDS, PokerSession, PokerVote
from apps.projects.models import ProjectMembership

Status = PokerSession.Status
VOTING_LEVELS = (
    ProjectMembership.AccessLevel.EDIT,
    ProjectMembership.AccessLevel.MANAGE,
)


def start_session(item, actor) -> PokerSession:
    """Returns the item's open session or starts a new one."""
    session, _ = PokerSession.objects.get_or_create(
        item=item,
        status__in=[Status.VOTING, Status.REVEALED],
        defaults={
            "project": item.project,
            "created_by": actor,
            "status": Status.VOTING,
        },
    )
    return session


def _require_status(session: PokerSession, status: str, message: str) -> None:
    session.refresh_from_db(fields=["status", "round"])
    if session.status != status:
        raise ValidationError(message)


def cast_vote(session: PokerSession, user, value: str) -> None:
    if value not in DECK:
        raise ValidationError("Ungültige Karte.")
    _require_status(session, Status.VOTING, "Die Abstimmung ist nicht offen.")
    PokerVote.objects.update_or_create(
        session=session, user=user, defaults={"value": value}
    )
    session.save(update_fields=["updated_at"])


def reveal(session: PokerSession, actor) -> None:
    _require_status(session, Status.VOTING, "Die Karten sind bereits aufgedeckt.")
    session.status = Status.REVEALED
    session.save(update_fields=["status", "updated_at"])


def reset_round(session: PokerSession, actor) -> None:
    if not session.is_open:
        raise ValidationError("Die Runde ist abgeschlossen.")
    with transaction.atomic():
        session.votes.all().delete()
        session.status = Status.VOTING
        session.round += 1
        session.save(update_fields=["status", "round", "updated_at"])


def accept_estimate(session: PokerSession, points: int, actor) -> None:
    if not session.is_open:
        raise ValidationError("Die Runde ist bereits abgeschlossen.")
    with transaction.atomic():
        update_backlog_item(
            session.item, actor=actor, expected_version=None, story_points=points
        )
        session.final_points = points
        session.status = Status.CLOSED
        session.save(update_fields=["final_points", "status", "updated_at"])


def close_session(session: PokerSession, actor) -> None:
    session.status = Status.CLOSED
    session.save(update_fields=["status", "updated_at"])


def suggested_points(average: float) -> int:
    """Smallest deck value that covers the average estimate."""
    return next(
        (card for card in NUMERIC_CARDS if card >= average), NUMERIC_CARDS[-1]
    )


def _summary(values: list[str]) -> dict | None:
    numbers = [int(value) for value in values if value.isdigit()]
    if not numbers:
        return None
    average = round(mean(numbers), 1)
    return {
        "average": average,
        "min": min(numbers),
        "max": max(numbers),
        "suggestion": suggested_points(average),
        "consensus": len(set(values)) == 1,
    }


def session_state(session: PokerSession, viewer) -> dict:
    """Current state for the polling client; hides other cards until reveal."""
    revealed = session.status != Status.VOTING
    cast = list(session.votes.select_related("user"))
    votes = {vote.user_id: vote.value for vote in cast}
    voters = [
        membership.user
        for membership in session.project.active_members().filter(
            access_level__in=VOTING_LEVELS
        ).order_by("user__first_name", "user__username")
    ]
    member_ids = {user.pk for user in voters}
    voters += [vote.user for vote in cast if vote.user_id not in member_ids]
    return {
        "status": session.status,
        "status_label": session.get_status_display(),
        "round": session.round,
        "item": {
            "key": session.item.key,
            "title": session.item.title,
            "story_points": session.item.story_points,
        },
        "final_points": session.final_points,
        "my_vote": votes.get(viewer.pk),
        "votes": [
            {
                "name": user.display_name,
                "initials": user.initials,
                "voted": user.pk in votes,
                "value": votes.get(user.pk) if revealed else None,
            }
            for user in voters
        ],
        "summary": _summary(list(votes.values())) if revealed else None,
    }
