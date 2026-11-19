from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.backlog.models import BacklogItem
from apps.core.http import wants_json
from apps.poker.models import DECK, PokerSession
from apps.poker.services import (
    accept_estimate,
    cast_vote,
    close_session,
    reset_round,
    reveal,
    session_state,
    start_session,
)
from apps.projects.mixins import ProjectAccessMixin

POLL_INTERVAL_MS = 2000


class PokerListView(ProjectAccessMixin, View):
    def get(self, request, project_key: str):
        sessions = self.project.poker_sessions.select_related("item")
        estimable = (
            self.project.items.active()
            .exclude(item_type=BacklogItem.ItemType.EPIC)
            .exclude(status=BacklogItem.Status.DONE)
            .order_by("story_points", "backlog_rank", "number")
        )
        return render(
            request,
            "poker/list.html",
            {
                "project": self.project,
                "access": self.access,
                "open_sessions": sessions.exclude(status=PokerSession.Status.CLOSED),
                "recent_sessions": sessions.filter(
                    status=PokerSession.Status.CLOSED
                )[:10],
                "estimable_items": estimable,
            },
        )


class PokerStartView(ProjectAccessMixin, View):
    required_permission = "can_manage_backlog"
    http_method_names = ["post"]

    def post(self, request, project_key: str):
        item = get_object_or_404(
            self.project.items.active(), number=request.POST.get("item") or 0
        )
        session = start_session(item, actor=request.user)
        return redirect("poker:detail", project_key=self.project.key, pk=session.pk)


class SessionMixin(ProjectAccessMixin):
    def get_session(self, pk: int) -> PokerSession:
        return get_object_or_404(
            PokerSession.objects.select_related("item__project", "project"),
            pk=pk,
            project=self.project,
        )

    def respond(self, request, session: PokerSession):
        if wants_json(request):
            return JsonResponse(session_state(session, viewer=request.user))
        return redirect("poker:detail", project_key=self.project.key, pk=session.pk)


class PokerDetailView(SessionMixin, View):
    def get(self, request, project_key: str, pk: int):
        session = self.get_session(pk)
        if wants_json(request):
            return JsonResponse(session_state(session, viewer=request.user))
        return render(
            request,
            "poker/detail.html",
            {
                "project": self.project,
                "access": self.access,
                "session": session,
                "state": session_state(session, viewer=request.user),
                "deck": DECK,
                "poll_interval": POLL_INTERVAL_MS,
            },
        )


class PokerActionView(SessionMixin, View):
    """Base for POST actions; subclasses implement ``perform``."""

    http_method_names = ["post"]
    required_permission = "can_manage_backlog"

    def post(self, request, project_key: str, pk: int):
        session = self.get_session(pk)
        try:
            self.perform(request, session)
        except ValidationError as error:
            if wants_json(request):
                return JsonResponse({"error": " ".join(error.messages)}, status=400)
            messages.error(request, " ".join(error.messages))
        return self.respond(request, session)

    def perform(self, request, session: PokerSession) -> None:
        raise NotImplementedError


class PokerVoteView(PokerActionView):
    required_permission = "can_change_status"

    def perform(self, request, session):
        cast_vote(session, request.user, request.POST.get("value", ""))


class PokerRevealView(PokerActionView):
    def perform(self, request, session):
        reveal(session, actor=request.user)


class PokerResetView(PokerActionView):
    def perform(self, request, session):
        reset_round(session, actor=request.user)


class PokerAcceptView(PokerActionView):
    def perform(self, request, session):
        points = request.POST.get("points", "")
        if not points.isdigit() or int(points) > 100:
            raise ValidationError("Story Points müssen zwischen 0 und 100 liegen.")
        accept_estimate(session, int(points), actor=request.user)
        messages.success(
            request, f"{session.item.key} mit {points} Story Points geschätzt."
        )


class PokerCloseView(PokerActionView):
    def perform(self, request, session):
        close_session(session, actor=request.user)
