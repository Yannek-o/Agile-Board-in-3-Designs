from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from apps.accounts.forms import (
    EmployeeCreationForm,
    EmployeeUpdateForm,
    ProfileForm,
    ThrottledAuthenticationForm,
)
from apps.accounts.models import User
from apps.accounts.services import (
    AccountError,
    invite_employee,
    send_invitation,
    set_avatar_colors,
    set_employee_active,
    update_employee,
)
from apps.accounts.throttling import allow_password_reset, client_ip
from apps.accounts.tokens import invitation_token_generator
from apps.core.http import request_payload, safe_next_url, wants_json


class SystemAdminRequiredMixin(UserPassesTestMixin):
    raise_exception = True

    def test_func(self) -> bool:
        return self.request.user.is_system_admin


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True
    authentication_form = ThrottledAuthenticationForm


class PasswordResetView(auth_views.PasswordResetView):
    template_name = "accounts/password_reset_form.html"
    email_template_name = "accounts/emails/password_reset.txt"
    subject_template_name = "accounts/emails/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")

    def form_valid(self, form):
        if not allow_password_reset(client_ip(self.request)):
            # Same response as success so that limits do not reveal anything.
            return HttpResponseRedirect(self.get_success_url())
        self.extra_email_context = {"site_url": settings.SITE_URL.rstrip("/")}
        return super().form_valid(form)


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["timeout_hours"] = settings.PASSWORD_RESET_TIMEOUT // 3600
        return context


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")


class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"


class ProfileView(UpdateView):
    form_class = ProfileForm
    template_name = "accounts/profile.html"
    success_url = reverse_lazy("accounts:profile")

    def get_object(self, queryset=None) -> User:
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, "Profil gespeichert.")
        return super().form_valid(form)


class DesignSwitchView(View):
    """Stores the personal UI design; functionality is the same in every design."""

    http_method_names = ["post"]

    def post(self, request):
        design = request_payload(request).get("design")
        valid = design in User.Design.values
        if valid:
            request.user.design = design
            request.user.save(update_fields=["design"])
        if wants_json(request):
            return JsonResponse(
                {"design": request.user.design}, status=200 if valid else 400
            )
        if not valid:
            messages.error(request, "Unbekanntes Design.")
        return redirect(safe_next_url(request, reverse("reporting:dashboard")))


class AvatarColorView(View):
    """Saves the personal avatar colour (single colour or two-colour gradient)."""

    http_method_names = ["post"]

    def post(self, request):
        data = request_payload(request)
        try:
            if data.get("reset"):
                set_avatar_colors(request.user)
            else:
                set_avatar_colors(
                    request.user,
                    color=data.get("color", ""),
                    color_2=data.get("color_2", "") if data.get("gradient") else "",
                )
        except ValidationError as error:
            if wants_json(request):
                return JsonResponse({"error": " ".join(error.messages)}, status=400)
            messages.error(request, " ".join(error.messages))
        else:
            if wants_json(request):
                user = request.user
                return JsonResponse(
                    {
                        "background": user.avatar_background,
                        "text": user.avatar_text_color,
                    }
                )
        return redirect(safe_next_url(request, reverse("reporting:dashboard")))


class PasswordChangeView(auth_views.PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("accounts:profile")

    def form_valid(self, form):
        messages.success(self.request, "Passwort geändert.")
        return super().form_valid(form)


class UserListView(SystemAdminRequiredMixin, ListView):
    template_name = "accounts/user_list.html"
    context_object_name = "employees"

    def get_queryset(self):
        queryset = User.objects.annotate(
            project_count=Count(
                "memberships", filter=Q(memberships__is_active=True)
            )
        )
        search = self.request.GET.get("q", "").strip()
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
            )
        return queryset


class UserCreateView(SystemAdminRequiredMixin, CreateView):
    form_class = EmployeeCreationForm
    template_name = "accounts/user_form.html"
    success_url = reverse_lazy("accounts:user_list")

    def form_valid(self, form):
        employee = invite_employee(self.request.user, **form.employee_fields())
        messages.success(
            self.request,
            f"Konto für {employee.display_name} angelegt – die Einladung geht an "
            f"{employee.email}.",
        )
        return redirect(self.success_url)


class UserUpdateView(SystemAdminRequiredMixin, UpdateView):
    model = User
    form_class = EmployeeUpdateForm
    template_name = "accounts/user_form.html"
    success_url = reverse_lazy("accounts:user_list")
    context_object_name = "employee"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if self.object == self.request.user:
            form.fields["is_staff"].disabled = True
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["account_events"] = self.object.account_events.select_related(
            "actor"
        )[:30]
        return context

    def form_valid(self, form):
        original = User.objects.get(pk=self.object.pk)
        try:
            update_employee(original, self.request.user, **form.employee_fields())
        except AccountError as error:
            form.add_error(None, str(error))
            return self.form_invalid(form)
        messages.success(self.request, "Mitarbeiterkonto gespeichert.")
        return redirect(self.success_url)


class UserToggleActiveView(SystemAdminRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk: int):
        employee = get_object_or_404(User, pk=pk)
        try:
            employee = set_employee_active(
                employee, actor=request.user, active=not employee.is_active
            )
        except AccountError as error:
            messages.error(request, str(error))
        else:
            state = "aktiviert" if employee.is_active else "deaktiviert"
            messages.success(request, f"{employee.display_name} wurde {state}.")
        return redirect("accounts:user_list")


class UserResendInvitationView(SystemAdminRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk: int):
        employee = get_object_or_404(User, pk=pk, is_active=True)
        try:
            send_invitation(employee, actor=request.user)
        except AccountError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, f"Einladung erneut an {employee.email} gesendet.")
        return redirect("accounts:user_list")


class InvitationAcceptView(auth_views.PasswordResetConfirmView):
    """Lets an invited employee choose the first password."""

    template_name = "accounts/invitation_accept.html"
    token_generator = invitation_token_generator
    reset_url_token = "einladung"
    success_url = reverse_lazy("accounts:password_reset_complete")
