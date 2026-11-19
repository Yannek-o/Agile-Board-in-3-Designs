import hashlib
import os

from django import forms, template
from django.contrib.staticfiles import finders
from django.templatetags.static import static
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

from apps.accounts.models import AVATAR_PRESETS
from apps.backlog.timeparse import format_minutes
from apps.core.markdown import render_markdown
from apps.core.toasts import UNDO_TAG_PREFIX
from apps.notifications.services import MENTION_PATTERN

register = template.Library()

TOAST_KINDS = {"success", "danger", "warning", "info"}


@register.filter
def message_kind(message) -> str:
    kind = message.level_tag
    return kind if kind in TOAST_KINDS else "info"


@register.filter
def message_undo_url(message) -> str:
    """Undo target of a message; only same-site paths are accepted."""
    for tag in (message.extra_tags or "").split():
        if not tag.startswith(UNDO_TAG_PREFIX):
            continue
        url = tag[len(UNDO_TAG_PREFIX):]
        if url.startswith("/") and not url.startswith("//") and "\\" not in url:
            return url
    return ""


@register.simple_tag
def avatar_presets() -> tuple:
    return AVATAR_PRESETS


@register.filter
def duration(minutes) -> str:
    return format_minutes(minutes)


@register.filter
def status_label(item) -> str:
    """Status name of an item as configured in its project's workflow."""
    return item.project.status_label(item.status)


@register.filter
def markdown(text) -> str:
    return render_markdown(text)


@register.filter
def markdown_mentions(text) -> str:
    return render_markdown(text, mentions=True)


BADGE_CLASSES = {
    "todo": "badge-neutral",
    "in_progress": "badge-warning",
    "in_review": "badge-info",
    "done": "badge-success",
    "low": "badge-neutral",
    "medium": "badge-warning",
    "high": "badge-danger",
    "critical": "badge-critical",
    "planned": "badge-info",
    "active": "badge-success",
    "completed": "badge-neutral",
    "cancelled": "badge-danger",
    "product_owner": "badge-info",
    "scrum_master": "badge-info",
    "developer": "badge-neutral",
    "stakeholder": "badge-neutral",
    "manage": "badge-warning",
    "edit": "badge-info",
    "read": "badge-neutral",
}


@register.filter
def badge_class(value: str) -> str:
    return BADGE_CLASSES.get(value, "badge-neutral")


@register.simple_tag(takes_context=True)
def query_with(context, **updates) -> str:
    """Returns the current query string with the given parameters replaced."""
    params = context["request"].GET.copy()
    for key, value in updates.items():
        if value in (None, ""):
            params.pop(key, None)
        else:
            params[key] = value
    params.pop("page", None)
    encoded = params.urlencode()
    return f"?{encoded}" if encoded else "?"


@register.filter
def get_item(mapping, key):
    return mapping.get(key) if mapping else None


@register.filter
def bootstrap(bound_field):
    """Renders a form field widget with the matching Bootstrap class."""
    widget = bound_field.field.widget
    if isinstance(widget, forms.CheckboxSelectMultiple):
        return bound_field
    if isinstance(widget, forms.CheckboxInput):
        css_class = "form-check-input"
    elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
        css_class = "form-select"
    else:
        css_class = "form-control"
    if bound_field.errors:
        css_class += " is-invalid"
    return bound_field.as_widget(attrs={"class": css_class})


@register.filter
def is_checkbox(bound_field) -> bool:
    return isinstance(bound_field.field.widget, forms.CheckboxInput)


@register.filter
def highlight_mentions(text):
    """Escapes the text and wraps ``@username`` tokens in a highlight span."""
    escaped = conditional_escape(text or "")
    return mark_safe(
        MENTION_PATTERN.sub(r'<span class="mention">@\1</span>', str(escaped))
    )


@register.simple_tag
def asset(path: str) -> str:
    """Static URL with a version suffix that changes whenever the file changes."""
    url = static(path)
    location = finders.find(path)
    if not location:
        return url
    stat = os.stat(location)
    version = hashlib.sha1(f"{stat.st_mtime_ns}:{stat.st_size}".encode()).hexdigest()
    return f"{url}?v={version[:8]}"
