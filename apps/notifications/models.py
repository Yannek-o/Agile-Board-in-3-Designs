from django.conf import settings
from django.db import models
from django.urls import reverse


class ItemWatch(models.Model):
    """A user follows a backlog item and is told about its changes."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="watches"
    )
    item = models.ForeignKey(
        "backlog.BacklogItem", on_delete=models.CASCADE, related_name="watches"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Beobachtung"
        verbose_name_plural = "Beobachtungen"
        constraints = [
            models.UniqueConstraint(fields=["user", "item"], name="unique_item_watch")
        ]


class Notification(models.Model):
    """In-app notification shown under the bell in the navigation bar."""

    class Kind(models.TextChoices):
        ASSIGNED = "assigned", "Zugewiesen"
        MENTIONED = "mentioned", "Erwähnt"
        COMMENTED = "commented", "Kommentar"
        STATUS_CHANGED = "status_changed", "Status geändert"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="notifications",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    item = models.ForeignKey(
        "backlog.BacklogItem", on_delete=models.CASCADE, null=True, blank=True,
        related_name="notifications",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    message = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "Benachrichtigung"
        verbose_name_plural = "Benachrichtigungen"
        indexes = [models.Index(fields=["recipient", "read_at"])]

    def __str__(self) -> str:
        return self.message

    @property
    def is_unread(self) -> bool:
        return self.read_at is None

    @property
    def target_url(self) -> str:
        if self.item_id is None:
            return reverse("notifications:list")
        return reverse(
            "backlog:detail", args=[self.item.project.key, self.item.number]
        )
