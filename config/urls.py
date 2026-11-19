from django.contrib import admin
from django.urls import include, path

PROJECT_PREFIX = "projects/<str:project_key>/"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("projects/", include("apps.projects.urls")),
    path(PROJECT_PREFIX + "backlog/", include("apps.backlog.urls")),
    path(PROJECT_PREFIX + "sprints/", include("apps.sprints.urls")),
    path(PROJECT_PREFIX + "board/", include("apps.board.urls")),
    path(PROJECT_PREFIX + "activity/", include("apps.activity.urls")),
    path(PROJECT_PREFIX + "poker/", include("apps.poker.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("api/", include("apps.api.urls")),
    path("", include("apps.reporting.urls")),
    path("", include("apps.core.urls")),
]
