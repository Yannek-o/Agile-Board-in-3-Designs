from django.urls import path

from apps.board import views

app_name = "board"

urlpatterns = [
    path("", views.BoardView.as_view(), name="board"),
    path("move/", views.BoardMoveView.as_view(), name="move"),
    path("state/", views.BoardStateView.as_view(), name="state"),
    path("create/", views.BoardQuickCreateView.as_view(), name="quick_create"),
]
