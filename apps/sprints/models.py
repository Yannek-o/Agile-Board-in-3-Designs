from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum
from django.utils import timezone

MAX_SPRINT_LENGTH = timedelta(days=31)
RETRO_FIELDS = ("retro_went_well", "retro_to_improve", "retro_actions")


class Sprint(models.Model):
    class Status(models.TextChoices):
        PLANNED = "planned", "Geplant"
        ACTIVE = "active", "Aktiv"
        COMPLETED = "completed", "Abgeschlossen"
        CANCELLED = "cancelled", "Abgebrochen"

    OPEN_STATUSES = (Status.PLANNED, Status.ACTIVE)

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="sprints"
    )
    number = models.PositiveIntegerField("Nummer", editable=False)
    name = models.CharField("Name", max_length=100, blank=True)
    goal = models.TextField("Sprint-Ziel", blank=True)
    start_date = models.DateField("Startdatum")
    end_date = models.DateField("Enddatum")
    status = models.CharField(
        "Status", max_length=20, choices=Status.choices, default=Status.PLANNED
    )
    started_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="closed_sprints",
    )
    review_notes = models.TextField("Abschlussnotiz", blank=True)
    retro_went_well = models.TextField("Was lief gut?", blank=True)
    retro_to_improve = models.TextField("Was lief nicht gut?", blank=True)
    retro_actions = models.TextField(
        "Was ändern wir?",
        blank=True,
        help_text="Konkrete Maßnahmen; sie werden im nächsten Sprint angezeigt.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-number"]
        verbose_name = "Sprint"
        verbose_name_plural = "Sprints"
        constraints = [
            models.UniqueConstraint(
                fields=["project", "number"], name="sprints_unique_number"
            ),
            models.UniqueConstraint(
                fields=["project"],
                condition=models.Q(status="active"),
                name="sprints_one_active_per_project",
            ),
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="sprints_end_after_start",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.project.key} {self.label}"

    @property
    def label(self) -> str:
        return self.name or f"Sprint {self.number}"

    @property
    def is_open(self) -> bool:
        return self.status in self.OPEN_STATUSES

    @property
    def is_overdue(self) -> bool:
        return (
            self.status == self.Status.ACTIVE
            and self.end_date < timezone.localdate()
        )

    def clean(self) -> None:
        if self.start_date and self.end_date:
            if self.end_date < self.start_date:
                raise ValidationError(
                    {"end_date": "Das Enddatum darf nicht vor dem Startdatum liegen."}
                )
            if self.end_date - self.start_date > MAX_SPRINT_LENGTH:
                raise ValidationError(
                    {"end_date": "Ein Sprint darf höchstens einen Monat dauern."}
                )

    def open_items(self):
        from apps.backlog.models import BacklogItem

        return BacklogItem.objects.filter(
            sprint_entries__sprint=self,
            sprint_entries__outcome=SprintItem.Outcome.OPEN,
            archived_at__isnull=True,
        ).order_by("backlog_rank", "number")

    def committed_entries(self):
        return self.entries.exclude(outcome=SprintItem.Outcome.REMOVED)

    def committed_points(self) -> int:
        if self.is_open:
            return self.open_items().aggregate(total=Sum("story_points"))["total"] or 0
        return (
            self.committed_entries().aggregate(total=Sum("points_at_close"))["total"]
            or 0
        )

    def completed_points(self) -> int:
        if self.is_open:
            return (
                self.open_items()
                .filter(status="done")
                .aggregate(total=Sum("story_points"))["total"]
                or 0
            )
        return (
            self.entries.filter(outcome=SprintItem.Outcome.COMPLETED).aggregate(
                total=Sum("points_at_close")
            )["total"]
            or 0
        )


class SprintItem(models.Model):
    """History of a backlog item's membership in a sprint."""

    class Outcome(models.TextChoices):
        OPEN = "open", "Im Sprint"
        COMPLETED = "completed", "Erledigt"
        CARRIED_OVER = "carried_over", "In Folgesprint übernommen"
        RETURNED = "returned", "Zurück ins Product Backlog"
        REMOVED = "removed", "Aus Sprint entfernt"
        CANCELLED = "cancelled", "Sprint abgebrochen"

    sprint = models.ForeignKey(Sprint, on_delete=models.CASCADE, related_name="entries")
    item = models.ForeignKey(
        "backlog.BacklogItem", on_delete=models.CASCADE, related_name="sprint_entries"
    )
    outcome = models.CharField(
        max_length=20, choices=Outcome.choices, default=Outcome.OPEN
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    added_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    status_at_close = models.CharField(max_length=20, blank=True)
    points_at_close = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["added_at", "pk"]
        verbose_name = "Sprint-Eintrag"
        verbose_name_plural = "Sprint-Einträge"
        constraints = [
            models.UniqueConstraint(
                fields=["sprint", "item"], name="sprints_unique_sprint_item"
            )
        ]

    def __str__(self) -> str:
        return f"{self.sprint} · {self.item.key}"

    @property
    def status_at_close_display(self) -> str:
        from apps.backlog.models import BacklogItem

        if not self.status_at_close:
            return ""
        return BacklogItem.Status(self.status_at_close).label
