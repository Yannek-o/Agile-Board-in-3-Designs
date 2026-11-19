from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.api.models import ApiToken

MAX_TOKENS_PER_USER = 10


class ApiTokenView(View):
    """Lists, creates and shows personal API tokens (raw value only once)."""

    template_name = "api/tokens.html"

    def get(self, request):
        return self.render(new_token=None)

    def post(self, request):
        name = request.POST.get("name", "").strip()[:60]
        tokens = ApiToken.objects.filter(user=request.user)
        if not name:
            messages.error(request, "Bitte eine Bezeichnung angeben.")
            return self.render(new_token=None)
        if tokens.count() >= MAX_TOKENS_PER_USER:
            messages.error(
                request, f"Höchstens {MAX_TOKENS_PER_USER} Tokens pro Person."
            )
            return self.render(new_token=None)
        _, raw_token = ApiToken.issue(request.user, name=name)
        return self.render(new_token=raw_token)

    def render(self, new_token):
        return render(
            self.request,
            self.template_name,
            {
                "tokens": ApiToken.objects.filter(user=self.request.user),
                "new_token": new_token,
            },
        )


class ApiTokenDeleteView(View):
    http_method_names = ["post"]

    def post(self, request, pk: int):
        token = get_object_or_404(ApiToken, pk=pk, user=request.user)
        token.delete()
        messages.success(request, f"Token „{token.name}“ widerrufen.")
        return redirect("api:tokens")
