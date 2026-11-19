from django.contrib import admin

from apps.projects.models import Label, Project, ProjectMembership


class MembershipInline(admin.TabularInline):
    model = ProjectMembership
    extra = 0


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("key", "name", "status", "archived_at")
    list_filter = ("status",)
    search_fields = ("key", "name")
    inlines = [MembershipInline]


admin.site.register(Label)
