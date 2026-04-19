from __future__ import annotations

import uuid


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
