import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

TOKEN_PREFIX = "ab_"
PREFIX_LENGTH = 10
LAST_USED_RESOLUTION_SECONDS = 60


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


class ApiToken(models.Model):
    """Personal access token; only the SHA-256 hash is stored."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_tokens"
    )
    name = models.CharField("Bezeichnung", max_length=60)
    prefix = models.CharField(max_length=PREFIX_LENGTH)
    key_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "API-Token"
        verbose_name_plural = "API-Tokens"

    def __str__(self) -> str:
        return f"{self.name} ({self.prefix}…)"

    @classmethod
    def issue(cls, user, name: str) -> tuple["ApiToken", str]:
        """Creates a token and returns it together with the one-time raw value."""
        raw_token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        token = cls.objects.create(
            user=user,
            name=name,
            prefix=raw_token[:PREFIX_LENGTH],
            key_hash=hash_token(raw_token),
        )
        return token, raw_token

    @classmethod
    def authenticate(cls, raw_token: str):
        """User of a valid token or ``None``."""
        token = (
            cls.objects.select_related("user")
            .filter(key_hash=hash_token(raw_token))
            .first()
        )
        if token is None or not token.user.is_active:
            return None
        now = timezone.now()
        stale = token.last_used_at is None or (
            (now - token.last_used_at).total_seconds() > LAST_USED_RESOLUTION_SECONDS
        )
        if stale:
            cls.objects.filter(pk=token.pk).update(last_used_at=now)
        return token.user
