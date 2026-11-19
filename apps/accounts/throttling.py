"""Database-backed throttling for logins and password reset requests.

The database is used instead of a process-local cache so that limits hold
across multiple application workers.
"""

from datetime import timedelta
from ipaddress import ip_address

from django.conf import settings
from django.utils import timezone

from apps.accounts.models import AuthAttempt

Kind = AuthAttempt.Kind


def client_ip(request) -> str | None:
    if request is None:
        return None
    candidate = request.META.get("REMOTE_ADDR", "")
    if settings.TRUST_X_FORWARDED_FOR:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            candidate = forwarded.split(",")[0].strip()
    try:
        return str(ip_address(candidate))
    except ValueError:
        return None


def normalize_username(username: str) -> str:
    return (username or "").strip().lower()[:150]


def _lockout_window() -> timedelta:
    return timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)


def _remaining_lock(failures, limit: int) -> timedelta | None:
    recent = list(
        failures.order_by("-created_at").values_list("created_at", flat=True)[:limit]
    )
    if len(recent) < limit:
        return None
    remaining = recent[0] + _lockout_window() - timezone.now()
    return remaining if remaining.total_seconds() > 0 else None


def login_lock_remaining(username: str, ip: str | None) -> timedelta | None:
    """Returns the remaining lock duration, or None if login is allowed."""
    since = timezone.now() - _lockout_window()
    failures = AuthAttempt.objects.filter(
        kind=Kind.LOGIN_FAILURE, created_at__gte=since
    )
    locks = [
        _remaining_lock(
            failures.filter(username=normalize_username(username)),
            settings.LOGIN_FAILURE_LIMIT,
        )
    ]
    if ip:
        locks.append(
            _remaining_lock(
                failures.filter(ip_address=ip), settings.LOGIN_IP_FAILURE_LIMIT
            )
        )
    active_locks = [lock for lock in locks if lock]
    return max(active_locks) if active_locks else None


def record_login_failure(username: str, ip: str | None) -> None:
    AuthAttempt.objects.create(
        kind=Kind.LOGIN_FAILURE, username=normalize_username(username), ip_address=ip
    )
    _purge_expired()


def clear_login_failures(username: str) -> None:
    AuthAttempt.objects.filter(
        kind=Kind.LOGIN_FAILURE, username=normalize_username(username)
    ).delete()


def allow_password_reset(ip: str | None) -> bool:
    """Counts a reset request and reports whether it is within the hourly limit."""
    since = timezone.now() - timedelta(hours=1)
    recent = AuthAttempt.objects.filter(
        kind=Kind.PASSWORD_RESET, ip_address=ip, created_at__gte=since
    ).count()
    AuthAttempt.objects.create(kind=Kind.PASSWORD_RESET, ip_address=ip)
    return recent < settings.PASSWORD_RESET_IP_LIMIT


def _purge_expired() -> None:
    cutoff = timezone.now() - max(_lockout_window(), timedelta(hours=1)) * 2
    AuthAttempt.objects.filter(created_at__lt=cutoff).delete()
