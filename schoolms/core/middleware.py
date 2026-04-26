from __future__ import annotations

import uuid
from django.conf import settings
from django.http import HttpResponsePermanentRedirect


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
