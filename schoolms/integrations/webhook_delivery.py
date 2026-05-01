"""Deliver signed JSON webhooks to school-configured HTTPS endpoints."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from datetime import timedelta
from typing import Any

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def _webhooks_globally_enabled() -> bool:
    return getattr(settings, "INTEGRATIONS_WEBHOOKS_ENABLED", True)


def deliver_school_event(school_id: int, event_type: str, payload: dict[str, Any]) -> None:
    """
    POST ``payload`` to all active endpoints for ``school_id`` that subscribe to ``event_type``.
    Event types: staff_leave.updated, expense.updated
    """
    if not _webhooks_globally_enabled():
        return

    from integrations.models import SchoolWebhookEndpoint, WebhookDeliveryAttempt

    if event_type.startswith("staff_leave."):
        flag = "notify_staff_leave"
    elif event_type.startswith("expense."):
        flag = "notify_expense"
    else:
        return

    qs = SchoolWebhookEndpoint.objects.filter(school_id=school_id, is_active=True, **{flag: True})
    if not qs.exists():
        return

    # S5 — include Unix timestamp in envelope for replay protection.
    # Receivers should reject if abs(time.time() - t) > REPLAY_WINDOW_SEC (default 300s).
    ts = int(time.time())
    body_obj = {
        "event": event_type,
        "school_id": school_id,
        "timestamp": ts,
        "payload": payload,
    }
    body = json.dumps(body_obj, separators=(",", ":"), default=str).encode("utf-8")
    timeout = getattr(settings, "INTEGRATIONS_WEBHOOK_TIMEOUT_SEC", 10)
    retries = int(getattr(settings, "INTEGRATIONS_WEBHOOK_RETRIES", 1) or 0)
    backoff_sec = float(getattr(settings, "INTEGRATIONS_WEBHOOK_RETRY_BACKOFF_SEC", 0.5) or 0)
    # Use (connect, read) timeouts for safer hanging protection.
    req_timeout = (min(5, timeout), timeout)

    for ep in qs:
        delivery = WebhookDeliveryAttempt.objects.create(
            school_id=school_id,
            endpoint=ep,
            event_type=event_type,
            payload=payload,
            status="pending",
            attempt_count=0,
        )
        # Sign: HMAC-SHA256 over "timestamp.body" so timestamp is part of the signed payload.
        signed_payload = f"{ts}.".encode("utf-8") + body
        sig = hmac.new(ep.signing_secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "X-Mastex-Event": event_type,
            "X-Mastex-Timestamp": str(ts),
            "X-Mastex-Signature": f"sha256={sig}",
            "User-Agent": "MastexSchoolOS-Webhook/1.0",
        }
        attempt = 0
        while True:
            attempt += 1
            WebhookDeliveryAttempt.objects.filter(pk=delivery.pk).update(attempt_count=attempt)
            try:
                r = requests.post(ep.url, data=body, headers=headers, timeout=req_timeout)
                if r.status_code >= 400:
                    body_excerpt = (r.text or "")[:200]
                    logger.warning(
                        "Webhook delivery HTTP %s for school=%s endpoint=%s url=%s attempt=%s body=%s",
                        r.status_code,
                        school_id,
                        ep.pk,
                        ep.url[:80],
                        attempt,
                        body_excerpt,
                    )
                    if attempt <= retries:
                        next_retry = timezone.now() + timedelta(seconds=max(0, backoff_sec * attempt))
                        WebhookDeliveryAttempt.objects.filter(pk=delivery.pk).update(
                            status="failed",
                            last_http_status=r.status_code,
                            last_error=f"HTTP {r.status_code}: {body_excerpt}"[:2000],
                            next_retry_at=next_retry,
                        )
                        if backoff_sec > 0:
                            time.sleep(backoff_sec * attempt)
                        continue
                    WebhookDeliveryAttempt.objects.filter(pk=delivery.pk).update(
                        status="failed",
                        last_http_status=r.status_code,
                        last_error=f"HTTP {r.status_code}: {body_excerpt}"[:2000],
                        next_retry_at=None,
                    )
                else:
                    WebhookDeliveryAttempt.objects.filter(pk=delivery.pk).update(
                        status="delivered",
                        last_http_status=r.status_code,
                        last_error="",
                        delivered_at=timezone.now(),
                        next_retry_at=None,
                    )
                break
            except (requests.Timeout, requests.ConnectionError) as exc:
                if attempt <= retries:
                    next_retry = timezone.now() + timedelta(seconds=max(0, backoff_sec * attempt))
                    WebhookDeliveryAttempt.objects.filter(pk=delivery.pk).update(
                        status="failed",
                        last_http_status=None,
                        last_error=str(exc)[:2000],
                        next_retry_at=next_retry,
                    )
                    if backoff_sec > 0:
                        time.sleep(backoff_sec * attempt)
                    continue
                logger.warning(
                    "Webhook delivery failed school=%s endpoint=%s url=%s attempt=%s: %s",
                    school_id,
                    ep.pk,
                    ep.url[:80],
                    attempt,
                    exc,
                    exc_info=False,
                )
                WebhookDeliveryAttempt.objects.filter(pk=delivery.pk).update(
                    status="failed",
                    last_http_status=None,
                    last_error=str(exc)[:2000],
                    next_retry_at=None,
                )
                break
            except requests.RequestException as exc:
                logger.warning(
                    "Webhook delivery failed school=%s endpoint=%s url=%s: %s",
                    school_id,
                    ep.pk,
                    ep.url[:80],
                    exc,
                    exc_info=False,
                )
                WebhookDeliveryAttempt.objects.filter(pk=delivery.pk).update(
                    status="failed",
                    last_http_status=None,
                    last_error=str(exc)[:2000],
                    next_retry_at=None,
                )
                break
