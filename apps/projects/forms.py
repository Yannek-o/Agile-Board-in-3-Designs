from django import forms

from apps.accounts.models import User
from apps.backlog.models import BacklogItem
from apps.projects.models import (
    PROJECT_KEY_VALIDATOR,
    Label,
    Project,
    ProjectMembership,
)

Access = ProjectMembership.AccessLevel
WORKFLOW_LABEL_FIELDS = (
    "status_label_todo",
    "status_label_in_progress",
    "status_label_in_review",
    "status_label_done",
)
WORKFLOW_RULE_FIELDS = (
    "use_review_column",
    "require_review",
    "done_requires_lead",
    "done_requires_criteria",
)


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = [
            "name",
            "key",
            "description",
            "product_goal",
            "definition_of_done",
            "wip_limit_in_progress",
            "wip_limit_in_review",
            *WORKFLOW_LABEL_FIELDS,
            *WORKFLOW_RULE_FIELDS,
            "status",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "product_goal": forms.Textarea(attrs={"rows": 3}),
            "definition_of_done": forms.Textarea(attrs={"rows": 5}),
        }
        help_texts = {
            "key": "2–10 Zeichen, z. B. HELP. Wird für Aufgaben-IDs verwendet "
            "und ist danach unveränderlich.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The format is validated after upper-case normalization in clean_key.
        self.fields["key"].validators = []
        if self.instance.pk:
            self.fields["key"].disabled = True
        for field in WORKFLOW_LABEL_FIELDS:
            self.fields[field].widget.attrs["placeholder"] = BacklogItem.Status(
                field.removeprefix("status_label_")
            ).label

    def clean_key(self) -> str:
        if self.instance.pk:
            return self.instance.key
        key = self.cleaned_data["key"].strip().upper()
        PROJECT_KEY_VALIDATOR(key)
        if Project.objects.filter(key__iexact=key).exists():
            raise forms.ValidationError("Dieses Projektkürzel ist bereits vergeben.")
        return key


class LastManagerGuardMixin:
    """Prevents a project from losing its last active project lead."""

    def would_remove_last_manager(
        self, membership: ProjectMembership, new_access: str | None
    ) -> bool:
        if not membership.pk or membership.access_level != Access.MANAGE:
            return False
        if new_access == Access.MANAGE and membership.is_active:
            return False
        other_managers = ProjectMembership.objects.filter(
            project=membership.project,
            access_level=Access.MANAGE,
            is_active=True,
            user__is_active=True,
        ).exclude(pk=membership.pk)
        return not other_managers.exists()


class MembershipCreateForm(forms.ModelForm):
    class Meta:
        model = ProjectMembership
        fields = ["user", "scrum_role", "access_level", "can_manage_backlog"]
        labels = {"user": "Mitarbeiter"}

    def __init__(self, *args, project: Project, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        active_member_ids = project.memberships.filter(is_active=True).values(
            "user_id"
        )
        self.fields["user"].queryset = User.objects.filter(is_active=True).exclude(
            pk__in=active_member_ids
        )

    def validate_unique(self):
        """Re-activation of former members is handled by the view."""


class MembershipUpdateForm(LastManagerGuardMixin, forms.ModelForm):
    class Meta:
        model = ProjectMembership
        fields = ["scrum_role", "access_level", "can_manage_backlog"]

    def clean_access_level(self) -> str:
        new_access = self.cleaned_data["access_level"]
        current = ProjectMembership.objects.get(pk=self.instance.pk)
        if self.would_remove_last_manager(current, new_access):
            raise forms.ValidationError(
                "Das Projekt benötigt mindestens eine aktive Projektleitung."
            )
        return new_access


class LabelForm(forms.ModelForm):
    class Meta:
        model = Label
        fields = ["name", "color"]
        widgets = {"color": forms.TextInput(attrs={"type": "color"})}

    def __init__(self, *args, project: Project, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.project = project

    def clean_name(self) -> str:
        name = self.cleaned_data["name"].strip()
        if Label.objects.filter(
            project=self.instance.project, name__iexact=name
        ).exists():
            raise forms.ValidationError("Dieses Label existiert bereits.")
        return name
