from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls import handler404, handler500
from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.views.generic import RedirectView
from django.db import connection
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from students.views import portal
from schools.views import school_register
from accounts.views import home

# Minimal HTML fallbacks if template rendering fails (DB / template issues).
_FALLBACK_404_HTML = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Not found</title></head>
<body style="font-family:system-ui;padding:2rem;background:#020617;color:#e2e8f8;"><p>Page not found.</p>
<p><a href="/" style="color:#4ade80;">Home</a> · <a href="/accounts/login/" style="color:#4ade80;">Sign in</a></p></body></html>"""

_FALLBACK_500_HTML = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Error</title></head>
<body style="font-family:system-ui;padding:2rem;background:#020617;color:#e2e8f8;"><p>Something went wrong. Please try again shortly.</p>
<p><a href="/" style="color:#4ade80;">Home</a></p></body></html>"""


def custom_404(request, exception):
    if request.path.startswith("/api/"):
        r = JsonResponse({"error": "Not found"}, status=404)
        r["Cache-Control"] = "no-store"
        return r
    try:
        response = render(request, "404.html", status=404)
        response.headers["Cache-Control"] = "no-store"
        return response
    except Exception:
        return HttpResponse(
            _FALLBACK_404_HTML,
            status=404,
            content_type="text/html; charset=utf-8",
            headers={"Cache-Control": "no-store"},
        )


def custom_500(request):
    if request.path.startswith("/api/"):
        r = JsonResponse({"error": "Internal server error"}, status=500)
        r["Cache-Control"] = "no-store"
        return r
    try:
        response = render(request, "500.html", status=500)
        response.headers["Cache-Control"] = "no-store"
        return response
    except Exception:
        return HttpResponse(
            _FALLBACK_500_HTML,
            status=500,
            content_type="text/html; charset=utf-8",
            headers={"Cache-Control": "no-store"},
        )


def health_check(request):
    """Lightweight health probe for load balancers and uptime monitors.

    Always returns HTTP 200 so platforms (e.g. Railway) mark the process as up.
    Use the JSON body for DB status; monitor ``status`` / ``database`` in ops.
    """
    status = {"status": "ok", "database": "ok"}
    try:
        connection.ensure_connection()
    except Exception:
        status["database"] = "unavailable"
        status["status"] = "degraded"
    return JsonResponse(status)


def ready_check(request):
    """Readiness probe.

    Returns non-200 when the database is unavailable so load balancers can stop
    routing traffic to an unhealthy instance.
    """
    status = {"status": "ok", "database": "ok"}
    http_status = 200
    try:
        connection.ensure_connection()
    except Exception:
        status["database"] = "unavailable"
        status["status"] = "unavailable"
        http_status = 503
    r = JsonResponse(status, status=http_status)
    r["Cache-Control"] = "no-store"
    return r


handler404 = custom_404
handler500 = custom_500

urlpatterns = [
    path("", home, name="home"),
    path(
        "favicon.ico",
        RedirectView.as_view(url=f"{settings.STATIC_URL}favicon.png", permanent=False),
    ),
    path("health/", health_check, name="health_check"),
    path("ready/", ready_check, name="ready_check"),
    path("admin/", admin.site.urls),
    path("schools/register/", school_register, name="school_register"),
    path("schools/", include("schools.urls")),
    path("portal/", portal, name="portal"),
    # API auth
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/v1/", include("integrations.urls")),
]

if settings.API_DOCS_ENABLED:
    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
        path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    ]

urlpatterns += [
    # App includes
    path("accounts/", include("accounts.urls")),
    path("", include("django.contrib.auth.urls")),
    path("students/", include("students.urls")),
    path("academics/", include("academics.urls")),
    path("finance/", include("finance.urls")),
    path("messaging/", include("messaging.urls")),
    path("operations/", include("operations.urls")),
    path("ai/", include("ai_assistant.urls")),
    path("notifications/", include("notifications.urls")),
    path("audit/", include("audit.urls")),
    # SSE real-time dashboard (Fix #32)
    path("core/sse/dashboard/", __import__("core.sse_views", fromlist=["sse_dashboard"]).sse_dashboard, name="sse_dashboard"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
