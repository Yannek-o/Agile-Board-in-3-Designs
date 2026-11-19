from django.contrib import admin

from apps.sprints.models import Sprint, SprintItem


class SprintItemInline(admin.TabularInline):
    model = SprintItem
    extra = 0
    raw_id_fields = ("item",)


@admin.register(Sprint)
class SprintAdmin(admin.ModelAdmin):
    list_display = ("__str__", "status", "start_date", "end_date")
    list_filter = ("status", "project")
    inlines = [SprintItemInline]
