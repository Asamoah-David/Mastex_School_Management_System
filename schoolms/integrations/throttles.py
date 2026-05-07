"""DRF throttle classes for integration API endpoints."""

from rest_framework.throttling import AnonRateThrottle


class TokenObtainThrottle(AnonRateThrottle):
    """Limit brute-force attempts against JWT obtain (per IP)."""

    scope = "token_obtain"
