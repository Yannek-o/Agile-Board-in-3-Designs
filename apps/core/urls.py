from django.urls import path

from apps.core import views

app_name = "core"

urlpatterns = [
    path("go/<slug:section>/", views.go_to_section, name="go"),
    path("search/", views.search, name="search"),
]
