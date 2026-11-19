from django.urls import path

from apps.reporting import views

app_name = "reporting"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("notes/", views.DashboardNotesView.as_view(), name="dashboard_notes"),
    path(
        "projects/<str:project_key>/reports/",
        views.ProjectReportView.as_view(),
        name="project_report",
    ),
]
