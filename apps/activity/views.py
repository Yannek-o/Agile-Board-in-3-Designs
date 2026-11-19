from django.views.generic import ListView

from apps.activity.models import ActivityEvent
from apps.projects.mixins import ProjectAccessMixin


class ProjectActivityView(ProjectAccessMixin, ListView):
    template_name = "activity/activity_list.html"
    context_object_name = "events"
    paginate_by = 50

    def get_queryset(self):
        return ActivityEvent.objects.filter(project=self.project).select_related(
            "actor", "item", "sprint"
        )
