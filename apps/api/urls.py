from django.urls import path

from apps.api import token_views, views

app_name = "api"

PROJECT = "v1/projects/<str:project_key>/"

urlpatterns = [
    path("tokens/", token_views.ApiTokenView.as_view(), name="tokens"),
    path(
        "tokens/<int:pk>/delete/",
        token_views.ApiTokenDeleteView.as_view(),
        name="token_delete",
    ),
    path("v1/projects/", views.projects, name="projects"),
    path(PROJECT + "items/", views.items, name="items"),
    path(PROJECT + "items/<int:number>/", views.item, name="item"),
    path(PROJECT + "sprints/", views.sprints, name="sprints"),
]
