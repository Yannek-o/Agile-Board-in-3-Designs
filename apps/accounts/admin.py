from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.accounts.forms import ThrottledAdminAuthenticationForm
from apps.accounts.models import AuthAttempt, User

admin.site.login_form = ThrottledAdminAuthenticationForm


@admin.register(User)
class EmployeeAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Profil", {"fields": ("job_title", "can_create_projects",
                               "email_notifications")}),
    )
    list_display = ("username", "email", "first_name", "last_name", "is_active")


@admin.register(AuthAttempt)
class AuthAttemptAdmin(admin.ModelAdmin):
    list_display = ("created_at", "kind", "username", "ip_address")
    list_filter = ("kind",)
    search_fields = ("username", "ip_address")
