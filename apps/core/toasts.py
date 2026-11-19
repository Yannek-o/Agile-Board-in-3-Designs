"""Flash messages shown as toasts, optionally with an undo action."""

from django.contrib import messages

UNDO_TAG_PREFIX = "undo="


def undo_tag(undo_url: str) -> str:
    return f"{UNDO_TAG_PREFIX}{undo_url}"


def success_with_undo(request, text: str, undo_url: str) -> None:
    """The toast offers a button that posts to ``undo_url``."""
    messages.success(request, text, extra_tags=undo_tag(undo_url))
