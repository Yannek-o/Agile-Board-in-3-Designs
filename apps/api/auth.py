"""Authentication and error handling shared by all API endpoints."""

import functools
import json

from django.contrib.auth.decorators import login_not_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.middleware.csrf import CsrfViewMiddleware
from django.views.decorators.csrf import csrf_exempt

from apps.api.models import ApiToken
from apps.projects.models import Project
from apps.projects.permissions import get_project_access

SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


class ApiError(Exception):
    def __init__(self, status: int, message: str, errors: dict | None = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.errors = errors or {}


def error_response(status: int, message: str, errors: dict | None = None):
    payload = {"error": message}
    if errors:
        payload["errors"] = errors
    return JsonResponse(payload, status=status)


def _csrf_failure(request):
    """Session-authenticated writes still need a valid CSRF token."""
    checker = CsrfViewMiddleware(lambda req: None)
    return checker.process_view(request, None, (), {})


def _authenticate(request):
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return ApiToken.authenticate(header.removeprefix("Bearer ").strip()), True
    if request.user.is_authenticated and request.user.is_active:
        return request.user, False
    return None, False


def api_view(*methods: str):
    """Restricts methods, authenticates and turns exceptions into JSON."""

    def decorator(view):
        @login_not_required
        @csrf_exempt
        @functools.wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.method not in methods:
                return error_response(405, "Methode nicht erlaubt.")
            user, via_token = _authenticate(request)
            if user is None:
                response = error_response(401, "Anmeldung erforderlich.")
                response["WWW-Authenticate"] = 'Bearer realm="api"'
                return response
            if not via_token and request.method not in SAFE_METHODS:
                if _csrf_failure(request) is not None:
                    return error_response(403, "CSRF-Prüfung fehlgeschlagen.")
            request.user = user
            try:
                return view(request, *args, **kwargs)
            except ApiError as error:
                return error_response(error.status, error.message, error.errors)
            except Http404:
                return error_response(404, "Nicht gefunden.")
            except PermissionDenied:
                return error_response(403, "Keine Berechtigung.")

        wrapper.allowed_methods = methods
        return wrapper

    return decorator


def project_for(request, project_key: str, permission: str = "can_view"):
    """Project with the same visibility rules as the web interface."""
    project = Project.objects.filter(key=project_key.upper()).first()
    if project is None:
        raise Http404
    access = get_project_access(request.user, project)
    if not access.can_view:
        raise Http404
    if not getattr(access, permission):
        raise PermissionDenied
    return project, access


def json_body(request) -> dict:
    try:
        payload = json.loads(request.body or b"{}")
    except ValueError as error:
        raise ApiError(400, "Ungültiges JSON.") from error
    if not isinstance(payload, dict):
        raise ApiError(400, "Ein JSON-Objekt wird erwartet.")
    return payload
