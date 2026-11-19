from apps.notifications.models import Notification

RECENT_LIMIT = 6


def notifications(request) -> dict:
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    mine = Notification.objects.filter(recipient=user)
    return {
        "unread_notifications": mine.filter(read_at__isnull=True).count(),
        "recent_notifications": mine.select_related("actor", "item__project")[
            :RECENT_LIMIT
        ],
    }
