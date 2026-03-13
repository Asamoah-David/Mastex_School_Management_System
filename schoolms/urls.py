from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from students.views import portal
from schools.views import school_register
from accounts.views import home

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
    path("students/", include("students.urls")),
    path("academics/", include("academics.urls")),
    path("finance/", include("finance.urls")),
    path("messaging/", include("messaging.urls")),
    path("operations/", include("operations.urls")),
    path("ai/", include("ai_assistant.urls")),
]