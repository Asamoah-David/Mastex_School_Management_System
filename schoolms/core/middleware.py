from __future__ import annotations

import logging
import uuid

from django.conf import settings
from django.http import HttpResponsePermanentRedirect

logger = logging.getLogger("mastex.unhandled")

# ---------------------------------------------------------------------------
# SEC-6 — Content Security Policy
# ---------------------------------------------------------------------------

_CSP_DEFAULT = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
    "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
    "img-src 'self' data: blob: https:; "
    "connect-src 'self' https://api.paystack.co "
    "https://meet.jit.si wss://meet.jit.si "
    "https://*.jitsi.net wss://*.jitsi.net; "
    "frame-src 'self' https://meet.jit.si; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self';"
)


class CspMiddleware:
    """Inject Content-Security-Policy and related security headers on every response.

    Override the policy via ``CSP_POLICY`` in settings. Set ``CSP_ENABLED=False``
    to disable in DEBUG/testing without removing the middleware from MIDDLEWARE.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.policy = getattr(settings, "CSP_POLICY", _CSP_DEFAULT)
        self.enabled = getattr(settings, "CSP_ENABLED", not settings.DEBUG)

    def __call__(self, request):
        response = self.get_response(request)
        if self.enabled:
            content_type = response.get("Content-Type", "")
            if "text/html" in content_type:
                response.setdefault("Content-Security-Policy", self.policy)
                # Allow Jitsi (meet.jit.si) iframes to use camera/mic; keep geolocation off.
                response.setdefault(
                    "Permissions-Policy",
                    'geolocation=(), camera=(self "https://meet.jit.si"), microphone=(self "https://meet.jit.si")',
                )
                response.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response


class CanonicalDomainMiddleware:
    """
    Redirect non-www to www for the primary domain.
    Ensures canonical URLs for SEO and consistency.
    Only applies to the configured primary domain, not Railway subdomains.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        self.primary_domain = getattr(settings, "CANONICAL_DOMAIN", "mastexedu.online")

    def __call__(self, request):
        host = request.get_host().split(":")[0]  # Remove port if present
        
        # Skip if already on canonical domain (www)
        if host == f"www.{self.primary_domain}":
            return self.get_response(request)
        
        # Skip if not on primary domain (e.g., Railway subdomains)
        if host != self.primary_domain:
            return self.get_response(request)
        
        # Skip if request is already HTTPS (Railway handles SSL)
        # Redirect non-www to www
        return HttpResponsePermanentRedirect(f"https://www.{self.primary_domain}{request.get_full_path()}")


class RequestIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        rid = request.headers.get("X-Request-ID")
        if not rid:
            rid = uuid.uuid4().hex
        request.request_id = rid
        response = self.get_response(request)
        try:
            response["X-Request-ID"] = rid
        except Exception:
            pass
        return response


class ExceptionLoggingMiddleware:
    """Log uncaught exceptions with request context; re-raises for normal Django handling."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        except Exception:
            uid = getattr(getattr(request, "user", None), "pk", None)
            logger.exception(
                "Unhandled exception method=%s path=%s user_id=%s request_id=%s",
                request.method,
                request.path,
                uid,
                getattr(request, "request_id", ""),
            )
            raise
