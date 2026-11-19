from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import ListView

from apps.notifications.models import Notification


def unread_for(user):
    return Notification.objects.filter(recipient=user, read_at__isnull=True)


class NotificationListView(ListView):
    template_name = "notifications/notification_list.html"
    context_object_name = "notifications"
    paginate_by = 50

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user).select_related(
            "actor", "item__project"
        )


class NotificationOpenView(View):
    """Marks a notification as read and opens the related item."""

    http_method_names = ["get"]

    def get(self, request, pk: int):
        notification = get_object_or_404(
            Notification.objects.select_related("item__project"),
            pk=pk, recipient=request.user,
        )
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at"])
        return redirect(notification.target_url)


class NotificationMarkAllReadView(View):
    http_method_names = ["post"]

    def post(self, request):
        unread_for(request.user).update(read_at=timezone.now())
        return redirect("notifications:list")


class UnreadCountView(View):
    http_method_names = ["get"]

    def get(self, request):
        response = JsonResponse({"count": unread_for(request.user).count()})
        response["Cache-Control"] = "no-store"
        return response
