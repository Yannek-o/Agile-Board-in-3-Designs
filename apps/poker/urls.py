from django.urls import path

from apps.poker import views

app_name = "poker"

urlpatterns = [
    path("", views.PokerListView.as_view(), name="list"),
    path("start/", views.PokerStartView.as_view(), name="start"),
    path("<int:pk>/", views.PokerDetailView.as_view(), name="detail"),
    path("<int:pk>/vote/", views.PokerVoteView.as_view(), name="vote"),
    path("<int:pk>/reveal/", views.PokerRevealView.as_view(), name="reveal"),
    path("<int:pk>/reset/", views.PokerResetView.as_view(), name="reset"),
    path("<int:pk>/accept/", views.PokerAcceptView.as_view(), name="accept"),
    path("<int:pk>/close/", views.PokerCloseView.as_view(), name="close"),
]
