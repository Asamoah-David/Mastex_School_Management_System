from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls import handler404, handler500
from django.shortcuts import render
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from students.views import portal
from schools.views import school_register
from accounts.views import home

# Custom error handlers
def custom_404(request, exception):
    return render(request, '404.html', status=404)

def custom_500(request):
    return render(request, '500.html', status=500)

handler404 = custom_404
handler500 = custom_500

urlpatterns = [
    # Smart home route: decides where to send user based on auth/role
    path("", home, name="home"),
    path("admin/", admin.site.urls),
    path("register/", school_register, name="school_register"),
    path("schools/", include("schools.urls")),
    # Removed conflicting login path, handled by accounts.urls
    # Removed conflicting dashboard path, handled by accounts.urls
    path("portal/", portal, name="portal"),
    path("api/token/", TokenObtainPairView.as_view()),
    path("api/token/refresh/", TokenRefreshView.as_view()),
    path("accounts/", include("accounts.urls")),
    path("", include("django.contrib.auth.urls")),  # Password reset URLs
    path("students/", include("students.urls")),
    path("academics/", include("academics.urls")),
    path("finance/", include("finance.urls")),
    path("messaging/", include("messaging.urls")),
    path("operations/", include("operations.urls")),
    path("ai/", include("ai_assistant.urls")),
    path("notifications/", include("notifications.urls")),
]

# Serve media files in all environments (production and development)
# This ensures uploaded files (profile photos, ID cards, etc.) are accessible
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
