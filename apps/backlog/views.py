import json
from datetime import date

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Case, Prefetch, Q, When
from django.http import (
    FileResponse,
    Http404,
    HttpResponse,
    HttpResponseBadRequest,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from apps.accounts.models import User
from apps.backlog.bulk import (
    BULK_ACTIONS,
    STATUS_ACTIONS,
    BulkActionError,
    apply_bulk_action,
    resolve_value,
)
from apps.backlog.csv_io import (
    IMPORTABLE_TYPES,
    CsvImportError,
    export_rows,
    import_items,
    write_csv,
)
from apps.backlog.forms import (
    AcceptanceCriterionForm,
    AttachmentForm,
    BacklogItemForm,
    CommentForm,
    EpicForm,
    ItemLinkForm,
    ReleaseForm,
    ReorderForm,
    WebLinkForm,
    WorkLogForm,
    upload_accept,
)
from apps.backlog.models import (
    AcceptanceCriterion,
    Attachment,
    BacklogItem,
    ItemLink,
    Release,
    SavedFilter,
    WebLink,
    WorkLog,
)
from apps.backlog.queries import (
    FILTER_PARAMS,
    PRIORITY_ORDER,
    apply_backlog_filters,
    clean_filter_query,
    epic_progress,
    release_progress,
)
from apps.backlog.services import (
    ConcurrentModificationError,
    add_attachment,
    add_comment,
    add_item_link,
    add_web_link,
    archive_item,
    change_item_status,
    create_backlog_item,
    delete_web_link,
    delete_work_log,
    display_value,
    log_work,
    move_item_in_backlog,
    publish_release,
    remove_item_link,
    restore_item,
    update_backlog_item,
)
from apps.backlog.timeparse import format_minutes
from apps.core.http import request_payload, safe_next_url, wants_json
from apps.core.markdown import render_markdown
from apps.core.toasts import success_with_undo
from apps.notifications.services import is_watching, toggle_watch
from apps.projects.mixins import ProjectAccessMixin
from apps.sprints.models import Sprint, SprintItem
from apps.sprints.services import SprintError, move_item_to_sprint

SORT_OPTIONS = {
    "rank": ("Backlog-Reihenfolge", ("backlog_rank", "number")),
    "priority": ("Priorität", ("priority_order", "backlog_rank")),
    "points": ("Story Points", ("-story_points", "backlog_rank")),
    "updated": ("Zuletzt geändert", ("-updated_at",)),
    "key": ("ID", ("number",)),
}

OPEN_SPRINT_STATUSES = ("planned", "active")


def item_detail_url(item: BacklogItem) -> str:
    return reverse("backlog:detail", args=[item.project.key, item.number])


def upload_limits() -> dict:
    return {
        "upload_limit_bytes": settings.ATTACHMENT_MAX_UPLOAD_BYTES,
        "upload_limit_mb": settings.ATTACHMENT_MAX_UPLOAD_BYTES // 1024**2,
        "upload_accept": upload_accept(),
    }


class ItemMixin(ProjectAccessMixin):
    """Loads a backlog item that belongs to the URL project."""

    item: BacklogItem

    def get_item(self) -> BacklogItem:
        if not hasattr(self, "item"):
            self.item = get_object_or_404(
                BacklogItem.objects.select_related("project", "assignee"),
                project=self.project,
                number=self.kwargs["number"],
            )
        return self.item


class BacklogListView(ProjectAccessMixin, ListView):
    template_name = "backlog/backlog_list.html"
    context_object_name = "items"
    paginate_by = 100

    def get_queryset(self):
        queryset = BacklogItem.objects.filter(project=self.project)
        if self.request.GET.get("archived") == "1":
            queryset = queryset.filter(archived_at__isnull=False)
        else:
            queryset = queryset.active()
        queryset = apply_backlog_filters(queryset, self.request.GET, self.project)
        sort_key = self.request.GET.get("sort", "rank")
        ordering = SORT_OPTIONS.get(sort_key, SORT_OPTIONS["rank"])[1]
        return (
            queryset.annotate(priority_order=PRIORITY_ORDER)
            .select_related("assignee", "project")
            .prefetch_related(
                "labels",
                Prefetch(
                    "sprint_entries",
                    queryset=self.open_sprint_entries(),
                    to_attr="open_sprint_entries",
                ),
            )
            .distinct()
            .order_by(*ordering)
        )

    def open_sprint_entries(self):
        return SprintItem.objects.filter(
            outcome=SprintItem.Outcome.OPEN,
            sprint__status__in=OPEN_SPRINT_STATUSES,
        ).select_related("sprint")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = self.request.GET
        context.update(
            {
                "filters": params,
                "type_choices": BacklogItem.ItemType.choices,
                "priority_choices": BacklogItem.Priority.choices,
                "status_choices": BacklogItem.Status.choices,
                "sort_choices": [
                    (key, label) for key, (label, _) in SORT_OPTIONS.items()
                ],
                "members": self.project.active_members(),
                "labels": self.project.labels.all(),
                "epics": self.project.items.active().filter(
                    item_type=BacklogItem.ItemType.EPIC
                ),
                "releases": self.project.releases.all(),
                "saved_filters": SavedFilter.objects.filter(
                    Q(user=self.request.user) | Q(shared=True), project=self.project
                ).select_related("user"),
                "current_query": clean_filter_query(params.urlencode()),
                "open_sprints": self.project.sprints.filter(
                    status__in=Sprint.OPEN_STATUSES
                ).order_by("start_date", "number"),
                "open_releases": self.project.releases.filter(
                    status=Release.Status.UNRELEASED
                ),
                "bulk_status_only": not self.access.can_manage_backlog,
                "can_reorder": self.access.can_manage_backlog
                and params.get("sort", "rank") == "rank"
                and not any(
                    params.get(name) for name in (*FILTER_PARAMS, "archived")
                ),
            }
        )
        return context


def plannable_items(project):
    """Items shown in the planning view; epics and sub-tasks are not planned."""
    excluded_types = [BacklogItem.ItemType.EPIC, BacklogItem.ItemType.SUBTASK]
    return (
        project.items.active()
        .exclude(item_type__in=excluded_types)
        .select_related("assignee", "project", "parent__parent")
        .prefetch_related("labels")
        .order_by("backlog_rank", "number")
    )


class BacklogPlanningView(ProjectAccessMixin, TemplateView):
    """Jira-style backlog: open sprints on top, unplanned items below."""

    template_name = "backlog/planning.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sprints = list(
            self.project.sprints.filter(status__in=Sprint.OPEN_STATUSES).order_by(
                Case(When(status=Sprint.Status.ACTIVE, then=0), default=1),
                "number",
            )
        )
        items = plannable_items(self.project)
        sections = []
        planned_ids = set()
        for sprint in sprints:
            sprint_items = list(
                items.filter(
                    sprint_entries__sprint=sprint,
                    sprint_entries__outcome=SprintItem.Outcome.OPEN,
                )
            )
            planned_ids.update(item.pk for item in sprint_items)
            sections.append(self.section(sprint.label, sprint, sprint_items))
        backlog_items = [
            item for item in items.exclude(status=BacklogItem.Status.DONE)
            if item.pk not in planned_ids
        ]
        sections.append(self.section("Backlog", None, backlog_items))
        context.update(
            {
                "sections": sections,
                "sprints": sprints,
                "can_plan": self.access.can_manage_backlog,
            }
        )
        return context

    @staticmethod
    def section(title: str, sprint, items: list) -> dict:
        return {
            "title": title,
            "sprint": sprint,
            "items": items,
            "points": sum(item.story_points or 0 for item in items),
        }


class BacklogPlanMoveView(ProjectAccessMixin, View):
    """Moves an item into an open sprint or back to the backlog."""

    required_permission = "can_manage_backlog"
    http_method_names = ["post"]

    def post(self, request, project_key: str):
        data = request_payload(request)
        planning_url = reverse("backlog:planning", args=[self.project.key])
        number = str(data.get("item", ""))
        sprint_number = data.get("sprint")
        if not number.isdigit():
            return self.error(request, "Ungültige Anfrage.", planning_url)
        item = get_object_or_404(
            self.project.items.active(), number=int(number)
        )
        target = None
        if sprint_number not in (None, "", "backlog"):
            target = get_object_or_404(
                self.project.sprints.filter(status__in=Sprint.OPEN_STATUSES),
                number=int(sprint_number) if str(sprint_number).isdigit() else 0,
            )
        try:
            move_item_to_sprint(item, target, actor=request.user)
        except SprintError as error:
            return self.error(request, str(error), planning_url)
        destination = target.label if target else "Backlog"
        if wants_json(request):
            return JsonResponse(
                {"item": item.number, "sprint": target and target.number}
            )
        messages.success(request, f"{item.key} → {destination}")
        return redirect(planning_url)

    @staticmethod
    def error(request, message: str, planning_url: str):
        if wants_json(request):
            return JsonResponse({"error": message}, status=400)
        messages.error(request, message)
        return redirect(planning_url)


class ReleaseListView(ProjectAccessMixin, View):
    template_name = "backlog/releases.html"

    def get_required_permission(self, request) -> str:
        return "can_manage_backlog" if request.method == "POST" else "can_view"

    def get(self, request, project_key: str):
        return self.render(ReleaseForm(project=self.project))

    def post(self, request, project_key: str):
        form = ReleaseForm(request.POST, project=self.project)
        if form.is_valid():
            form.save()
            messages.success(request, f"Release „{form.instance.name}“ angelegt.")
            return redirect("backlog:releases", project_key=self.project.key)
        return self.render(form)

    def render(self, form):
        return render(
            self.request,
            self.template_name,
            {
                "project": self.project,
                "access": self.access,
                "form": form,
                "releases": release_progress(self.project),
            },
        )


class ReleasePublishView(ProjectAccessMixin, View):
    required_permission = "can_manage_backlog"
    http_method_names = ["post"]

    def post(self, request, project_key: str, pk: int):
        release = get_object_or_404(Release, pk=pk, project=self.project)
        open_items = publish_release(release, actor=request.user)
        message = f"Release „{release.name}“ veröffentlicht."
        if open_items:
            message += f" {open_items} Einträge waren noch nicht erledigt."
        messages.success(request, message)
        return redirect("backlog:releases", project_key=self.project.key)


class EpicListView(ProjectAccessMixin, View):
    template_name = "backlog/epics.html"

    def get_required_permission(self, request) -> str:
        return "can_manage_backlog" if request.method == "POST" else "can_view"

    def get(self, request, project_key: str):
        return self.render(EpicForm())

    def post(self, request, project_key: str):
        form = EpicForm(request.POST)
        if form.is_valid():
            try:
                epic = create_backlog_item(
                    project=self.project,
                    actor=request.user,
                    item_type=BacklogItem.ItemType.EPIC,
                    **form.cleaned_data,
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(request, f"Epic {epic.key} angelegt.")
                return redirect("backlog:epics", project_key=self.project.key)
        return self.render(form)

    def render(self, form):
        return render(
            self.request,
            self.template_name,
            {
                "project": self.project,
                "access": self.access,
                "form": form,
                "epics": epic_progress(self.project),
            },
        )


class BacklogItemCreateView(ProjectAccessMixin, View):
    required_permission = "can_manage_backlog"
    template_name = "backlog/item_form.html"

    def get(self, request, project_key: str):
        return self.render(
            BacklogItemForm(project=self.project, initial=self.parent_initial())
        )

    def parent_initial(self) -> dict:
        number = self.request.GET.get("parent", "")
        if not number.isdigit():
            return {}
        parent = self.project.items.active().filter(number=int(number)).first()
        if parent is None or parent.is_subtask:
            return {}
        item_type = (
            BacklogItem.ItemType.STORY if parent.is_epic
            else BacklogItem.ItemType.SUBTASK
        )
        return {"parent": parent.pk, "item_type": item_type}

    def post(self, request, project_key: str):
        form = BacklogItemForm(request.POST, request.FILES, project=self.project)
        if form.is_valid():
            try:
                item = create_backlog_item(
                    project=self.project,
                    actor=request.user,
                    labels=form.cleaned_data["labels"],
                    acceptance_criteria=form.cleaned_data["acceptance_criteria_text"],
                    uploads=form.cleaned_data["attachments"],
                    web_links=form.cleaned_data["web_links"],
                    **form.item_fields(),
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(request, f"{item.key} wurde angelegt.")
                return redirect(item_detail_url(item))
        return self.render(form)

    def render(self, form, status: int = 200):
        return render(
            self.request,
            self.template_name,
            {
                "form": form,
                "project": self.project,
                "access": self.access,
                **upload_limits(),
            },
            status=status,
        )


class BacklogItemDetailView(ItemMixin, DetailView):
    template_name = "backlog/item_detail.html"
    context_object_name = "item"

    def get_template_names(self):
        if self.request.GET.get("partial") == "1":
            return ["backlog/_item_panel.html"]
        return [self.template_name]

    def get_object(self, queryset=None):
        return self.get_item()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        item = self.object
        context.update(
            {
                "criteria": item.acceptance_criteria.all(),
                "children": item.children.filter(archived_at__isnull=True)
                .select_related("assignee", "project")
                .order_by("number"),
                "child_progress": item.child_progress,
                "links": item.link_overview(),
                "is_watching": is_watching(item, self.request.user),
                "watcher_count": item.watches.count(),
                "mention_users": [
                    {"username": m.user.username, "name": m.user.display_name}
                    for m in self.project.active_members()
                ],
                "members": self.project.active_members(),
                "priority_choices": BacklogItem.Priority.choices,
                "can_inline_edit": self.access.can_change_status
                and not item.is_archived,
                "can_inline_plan": self.access.can_manage_backlog
                and not item.is_archived,
                "link_form": ItemLinkForm(project=self.project),
                "link_types": ItemLink.LinkType.choices,
                "comments": item.comments.select_related("author"),
                "attachments": item.attachments.select_related("uploaded_by"),
                "web_links": item.web_links.all(),
                "web_link_form": WebLinkForm(),
                "work_logs": item.work_logs.select_related("user")[:20],
                "work_log_form": WorkLogForm(
                    initial={"work_date": date.today().isoformat()}
                ),
                "history": item.activity.select_related("actor")[:50],
                "sprint_history": item.sprint_entries.select_related(
                    "sprint"
                ).order_by("sprint__number"),
                "comment_form": CommentForm(),
                "attachment_form": AttachmentForm(),
                "criterion_form": AcceptanceCriterionForm(),
                "status_choices": self.project.status_choices(),
                "next_url": safe_next_url(self.request, ""),
            }
        )
        return context


class BacklogItemEditView(ItemMixin, View):
    required_permission = "can_change_status"
    template_name = "backlog/item_form.html"

    def make_form(self, data=None):
        return BacklogItemForm(
            data,
            instance=self.get_item(),
            project=self.project,
            limited=not self.access.can_manage_backlog,
        )

    def get(self, request, project_key: str, number: int):
        return self.render(self.make_form())

    def post(self, request, project_key: str, number: int):
        item = self.get_item()
        form = self.make_form(request.POST)
        if form.is_valid():
            try:
                update_backlog_item(
                    item,
                    actor=request.user,
                    expected_version=form.cleaned_data.get("version"),
                    labels=form.selected_labels(),
                    **form.item_fields(),
                )
            except ConcurrentModificationError:
                messages.error(
                    request,
                    "Der Eintrag wurde zwischenzeitlich von jemand anderem geändert. "
                    "Bitte die aktuellen Werte prüfen und erneut speichern.",
                )
                item.refresh_from_db()
                return self.render(self.make_form(), status=409)
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(request, f"{item.key} wurde gespeichert.")
                return redirect(safe_next_url(request, item_detail_url(item)))
        return self.render(form)

    def render(self, form, status: int = 200):
        return render(
            self.request,
            self.template_name,
            {
                "form": form,
                "item": self.get_item(),
                "project": self.project,
                "access": self.access,
                "next_url": safe_next_url(self.request, ""),
            },
            status=status,
        )


class ItemStatusView(ItemMixin, View):
    required_permission = "can_change_status"
    http_method_names = ["post"]

    def post(self, request, project_key: str, number: int):
        item = self.get_item()
        version = request.POST.get("version", "")
        try:
            change_item_status(
                item,
                request.POST.get("status", ""),
                actor=request.user,
                expected_version=int(version) if version.isdigit() else None,
            )
        except ConcurrentModificationError:
            messages.error(request, "Status wurde zwischenzeitlich geändert.")
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, f"Status von {item.key} geändert.")
        return redirect(safe_next_url(request, item_detail_url(item)))


class ItemArchiveView(ItemMixin, View):
    required_permission = "can_manage_backlog"
    http_method_names = ["post"]
    archive = True

    def post(self, request, project_key: str, number: int):
        item = self.get_item()
        if self.archive:
            archive_item(item, actor=request.user)
            success_with_undo(
                request,
                f"{item.key} wurde archiviert.",
                reverse("backlog:restore", args=[item.project.key, item.number]),
            )
        else:
            restore_item(item, actor=request.user)
            messages.success(request, f"{item.key} wurde wiederhergestellt.")
        return redirect(item_detail_url(item))


class CommentCreateView(ItemMixin, View):
    required_permission = "can_comment"
    http_method_names = ["post"]

    def post(self, request, project_key: str, number: int):
        item = self.get_item()
        form = CommentForm(request.POST)
        if form.is_valid():
            try:
                add_comment(item, author=request.user, body=form.cleaned_data["body"])
            except ValidationError as error:
                messages.error(request, " ".join(error.messages))
            else:
                messages.success(request, "Kommentar gespeichert.")
        else:
            messages.error(request, "Der Kommentar ist ungültig.")
        return redirect(safe_next_url(request, item_detail_url(item)))


INLINE_FIELDS = (
    "title", "description", "priority", "story_points", "assignee", "due_date",
)
NOT_INLINE_EDITABLE = "Dieses Feld kann nicht direkt bearbeitet werden."


def inline_html(item: BacklogItem, field: str) -> str | None:
    """Rendered Markdown for rich-text fields; ``None`` for plain fields."""
    if field != "description":
        return None
    return str(render_markdown(item.description)) or "Keine Beschreibung."


def inline_display(item: BacklogItem, field: str) -> str:
    if field == "assignee":
        return item.assignee.display_name if item.assignee else "?"
    return display_value(item, field)


def inline_raw_value(item: BacklogItem, field: str) -> str:
    value = getattr(item, f"{field}_id" if field == "assignee" else field)
    if value is None:
        return ""
    if field == "due_date":
        return value.isoformat()
    return str(value)


def parse_inline_value(field: str, raw):
    """Converts a submitted inline value into the model value or raises."""
    text = "" if raw is None else str(raw).strip()
    if field == "title":
        if not text:
            raise ValidationError("Bitte einen Titel angeben.")
        return text
    if field == "description":
        return "" if raw is None else str(raw)
    if field == "priority":
        if text not in BacklogItem.Priority.values:
            raise ValidationError("Ungültige Priorität.")
        return text
    if field == "story_points":
        if not text:
            return None
        if not text.isdigit():
            raise ValidationError("Story Points müssen eine ganze Zahl sein.")
        return int(text)
    if field == "assignee":
        if not text:
            return None
        user = User.objects.filter(pk=int(text)).first() if text.isdigit() else None
        if user is None:
            raise ValidationError("Unbekannter Bearbeiter.")
        return user
    if field == "due_date":
        if not text:
            return None
        try:
            return date.fromisoformat(text)
        except ValueError as error:
            raise ValidationError("Ungültiges Datum.") from error
    raise ValidationError(NOT_INLINE_EDITABLE)


class ItemInlineUpdateView(ItemMixin, View):
    """Saves a single field edited in place on the detail page or dialog."""

    required_permission = "can_change_status"
    http_method_names = ["post"]

    def post(self, request, project_key: str, number: int):
        item = self.get_item()
        data = request_payload(request)
        field = data.get("field", "")
        if field not in INLINE_FIELDS:
            return JsonResponse({"error": NOT_INLINE_EDITABLE}, status=400)
        planning_field = field in BacklogItemForm.PLANNING_FIELDS
        if planning_field and not self.access.can_manage_backlog:
            return JsonResponse(
                {"error": "Keine Berechtigung für dieses Feld."}, status=403
            )
        try:
            version = int(data.get("version", ""))
            value = parse_inline_value(field, data.get("value"))
            item = update_backlog_item(
                item, actor=request.user, expected_version=version, **{field: value}
            )
        except (TypeError, ValueError):
            return JsonResponse({"error": "Ungültige Anfrage."}, status=400)
        except ConcurrentModificationError as conflict:
            return JsonResponse(
                {
                    "error": f"{conflict.current.key} wurde zwischenzeitlich geändert.",
                    "display": inline_display(conflict.current, field),
                    "html": inline_html(conflict.current, field),
                    "value": inline_raw_value(conflict.current, field),
                    "version": conflict.current.version,
                },
                status=409,
            )
        except ValidationError as error:
            return JsonResponse({"error": " ".join(error.messages)}, status=400)
        return JsonResponse(
            {
                "field": field,
                "display": inline_display(item, field),
                "html": inline_html(item, field),
                "value": inline_raw_value(item, field),
                "version": item.version,
            }
        )


class ItemWatchToggleView(ItemMixin, View):
    """Starts or stops watching an item for the current user."""

    http_method_names = ["post"]

    def post(self, request, project_key: str, number: int):
        item = self.get_item()
        watching = toggle_watch(item, request.user)
        if wants_json(request):
            return JsonResponse(
                {"watching": watching, "watchers": item.watches.count()}
            )
        messages.success(
            request,
            f"Du beobachtest {item.key}." if watching
            else f"Du beobachtest {item.key} nicht mehr.",
        )
        return redirect(safe_next_url(request, item_detail_url(item)))


class ItemLinkAddView(ItemMixin, View):
    required_permission = "can_change_status"
    http_method_names = ["post"]

    def post(self, request, project_key: str, number: int):
        item = self.get_item()
        form = ItemLinkForm(request.POST, project=self.project)
        if form.is_valid():
            try:
                add_item_link(
                    item, form.cleaned_data["target"],
                    form.cleaned_data["link_type"], actor=request.user,
                )
            except ValidationError as error:
                messages.error(request, " ".join(error.messages))
            else:
                messages.success(request, "Verknüpfung gespeichert.")
        else:
            errors = [message for field in form.errors.values() for message in field]
            messages.error(request, " ".join(errors))
        return redirect(safe_next_url(request, item_detail_url(item)))


class ItemLinkDeleteView(ItemMixin, View):
    required_permission = "can_change_status"
    http_method_names = ["post"]

    def post(self, request, project_key: str, number: int, pk: int):
        item = self.get_item()
        link = get_object_or_404(
            ItemLink.objects.filter(Q(source=item) | Q(target=item)), pk=pk
        )
        remove_item_link(link, actor=request.user)
        messages.success(request, "Verknüpfung entfernt.")
        return redirect(safe_next_url(request, item_detail_url(item)))


class WebLinkAddView(ItemMixin, View):
    required_permission = "can_comment"
    http_method_names = ["post"]

    def post(self, request, project_key: str, number: int):
        item = self.get_item()
        form = WebLinkForm(request.POST)
        if form.is_valid():
            add_web_link(item, actor=request.user, url=form.cleaned_data["url"])
            messages.success(request, "Link hinzugefügt.")
        else:
            messages.error(request, " ".join(form.errors.get("url", [])))
        return redirect(safe_next_url(request, item_detail_url(item)))


class WebLinkDeleteView(ItemMixin, View):
    required_permission = "can_change_status"
    http_method_names = ["post"]

    def post(self, request, project_key: str, number: int, pk: int):
        item = self.get_item()
        delete_web_link(get_object_or_404(WebLink, pk=pk, item=item))
        messages.success(request, "Link entfernt.")
        return redirect(safe_next_url(request, item_detail_url(item)))


class WorkLogCreateView(ItemMixin, View):
    required_permission = "can_change_status"
    http_method_names = ["post"]

    def post(self, request, project_key: str, number: int):
        item = self.get_item()
        form = WorkLogForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            log_work(
                item, request.user, minutes=data["duration"],
                work_date=data["work_date"], comment=data["comment"],
                remaining=data["remaining"],
            )
            messages.success(request, f"{format_minutes(data['duration'])} gebucht.")
        else:
            errors = [error for field in form.errors.values() for error in field]
            messages.error(request, " ".join(errors))
        return redirect(safe_next_url(request, item_detail_url(item)))


class WorkLogDeleteView(ItemMixin, View):
    required_permission = "can_change_status"
    http_method_names = ["post"]

    def post(self, request, project_key: str, number: int, pk: int):
        item = self.get_item()
        log = get_object_or_404(WorkLog, pk=pk, item=item)
        if log.user_id != request.user.pk and not self.access.can_manage_backlog:
            raise PermissionDenied("Nur eigene Buchungen können gelöscht werden.")
        delete_work_log(log, actor=request.user)
        messages.success(request, "Zeitbuchung gelöscht.")
        return redirect(safe_next_url(request, item_detail_url(item)))


class CriterionAddView(ItemMixin, View):
    required_permission = "can_manage_backlog"
    http_method_names = ["post"]

    def post(self, request, project_key: str, number: int):
        item = self.get_item()
        form = AcceptanceCriterionForm(request.POST)
        if form.is_valid():
            position = item.acceptance_criteria.count() + 1
            AcceptanceCriterion.objects.create(
                item=item, text=form.cleaned_data["text"].strip(), position=position
            )
        else:
            messages.error(request, "Kriterium ist ungültig.")
        return redirect(safe_next_url(request, item_detail_url(item)))


class CriterionToggleView(ItemMixin, View):
    required_permission = "can_change_status"
    http_method_names = ["post"]

    def post(self, request, project_key: str, number: int, pk: int):
        item = self.get_item()
        criterion = get_object_or_404(AcceptanceCriterion, pk=pk, item=item)
        criterion.is_met = not criterion.is_met
        criterion.save(update_fields=["is_met"])
        return redirect(safe_next_url(request, item_detail_url(item)))


class CriterionDeleteView(ItemMixin, View):
    required_permission = "can_manage_backlog"
    http_method_names = ["post"]

    def post(self, request, project_key: str, number: int, pk: int):
        item = self.get_item()
        get_object_or_404(AcceptanceCriterion, pk=pk, item=item).delete()
        return redirect(safe_next_url(request, item_detail_url(item)))


class AttachmentUploadView(ItemMixin, View):
    required_permission = "can_comment"
    http_method_names = ["post"]

    def post(self, request, project_key: str, number: int):
        item = self.get_item()
        form = AttachmentForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                add_attachment(
                    item, uploaded_by=request.user,
                    uploaded_file=form.cleaned_data["file"],
                )
            except ValidationError as error:
                messages.error(request, " ".join(error.messages))
            else:
                messages.success(request, "Anhang hochgeladen.")
        else:
            messages.error(request, "Bitte eine Datei auswählen.")
        return redirect(safe_next_url(request, item_detail_url(item)))


class AttachmentDownloadView(ItemMixin, View):
    def get(self, request, project_key: str, number: int, pk: int):
        attachment = get_object_or_404(Attachment, pk=pk, item=self.get_item())
        try:
            file_handle = attachment.file.open("rb")
        except FileNotFoundError as error:
            raise Http404("Datei nicht gefunden.") from error
        return FileResponse(
            file_handle, as_attachment=True, filename=attachment.original_name
        )


class BacklogReorderView(ProjectAccessMixin, View):
    required_permission = "can_manage_backlog"
    http_method_names = ["post"]

    def post(self, request, project_key: str):
        if request.content_type == "application/json":
            try:
                data = json.loads(request.body or b"{}")
            except ValueError:
                data = {}
        else:
            data = request.POST
        form = ReorderForm(data)
        if not form.is_valid():
            if wants_json(request):
                return JsonResponse({"error": "Ungültige Anfrage."}, status=400)
            messages.error(request, "Ungültige Anfrage.")
            return redirect("backlog:list", project_key=self.project.key)
        item = get_object_or_404(
            BacklogItem.objects.active(),
            project=self.project,
            number=form.cleaned_data["item"],
        )
        move_item_in_backlog(item, form.cleaned_data["position"], actor=request.user)
        if wants_json(request):
            return JsonResponse({"ok": True})
        return redirect("backlog:list", project_key=self.project.key)


class SavedFilterCreateView(ProjectAccessMixin, View):
    def post(self, request, project_key):
        name = request.POST.get("name", "").strip()[:60]
        query = clean_filter_query(request.POST.get("query", ""))
        if name and query:
            SavedFilter.objects.create(
                project=self.project,
                user=request.user,
                name=name,
                query=query,
                shared=request.POST.get("shared") == "on",
            )
            messages.success(request, f"Filter „{name}“ gespeichert.")
        else:
            messages.error(request, "Name und mindestens ein Filter sind nötig.")
        return redirect(f"{reverse('backlog:list', args=[project_key])}?{query}")


class SavedFilterDeleteView(ProjectAccessMixin, View):
    def post(self, request, project_key, pk):
        saved = get_object_or_404(
            SavedFilter, pk=pk, project=self.project, user=request.user
        )
        saved.delete()
        messages.success(request, f"Filter „{saved.name}“ gelöscht.")
        return redirect("backlog:list", project_key=project_key)


class BulkEditView(ProjectAccessMixin, View):
    """Applies one action to all selected items of the backlog list."""

    http_method_names = ["post"]

    def get_required_permission(self, request) -> str:
        if request.POST.get("action") in STATUS_ACTIONS:
            return "can_change_status"
        return "can_manage_backlog"

    def post(self, request, project_key: str):
        action = request.POST.get("action", "")
        if action not in BULK_ACTIONS:
            return HttpResponseBadRequest("Unbekannte Aktion.")
        back_url = safe_next_url(
            request, reverse("backlog:list", args=[self.project.key])
        )
        numbers = [n for n in request.POST.getlist("items") if n.isdigit()]
        items = list(
            self.project.items.active()
            .filter(number__in=numbers)
            .select_related("project")
            .order_by("number")
        )
        if not items:
            messages.error(request, "Keine Einträge ausgewählt.")
            return redirect(back_url)
        try:
            value = resolve_value(self.project, action, request.POST.get("value", ""))
        except BulkActionError as error:
            messages.error(request, str(error))
            return redirect(back_url)
        result = apply_bulk_action(items, action, value, actor=request.user)
        if result.changed:
            messages.success(request, f"{result.changed} Einträge geändert.")
        for failure in result.failures:
            messages.error(request, failure)
        return redirect(back_url)


class CsvExportView(BacklogListView):
    """Downloads the (filtered) backlog list as Excel-friendly CSV."""

    def get(self, request, project_key: str):
        items = self.get_queryset().select_related("fix_version")
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        filename = f"{self.project.key}-backlog-{date.today():%Y-%m-%d}.csv"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        write_csv(export_rows(items), response)
        return response


class CsvImportView(ProjectAccessMixin, View):
    required_permission = "can_manage_backlog"
    template_name = "backlog/import.html"

    def get(self, request, project_key: str):
        return self.render([])

    def post(self, request, project_key: str):
        uploaded = request.FILES.get("file")
        if uploaded is None:
            return self.render(["Bitte eine CSV-Datei auswählen."])
        try:
            result = import_items(self.project, uploaded, actor=request.user)
        except CsvImportError as error:
            return self.render([str(error)])
        if result.errors:
            return self.render(result.errors)
        messages.success(request, f"{len(result.created)} Einträge importiert.")
        return redirect("backlog:list", project_key=self.project.key)

    def render(self, errors):
        return render(
            self.request,
            self.template_name,
            {
                "project": self.project,
                "access": self.access,
                "errors": errors,
                "type_choices": [(c.value, c.label) for c in IMPORTABLE_TYPES],
                "priority_choices": BacklogItem.Priority.choices,
            },
        )
