from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q

from apps.accounts.models import User
from apps.backlog.models import (
    DEFAULT_EPIC_COLOR,
    WEB_LINK_VALIDATOR,
    BacklogItem,
    ItemLink,
    Release,
)
from apps.backlog.services import check_upload_type_and_size
from apps.backlog.timeparse import format_minutes, parse_duration
from apps.projects.models import HEX_COLOR_VALIDATOR, Project

MAX_UPLOADS_PER_REQUEST = 10


def upload_accept() -> str:
    return ",".join(f".{ext}" for ext in settings.ATTACHMENT_ALLOWED_EXTENSIONS)


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def widget_attrs(self, widget) -> dict:
        attrs = super().widget_attrs(widget)
        attrs.update({"accept": upload_accept(), "class": "dropzone-input"})
        return attrs

    def clean(self, data, initial=None) -> list:
        uploads = [upload for upload in (data or []) if upload]
        if len(uploads) > MAX_UPLOADS_PER_REQUEST:
            raise forms.ValidationError(
                f"Höchstens {MAX_UPLOADS_PER_REQUEST} Dateien auf einmal."
            )
        cleaned = [super(MultipleFileField, self).clean(upload) for upload in uploads]
        errors = []
        for upload in cleaned:
            try:
                check_upload_type_and_size(upload)
            except ValidationError as error:
                errors.extend(f"{upload.name}: {message}" for message in error.messages)
        if errors:
            raise forms.ValidationError(errors)
        return cleaned


class DurationTextField(forms.CharField):
    """Accepts Jira-style durations (1d 2h 30m) and stores whole minutes."""

    def __init__(self, *args, **kwargs):
        # Integer model fields pass numeric bounds that a text field cannot use.
        kwargs.pop("min_value", None)
        kwargs.pop("max_value", None)
        kwargs.pop("step_size", None)
        kwargs.setdefault("required", False)
        kwargs.pop("max_length", None)
        kwargs.setdefault("help_text", "z. B. 2h, 1h 30m oder 1d (= 8 Stunden)")
        super().__init__(*args, **kwargs)
        self.widget.attrs.setdefault("placeholder", "z. B. 1d 4h")
        self.widget.attrs.setdefault("maxlength", "30")

    def prepare_value(self, value):
        if isinstance(value, int):
            return format_minutes(value)
        return value

    def to_python(self, value) -> int | None:
        text = super().to_python(value)
        if not text:
            return None
        return parse_duration(text)


class WebLinkListWidget(forms.Widget):
    def value_from_datadict(self, data, files, name):
        return data.getlist(name) if hasattr(data, "getlist") else data.get(name, [])


class WebLinkListField(forms.Field):
    widget = WebLinkListWidget

    def to_python(self, value) -> list[str]:
        return [url.strip() for url in (value or []) if url and url.strip()]

    def validate(self, value: list[str]) -> None:
        super().validate(value)
        for url in value:
            WEB_LINK_VALIDATOR(url)


class BacklogItemForm(forms.ModelForm):
    acceptance_criteria_text = forms.CharField(
        label="Akzeptanzkriterien",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="Ein Kriterium pro Zeile.",
    )
    attachments = MultipleFileField(label="Anhänge", required=False)
    web_links = WebLinkListField(label="Links", required=False)
    version = forms.IntegerField(widget=forms.HiddenInput, required=False)

    # Fields rendered in the side column of the create form.
    SIDE_FIELDS = ("attachments", "web_links")

    # Fields reserved for members with backlog planning rights.
    PLANNING_FIELDS = (
        "item_type", "title", "priority", "story_points", "labels", "due_date",
        "parent", "color", "original_estimate", "fix_version",
    )

    class Meta:
        model = BacklogItem
        fields = [
            "item_type",
            "parent",
            "title",
            "color",
            "description",
            "priority",
            "story_points",
            "assignee",
            "status",
            "is_blocked",
            "blocked_reason",
            "labels",
            "due_date",
            "fix_version",
            "original_estimate",
            "remaining_estimate",
        ]
        field_classes = {
            "original_estimate": DurationTextField,
            "remaining_estimate": DurationTextField,
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "due_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "labels": forms.CheckboxSelectMultiple,
            "color": forms.TextInput(attrs={"type": "color"}),
        }

    def __init__(self, *args, project: Project, limited: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        self.instance.project = project
        self.fields["assignee"].queryset = User.objects.filter(
            is_active=True,
            memberships__project=project,
            memberships__is_active=True,
        ).distinct()
        self.fields["labels"].queryset = project.labels.all()
        parent_choices = project.items.active().exclude(
            item_type=BacklogItem.ItemType.SUBTASK
        ).order_by("number")
        if self.instance.pk:
            parent_choices = parent_choices.exclude(pk=self.instance.pk)
        self.fields["parent"].queryset = parent_choices
        releases = project.releases.filter(status=Release.Status.UNRELEASED)
        if self.instance.fix_version_id:
            releases = project.releases.filter(
                Q(status=Release.Status.UNRELEASED) | Q(pk=self.instance.fix_version_id)
            )
        self.fields["fix_version"].queryset = releases
        self.fields["fix_version"].empty_label = "Kein Release"
        self.fields["parent"].label_from_instance = (
            lambda item: f"{item.key} · {item.get_item_type_display()} · {item.title}"
        )
        self.fields["parent"].help_text = (
            "Stories, Aufgaben und Bugs gehören zu einem Epic; "
            "Unteraufgaben zu einer Story, Aufgabe oder einem Bug."
        )
        if self.instance.pk:
            self.fields.pop("acceptance_criteria_text")
            for field in self.SIDE_FIELDS:
                self.fields.pop(field)
            self.fields["version"].initial = self.instance.version
        else:
            self.fields.pop("version")
            self.fields.pop("remaining_estimate")
        if not (self.instance.pk and self.instance.is_epic):
            self.fields.pop("color")
        if limited:
            for field in self.PLANNING_FIELDS:
                self.fields.pop(field, None)

    def clean_title(self) -> str:
        title = self.cleaned_data["title"].strip()
        if not title:
            raise forms.ValidationError("Bitte einen Titel angeben.")
        return title

    def clean_acceptance_criteria_text(self) -> list[str]:
        raw_text = self.cleaned_data.get("acceptance_criteria_text", "")
        return [line.strip() for line in raw_text.splitlines() if line.strip()]

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("is_blocked") is False:
            cleaned_data["blocked_reason"] = ""
        return cleaned_data

    def item_fields(self) -> dict:
        return {
            field: self.cleaned_data[field]
            for field in self.Meta.fields
            if field != "labels" and field in self.fields
        }

    def selected_labels(self):
        if "labels" not in self.fields:
            return None
        return self.cleaned_data["labels"]

    def main_fields(self) -> list:
        return [
            field for field in self.visible_fields()
            if field.name not in self.SIDE_FIELDS
        ]

    def has_side_fields(self) -> bool:
        return any(name in self.fields for name in self.SIDE_FIELDS)


class CommentForm(forms.Form):
    body = forms.CharField(
        label="Kommentar",
        max_length=5000,
        widget=forms.Textarea(attrs={"rows": 3}),
    )


class AttachmentForm(forms.Form):
    file = forms.FileField(label="Datei")


class WebLinkForm(forms.Form):
    url = forms.CharField(
        label="Link", max_length=2000, validators=[WEB_LINK_VALIDATOR]
    )


class WorkLogForm(forms.Form):
    duration = DurationTextField(label="Dauer", required=True)
    work_date = forms.DateField(
        label="Datum", widget=forms.DateInput(attrs={"type": "date"})
    )
    comment = forms.CharField(label="Notiz", max_length=500, required=False)
    remaining = DurationTextField(
        label="Restaufwand neu",
        help_text="Leer lassen, um automatisch zu verringern.",
    )


class EpicForm(forms.Form):
    title = forms.CharField(label="Name", max_length=200)
    color = forms.CharField(
        label="Farbe",
        max_length=7,
        initial=DEFAULT_EPIC_COLOR,
        validators=[HEX_COLOR_VALIDATOR],
        widget=forms.TextInput(attrs={"type": "color"}),
    )
    description = forms.CharField(
        label="Beschreibung",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def clean_title(self) -> str:
        title = self.cleaned_data["title"].strip()
        if not title:
            raise forms.ValidationError("Bitte einen Namen angeben.")
        return title


class AcceptanceCriterionForm(forms.Form):
    text = forms.CharField(label="Neues Kriterium", max_length=500)


class ReorderForm(forms.Form):
    item = forms.IntegerField(min_value=1)
    position = forms.IntegerField(min_value=0)


class ItemLinkForm(forms.Form):
    link_type = forms.ChoiceField(label="Art", choices=ItemLink.LinkType.choices)
    target = forms.CharField(label="Eintrag", max_length=30)

    def __init__(self, *args, project: Project, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project

    def clean_target(self) -> BacklogItem:
        raw = self.cleaned_data["target"].strip().upper()
        prefix = f"{self.project.key}-"
        number = raw[len(prefix):] if raw.startswith(prefix) else raw
        item = None
        if number.isdigit():
            item = self.project.items.active().filter(number=int(number)).first()
        if item is None:
            raise forms.ValidationError(f"Eintrag „{raw}“ wurde nicht gefunden.")
        return item


class ReleaseForm(forms.ModelForm):
    class Meta:
        model = Release
        fields = ["name", "release_date", "description"]
        widgets = {
            "release_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, project: Project, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.project = project

    def clean_name(self) -> str:
        return self.cleaned_data["name"].strip()
