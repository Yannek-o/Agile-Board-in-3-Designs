from django.conf import settings
from django.db import models


class ActivityEvent(models.Model):
    """Append-only audit entry: who changed what and when."""

    class Action(models.TextChoices):
        CREATED = "created", "Angelegt"
        UPDATED = "updated", "Geändert"
        STATUS_CHANGED = "status_changed", "Status geändert"
        COMMENTED = "commented", "Kommentiert"
        ATTACHMENT_ADDED = "attachment_added", "Anhang hinzugefügt"
        LINK_ADDED = "link_added", "Link hinzugefügt"
        WORK_LOGGED = "work_logged", "Zeit gebucht"
        RELEASE_PUBLISHED = "release_published", "Release veröffentlicht"
        ARCHIVED = "archived", "Archiviert"
        RESTORED = "restored", "Wiederhergestellt"
        REORDERED = "reordered", "Neu priorisiert"
        SPRINT_CREATED = "sprint_created", "Sprint angelegt"
        SPRINT_UPDATED = "sprint_updated", "Sprint geändert"
        SPRINT_ITEM_ADDED = "sprint_item_added", "Zum Sprint hinzugefügt"
        SPRINT_ITEM_REMOVED = "sprint_item_removed", "Aus Sprint entfernt"
        SPRINT_STARTED = "sprint_started", "Sprint gestartet"
        SPRINT_COMPLETED = "sprint_completed", "Sprint abgeschlossen"
        SPRINT_CANCELLED = "sprint_cancelled", "Sprint abgebrochen"
        MEMBER_CHANGED = "member_changed", "Mitglied geändert"

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="activity"
    )
    item = models.ForeignKey(
        "backlog.BacklogItem",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="activity",
    )
    sprint = models.ForeignKey(
        "sprints.Sprint",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="activity",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity",
    )
    action = models.CharField(max_length=30, choices=Action.choices)
    field = models.CharField(max_length=50, blank=True)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    message = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "Aktivität"
        verbose_name_plural = "Aktivitäten"
        indexes = [models.Index(fields=["project", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.get_action_display()} · {self.created_at:%d.%m.%Y %H:%M}"
