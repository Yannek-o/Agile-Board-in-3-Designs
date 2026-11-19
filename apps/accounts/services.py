"""Administrative changes to employee accounts. Views must use these functions
for writes so that the last-admin rule and the audit trail always apply."""

import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.accounts.models import AVATAR_COLOR_VALIDATOR, AccountEvent, User
from apps.accounts.tokens import invitation_token_generator

logger = logging.getLogger(__name__)

EDITABLE_FIELDS = (
    "username",
    "first_name",
    "last_name",
    "email",
    "job_title",
    "can_create_projects",
    "is_staff",
)


class AccountError(Exception):
    """An account change violates a business rule."""


def log_account_event(user: User, actor, action: str, details: str = "") -> None:
    AccountEvent.objects.create(
        user=user,
        user_label=user.display_name,
        actor=actor if actor and actor.is_authenticated else None,
        action=action,
        details=details[:255],
    )


def _would_leave_no_admin(user: User) -> bool:
    """Locks all active admins so that concurrent demotions cannot both pass."""
    admins = list(
        User.objects.select_for_update()
        .filter(is_active=True)
        .filter(Q(is_staff=True) | Q(is_superuser=True))
        .values_list("pk", flat=True)
    )
    return admins == [user.pk]


def _require_remaining_admin(user: User) -> None:
    if _would_leave_no_admin(user):
        raise AccountError(
            "Es muss mindestens eine aktive Systemadministration bestehen bleiben."
        )


def invitation_url(user: User) -> str:
    path = reverse(
        "accounts:invitation_accept",
        kwargs={
            "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": invitation_token_generator.make_token(user),
        },
    )
    return f"{settings.SITE_URL.rstrip('/')}{path}"


def send_invitation(user: User, actor) -> None:
    if not user.email:
        raise AccountError("Für eine Einladung wird eine E-Mail-Adresse benötigt.")
    context = {
        "user": user,
        "actor": actor,
        "invitation_url": invitation_url(user),
        "valid_days": settings.INVITATION_TIMEOUT // 86400,
    }
    message = EmailMessage(
        subject=" ".join(
            render_to_string("accounts/emails/invitation_subject.txt", context).split()
        ),
        body=render_to_string("accounts/emails/invitation.txt", context),
        to=[user.email],
    )
    log_account_event(user, actor, AccountEvent.Action.INVITED, user.email)
    transaction.on_commit(lambda: _deliver(message))


def _deliver(message: EmailMessage) -> None:
    try:
        message.send()
    except Exception:  # noqa: BLE001 - mail problems must not break requests
        logger.exception("Einladung an %s konnte nicht gesendet werden.", message.to)


def invite_employee(actor, **fields) -> User:
    unknown = set(fields) - set(EDITABLE_FIELDS)
    if unknown:
        raise ValueError(f"Nicht änderbare Felder: {', '.join(sorted(unknown))}")
    with transaction.atomic():
        user = User(**fields)
        user.set_unusable_password()
        user.full_clean(exclude=["password"])
        user.save()
        log_account_event(user, actor, AccountEvent.Action.CREATED)
        send_invitation(user, actor)
    return user


def update_employee(user: User, actor, **changes) -> User:
    unknown = set(changes) - set(EDITABLE_FIELDS)
    if unknown:
        raise ValueError(f"Nicht änderbare Felder: {', '.join(sorted(unknown))}")
    with transaction.atomic():
        current = User.objects.select_for_update().get(pk=user.pk)
        changed = [
            field for field, value in changes.items()
            if getattr(current, field) != value
        ]
        if not changed:
            return current
        loses_admin = (
            "is_staff" in changed and not changes["is_staff"]
            and not current.is_superuser
        )
        if loses_admin:
            _require_remaining_admin(current)
        for field in changed:
            setattr(current, field, changes[field])
        current.full_clean(exclude=["password"])
        current.save(update_fields=changed)
        labels = ", ".join(
            str(User._meta.get_field(field).verbose_name) for field in changed
        )
        log_account_event(current, actor, AccountEvent.Action.UPDATED, labels)
    return current


def set_employee_active(user: User, actor, active: bool) -> User:
    if actor is not None and actor.pk == user.pk and not active:
        raise AccountError("Das eigene Konto kann nicht deaktiviert werden.")
    with transaction.atomic():
        current = User.objects.select_for_update().get(pk=user.pk)
        if current.is_active == active:
            return current
        if not active and current.is_system_admin:
            _require_remaining_admin(current)
        current.is_active = active
        current.save(update_fields=["is_active"])
        action = (
            AccountEvent.Action.ACTIVATED if active
            else AccountEvent.Action.DEACTIVATED
        )
        log_account_event(current, actor, action)
    return current


def set_avatar_colors(user: User, color: str = "", color_2: str = "") -> User:
    """Stores the personal avatar colour; ``color_2`` turns it into a gradient."""
    color = (color or "").strip().lower()
    color_2 = (color_2 or "").strip().lower() if color else ""
    for value in (color, color_2):
        if value:
            AVATAR_COLOR_VALIDATOR(value)
    user.avatar_color = color
    user.avatar_color_2 = color_2
    user.save(update_fields=["avatar_color", "avatar_color_2"])
    return user
