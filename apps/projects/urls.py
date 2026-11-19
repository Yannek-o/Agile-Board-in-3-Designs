from django.urls import path

from apps.projects import views

app_name = "projects"

KEY = "<str:project_key>/"

urlpatterns = [
    path("", views.ProjectListView.as_view(), name="list"),
    path("new/", views.ProjectCreateView.as_view(), name="create"),
    path(KEY, views.ProjectDetailView.as_view(), name="detail"),
    path(KEY + "edit/", views.ProjectUpdateView.as_view(), name="edit"),
    path(KEY + "archive/", views.ProjectArchiveView.as_view(), name="archive"),
    path(
        KEY + "restore/",
        views.ProjectArchiveView.as_view(archive=False),
        name="restore",
    ),
    path(KEY + "team/", views.TeamView.as_view(), name="team"),
    path(KEY + "team/add/", views.MemberAddView.as_view(), name="member_add"),
    path(
        KEY + "team/<int:pk>/edit/",
        views.MemberEditView.as_view(),
        name="member_edit",
    ),
    path(
        KEY + "team/<int:pk>/remove/",
        views.MemberRemoveView.as_view(),
        name="member_remove",
    ),
    path(KEY + "labels/", views.LabelListView.as_view(), name="labels"),
    path(
        KEY + "labels/<int:pk>/delete/",
        views.LabelDeleteView.as_view(),
        name="label_delete",
    ),
]
