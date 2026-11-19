from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, ListView

from apps.backlog.models import BacklogItem
from apps.backlog.queries import apply_backlog_filters
from apps.projects.mixins import ProjectAccessMixin
from apps.reporting.burndown import sprint_burndown
from apps.reporting.sprint_report import sprint_report
from apps.reporting.services import sprint_capacity, sprint_point_breakdowns
from apps.sprints.forms import (
    SprintCompleteForm,
    SprintForm,
    SprintItemForm,
    SprintRetroForm,
)
from apps.sprints.models import RETRO_FIELDS, Sprint, SprintItem
from apps.sprints.services import (
    SprintError,
    add_item_to_sprint,
    cancel_sprint,
    complete_sprint,
    create_sprint,
    last_sprint_with_retro_actions,
    remove_item_from_sprint,
    save_retrospective,
    start_sprint,
    update_sprint,
)


def sprint_detail_url(sprint: Sprint) -> str:
    return reverse("sprints:detail", args=[sprint.project.key, sprint.number])


class SprintMixin(ProjectAccessMixin):
    def get_sprint(self) -> Sprint:
        if not hasattr(self, "sprint"):
            self.sprint = get_object_or_404(
                Sprint.objects.select_related("project", "completed_by"),
                project=self.project,
                number=self.kwargs["number"],
            )
        return self.sprint


class SprintListView(ProjectAccessMixin, ListView):
    template_name = "sprints/sprint_list.html"
    context_object_name = "sprints"

    def get_queryset(self):
        return self.project.sprints.annotate(
            item_count=Count(
                "entries", filter=~Q(entries__outcome=SprintItem.Outcome.REMOVED)
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        breakdowns = sprint_point_breakdowns(context["sprints"])
        for sprint in context["sprints"]:
            sprint.point_breakdown = breakdowns[sprint.pk]
        return context


class SprintCreateView(ProjectAccessMixin, View):
    required_permission = "can_manage_backlog"
    template_name = "sprints/sprint_form.html"

    def get(self, request, project_key: str):
        return self.render(SprintForm(project=self.project))

    def post(self, request, project_key: str):
        form = SprintForm(request.POST, project=self.project)
        if form.is_valid():
            try:
                sprint = create_sprint(
                    project=self.project, actor=request.user, **form.cleaned_data
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(request, f"{sprint.label} wurde angelegt.")
                return redirect(sprint_detail_url(sprint))
        return self.render(form)

    def render(self, form, sprint=None):
        return render(
            self.request,
            self.template_name,
            {
                "form": form,
                "project": self.project,
                "access": self.access,
                "sprint": sprint,
            },
        )


class SprintUpdateView(SprintMixin, SprintCreateView):
    def get(self, request, project_key: str, number: int):
        sprint = self.get_sprint()
        return self.render(
            SprintForm(instance=sprint, project=self.project), sprint=sprint
        )

    def post(self, request, project_key: str, number: int):
        sprint = self.get_sprint()
        form = SprintForm(request.POST, instance=sprint, project=self.project)
        if form.is_valid():
            try:
                update_sprint(sprint, actor=request.user, **form.cleaned_data)
            except (SprintError, ValidationError) as error:
                form.add_error(None, str(error))
            else:
                messages.success(request, "Sprint gespeichert.")
                return redirect(sprint_detail_url(sprint))
        return self.render(form, sprint=sprint)


class SprintDetailView(SprintMixin, DetailView):
    template_name = "sprints/sprint_detail.html"
    context_object_name = "sprint"

    def get_object(self, queryset=None):
        return self.get_sprint()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sprint = self.object
        sprint_items = sprint.open_items().select_related("assignee")
        context["sprint_items"] = sprint_items
        context["sprint_points"] = (
            sprint_items.aggregate(total=Sum("story_points"))["total"] or 0
        )
        if sprint.is_open:
            candidates = (
                BacklogItem.objects.open()
                .filter(project=self.project)
                .exclude(
                    sprint_entries__outcome=SprintItem.Outcome.OPEN,
                    sprint_entries__sprint__status__in=Sprint.OPEN_STATUSES,
                )
                .select_related("assignee")
            )
            candidates = apply_backlog_filters(
                candidates, self.request.GET, self.project
            )
            context["candidates"] = candidates
            context["search"] = self.request.GET.get("q", "")
        context["history"] = sprint.entries.select_related("item").order_by(
            "item__number"
        )
        context["complete_form"] = SprintCompleteForm(sprint=sprint)
        context["retro_form"] = SprintRetroForm(instance=sprint)
        context["previous_retro"] = (
            last_sprint_with_retro_actions(sprint) if sprint.is_open else None
        )
        context["capacity"] = sprint_capacity(sprint) if sprint.is_open else None
        context["burndown"] = sprint_burndown(sprint)
        context["report"] = sprint_report(sprint)
        context["done_count"] = sprint_items.filter(
            status=BacklogItem.Status.DONE
        ).count()
        return context


class SprintActionView(SprintMixin, View):
    required_permission = "can_manage_backlog"
    http_method_names = ["post"]

    def post(self, request, project_key: str, number: int):
        sprint = self.get_sprint()
        try:
            message = self.perform(request, sprint)
        except SprintError as error:
            messages.error(request, str(error))
        else:
            if message:
                messages.success(request, message)
        return redirect(self.get_success_url(sprint))

    def perform(self, request, sprint: Sprint) -> str:
        raise NotImplementedError

    def get_success_url(self, sprint: Sprint) -> str:
        return sprint_detail_url(sprint)

    def get_item(self, request) -> BacklogItem:
        form = SprintItemForm(request.POST)
        if not form.is_valid():
            raise SprintError("Ungültiger Eintrag.")
        return get_object_or_404(
            BacklogItem, project=self.project, number=form.cleaned_data["item"]
        )


class SprintAddItemView(SprintActionView):
    def perform(self, request, sprint: Sprint) -> str:
        item = self.get_item(request)
        add_item_to_sprint(sprint, item, actor=request.user)
        return f"{item.key} wurde eingeplant."


class SprintRemoveItemView(SprintActionView):
    def perform(self, request, sprint: Sprint) -> str:
        item = self.get_item(request)
        remove_item_from_sprint(sprint, item, actor=request.user)
        return f"{item.key} wurde aus dem Sprint entfernt."


class SprintStartView(SprintActionView):
    def perform(self, request, sprint: Sprint) -> str:
        start_sprint(sprint, actor=request.user)
        return f"{sprint.label} wurde gestartet."


class SprintCompleteView(SprintActionView):
    def perform(self, request, sprint: Sprint) -> str:
        form = SprintCompleteForm(request.POST, sprint=sprint)
        if not form.is_valid():
            raise SprintError("Ungültiger Folgesprint.")
        complete_sprint(
            sprint,
            actor=request.user,
            carry_over_to=form.cleaned_data["carry_over_to"],
            review_notes=form.cleaned_data["review_notes"],
        )
        return f"{sprint.label} wurde abgeschlossen."


class SprintCancelView(SprintActionView):
    def perform(self, request, sprint: Sprint) -> str:
        cancel_sprint(sprint, actor=request.user)
        return f"{sprint.label} wurde abgebrochen."


class SprintRetroView(SprintActionView):
    def perform(self, request, sprint: Sprint) -> str:
        form = SprintRetroForm(request.POST)
        if not form.is_valid():
            raise SprintError("Die Retrospektive konnte nicht gespeichert werden.")
        save_retrospective(
            sprint,
            actor=request.user,
            **{field: form.cleaned_data[field] for field in RETRO_FIELDS},
        )
        return "Retrospektive gespeichert."
