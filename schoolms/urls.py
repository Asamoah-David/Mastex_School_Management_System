from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from accounts.views import dashboard
from students.views import portal
from schools.views import school_register

urlpatterns = [
    path("", dashboard, name="home"),
    path("admin/", admin.site.urls),
    path("register/", school_register, name="school_register"),
    path("login/", RedirectView.as_view(pattern_name="accounts:login", permanent=False), name="login"),
    path("dashboard/", dashboard, name="dashboard"),
    path("portal/", portal, name="portal"),
    path("api/token/", TokenObtainPairView.as_view()),
    path("api/token/refresh/", TokenRefreshView.as_view()),
    path("accounts/", include("accounts.urls")),
    path("students/", include("students.urls")),
    path("academics/", include("academics.urls")),
    path("finance/", include("finance.urls")),
    path("messaging/", include("messaging.urls")),
    path("operations/", include("operations.urls")),
    path("ai/", include("ai_assistant.urls")),
]