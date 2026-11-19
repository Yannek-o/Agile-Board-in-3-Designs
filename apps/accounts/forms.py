from math import ceil

from django import forms
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth.forms import AuthenticationForm

from apps.accounts.models import User
from apps.accounts.services import EDITABLE_FIELDS
from apps.accounts.throttling import (
    clear_login_failures,
    client_ip,
    login_lock_remaining,
    record_login_failure,
)


class ThrottledLoginMixin:
    """Rejects logins while an account or client IP is locked out."""

    lockout_message = (
        "Zu viele fehlgeschlagene Anmeldeversuche. Bitte in {minutes} "
        "Minute(n) erneut versuchen."
    )

    def clean(self):
        username = self.cleaned_data.get("username", "")
        ip = client_ip(self.request)
        remaining = login_lock_remaining(username, ip)
        if remaining:
            minutes = max(1, ceil(remaining.total_seconds() / 60))
            raise forms.ValidationError(
                self.lockout_message.format(minutes=minutes), code="locked"
            )
        try:
            cleaned_data = super().clean()
        except forms.ValidationError:
            record_login_failure(username, ip)
            raise
        clear_login_failures(username)
        return cleaned_data


class ThrottledAuthenticationForm(ThrottledLoginMixin, AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Benutzername oder Passwort ist falsch, oder das Konto "
        "ist deaktiviert.",
        "inactive": "Benutzername oder Passwort ist falsch, oder das Konto "
        "ist deaktiviert.",
    }


class ThrottledAdminAuthenticationForm(ThrottledLoginMixin, AdminAuthenticationForm):
    pass


class EmailUniquenessMixin:
    def clean_email(self) -> str:
        email = self.cleaned_data.get("email", "").strip().lower()
        if not email:
            return email
        duplicates = User.objects.filter(email__iexact=email)
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise forms.ValidationError("Diese E-Mail-Adresse wird bereits verwendet.")
        return email


class ProfileForm(EmailUniquenessMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "job_title",
                  "email_notifications", "design"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["design"].required = False

    def clean_design(self) -> str:
        return self.cleaned_data.get("design") or self.instance.design


EMPLOYEE_FIELDS = list(EDITABLE_FIELDS)


class EmployeeFormMixin(EmailUniquenessMixin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True
        self.fields["email"].help_text = (
            "Pflichtfeld – wird für die Einladung und das Zurücksetzen des "
            "Passworts benötigt."
        )

    def employee_fields(self) -> dict:
        return {
            field: self.cleaned_data[field]
            for field in EMPLOYEE_FIELDS
            if field in self.fields and not self.fields[field].disabled
        }


class EmployeeCreationForm(EmployeeFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = EMPLOYEE_FIELDS
        labels = {"is_staff": "Systemadministration"}


class EmployeeUpdateForm(EmployeeFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = EMPLOYEE_FIELDS
        labels = {"is_staff": "Systemadministration"}
