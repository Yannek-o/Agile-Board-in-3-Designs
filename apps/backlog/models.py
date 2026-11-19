from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import (
    MaxValueValidator,
    MinValueValidator,
    URLValidator,
)
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from apps.projects.models import HEX_COLOR_VALIDATOR

DEFAULT_EPIC_COLOR = "#a855f7"
WEB_LINK_VALIDATOR = URLValidator(
    schemes=["http", "https"],
    message="Bitte einen gültigen Link mit http:// oder https:// angeben.",
)

HIERARCHY_ERRORS = {
    "subtask_needs_parent": "Eine Unteraufgabe braucht einen übergeordneten Eintrag.",
    "self_parent": "Ein Eintrag kann nicht sich selbst untergeordnet sein.",
    "other_project": "Der übergeordnete Eintrag gehört zu einem anderen Projekt.",
    "epic_has_parent": "Ein Epic kann keinem Eintrag untergeordnet werden.",
    "subtask_parent": (
        "Unteraufgaben gehören zu einer Story, Aufgabe, einem Bug "
        "oder einer technischen Verbesserung."
    ),
    "item_parent": (
        "Stories, Aufgaben und Bugs können nur einem Epic zugeordnet werden."
    ),
}


class Release(models.Model):
    """A planned version that bundles backlog items (fix version)."""

    class Status(models.TextChoices):
        UNRELEASED = "unreleased", "Geplant"
        RELEASED = "released", "Veröffentlicht"

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="releases"
    )
    name = models.CharField("Name", max_length=60)
    description = models.TextField("Beschreibung", blank=True)
    release_date = models.DateField("Geplantes Datum", null=True, blank=True)
    status = models.CharField(
        "Status", max_length=20, choices=Status.choices, default=Status.UNRELEASED
    )
    released_at = models.DateTimeField("Veröffentlicht am", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["status", "release_date", "name"]
        verbose_name = "Release"
        verbose_name_plural = "Releases"
        constraints = [
            models.UniqueConstraint(
                Lower("name"), "project", name="backlog_unique_release_name",
                violation_error_message="Ein Release mit diesem Namen gibt es bereits.",
            )
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_released(self) -> bool:
        return self.status == self.Status.RELEASED


class BacklogItemQuerySet(models.QuerySet):
    def active(self):
        return self.filter(archived_at__isnull=True)

    def open(self):
        return self.active().exclude(status=BacklogItem.Status.DONE)


class BacklogItem(models.Model):
    class ItemType(models.TextChoices):
        EPIC = "epic", "Epic"
        STORY = "story", "User Story"
        TASK = "task", "Aufgabe"
        BUG = "bug", "Bug"
        TECHNICAL = "technical", "Technische Verbesserung"
        SUBTASK = "subtask", "Unteraufgabe"

    class Priority(models.TextChoices):
        LOW = "low", "Niedrig"
        MEDIUM = "medium", "Mittel"
        HIGH = "high", "Hoch"
        CRITICAL = "critical", "Kritisch"

    class Status(models.TextChoices):
        TODO = "todo", "To Do"
        IN_PROGRESS = "in_progress", "In Progress"
        IN_REVIEW = "in_review", "In Review"
        DONE = "done", "Done"

    HIGH_PRIORITIES = (Priority.HIGH, Priority.CRITICAL)

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="items"
    )
    number = models.PositiveIntegerField("Nummer", editable=False)
    item_type = models.CharField(
        "Typ", max_length=20, choices=ItemType.choices, default=ItemType.STORY
    )
    title = models.CharField("Titel", max_length=200)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="Übergeordnet",
    )
    description = models.TextField("Beschreibung", blank=True)
    color = models.CharField(
        "Farbe",
        max_length=7,
        blank=True,
        validators=[HEX_COLOR_VALIDATOR],
        help_text="Kennfarbe des Epics auf Board und Backlog.",
    )
    priority = models.CharField(
        "Priorität", max_length=10, choices=Priority.choices,
        default=Priority.MEDIUM,
    )
    story_points = models.PositiveSmallIntegerField(
        "Story Points",
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_items",
        verbose_name="Bearbeiter",
    )
    status = models.CharField(
        "Status", max_length=20, choices=Status.choices, default=Status.TODO
    )
    is_blocked = models.BooleanField("Blockiert", default=False)
    blocked_reason = models.CharField("Blockiergrund", max_length=255, blank=True)
    labels = models.ManyToManyField(
        "projects.Label", blank=True, related_name="items", verbose_name="Labels"
    )
    due_date = models.DateField("Fällig am", null=True, blank=True)
    fix_version = models.ForeignKey(
        Release,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="items",
        verbose_name="Release",
    )
    original_estimate = models.PositiveIntegerField(
        "Schätzung", null=True, blank=True, help_text="Geschätzter Aufwand in Minuten."
    )
    remaining_estimate = models.PositiveIntegerField(
        "Restaufwand",
        null=True,
        blank=True,
        help_text="Verbleibender Aufwand in Minuten.",
    )
    time_spent = models.PositiveIntegerField(
        "Gebuchte Zeit", default=0, editable=False,
        help_text="Summe aller Zeitbuchungen in Minuten.",
    )
    backlog_rank = models.PositiveIntegerField(
        "Backlog-Reihenfolge", default=0, db_index=True
    )
    version = models.PositiveIntegerField(default=1, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_items",
    )
    created_at = models.DateTimeField("Erstellt am", auto_now_add=True)
    updated_at = models.DateTimeField("Geändert am", auto_now=True)
    completed_at = models.DateTimeField("Erledigt am", null=True, blank=True)
    archived_at = models.DateTimeField("Archiviert am", null=True, blank=True)

    objects = BacklogItemQuerySet.as_manager()

    class Meta:
        ordering = ["backlog_rank", "number"]
        verbose_name = "Backlog-Eintrag"
        verbose_name_plural = "Backlog-Einträge"
        constraints = [
            models.UniqueConstraint(
                fields=["project", "number"], name="backlog_unique_item_number"
            ),
            models.CheckConstraint(
                condition=models.Q(story_points__isnull=True)
                | models.Q(story_points__lte=100),
                name="backlog_story_points_range",
            ),
        ]
        indexes = [
            models.Index(fields=["project", "status"]),
            models.Index(fields=["assignee", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.key} {self.title}"

    @property
    def key(self) -> str:
        return f"{self.project.key}-{self.number}"

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    @property
    def is_high_priority(self) -> bool:
        return self.priority in self.HIGH_PRIORITIES

    @property
    def is_overdue(self) -> bool:
        return (
            self.due_date is not None
            and self.due_date < timezone.localdate()
            and self.status != self.Status.DONE
            and not self.is_archived
        )

    @property
    def is_epic(self) -> bool:
        return self.item_type == self.ItemType.EPIC

    @property
    def display_color(self) -> str:
        return self.color or DEFAULT_EPIC_COLOR

    @property
    def is_subtask(self) -> bool:
        return self.item_type == self.ItemType.SUBTASK

    @property
    def epic(self) -> "BacklogItem | None":
        """The epic this item belongs to, directly or via its parent story."""
        if self.parent is None:
            return None
        if self.parent.is_epic:
            return self.parent
        return self.parent.parent if self.parent.parent_id else None

    @property
    def time_progress(self) -> dict:
        """Logged vs. remaining work, as shares of the larger of both totals."""
        remaining = self.remaining_estimate or 0
        total = max(self.time_spent + remaining, self.original_estimate or 0, 1)
        return {
            "spent_percent": round(self.time_spent * 100 / total),
            "remaining_percent": round(remaining * 100 / total),
            "over_estimate": bool(
                self.original_estimate
                and self.time_spent + remaining > self.original_estimate
            ),
        }

    @property
    def child_progress(self) -> dict:
        children = self.children.filter(archived_at__isnull=True)
        total = children.count()
        done = children.filter(status=self.Status.DONE).count()
        percent = round(done * 100 / total) if total else 0
        return {"done": done, "total": total, "percent": percent}

    def clean(self) -> None:
        super().clean()
        error = self.hierarchy_error()
        if error:
            raise ValidationError({"parent": error})
        if self.fix_version_id and self.fix_version.project_id != self.project_id:
            raise ValidationError(
                {"fix_version": "Das Release gehört zu einem anderen Projekt."}
            )

    def hierarchy_error(self) -> str | None:
        parent = self.parent
        if parent is None:
            return HIERARCHY_ERRORS["subtask_needs_parent"] if self.is_subtask else None
        if self.pk and parent.pk == self.pk:
            return HIERARCHY_ERRORS["self_parent"]
        if parent.project_id != self.project_id:
            return HIERARCHY_ERRORS["other_project"]
        if self.is_epic:
            return HIERARCHY_ERRORS["epic_has_parent"]
        if self.is_subtask and (parent.is_epic or parent.is_subtask):
            return HIERARCHY_ERRORS["subtask_parent"]
        if not self.is_subtask and not parent.is_epic:
            return HIERARCHY_ERRORS["item_parent"]
        return None

    def link_overview(self) -> list[dict]:
        """All links of this item, phrased from this item's point of view."""
        entries = []
        outgoing = self.outgoing_links.select_related("target__project")
        incoming = self.incoming_links.select_related("source__project")
        for link in outgoing:
            entries.append(
                {"link": link, "label": link.outgoing_label, "item": link.target}
            )
        for link in incoming:
            entries.append(
                {"link": link, "label": link.incoming_label, "item": link.source}
            )
        return sorted(entries, key=lambda entry: (entry["label"], entry["item"].number))

    def open_blockers(self):
        return BacklogItem.objects.filter(
            outgoing_links__target=self,
            outgoing_links__link_type=ItemLink.LinkType.BLOCKS,
            archived_at__isnull=True,
        ).exclude(status=self.Status.DONE)


class ItemLink(models.Model):
    class LinkType(models.TextChoices):
        BLOCKS = "blocks", "blockiert"
        RELATES = "relates", "gehört zu"
        DUPLICATES = "duplicates", "ist Duplikat von"

    INCOMING_LABELS = {
        LinkType.BLOCKS: "wird blockiert von",
        LinkType.RELATES: "gehört zu",
        LinkType.DUPLICATES: "hat Duplikat",
    }

    source = models.ForeignKey(
        BacklogItem, on_delete=models.CASCADE, related_name="outgoing_links"
    )
    target = models.ForeignKey(
        BacklogItem, on_delete=models.CASCADE, related_name="incoming_links"
    )
    link_type = models.CharField("Art", max_length=20, choices=LinkType.choices)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Verknüpfung"
        verbose_name_plural = "Verknüpfungen"
        constraints = [
            models.UniqueConstraint(
                fields=["source", "target", "link_type"], name="backlog_unique_link"
            ),
            models.CheckConstraint(
                condition=~models.Q(source=models.F("target")),
                name="backlog_link_not_self",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.source.key} {self.outgoing_label} {self.target.key}"

    @property
    def outgoing_label(self) -> str:
        return self.get_link_type_display()

    @property
    def incoming_label(self) -> str:
        return self.INCOMING_LABELS[self.link_type]


class AcceptanceCriterion(models.Model):
    item = models.ForeignKey(
        BacklogItem, on_delete=models.CASCADE, related_name="acceptance_criteria"
    )
    text = models.CharField("Kriterium", max_length=500)
    is_met = models.BooleanField("Erfüllt", default=False)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "pk"]
        verbose_name = "Akzeptanzkriterium"
        verbose_name_plural = "Akzeptanzkriterien"

    def __str__(self) -> str:
        return self.text


class Comment(models.Model):
    item = models.ForeignKey(
        BacklogItem, on_delete=models.CASCADE, related_name="comments"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="comments",
    )
    body = models.TextField("Kommentar", max_length=5000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = "Kommentar"
        verbose_name_plural = "Kommentare"

    def __str__(self) -> str:
        return f"{self.author}: {self.body[:40]}"


def attachment_upload_path(instance: "Attachment", filename: str) -> str:
    extension = Path(filename).suffix.lower()
    return f"attachments/{instance.item.project_id}/{uuid4().hex}{extension}"


class Attachment(models.Model):
    item = models.ForeignKey(
        BacklogItem, on_delete=models.CASCADE, related_name="attachments"
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="attachments",
    )
    file = models.FileField(upload_to=attachment_upload_path, max_length=255)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, blank=True)
    size = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Anhang"
        verbose_name_plural = "Anhänge"

    def __str__(self) -> str:
        return self.original_name

    @property
    def is_image(self) -> bool:
        return self.content_type.startswith("image/")


class WebLink(models.Model):
    """External URL attached to an item, e.g. a specification or pull request."""

    item = models.ForeignKey(
        BacklogItem, on_delete=models.CASCADE, related_name="web_links"
    )
    url = models.URLField("Link", max_length=2000, validators=[WEB_LINK_VALIDATOR])
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = "Web-Link"
        verbose_name_plural = "Web-Links"

    def __str__(self) -> str:
        return self.url


class WorkLog(models.Model):
    """Time booked on an item by one employee."""

    item = models.ForeignKey(
        BacklogItem, on_delete=models.CASCADE, related_name="work_logs"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="work_logs",
    )
    minutes = models.PositiveIntegerField("Dauer (Minuten)")
    work_date = models.DateField("Datum")
    comment = models.CharField("Notiz", max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-work_date", "-created_at", "-pk"]
        verbose_name = "Zeitbuchung"
        verbose_name_plural = "Zeitbuchungen"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(minutes__gt=0), name="backlog_worklog_positive"
            )
        ]

    def __str__(self) -> str:
        return f"{self.item.key}: {self.minutes} min"


class SavedFilter(models.Model):
    """Named backlog filter; private or shared with the project team."""

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="saved_filters"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_filters",
    )
    name = models.CharField("Name", max_length=60)
    query = models.CharField("Filter", max_length=500)
    shared = models.BooleanField("Für das Team sichtbar", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "pk"]
        verbose_name = "Gespeicherter Filter"
        verbose_name_plural = "Gespeicherte Filter"

    def __str__(self) -> str:
        return self.name
