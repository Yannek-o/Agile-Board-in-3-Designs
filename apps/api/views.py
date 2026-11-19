"""JSON API v1 for projects, backlog items and sprints."""

from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from apps.api.auth import ApiError, api_view, json_body, project_for
from apps.backlog.models import BacklogItem
from apps.backlog.queries import apply_backlog_filters
from apps.backlog.services import (
    ConcurrentModificationError,
    create_backlog_item,
    update_backlog_item,
)
from apps.projects.permissions import visible_projects

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
CREATE_FIELDS = (
    "title", "description", "item_type", "priority", "story_points", "due_date",
)
STATUS_FIELDS = {"status"}
PLANNING_FIELDS = {
    "title", "description", "item_type", "priority", "story_points", "assignee",
    "due_date",
}


def user_ref(user) -> dict | None:
    if user is None:
        return None
    return {"username": user.username, "name": user.display_name}


def item_data(item: BacklogItem) -> dict:
    return {
        "key": item.key,
        "number": item.number,
        "title": item.title,
        "description": item.description,
        "item_type": item.item_type,
        "status": item.status,
        "status_label": item.project.status_label(item.status),
        "priority": item.priority,
        "story_points": item.story_points,
        "assignee": user_ref(item.assignee),
        "due_date": item.due_date.isoformat() if item.due_date else None,
        "version": item.version,
        "archived": item.archived_at is not None,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def paginate(request, queryset):
    try:
        limit = min(int(request.GET.get("limit", DEFAULT_LIMIT)), MAX_LIMIT)
        offset = max(int(request.GET.get("offset", 0)), 0)
    except ValueError as error:
        raise ApiError(400, "limit und offset müssen Zahlen sein.") from error
    limit = max(limit, 1)
    return queryset.count(), queryset[offset:offset + limit], limit, offset


def resolve_assignee(project, username):
    if username in (None, ""):
        return None
    membership = project.active_members().filter(user__username=username).first()
    if membership is None:
        raise ApiError(
            400, "Ungültige Eingaben.", {"assignee": ["Kein aktives Projektmitglied."]}
        )
    return membership.user


def validation_error(error: ValidationError) -> ApiError:
    errors = (
        error.message_dict if hasattr(error, "error_dict")
        else {"__all__": error.messages}
    )
    return ApiError(400, "Ungültige Eingaben.", errors)


@api_view("GET")
def projects(request):
    queryset = visible_projects(request.user).not_archived().order_by("key")
    return JsonResponse(
        {
            "results": [
                {
                    "key": project.key,
                    "name": project.name,
                    "status": project.status,
                }
                for project in queryset
            ]
        }
    )


@api_view("GET", "POST")
def items(request, project_key: str):
    if request.method == "POST":
        return create_item(request, project_key)
    project, _ = project_for(request, project_key)
    queryset = (
        apply_backlog_filters(project.items.active(), request.GET, project)
        .select_related("assignee", "project")
        .distinct()
        .order_by("backlog_rank", "number")
    )
    count, page, limit, offset = paginate(request, queryset)
    return JsonResponse(
        {
            "count": count,
            "limit": limit,
            "offset": offset,
            "results": [item_data(item) for item in page],
        }
    )


def create_item(request, project_key: str):
    project, _ = project_for(request, project_key, "can_manage_backlog")
    payload = json_body(request)
    fields = {name: payload[name] for name in CREATE_FIELDS if name in payload}
    if "assignee" in payload:
        fields["assignee"] = resolve_assignee(project, payload["assignee"])
    if not str(fields.get("title", "")).strip():
        raise ApiError(400, "Ungültige Eingaben.", {"title": ["Pflichtfeld."]})
    try:
        item = create_backlog_item(project=project, actor=request.user, **fields)
    except ValidationError as error:
        raise validation_error(error) from error
    return JsonResponse(item_data(item), status=201)


@api_view("GET", "PATCH")
def item(request, project_key: str, number: int):
    project, access = project_for(request, project_key)
    backlog_item = get_object_or_404(
        project.items.select_related("assignee", "project"), number=number
    )
    if request.method == "GET":
        return JsonResponse(item_data(backlog_item))

    payload = json_body(request)
    version = payload.pop("version", None)
    unknown = set(payload) - STATUS_FIELDS - PLANNING_FIELDS
    if unknown:
        raise ApiError(
            400, "Ungültige Eingaben.",
            {name: ["Feld kann nicht geändert werden."] for name in sorted(unknown)},
        )
    needs_planning = bool(set(payload) & PLANNING_FIELDS)
    allowed = access.can_manage_backlog if needs_planning else access.can_change_status
    if not allowed:
        raise ApiError(403, "Keine Berechtigung.")
    if "assignee" in payload:
        payload["assignee"] = resolve_assignee(project, payload["assignee"])
    if "status" in payload and payload["status"] not in BacklogItem.Status.values:
        raise ApiError(400, "Ungültige Eingaben.", {"status": ["Ungültiger Status."]})
    try:
        updated = update_backlog_item(
            backlog_item, actor=request.user, expected_version=version, **payload
        )
    except ConcurrentModificationError as error:
        raise ApiError(409, str(error)) from error
    except ValidationError as error:
        raise validation_error(error) from error
    return JsonResponse(item_data(updated))


@api_view("GET")
def sprints(request, project_key: str):
    project, _ = project_for(request, project_key)
    queryset = project.sprints.order_by("-number")
    return JsonResponse(
        {
            "results": [
                {
                    "number": sprint.number,
                    "name": sprint.label,
                    "goal": sprint.goal,
                    "status": sprint.status,
                    "start_date": sprint.start_date.isoformat(),
                    "end_date": sprint.end_date.isoformat(),
                    "items": [
                        entry.key
                        for entry in sprint.open_items().select_related("project")
                    ],
                }
                for sprint in queryset
            ]
        }
    )
