from django.conf import settings

from apps.projects.mixins import LAST_PROJECT_SESSION_KEY
from apps.projects.permissions import visible_projects

BRAND_LOGO_FILENAMES = ("logo.svg", "logo.png", "logo.webp", "logo.jpg")


def brand(request) -> dict:
    """Uses a custom logo from static/img/brand/ if one has been added."""
    logo_dir = settings.BRAND_LOGO_DIR
    for filename in BRAND_LOGO_FILENAMES:
        if (logo_dir / filename).is_file():
            return {"brand_logo": f"img/brand/{filename}"}
    return {"brand_logo": None}


def navigation(request) -> dict:
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    project_key = request.session.get(LAST_PROJECT_SESSION_KEY)
    current_project = None
    if project_key:
        current_project = visible_projects(user).filter(key=project_key).first()
    resolver = getattr(request, "resolver_match", None)
    return {
        "nav_current_project": current_project,
        "nav_namespace": resolver.namespace if resolver else "",
        "nav_url_name": resolver.url_name if resolver else "",
    }
