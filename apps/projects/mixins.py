"""Reusable view mixins that load a project and enforce access rules."""

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404

from apps.projects.models import Project
from apps.projects.permissions import ProjectAccess, get_project_access

LAST_PROJECT_SESSION_KEY = "last_project_key"


class ProjectAccessMixin:
    """Resolves ``project_key`` from the URL.

    Non-members receive 404 so that foreign project keys are not disclosed.
    ``required_permission`` names a boolean attribute of ``ProjectAccess``.
    """

    required_permission = "can_view"
    project_kwarg = "project_key"

    project: Project
    access: ProjectAccess

    def dispatch(self, request, *args, **kwargs):
        self.project = get_object_or_404(
            Project, key=kwargs[self.project_kwarg].upper()
        )
        self.access = get_project_access(request.user, self.project)
        if not self.access.can_view:
            raise Http404("Projekt nicht gefunden.")
        if not getattr(self.access, self.get_required_permission(request)):
            raise PermissionDenied("Keine Berechtigung für diese Aktion.")
        request.session[LAST_PROJECT_SESSION_KEY] = self.project.key
        return super().dispatch(request, *args, **kwargs)

    def get_required_permission(self, request) -> str:
        return self.required_permission

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["project"] = self.project
        context["access"] = self.access
        return context
