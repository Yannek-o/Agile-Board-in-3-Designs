from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

PROJECT_KEY_VALIDATOR = RegexValidator(
    r"^[A-Z][A-Z0-9]{1,9}$",
    "Das Kürzel muss mit einem Buchstaben beginnen und 2–10 Großbuchstaben "
    "oder Ziffern enthalten.",
)
HEX_COLOR_VALIDATOR = RegexValidator(r"^#[0-9a-fA-F]{6}$", "Ungültiger Farbwert.")


class ProjectQuerySet(models.QuerySet):
    def not_archived(self):
        return self.filter(archived_at__isnull=True)


class Project(models.Model):
    class Status(models.TextChoices):
        PLANNED = "planned", "Geplant"
        ACTIVE = "active", "Aktiv"
        IN_REVIEW = "in_review", "In Prüfung"
        COMPLETED = "completed", "Abgeschlossen"

    name = models.CharField("Projektname", max_length=150)
    key = models.CharField(
        "Projektkürzel",
        max_length=10,
        unique=True,
        validators=[PROJECT_KEY_VALIDATOR],
    )
    description = models.TextField("Beschreibung", blank=True)
    product_goal = models.TextField("Product Goal", blank=True)
    definition_of_done = models.TextField("Definition of Done", blank=True)
    wip_limit_in_progress = models.PositiveSmallIntegerField(
        "WIP-Limit „In Progress“",
        null=True,
        blank=True,
        help_text="Höchstzahl gleichzeitiger Karten; leer = kein Limit.",
    )
    wip_limit_in_review = models.PositiveSmallIntegerField(
        "WIP-Limit „In Review“",
        null=True,
        blank=True,
        help_text="Höchstzahl gleichzeitiger Karten; leer = kein Limit.",
    )
    status_label_todo = models.CharField(
        "Spaltenname „To Do“", max_length=30, blank=True,
        help_text="Leer = Standardname.",
    )
    status_label_in_progress = models.CharField(
        "Spaltenname „In Progress“", max_length=30, blank=True,
        help_text="Leer = Standardname.",
    )
    status_label_in_review = models.CharField(
        "Spaltenname „In Review“", max_length=30, blank=True,
        help_text="Leer = Standardname.",
    )
    status_label_done = models.CharField(
        "Spaltenname „Done“", max_length=30, blank=True,
        help_text="Leer = Standardname.",
    )
    use_review_column = models.BooleanField(
        "Review-Spalte verwenden", default=True,
        help_text="Ohne Haken gibt es nur To Do, In Progress und Done.",
    )
    require_review = models.BooleanField(
        "Review-Pflicht vor Done", default=False,
        help_text="Einträge dürfen nur aus „In Review“ auf Done gesetzt werden.",
    )
    done_requires_lead = models.BooleanField(
        "Done nur durch Projektleitung oder Product Owner", default=False,
    )
    done_requires_criteria = models.BooleanField(
        "Done nur mit erfüllten Akzeptanzkriterien", default=False,
    )
    status = models.CharField(
        "Status", max_length=20, choices=Status.choices, default=Status.PLANNED
    )
    next_item_number = models.PositiveIntegerField(default=1, editable=False)
    next_sprint_number = models.PositiveIntegerField(default=1, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_projects",
    )
    created_at = models.DateTimeField("Erstellt am", auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    archived_at = models.DateTimeField("Archiviert am", null=True, blank=True)

    objects = ProjectQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        verbose_name = "Projekt"
        verbose_name_plural = "Projekte"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(key__regex=r"^[A-Z][A-Z0-9]{1,9}$"),
                name="projects_project_key_format",
            )
        ]

    def __str__(self) -> str:
        return f"{self.key} · {self.name}"

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    def archive(self) -> None:
        self.archived_at = timezone.now()
        self.save(update_fields=["archived_at", "updated_at"])

    def restore(self) -> None:
        self.archived_at = None
        self.save(update_fields=["archived_at", "updated_at"])

    def wip_limit_for(self, status: str) -> int | None:
        limits = {
            "in_progress": self.wip_limit_in_progress,
            "in_review": self.wip_limit_in_review,
        }
        return limits.get(status) or None

    def clean(self) -> None:
        super().clean()
        if self.require_review and not self.use_review_column:
            raise ValidationError(
                {"require_review": "Die Review-Pflicht braucht die Review-Spalte."}
            )

    def status_label(self, status: str) -> str:
        """Column name of a status in this project (custom or default)."""
        from apps.backlog.models import BacklogItem

        custom = getattr(self, f"status_label_{status}", "")
        return custom or BacklogItem.Status(status).label

    def status_choices(self) -> list[tuple[str, str]]:
        """Statuses usable in this project, with project-specific names."""
        from apps.backlog.models import BacklogItem

        return [
            (value, self.status_label(value))
            for value in BacklogItem.Status.values
            if value != BacklogItem.Status.IN_REVIEW or self.use_review_column
        ]

    def active_members(self):
        return self.memberships.filter(
            is_active=True, user__is_active=True
        ).select_related("user")


class ProjectMembership(models.Model):
    """Links a user to a project. Scrum accountability and access are separate."""

    class ScrumRole(models.TextChoices):
        PRODUCT_OWNER = "product_owner", "Product Owner"
        SCRUM_MASTER = "scrum_master", "Scrum Master"
        DEVELOPER = "developer", "Developer"
        STAKEHOLDER = "stakeholder", "Stakeholder"

    class AccessLevel(models.TextChoices):
        MANAGE = "manage", "Projektleitung"
        EDIT = "edit", "Bearbeitung"
        READ = "read", "Nur Lesen"

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    scrum_role = models.CharField(
        "Scrum-Verantwortlichkeit",
        max_length=20,
        choices=ScrumRole.choices,
        default=ScrumRole.DEVELOPER,
    )
    access_level = models.CharField(
        "Technische Rechte",
        max_length=10,
        choices=AccessLevel.choices,
        default=AccessLevel.EDIT,
    )
    can_manage_backlog = models.BooleanField(
        "Backlog & Sprint freigegeben",
        default=False,
        help_text="Erlaubt Mitgliedern mit Bearbeitungsrechten die Pflege von "
        "Backlog und Sprints.",
    )
    is_active = models.BooleanField("Zugriff aktiv", default=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__first_name", "user__last_name", "user__username"]
        verbose_name = "Projektmitgliedschaft"
        verbose_name_plural = "Projektmitgliedschaften"
        constraints = [
            models.UniqueConstraint(
                fields=["project", "user"], name="projects_unique_membership"
            )
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.project.key}"


class Label(models.Model):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="labels"
    )
    name = models.CharField("Name", max_length=40)
    color = models.CharField(
        "Farbe",
        max_length=7,
        default="#5b7db1",
        validators=[HEX_COLOR_VALIDATOR],
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Label"
        verbose_name_plural = "Labels"
        constraints = [
            models.UniqueConstraint(
                fields=["project", "name"], name="projects_unique_label_name"
            )
        ]

    def __str__(self) -> str:
        return self.name
