"""E-mail notifications. Messages are sent after the surrounding transaction
commits, so rolled-back changes never trigger mails. Delivery errors are
logged and never break the triggering request.
"""

import logging
import re
from collections.abc import Iterable

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse

from apps.notifications.models import ItemWatch, Notification

logger = logging.getLogger(__name__)

MENTION_PATTERN = re.compile(r"(?<![\w@])@([\w.+-]+)")
Kind = Notification.Kind


def absolute_url(path: str) -> str:
    return f"{settings.SITE_URL.rstrip('/')}{path}"


def eligible_recipients(users: Iterable, exclude=None) -> list:
    unique = {}
    for user in users:
        if (
            user is not None
            and user.is_active
            and user.email
            and user.email_notifications
            and (exclude is None or user.pk != exclude.pk)
        ):
            unique[user.pk] = user
    return list(unique.values())


def schedule_mail(recipients: list, template: str, context: dict) -> None:
    if not recipients:
        return
    subject = render_to_string(f"notifications/{template}_subject.txt", context)
    subject = " ".join(subject.split())
    messages = [
        EmailMessage(
            subject=subject,
            body=render_to_string(
                f"notifications/{template}.txt", {**context, "recipient": user}
            ),
            to=[user.email],
        )
        for user in recipients
    ]
    transaction.on_commit(lambda: deliver(messages))


def deliver(messages: list[EmailMessage]) -> None:
    try:
        get_connection().send_messages(messages)
    except Exception:  # noqa: BLE001 - mail problems must not break requests
        logger.exception("E-Mail-Benachrichtigung konnte nicht gesendet werden.")


def item_context(item, actor) -> dict:
    return {
        "item": item,
        "project": item.project,
        "actor": actor,
        "url": absolute_url(
            reverse("backlog:detail", args=[item.project.key, item.number])
        ),
    }


def notify_assignment(item, actor) -> None:
    watch(item, item.assignee)
    create_notifications(
        [item.assignee], Kind.ASSIGNED, item, actor,
        f"{actor_name(actor)} hat dir {item.key} zugewiesen: {item.title}",
    )
    recipients = eligible_recipients([item.assignee], exclude=actor)
    schedule_mail(recipients, "assignment", item_context(item, actor))


def notify_comment(comment) -> None:
    item = comment.item
    author = comment.author
    watch(item, author)
    mentioned = create_notifications(
        extract_mentions(comment.body, item.project), Kind.MENTIONED, item, author,
        f"{actor_name(author)} hat dich in {item.key} erwähnt: {comment.body}",
    )
    mentioned_ids = {user.pk for user in mentioned}
    create_notifications(
        [
            user for user in [*watchers(item), item.assignee, item.created_by]
            if user is not None and user.pk not in mentioned_ids
        ],
        Kind.COMMENTED, item, author,
        f"{actor_name(author)} hat {item.key} kommentiert: {comment.body}",
    )
    context = item_context(item, author)
    context["comment"] = comment
    schedule_mail(eligible_recipients(mentioned, exclude=author), "mention", context)
    recipients = [
        user for user in eligible_recipients(
            [item.assignee, item.created_by], exclude=author
        )
        if user.pk not in mentioned_ids
    ]
    schedule_mail(recipients, "comment", context)


def notify_status_change(item, actor, old_label: str, new_label: str) -> None:
    create_notifications(
        watchers(item), Kind.STATUS_CHANGED, item, actor,
        f"{item.key} {old_label} → {new_label} ({actor_name(actor)})",
    )


def actor_name(actor) -> str:
    if actor is None or not getattr(actor, "is_authenticated", False):
        return "Jemand"
    return actor.display_name


def project_member_ids(project) -> set[int]:
    return set(project.active_members().values_list("user_id", flat=True))


def extract_mentions(text: str, project) -> list:
    """Active project members mentioned as ``@username`` (case-insensitive)."""
    names = []
    for match in MENTION_PATTERN.finditer(text or ""):
        name = match.group(1).rstrip(".").lower()
        if name and name not in names:
            names.append(name)
    if not names:
        return []
    members = {
        membership.user.username.lower(): membership.user
        for membership in project.active_members()
    }
    return [members[name] for name in names if name in members]


def watch(item, user) -> None:
    if user is not None and getattr(user, "is_authenticated", False):
        ItemWatch.objects.get_or_create(item=item, user=user)


def is_watching(item, user) -> bool:
    return ItemWatch.objects.filter(item=item, user=user).exists()


def toggle_watch(item, user) -> bool:
    """Starts or stops watching; returns the new state."""
    deleted, _ = ItemWatch.objects.filter(item=item, user=user).delete()
    if deleted:
        return False
    watch(item, user)
    return True


def watchers(item) -> list:
    return [
        watch_entry.user
        for watch_entry in item.watches.select_related("user").filter(
            user__is_active=True
        )
    ]


def create_notifications(users: Iterable, kind: str, item, actor, message: str):
    """Stores in-app notifications for active project members except the actor."""
    member_ids = project_member_ids(item.project)
    actor_user = actor if getattr(actor, "is_authenticated", False) else None
    actor_id = actor_user.pk if actor_user else None
    recipients = {}
    for user in users:
        if user is not None and user.pk in member_ids and user.pk != actor_id:
            recipients[user.pk] = user
    Notification.objects.bulk_create(
        Notification(
            recipient=user, actor=actor_user, item=item,
            kind=kind, message=message[:255],
        )
        for user in recipients.values()
    )
    return list(recipients.values())


def notify_sprint_event(sprint, actor, event: str) -> None:
    members = [
        membership.user for membership in sprint.project.active_members()
    ]
    context = {
        "sprint": sprint,
        "project": sprint.project,
        "actor": actor,
        "event": event,
        "url": absolute_url(
            reverse("sprints:detail", args=[sprint.project.key, sprint.number])
        ),
    }
    schedule_mail(eligible_recipients(members, exclude=actor), "sprint", context)
