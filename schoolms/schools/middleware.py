from django.core.cache import cache
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.http import HttpResponseForbidden
from django.conf import settings

from core.subscription_access import (
    maybe_update_subscription_status_from_dates,
    subscription_hard_block_applies,
)

from .models import School

_SUBSCRIPTION_CACHE_TTL = 60  # seconds


def _refresh_school_subscription_cached(school):
    """Update the in-memory school object's subscription fields using a
    short-lived per-school cache to avoid a DB round-trip on every request.

    Calls maybe_update_subscription_status_from_dates() at most once per
    ``_SUBSCRIPTION_CACHE_TTL`` seconds per school, then refreshes only the
    subscription-related fields from DB.
    """
    school_pk = school.pk
    staleness_key = f"sub_checked:{school_pk}"
    if cache.get(staleness_key):
        return
    maybe_update_subscription_status_from_dates(school)
    try:
        fresh = School.objects.only(
            "subscription_status",
            "subscription_end_date",
            "subscription_start_date",
            "subscription_grace_days",
            "is_active",
        ).get(pk=school_pk)
        school.subscription_status = fresh.subscription_status
        school.subscription_end_date = fresh.subscription_end_date
        school.subscription_start_date = fresh.subscription_start_date
        school.subscription_grace_days = fresh.subscription_grace_days
        school.is_active = fresh.is_active
    except School.DoesNotExist:
        pass
    cache.set(staleness_key, True, _SUBSCRIPTION_CACHE_TTL)


class SchoolMiddleware:
    _skip_paths = frozenset([
        "/", "/health/", "/ready/", "/accounts/login/", "/accounts/logout/",
        "/login/", "/logout/", "/register/",
        "/admin/login/", "/portal/",
    ])
    _skip_prefixes = ("/static/", "/media/", "/admin/jsi18n/", "/portal")
    _subscription_paths = (
        "/finance/subscription/",
        "/finance/subscription/pay/",
        "/finance/subscription/callback/",
        "/finance/pay-subscription/",
        "/finance/subscription-callback/",
        "/finance/subscription-expired/",
        "/accounts/login/",
        "/accounts/logout/",
        "/schools/register/",
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
                return HttpResponseForbidden("Forbidden")

        if request.user.is_authenticated:
            resp = self._enforce_school_access(request)
            if resp:
                return resp

        return self.get_response(request)

    # ------------------------------------------------------------------
    @staticmethod
    def _resolve_school_from_host(request):
        host = request.get_host().split(":")[0]
        if host in ("localhost", "127.0.0.1"):
            return None
        if "." not in host:
            return None

        suffixes = getattr(settings, "TENANT_DOMAIN_SUFFIXES", None)
        if suffixes:
            try:
                allowed = any(host.endswith(sfx) for sfx in suffixes)
            except TypeError:
                allowed = False
            if not allowed:
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

        _refresh_school_subscription_cached(user_school)

        if subscription_hard_block_applies(user_school):
            if not any(request.path.startswith(p) for p in self._subscription_paths):
                is_ajax = (
                    request.headers.get("X-Requested-With") == "XMLHttpRequest"
                    or "application/json" in request.headers.get("Accept", "")
                    or "application/json" in request.headers.get("Content-Type", "")
                    or request.headers.get("HX-Request") == "true"
                    or request.path.startswith("/api/")
                )
                if is_ajax:
                    from django.http import JsonResponse
                    r = JsonResponse(
                        {"error": "School subscription has expired. Please contact your school administrator."},
                        status=403,
                    )
                    r["Cache-Control"] = "no-store"
                    return r
                return render(
                    request,
                    "finance/subscription_expired.html",
                    {"school": user_school},
                )

        return None
