from django.urls import path

from apps.sprints import views

app_name = "sprints"

SPRINT = "<int:number>/"

urlpatterns = [
    path("", views.SprintListView.as_view(), name="list"),
    path("new/", views.SprintCreateView.as_view(), name="create"),
    path(SPRINT, views.SprintDetailView.as_view(), name="detail"),
    path(SPRINT + "edit/", views.SprintUpdateView.as_view(), name="edit"),
    path(SPRINT + "add-item/", views.SprintAddItemView.as_view(), name="add_item"),
    path(
        SPRINT + "remove-item/",
        views.SprintRemoveItemView.as_view(),
        name="remove_item",
    ),
    path(SPRINT + "start/", views.SprintStartView.as_view(), name="start"),
    path(SPRINT + "complete/", views.SprintCompleteView.as_view(), name="complete"),
    path(SPRINT + "cancel/", views.SprintCancelView.as_view(), name="cancel"),
    path(SPRINT + "retro/", views.SprintRetroView.as_view(), name="retro"),
]
