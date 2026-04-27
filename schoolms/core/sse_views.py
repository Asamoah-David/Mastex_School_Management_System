"""
Server-Sent Events (SSE) views for real-time dashboard updates (Fix #32).

No Django Channels or WebSocket required — pure HTTP streaming.
Clients reconnect automatically every 15 s via the EventSource API.

Usage in template:
    const es = new EventSource('/core/sse/dashboard/');
    es.addEventListener('dashboard', e => {
        const data = JSON.parse(e.data);
        // update counters …
    });
"""

import json
import time
import logging

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import HttpResponse, StreamingHttpResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


def _sse_event(event_name: str, data: dict) -> str:
    """Format a single SSE frame."""
    payload = json.dumps(data, default=str)
    return f"event: {event_name}\ndata: {payload}\n\n"


def _build_dashboard_snapshot(school):
    """Build a lightweight real-time snapshot for the school dashboard."""
    from django.db.models import Count, Q

    snapshot = {"ts": timezone.now().isoformat()}

    # Today's attendance
    try:
        from operations.models import StudentAttendance
        today = timezone.localdate()
        agg = StudentAttendance.objects.filter(school=school, date=today).aggregate(
            present=Count("id", filter=Q(status="present")),
            absent=Count("id", filter=Q(status="absent")),
            late=Count("id", filter=Q(status="late")),
        )
        snapshot["attendance"] = agg
    except Exception:
        snapshot["attendance"] = {}

    # Active student count
    try:
        from students.models import Student
        snapshot["student_count"] = Student.objects.filter(school=school, status="active").count()
    except Exception:
        snapshot["student_count"] = None

    # Outstanding fees
    try:
        from django.db.models import Sum, F
        from finance.models import Fee
        result = Fee.objects.filter(school=school, is_active=True).aggregate(
            total=Sum("amount"), paid=Sum("amount_paid")
        )
        snapshot["fees"] = {
            "total_billed": float(result["total"] or 0),
            "total_paid": float(result["paid"] or 0),
            "outstanding": float((result["total"] or 0) - (result["paid"] or 0)),
        }
    except Exception:
        snapshot["fees"] = {}

    # Low stock items count
    try:
        from operations.models.inventory import InventoryItem
        from django.db.models import F
        snapshot["low_stock_count"] = InventoryItem.objects.filter(
            school=school, quantity__lte=F("min_quantity")
        ).count()
    except Exception:
        snapshot["low_stock_count"] = None

    return snapshot


def _dashboard_stream(school):
    """Generator: emit one SSE snapshot, then close (client auto-reconnects)."""
    try:
        data = _build_dashboard_snapshot(school)
        yield _sse_event("dashboard", data)
        # Keepalive comment so the connection isn't prematurely closed
        yield ": keepalive\n\n"
    except Exception as exc:
        logger.warning("SSE dashboard stream error: %s", exc)
        yield _sse_event("error", {"detail": "Dashboard data unavailable."})


_SSE_RATE_WINDOW = 60
_SSE_MAX_PER_WINDOW = 4


@require_GET
@login_required
def sse_dashboard(request):
    """SSE endpoint — streams one dashboard snapshot then closes.

    The browser EventSource automatically reconnects (default: 3 s).
    Rate-limited to 4 requests / 60 s per user to prevent resource exhaustion.
    """
    user = request.user

    rate_key = f"sse_rate:{user.pk}"
    hit_count = cache.get(rate_key, 0)
    if hit_count >= _SSE_MAX_PER_WINDOW:
        response = HttpResponse(status=429)
        response["Retry-After"] = str(_SSE_RATE_WINDOW)
        return response
    cache.set(rate_key, hit_count + 1, timeout=_SSE_RATE_WINDOW)

    school = getattr(user, "school", None)

    if not school:
        def _no_school():
            yield _sse_event("error", {"detail": "No school context."})
        response = StreamingHttpResponse(_no_school(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        return response

    def _stream():
        # Tell client to wait 15 s before reconnecting
        yield "retry: 15000\n\n"
        yield from _dashboard_stream(school)

    response = StreamingHttpResponse(_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"  # Disable nginx buffering
    return response
