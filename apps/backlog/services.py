"""Business rules for backlog items. Views must use these functions for writes."""

from collections.abc import Iterable
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from apps.activity.models import ActivityEvent
from apps.activity.services import record_event
from apps.backlog.models import (
    AcceptanceCriterion,
    Attachment,
    BacklogItem,
    Comment,
    ItemLink,
    Release,
    WEB_LINK_VALIDATOR,
    WebLink,
    WorkLog,
)
from apps.backlog.scanning import scan_upload
from apps.backlog.timeparse import format_minutes
from apps.backlog.workflow import check_transition
from apps.notifications.services import (
    notify_assignment,
    notify_comment,
    notify_status_change,
    watch,
)
from apps.projects.models import Project

TRACKED_FIELDS = (
    "title",
    "description",
    "item_type",
    "priority",
    "story_points",
    "assignee",
    "status",
    "is_blocked",
    "blocked_reason",
    "due_date",
    "parent",
    "color",
    "original_estimate",
    "remaining_estimate",
    "fix_version",
)
DURATION_FIELDS = ("original_estimate", "remaining_estimate")


class ConcurrentModificationError(Exception):
    """Raised when an item was changed by someone else since it was loaded."""

    def __init__(self, current: BacklogItem):
        super().__init__(f"{current.key} wurde zwischenzeitlich geändert.")
        self.current = current


def validate_assignee(project: Project, assignee) -> None:
    if assignee is None:
        return
    is_member = project.memberships.filter(
        user=assignee, is_active=True, user__is_active=True
    ).exists()
    if not is_member:
        raise ValidationError(
            {"assignee": "Bearbeiter muss aktives Projektmitglied sein."}
        )


def display_value(item: BacklogItem, field: str) -> str:
    value = getattr(item, field)
    if value is None or value == "":
        return "–"
    if field in ("item_type", "priority", "status"):
        return getattr(item, f"get_{field}_display")()
    if isinstance(value, bool):
        return "Ja" if value else "Nein"
    if field == "due_date":
        return value.strftime("%d.%m.%Y")
    if field == "parent":
        return value.key
    if field in DURATION_FIELDS:
        return format_minutes(value)
    return str(value)


def _sync_completion(item: BacklogItem) -> None:
    if item.status == BacklogItem.Status.DONE and item.completed_at is None:
        item.completed_at = timezone.now()
    elif item.status != BacklogItem.Status.DONE:
        item.completed_at = None


def create_backlog_item(
    project: Project,
    actor=None,
    labels: Iterable = (),
    acceptance_criteria: Iterable[str] = (),
    uploads: Iterable = (),
    web_links: Iterable[str] = (),
    **fields,
) -> BacklogItem:
    validate_assignee(project, fields.get("assignee"))
    if fields.get("original_estimate") and fields.get("remaining_estimate") is None:
        fields["remaining_estimate"] = fields["original_estimate"]
    uploads = list(uploads)
    try:
        upload_names = [validate_upload(upload) for upload in uploads]
    except ValidationError as error:
        raise ValidationError({"attachments": error.messages}) from error
    link_urls = [validate_web_link_url(url) for url in web_links]
    with transaction.atomic():
        locked_project = Project.objects.select_for_update().get(pk=project.pk)
        number = locked_project.next_item_number
        locked_project.next_item_number = number + 1
        locked_project.save(update_fields=["next_item_number"])
        max_rank = project.items.aggregate(rank=Max("backlog_rank"))["rank"] or 0

        item = BacklogItem(
            project=project,
            number=number,
            backlog_rank=max_rank + 1,
            created_by=actor if actor and actor.is_authenticated else None,
            **fields,
        )
        _sync_completion(item)
        item.full_clean()
        item.save()
        item.labels.set(labels)
        AcceptanceCriterion.objects.bulk_create(
            AcceptanceCriterion(item=item, text=text, position=index)
            for index, text in enumerate(acceptance_criteria, start=1)
        )
        record_event(
            project, ActivityEvent.Action.CREATED, actor=actor, item=item,
            message=f"{item.key} angelegt",
        )
        watch(item, actor)
        uploader = actor if actor and actor.is_authenticated else None
        for upload, original_name in zip(uploads, upload_names):
            _store_attachment(item, uploader, upload, original_name)
        for url in link_urls:
            _store_web_link(item, uploader, url)
        if item.assignee_id:
            notify_assignment(item, actor)
    project.next_item_number = number + 1
    return item


def update_backlog_item(
    item: BacklogItem,
    actor,
    expected_version: int | None,
    labels: Iterable | None = None,
    **changes,
) -> BacklogItem:
    unknown = set(changes) - set(TRACKED_FIELDS)
    if unknown:
        raise ValueError(f"Nicht änderbare Felder: {', '.join(sorted(unknown))}")
    if "assignee" in changes:
        validate_assignee(item.project, changes["assignee"])

    with transaction.atomic():
        current = (
            BacklogItem.objects.select_for_update(of=("self",))
            .select_related("project", "assignee")
            .get(pk=item.pk)
        )
        if expected_version is not None and current.version != expected_version:
            raise ConcurrentModificationError(current)

        previous = {field: display_value(current, field) for field in changes}
        previous_assignee_id = current.assignee_id
        if "status" in changes:
            check_transition(current, current.status, changes["status"], actor)
        for field, value in changes.items():
            setattr(current, field, value)
        _sync_completion(current)
        current.full_clean()

        changed_fields = [
            field for field in changes
            if display_value(current, field) != previous[field]
        ]
        label_change = None
        if labels is not None:
            old_labels = sorted(label.name for label in current.labels.all())
            new_labels = sorted(label.name for label in labels)
            if old_labels != new_labels:
                label_change = (", ".join(old_labels), ", ".join(new_labels))

        if changed_fields or label_change:
            current.version += 1
            current.save()
            if labels is not None:
                current.labels.set(labels)
            for field in changed_fields:
                action = (
                    ActivityEvent.Action.STATUS_CHANGED
                    if field == "status"
                    else ActivityEvent.Action.UPDATED
                )
                record_event(
                    current.project, action, actor=actor, item=current,
                    field=field, old_value=previous[field],
                    new_value=display_value(current, field),
                )
            if label_change:
                record_event(
                    current.project, ActivityEvent.Action.UPDATED, actor=actor,
                    item=current, field="labels", old_value=label_change[0],
                    new_value=label_change[1],
                )
        if current.assignee_id and current.assignee_id != previous_assignee_id:
            notify_assignment(current, actor)
        if "status" in changed_fields:
            notify_status_change(
                current, actor, previous["status"], display_value(current, "status")
            )
    item.refresh_from_db()
    return item


def change_item_status(
    item: BacklogItem, new_status: str, actor, expected_version: int | None = None
) -> BacklogItem:
    if new_status not in BacklogItem.Status.values:
        raise ValidationError({"status": "Ungültiger Status."})
    return update_backlog_item(
        item, actor=actor, expected_version=expected_version, status=new_status
    )


def move_item_in_backlog(item: BacklogItem, position: int, actor) -> None:
    with transaction.atomic():
        ordered = list(
            BacklogItem.objects.select_for_update()
            .filter(project_id=item.project_id)
            .active()
            .order_by("backlog_rank", "number")
        )
        ordered = [entry for entry in ordered if entry.pk != item.pk]
        position = max(0, min(position, len(ordered)))
        ordered.insert(position, item)
        for rank, entry in enumerate(ordered, start=1):
            entry.backlog_rank = rank
        BacklogItem.objects.bulk_update(ordered, ["backlog_rank"])
        record_event(
            item.project, ActivityEvent.Action.REORDERED, actor=actor, item=item,
            new_value=str(position + 1),
            message=f"{item.key} auf Position {position + 1} verschoben",
        )


def archive_item(item: BacklogItem, actor) -> None:
    """Archives the item and takes it out of every open sprint."""
    from apps.sprints.models import Sprint, SprintItem
    from apps.sprints.services import remove_item_from_sprint

    with transaction.atomic():
        open_entries = SprintItem.objects.filter(
            item=item,
            outcome=SprintItem.Outcome.OPEN,
            sprint__status__in=Sprint.OPEN_STATUSES,
        ).select_related("sprint")
        for entry in open_entries:
            remove_item_from_sprint(entry.sprint, item, actor=actor)
        item.refresh_from_db(fields=["version"])
        item.archived_at = timezone.now()
        item.version += 1
        item.save(update_fields=["archived_at", "version", "updated_at"])
        record_event(
            item.project, ActivityEvent.Action.ARCHIVED, actor=actor, item=item
        )


def restore_item(item: BacklogItem, actor) -> None:
    item.archived_at = None
    item.version += 1
    item.save(update_fields=["archived_at", "version", "updated_at"])
    record_event(item.project, ActivityEvent.Action.RESTORED, actor=actor, item=item)


def add_comment(item: BacklogItem, author, body: str) -> Comment:
    body = body.strip()
    if not body:
        raise ValidationError({"body": "Der Kommentar darf nicht leer sein."})
    comment = Comment(item=item, author=author, body=body)
    comment.full_clean()
    comment.save()
    record_event(
        item.project, ActivityEvent.Action.COMMENTED, actor=author, item=item,
        message=body[:120],
    )
    notify_comment(comment)
    return comment


def _record_link_change(link: ItemLink, actor, added: bool) -> None:
    for item, label, other in (
        (link.source, link.outgoing_label, link.target),
        (link.target, link.incoming_label, link.source),
    ):
        description = f"{label} {other.key}"
        record_event(
            item.project, ActivityEvent.Action.UPDATED, actor=actor, item=item,
            field="links",
            old_value="" if added else description,
            new_value=description if added else "",
        )


def add_item_link(
    source: BacklogItem, target: BacklogItem, link_type: str, actor
) -> ItemLink:
    if link_type not in ItemLink.LinkType.values:
        raise ValidationError({"link_type": "Unbekannte Art der Verknüpfung."})
    if source.pk == target.pk:
        raise ValidationError(
            {"target": "Ein Eintrag kann nicht mit sich selbst verknüpft werden."}
        )
    if source.project_id != target.project_id:
        raise ValidationError(
            {"target": "Verknüpfungen sind nur innerhalb eines Projekts möglich."}
        )
    existing = ItemLink.objects.filter(link_type=link_type).filter(
        Q(source=source, target=target) | Q(source=target, target=source)
    )
    if existing.exists():
        raise ValidationError({"target": "Diese Verknüpfung besteht bereits."})
    with transaction.atomic():
        link = ItemLink.objects.create(
            source=source, target=target, link_type=link_type,
            created_by=actor if actor and actor.is_authenticated else None,
        )
        _record_link_change(link, actor, added=True)
    return link


def remove_item_link(link: ItemLink, actor) -> None:
    with transaction.atomic():
        _record_link_change(link, actor, added=False)
        link.delete()


def check_upload_type_and_size(uploaded_file) -> str:
    original_name = Path(uploaded_file.name).name[:255]
    extension = Path(original_name).suffix.lower().lstrip(".")
    allowed = settings.ATTACHMENT_ALLOWED_EXTENSIONS
    if extension not in allowed:
        raise ValidationError(
            {"file": f"Dateityp nicht erlaubt. Erlaubt: {', '.join(allowed)}."}
        )
    if uploaded_file.size <= 0:
        raise ValidationError({"file": "Die Datei ist leer."})
    if uploaded_file.size > settings.ATTACHMENT_MAX_UPLOAD_BYTES:
        limit_mb = settings.ATTACHMENT_MAX_UPLOAD_BYTES // (1024 * 1024)
        raise ValidationError({"file": f"Die Datei ist größer als {limit_mb} MB."})
    return original_name


def validate_upload(uploaded_file) -> str:
    original_name = check_upload_type_and_size(uploaded_file)
    scan_upload(uploaded_file)
    return original_name


def add_attachment(item: BacklogItem, uploaded_by, uploaded_file) -> Attachment:
    original_name = validate_upload(uploaded_file)
    return _store_attachment(item, uploaded_by, uploaded_file, original_name)


def _store_attachment(
    item: BacklogItem, uploaded_by, uploaded_file, original_name: str
) -> Attachment:
    attachment = Attachment.objects.create(
        item=item,
        uploaded_by=uploaded_by,
        file=uploaded_file,
        original_name=original_name,
        content_type=(getattr(uploaded_file, "content_type", "") or "")[:100],
        size=uploaded_file.size,
    )
    record_event(
        item.project, ActivityEvent.Action.ATTACHMENT_ADDED, actor=uploaded_by,
        item=item, message=original_name,
    )
    return attachment


def validate_web_link_url(url: str) -> str:
    url = url.strip()
    try:
        WEB_LINK_VALIDATOR(url)
    except ValidationError as error:
        raise ValidationError({"web_links": error.messages}) from error
    return url


def add_web_link(item: BacklogItem, actor, url: str) -> WebLink:
    return _store_web_link(item, actor, validate_web_link_url(url))


def _store_web_link(item: BacklogItem, actor, url: str) -> WebLink:
    link = WebLink.objects.create(item=item, added_by=actor, url=url)
    record_event(
        item.project, ActivityEvent.Action.LINK_ADDED, actor=actor, item=item,
        message=url[:120],
    )
    return link


def delete_web_link(link: WebLink) -> None:
    link.delete()


def log_work(
    item: BacklogItem,
    user,
    minutes: int,
    work_date,
    comment: str = "",
    remaining: int | None = None,
) -> WorkLog:
    """Books time; without an explicit value the remaining estimate shrinks."""
    if not minutes or minutes <= 0:
        raise ValidationError({"minutes": "Die Dauer muss größer als null sein."})
    with transaction.atomic():
        locked = BacklogItem.objects.select_for_update().get(pk=item.pk)
        log = WorkLog.objects.create(
            item=locked, user=user, minutes=minutes, work_date=work_date,
            comment=comment.strip()[:500],
        )
        locked.time_spent += minutes
        if remaining is not None:
            locked.remaining_estimate = remaining
        elif locked.remaining_estimate is not None:
            locked.remaining_estimate = max(locked.remaining_estimate - minutes, 0)
        locked.save(update_fields=["time_spent", "remaining_estimate", "updated_at"])
        record_event(
            locked.project, ActivityEvent.Action.WORK_LOGGED, actor=user, item=locked,
            message=f"{format_minutes(minutes)} am {work_date:%d.%m.%Y}",
        )
    return log


def delete_work_log(log: WorkLog, actor) -> None:
    """Removes a booking and gives its time back to the remaining estimate."""
    with transaction.atomic():
        item = BacklogItem.objects.select_for_update().get(pk=log.item_id)
        item.time_spent = max(item.time_spent - log.minutes, 0)
        if item.remaining_estimate is not None:
            item.remaining_estimate += log.minutes
        item.save(update_fields=["time_spent", "remaining_estimate", "updated_at"])
        log.delete()


def publish_release(release: Release, actor) -> int:
    """Marks the release as published; returns the number of unfinished items."""
    with transaction.atomic():
        locked = Release.objects.select_for_update().get(pk=release.pk)
        open_items = locked.items.open().count()
        locked.status = Release.Status.RELEASED
        locked.released_at = timezone.now()
        locked.save(update_fields=["status", "released_at"])
        record_event(
            locked.project, ActivityEvent.Action.RELEASE_PUBLISHED, actor=actor,
            message=locked.name,
        )
    return open_items
