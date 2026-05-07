"""JWT views with production-oriented rate limits."""

from rest_framework_simplejwt.views import TokenObtainPairView

from integrations.throttles import TokenObtainThrottle


class ThrottledTokenObtainPairView(TokenObtainPairView):
    throttle_classes = [TokenObtainThrottle]
