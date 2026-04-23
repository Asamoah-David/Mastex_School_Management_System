from django.shortcuts import redirect
from django.urls import reverse


class ForcePasswordChangeMiddleware:
    """
    Redirect users with ``must_change_password=True`` to the
    force-change-password page on every request until they reset it.
    """

    ALLOWED_URLS = None

    def __init__(self, get_response):
        self.get_response = get_response

    # Prefixes that must remain reachable while a forced change is pending, so
    # the change page and auth flows render correctly (CSS/images, password
    # reset confirmation, favicon).
    ALLOWED_PREFIXES = ("/static", "/media", "/favicon", "/accounts/password-reset", "/api/")

    def __call__(self, request):
        if request.user.is_authenticated and getattr(request.user, "must_change_password", False):
            change_url = reverse("accounts:force_password_change")
            logout_url = reverse("logout")
            allowed = {change_url, logout_url}
            path = request.path or ""
            if path not in allowed and not any(path.startswith(p) for p in self.ALLOWED_PREFIXES):
                return redirect(change_url)
        return self.get_response(request)
