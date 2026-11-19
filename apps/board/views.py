import hashlib

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from apps.backlog.models import BacklogItem, ItemLink
from apps.backlog.services import (
    ConcurrentModificationError,
    change_item_status,
    create_backlog_item,
)
from apps.backlog.queries import apply_backlog_filters
from apps.board.lanes import (
    active_quick_filters,
    apply_quick_filters,
    board_statuses,
    build_columns,
    build_lanes,
    quick_filter_chips,
    selected_swimlane,
    swimlane_options,
    wip_status_info,
)
from apps.core.http import request_payload, wants_json
from apps.projects.mixins import ProjectAccessMixin
from apps.sprints.models import Sprint, SprintItem
from apps.sprints.services import SprintError, add_item_to_sprint

Status = BacklogItem.Status


def board_revision(project) -> str:
    """Fingerprint of the active sprint board; changes on every relevant edit."""
    sprint = project.sprints.filter(status=Sprint.Status.ACTIVE).first()
    if sprint is None:
        return "none"
    cards = sprint.open_items().values_list("number", "status", "version")
    fingerprint = f"{sprint.pk}:{sprint.updated_at.isoformat()}:" + ";".join(
        f"{number}/{status}/{version}" for number, status, version in cards
    )
    return hashlib.sha256(fingerprint.encode()).hexdigest()[:16]


def card_payload(item: BacklogItem) -> dict:
    return {
        "item": item.number,
        "key": item.key,
        "status": item.status,
        "status_label": item.get_status_display(),
        "version": item.version,
        "revision": board_revision(item.project),
    }


class BoardView(ProjectAccessMixin, TemplateView):
    template_name = "board/board.html"

    def get_sprint(self) -> Sprint | None:
        sprint_number = self.request.GET.get("sprint", "")
        sprints = self.project.sprints.all()
        if sprint_number.isdigit():
            return get_object_or_404(sprints, number=int(sprint_number))
        return sprints.filter(status=Sprint.Status.ACTIVE).first()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sprint = self.get_sprint()
        context["sprint"] = sprint
        context["status_choices"] = self.project.status_choices()
        context["priority_choices"] = BacklogItem.Priority.choices
        context["type_choices"] = BacklogItem.ItemType.choices
        context["members"] = self.project.active_members()
        context["filters"] = self.request.GET
        context["selectable_sprints"] = self.project.sprints.exclude(
            status=Sprint.Status.CANCELLED
        )
        if sprint is None:
            context["columns"] = []
            return context

        items = (
            sprint.open_items()
            if sprint.is_open
            else BacklogItem.objects.filter(
                sprint_entries__in=sprint.committed_entries()
            )
        )
        items = apply_backlog_filters(items, self.request.GET, self.project)
        quick = active_quick_filters(self.request.GET)
        swimlane = selected_swimlane(self.request.GET)
        items = apply_quick_filters(items, quick, self.request.user)
        open_children = Q(children__archived_at__isnull=True)
        items = list(
            items.select_related("assignee", "project", "parent__parent")
            .prefetch_related("labels")
            .annotate(
                subtask_total=Count("children", filter=open_children, distinct=True),
                subtask_done=Count(
                    "children",
                    filter=open_children & Q(children__status=Status.DONE),
                    distinct=True,
                ),
                open_blocker_count=Count(
                    "incoming_links",
                    filter=Q(incoming_links__link_type=ItemLink.LinkType.BLOCKS)
                    & Q(incoming_links__source__archived_at__isnull=True)
                    & ~Q(incoming_links__source__status=Status.DONE),
                    distinct=True,
                ),
            )
        )
        wip_info = wip_status_info(items, self.project)
        statuses = board_statuses(self.project, items)
        context["columns"] = build_columns(items, wip_info, statuses)
        context["lanes"] = [
            lane for lane in build_lanes(items, swimlane, wip_info, statuses)
            if lane["items"] or swimlane == "none"
        ]
        context["swimlane"] = swimlane
        context["swimlane_options"] = swimlane_options(self.request.GET, swimlane)
        context["quick_filters"] = quick_filter_chips(self.request.GET, quick)
        all_points = sum(item.story_points or 0 for item in items)
        done_points = sum(
            item.story_points or 0 for item in items if item.status == Status.DONE
        )
        context["points_total"] = all_points
        context["points_done"] = done_points
        context["board_editable"] = (
            sprint.status == Sprint.Status.ACTIVE and self.access.can_change_status
        )
        context["can_quick_create"] = (
            sprint.status == Sprint.Status.ACTIVE and self.access.can_manage_backlog
        )
        context["quick_create_statuses"] = QUICK_CREATE_STATUSES
        if sprint.status == Sprint.Status.ACTIVE:
            context["board_revision"] = board_revision(self.project)
            context["poll_interval_ms"] = settings.BOARD_POLL_INTERVAL_SECONDS * 1000
        return context


QUICK_CREATE_STATUSES = (Status.TODO, Status.IN_PROGRESS, Status.IN_REVIEW)
QUICK_CREATE_TYPES = (
    BacklogItem.ItemType.STORY,
    BacklogItem.ItemType.TASK,
    BacklogItem.ItemType.BUG,
    BacklogItem.ItemType.TECHNICAL,
)


class BoardQuickCreateView(ProjectAccessMixin, View):
    """Creates an item directly in a column of the active sprint."""

    required_permission = "can_manage_backlog"
    http_method_names = ["post"]

    def post(self, request, project_key: str):
        data = request_payload(request)
        board_url = reverse("board:board", args=[self.project.key])
        title = str(data.get("title", "")).strip()
        status = data.get("status") or Status.TODO
        item_type = data.get("item_type") or BacklogItem.ItemType.STORY
        sprint = self.project.sprints.filter(status=Sprint.Status.ACTIVE).first()
        if not title:
            return self.error(request, "Bitte einen Titel angeben.", board_url)
        if status not in QUICK_CREATE_STATUSES or item_type not in QUICK_CREATE_TYPES:
            return self.error(
                request, "Ungültige Spalte oder ungültiger Typ.", board_url
            )
        if sprint is None:
            return self.error(request, "Es gibt keinen aktiven Sprint.", board_url)
        try:
            with transaction.atomic():
                item = create_backlog_item(
                    self.project, actor=request.user, title=title[:200],
                    item_type=item_type, status=status,
                )
                add_item_to_sprint(sprint, item, actor=request.user)
        except (ValidationError, SprintError) as error:
            message = " ".join(getattr(error, "messages", [str(error)]))
            return self.error(request, message, board_url)
        if wants_json(request):
            return JsonResponse(
                {
                    "item": item.number,
                    "key": item.key,
                    "revision": board_revision(self.project),
                },
                status=201,
            )
        messages.success(request, f"{item.key} wurde angelegt.")
        return redirect(board_url)

    @staticmethod
    def error(request, message: str, board_url: str):
        if wants_json(request):
            return JsonResponse({"error": message}, status=400)
        messages.error(request, message)
        return redirect(board_url)


class BoardStateView(ProjectAccessMixin, View):
    """Lightweight polling endpoint for live board updates."""

    http_method_names = ["get"]

    def get(self, request, project_key: str):
        response = JsonResponse({"revision": board_revision(self.project)})
        response["Cache-Control"] = "no-store"
        return response


class BoardMoveView(ProjectAccessMixin, View):
    """Persists a card move. Accepts JSON (drag & drop) or form posts."""

    required_permission = "can_change_status"
    http_method_names = ["post"]

    def post(self, request, project_key: str):
        data = request_payload(request)
        board_url = reverse("board:board", args=[self.project.key])
        try:
            number = int(data.get("item", ""))
            version = int(data.get("version", ""))
        except (TypeError, ValueError):
            return self.error(request, "Ungültige Anfrage.", 400, board_url)

        item = get_object_or_404(
            BacklogItem.objects.active(), project=self.project, number=number
        )
        in_active_sprint = SprintItem.objects.filter(
            item=item,
            outcome=SprintItem.Outcome.OPEN,
            sprint__status=Sprint.Status.ACTIVE,
        ).exists()
        if not in_active_sprint:
            return self.error(
                request, f"{item.key} ist nicht im aktiven Sprint.", 400, board_url
            )
        try:
            item = change_item_status(
                item, data.get("status", ""), actor=request.user,
                expected_version=version,
            )
        except ValidationError as error:
            return self.error(request, " ".join(error.messages), 400, board_url)
        except ConcurrentModificationError as conflict:
            message = (
                f"{conflict.current.key} wurde zwischenzeitlich von jemand anderem "
                "geändert. Die Karte zeigt jetzt den aktuellen Stand."
            )
            if wants_json(request):
                payload = card_payload(conflict.current)
                payload["error"] = message
                return JsonResponse(payload, status=409)
            messages.error(request, message)
            return redirect(board_url)

        if wants_json(request):
            return JsonResponse(card_payload(item))
        messages.success(
            request, f"{item.key} → {item.get_status_display()}"
        )
        return redirect(board_url)

    @staticmethod
    def error(request, message: str, status: int, board_url: str):
        if wants_json(request):
            return JsonResponse({"error": message}, status=status)
        messages.error(request, message)
        return redirect(board_url)
