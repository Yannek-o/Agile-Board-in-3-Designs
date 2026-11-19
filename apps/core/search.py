"""Search across all backlog items the user may see."""

import re

from django.db.models import Q, QuerySet

from apps.backlog.models import BacklogItem
from apps.projects.permissions import visible_projects

MIN_QUERY_LENGTH = 2
MAX_RESULTS = 50
ITEM_KEY = re.compile(r"^([A-Za-z][A-Za-z0-9]{1,9})-(\d+)$")


def search_items(user, query: str, limit: int = MAX_RESULTS) -> QuerySet:
    """Exact key matches (HELP-12) or text matches in title and description."""
    query = (query or "").strip()
    items = BacklogItem.objects.active().filter(
        project__in=visible_projects(user).not_archived()
    )
    if len(query) < MIN_QUERY_LENGTH:
        return items.none()
    key = ITEM_KEY.match(query)
    if key:
        return items.filter(
            project__key=key.group(1).upper(), number=int(key.group(2))
        ).select_related("project", "assignee")
    return (
        items.filter(Q(title__icontains=query) | Q(description__icontains=query))
        .select_related("project", "assignee")
        .order_by("-updated_at")[:limit]
    )
