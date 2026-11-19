from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.core.http import wants_json
from apps.core.search import MIN_QUERY_LENGTH, search_items
from apps.projects.mixins import LAST_PROJECT_SESSION_KEY
from apps.projects.models import Project
from apps.projects.permissions import visible_projects
from apps.sprints.models import Sprint

PALETTE_RESULTS = 8

SECTION_ROUTES = {
    "backlog": "backlog:planning",
    "sprints": "sprints:list",
    "board": "board:board",
    "team": "projects:team",
    "reports": "reporting:project_report",
    "activity": "activity:list",
}


def default_project_key(user) -> str | None:
    """Prefers a project with a running sprint, then any active project."""
    projects = visible_projects(user).not_archived().filter(
        status=Project.Status.ACTIVE
    )
    with_sprint = projects.filter(sprints__status=Sprint.Status.ACTIVE)
    project = with_sprint.order_by("name").first() or projects.order_by("name").first()
    return project.key if project else None


def go_to_section(request, section: str):
    """Opens a project-scoped section for the most recently used project."""
    if section not in SECTION_ROUTES:
        raise Http404("Unbekannter Bereich.")
    project_key = request.session.get(LAST_PROJECT_SESSION_KEY)
    if not (
        project_key and visible_projects(request.user).filter(key=project_key).exists()
    ):
        project_key = default_project_key(request.user)
    if project_key:
        return redirect(SECTION_ROUTES[section], project_key=project_key)
    return redirect(f"{reverse('projects:list')}?section={section}")


def search(request):
    """Full-text search page; JSON for the command palette."""
    query = request.GET.get("q", "").strip()
    results = list(search_items(request.user, query))
    if wants_json(request):
        return JsonResponse(
            {
                "results": [
                    {
                        "key": item.key,
                        "title": item.title,
                        "project": item.project.name,
                        "status": item.project.status_label(item.status),
                        "url": reverse(
                            "backlog:detail", args=[item.project.key, item.number]
                        ),
                    }
                    for item in results[:PALETTE_RESULTS]
                ]
            }
        )
    return render(
        request,
        "core/search.html",
        {"query": query, "results": results, "min_length": MIN_QUERY_LENGTH},
    )
