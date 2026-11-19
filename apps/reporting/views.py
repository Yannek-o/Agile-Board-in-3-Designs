from django import forms
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from apps.core.http import wants_json
from apps.projects.mixins import ProjectAccessMixin
from apps.reporting.kpis import kpi_tiles, record_dashboard_snapshot
from apps.reporting.services import dashboard_data, project_report


class DashboardNotesForm(forms.Form):
    notes = forms.CharField(required=False, max_length=5000)


class DashboardNotesView(View):
    http_method_names = ["post"]

    def post(self, request):
        form = DashboardNotesForm(request.POST)
        saved = form.is_valid()
        if saved:
            request.user.dashboard_notes = form.cleaned_data["notes"].strip()
            request.user.save(update_fields=["dashboard_notes"])
        if wants_json(request):
            return JsonResponse({"saved": saved}, status=200 if saved else 400)
        if saved:
            messages.success(request, "Notizen gespeichert.")
        else:
            messages.error(request, "Notizen sind zu lang (max. 5000 Zeichen).")
        return redirect("reporting:dashboard")


class DashboardView(TemplateView):
    template_name = "reporting/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data = dashboard_data(self.request.user)
        data["kpi_tiles"] = kpi_tiles(self.request.user, data["metrics"])
        record_dashboard_snapshot(self.request.user, data["metrics"])
        context.update(data)
        return context


class ProjectReportView(ProjectAccessMixin, TemplateView):
    template_name = "reporting/project_report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(project_report(self.project))
        return context
