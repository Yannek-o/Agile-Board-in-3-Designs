from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import (
    BooleanField,
    Case,
    Count,
    Exists,
    OuterRef,
    Q,
    Value,
    When,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.activity.models import ActivityEvent
from apps.activity.services import record_event
from apps.projects.forms import (
    LabelForm,
    LastManagerGuardMixin,
    MembershipCreateForm,
    MembershipUpdateForm,
    ProjectForm,
)
from apps.projects.mixins import ProjectAccessMixin
from apps.projects.models import Label, Project, ProjectMembership
from apps.projects.permissions import visible_projects
from apps.sprints.models import Sprint

OPEN_ITEMS_FILTER = Q(items__archived_at__isnull=True) & ~Q(items__status="done")


class ProjectListView(ListView):
    template_name = "projects/project_list.html"
    context_object_name = "projects"

    def get_queryset(self):
        queryset = visible_projects(self.request.user)
        status = self.request.GET.get("status", "")
        if status == "archived":
            queryset = queryset.filter(archived_at__isnull=False)
        else:
            queryset = queryset.not_archived()
            if status in Project.Status.values:
                queryset = queryset.filter(status=status)
        search = self.request.GET.get("q", "").strip()
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(key__icontains=search)
                | Q(description__icontains=search)
            )
        today = timezone.localdate()
        overdue_sprints = Sprint.objects.filter(
            project=OuterRef("pk"), status=Sprint.Status.ACTIVE, end_date__lt=today
        )
        return (
            queryset.annotate(
                open_items=Count("items", filter=OPEN_ITEMS_FILTER),
                overdue_items=Count(
                    "items", filter=OPEN_ITEMS_FILTER & Q(items__due_date__lt=today)
                ),
                has_overdue_sprint=Exists(overdue_sprints),
            )
            .annotate(
                is_delayed=Case(
                    When(
                        Q(overdue_items__gt=0) | Q(has_overdue_sprint=True),
                        then=Value(True),
                    ),
                    default=Value(False),
                    output_field=BooleanField(),
                )
            )
            .prefetch_related("memberships__user")
            .order_by("name")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        all_visible = visible_projects(self.request.user).not_archived()
        context["status_counts"] = {
            row["status"]: row["count"]
            for row in all_visible.values("status").annotate(count=Count("id"))
        }
        context["status_choices"] = Project.Status.choices
        context["current_status"] = self.request.GET.get("status", "")
        context["search"] = self.request.GET.get("q", "")
        context["section"] = self.request.GET.get("section", "")
        return context


class ProjectCreateView(CreateView):
    form_class = ProjectForm
    template_name = "projects/project_form.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.may_create_projects:
            raise PermissionDenied("Keine Berechtigung zum Anlegen von Projekten.")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        if not self.request.user.is_system_admin:
            ProjectMembership.objects.create(
                project=self.object,
                user=self.request.user,
                access_level=ProjectMembership.AccessLevel.MANAGE,
                scrum_role=ProjectMembership.ScrumRole.PRODUCT_OWNER,
            )
        record_event(
            self.object, ActivityEvent.Action.CREATED, actor=self.request.user,
            message=f"Projekt {self.object.key} angelegt",
        )
        messages.success(self.request, "Projekt angelegt.")
        return response

    def get_success_url(self) -> str:
        return reverse("projects:detail", args=[self.object.key])


class ProjectDetailView(ProjectAccessMixin, DetailView):
    template_name = "projects/project_detail.html"
    context_object_name = "project_obj"

    def get_object(self, queryset=None):
        return self.project

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        items = self.project.items.filter(archived_at__isnull=True)
        context["item_counts"] = {
            row["status"]: row["count"]
            for row in items.values("status").annotate(count=Count("id"))
        }
        context["item_total"] = items.count()
        context["members"] = self.project.active_members()
        context["active_sprint"] = self.project.sprints.filter(
            status="active"
        ).first()
        context["recent_events"] = self.project.activity.select_related(
            "actor", "item"
        )[:8]
        return context


class ProjectUpdateView(ProjectAccessMixin, UpdateView):
    required_permission = "can_manage_project"
    form_class = ProjectForm
    template_name = "projects/project_form.html"

    def get_object(self, queryset=None):
        return self.project

    def form_valid(self, form):
        record_event(
            self.project, ActivityEvent.Action.UPDATED, actor=self.request.user,
            message="Projektdaten geändert",
        )
        messages.success(self.request, "Projekt gespeichert.")
        return super().form_valid(form)

    def get_success_url(self) -> str:
        return reverse("projects:detail", args=[self.project.key])


class ProjectArchiveView(ProjectAccessMixin, View):
    required_permission = "can_manage_project"
    http_method_names = ["post"]
    archive = True

    def post(self, request, project_key: str):
        if self.archive:
            self.project.archive()
            action = ActivityEvent.Action.ARCHIVED
            messages.success(request, "Projekt archiviert.")
        else:
            self.project.restore()
            action = ActivityEvent.Action.RESTORED
            messages.success(request, "Projekt wiederhergestellt.")
        record_event(self.project, action, actor=request.user)
        return redirect("projects:detail", project_key=self.project.key)


class TeamView(ProjectAccessMixin, ListView):
    template_name = "projects/team.html"
    context_object_name = "memberships"

    def get_queryset(self):
        queryset = self.project.memberships.select_related("user")
        if not self.access.can_manage_project:
            queryset = queryset.filter(is_active=True)
        return queryset.order_by("-is_active", "user__first_name", "user__username")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["switch_projects"] = visible_projects(
            self.request.user
        ).not_archived()
        if self.access.can_manage_project:
            context["add_form"] = MembershipCreateForm(project=self.project)
        return context


class MemberAddView(ProjectAccessMixin, View):
    required_permission = "can_manage_project"
    template_name = "projects/member_form.html"

    def get(self, request, project_key: str):
        return self.render(MembershipCreateForm(project=self.project))

    def post(self, request, project_key: str):
        form = MembershipCreateForm(request.POST, project=self.project)
        if not form.is_valid():
            return self.render(form)
        membership, _ = ProjectMembership.objects.update_or_create(
            project=self.project,
            user=form.cleaned_data["user"],
            defaults={
                "scrum_role": form.cleaned_data["scrum_role"],
                "access_level": form.cleaned_data["access_level"],
                "can_manage_backlog": form.cleaned_data["can_manage_backlog"],
                "is_active": True,
            },
        )
        record_event(
            self.project, ActivityEvent.Action.MEMBER_CHANGED, actor=request.user,
            message=f"{membership.user} hinzugefügt",
        )
        messages.success(request, f"{membership.user} wurde hinzugefügt.")
        return redirect("projects:team", project_key=self.project.key)

    def render(self, form):
        return render(
            self.request,
            self.template_name,
            {"form": form, "project": self.project, "access": self.access},
        )


class MemberEditView(ProjectAccessMixin, UpdateView):
    required_permission = "can_manage_project"
    form_class = MembershipUpdateForm
    template_name = "projects/member_form.html"
    context_object_name = "membership"

    def get_object(self, queryset=None):
        return get_object_or_404(
            ProjectMembership, pk=self.kwargs["pk"], project=self.project
        )

    def form_valid(self, form):
        record_event(
            self.project, ActivityEvent.Action.MEMBER_CHANGED,
            actor=self.request.user,
            message=f"Rechte von {form.instance.user} geändert",
        )
        messages.success(self.request, "Mitgliedschaft gespeichert.")
        return super().form_valid(form)

    def get_success_url(self) -> str:
        return reverse("projects:team", args=[self.project.key])


class MemberRemoveView(LastManagerGuardMixin, ProjectAccessMixin, View):
    required_permission = "can_manage_project"
    http_method_names = ["post"]

    def post(self, request, project_key: str, pk: int):
        membership = get_object_or_404(
            ProjectMembership, pk=pk, project=self.project
        )
        if self.would_remove_last_manager(membership, None):
            messages.error(
                request, "Die letzte aktive Projektleitung kann nicht entfernt werden."
            )
        else:
            membership.is_active = False
            membership.save(update_fields=["is_active", "updated_at"])
            record_event(
                self.project, ActivityEvent.Action.MEMBER_CHANGED,
                actor=request.user, message=f"{membership.user} entfernt",
            )
            messages.success(request, f"{membership.user} wurde entfernt.")
        return redirect("projects:team", project_key=self.project.key)


class LabelListView(ProjectAccessMixin, ListView):
    template_name = "projects/labels.html"
    context_object_name = "labels"

    def get_required_permission(self, request) -> str:
        return "can_manage_backlog" if request.method == "POST" else "can_view"

    def get_queryset(self):
        return self.project.labels.annotate(item_count=Count("items"))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("form", LabelForm(project=self.project))
        return context

    def post(self, request, project_key: str):
        form = LabelForm(request.POST, project=self.project)
        if form.is_valid():
            form.save()
            messages.success(request, "Label angelegt.")
            return redirect("projects:labels", project_key=self.project.key)
        self.object_list = self.get_queryset()
        return self.render_to_response(self.get_context_data(form=form))


class LabelDeleteView(ProjectAccessMixin, View):
    required_permission = "can_manage_backlog"
    http_method_names = ["post"]

    def post(self, request, project_key: str, pk: int):
        label = get_object_or_404(Label, pk=pk, project=self.project)
        label.delete()
        messages.success(request, "Label gelöscht.")
        return redirect("projects:labels", project_key=self.project.key)
