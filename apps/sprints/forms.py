from django import forms

from apps.projects.models import Project
from apps.sprints.models import RETRO_FIELDS, Sprint


class SprintForm(forms.ModelForm):
    class Meta:
        model = Sprint
        fields = ["name", "goal", "start_date", "end_date"]
        widgets = {
            "goal": forms.Textarea(attrs={"rows": 3}),
            "start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "end_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }
        help_texts = {"name": "Optional – Standard ist „Sprint <Nummer>“."}

    def __init__(self, *args, project: Project, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.project = project


class SprintCompleteForm(forms.Form):
    carry_over_to = forms.ModelChoiceField(
        queryset=Sprint.objects.none(),
        required=False,
        label="Offene Einträge übernehmen in",
        empty_label="Zurück ins Product Backlog",
    )
    review_notes = forms.CharField(
        label="Abschlussnotiz",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, sprint: Sprint, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["carry_over_to"].queryset = Sprint.objects.filter(
            project=sprint.project, status=Sprint.Status.PLANNED
        ).exclude(pk=sprint.pk)


class SprintRetroForm(forms.ModelForm):
    class Meta:
        model = Sprint
        fields = list(RETRO_FIELDS)
        widgets = {
            field: forms.Textarea(attrs={"rows": 4}) for field in RETRO_FIELDS
        }


class SprintItemForm(forms.Form):
    item = forms.IntegerField(min_value=1)
