from django.urls import path

from apps.notifications import views

app_name = "notifications"

urlpatterns = [
    path("", views.NotificationListView.as_view(), name="list"),
    path("<int:pk>/open/", views.NotificationOpenView.as_view(), name="open"),
    path(
        "read-all/", views.NotificationMarkAllReadView.as_view(), name="mark_all_read"
    ),
    path("unread-count/", views.UnreadCountView.as_view(), name="unread_count"),
]
