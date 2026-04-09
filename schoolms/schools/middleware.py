from django.core.cache import cache
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from .models import School


class SchoolMiddleware:
    _skip_paths = frozenset([
        "/", "/accounts/login/", "/accounts/logout/", "/accounts/dashboard/",
        "/accounts/school-dashboard/", "/login/", "/logout/", "/register/",
        "/admin/login/", "/portal/",
    ])
    _skip_prefixes = ("/static/", "/media/", "/admin/jsi18n/", "/portal")
    _subscription_paths = (
        "/finance/subscription/", "/finance/pay-subscription/",
        "/finance/subscription-callback/", "/finance/subscription-expired/",
        "/accounts/login/", "/accounts/logout/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if path in self._skip_paths:
            return self.get_response(request)
        if any(path.startswith(p) for p in self._skip_prefixes):
            return self.get_response(request)

        request.school = self._resolve_school_from_host(request)

        if path.startswith("/admin/"):
            if not request.user.is_authenticated:
                return redirect(reverse("accounts:login"))
            if not request.user.is_superuser and getattr(request.user, "role", "") != "super_admin":
                return redirect(reverse("accounts:school_dashboard"))

        if request.user.is_authenticated:
            resp = self._enforce_school_access(request)
            if resp:
                return resp

        return self.get_response(request)

    # ------------------------------------------------------------------
    @staticmethod
    def _resolve_school_from_host(request):
        host = request.get_host().split(":")[0]
        if "." not in host or "localhost" in host or "onrender" in host:
            return None
        subdomain = host.split(".")[0]
        cache_key = f"school_subdomain:{subdomain}"
        school = cache.get(cache_key)
        if school is None:
            try:
                school = School.objects.get(subdomain=subdomain)
            except School.DoesNotExist:
                school = False
            cache.set(cache_key, school, 300)
        return school if school else None

    def _enforce_school_access(self, request):
        user = request.user
        if getattr(user, "is_superuser", False) or getattr(user, "role", "") == "super_admin":
            return None
        user_school = getattr(user, "school", None)
        if not user_school:
            return None

        # Cross-tenant protection: if a subdomain-based school was resolved
        # and it differs from the user's school, deny access.
        subdomain_school = request.school
        if subdomain_school and user_school.pk != subdomain_school.pk:
            from django.contrib.auth import logout
            logout(request)
            return redirect(reverse("accounts:login"))

        if not user_school.is_active:
            from django.contrib.auth import logout
            logout(request)
            return redirect(f"{reverse('accounts:login')}?inactive=1")

        if user_school.subscription_status == "expired":
            if not any(request.path.startswith(p) for p in self._subscription_paths):
                return render(request, "finance/subscription_expired.html", {"school": user_school})

        if (
            user_school.subscription_status == "active"
            and user_school.subscription_end_date
            and user_school.subscription_end_date < timezone.now()
        ):
            School.objects.filter(id=user_school.id, subscription_status="active").update(
                subscription_status="expired"
            )
            user_school.subscription_status = "expired"
            if not any(request.path.startswith(p) for p in self._subscription_paths):
                return render(request, "finance/subscription_expired.html", {"school": user_school})

        return None
