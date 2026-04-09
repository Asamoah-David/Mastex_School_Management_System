from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls import handler404, handler500
from django.shortcuts import render
from django.http import JsonResponse
from django.db import connection
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from students.views import portal
from schools.views import school_register
from accounts.views import home


def custom_404(request, exception):
    if request.path.startswith("/api/"):
        return JsonResponse({"error": "Not found"}, status=404)
    return render(request, "404.html", status=404)


def custom_500(request):
    if request.path.startswith("/api/"):
        return JsonResponse({"error": "Internal server error"}, status=500)
    return render(request, "500.html", status=500)


def health_check(request):
    """Lightweight health probe for load balancers and uptime monitors."""
    status = {"status": "ok", "database": "ok"}
    http_status = 200
    try:
        connection.ensure_connection()
    except Exception:
        status["database"] = "unavailable"
        status["status"] = "degraded"
        http_status = 503
    return JsonResponse(status, status=http_status)


handler404 = custom_404
handler500 = custom_500

urlpatterns = [
    path("", home, name="home"),
    path("health/", health_check, name="health_check"),
    path("admin/", admin.site.urls),
    path("schools/register/", school_register, name="school_register"),
    path("schools/", include("schools.urls")),
    path("portal/", portal, name="portal"),
    # API auth
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # API docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
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
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
