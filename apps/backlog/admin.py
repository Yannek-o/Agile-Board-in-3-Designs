from django.contrib import admin

from apps.backlog.models import AcceptanceCriterion, Attachment, BacklogItem, Comment


class CriterionInline(admin.TabularInline):
    model = AcceptanceCriterion
    extra = 0


@admin.register(BacklogItem)
class BacklogItemAdmin(admin.ModelAdmin):
    list_display = ("__str__", "item_type", "priority", "status", "assignee")
    list_filter = ("project", "item_type", "priority", "status")
    search_fields = ("title",)
    inlines = [CriterionInline]


admin.site.register(Comment)
admin.site.register(Attachment)
