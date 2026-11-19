from django.urls import path

from apps.activity import views

app_name = "activity"

urlpatterns = [
    path("", views.ProjectActivityView.as_view(), name="list"),
]
