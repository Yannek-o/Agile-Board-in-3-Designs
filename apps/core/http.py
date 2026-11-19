import json

from django.utils.http import url_has_allowed_host_and_scheme


def safe_next_url(request, default: str) -> str:
    """Returns the ``next`` parameter only if it points to this host."""
    candidate = request.POST.get("next") or request.GET.get("next")
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return default


def wants_json(request) -> bool:
    return (
        request.content_type == "application/json"
        or "application/json" in request.headers.get("Accept", "")
    )


def request_payload(request) -> dict:
    """Request data from a JSON body or, for regular form posts, from POST."""
    if request.content_type == "application/json":
        try:
            payload = json.loads(request.body or b"{}")
        except ValueError:
            return {}
        return payload if isinstance(payload, dict) else {}
    return request.POST
