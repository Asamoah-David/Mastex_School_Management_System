"""Deliver signed JSON webhooks to school-configured HTTPS endpoints."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

import requests
from django.conf import settings

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

    from integrations.models import SchoolWebhookEndpoint

    if event_type.startswith("staff_leave."):
        flag = "notify_staff_leave"
    elif event_type.startswith("expense."):
        flag = "notify_expense"
    else:
        return

    qs = SchoolWebhookEndpoint.objects.filter(school_id=school_id, is_active=True, **{flag: True})
    if not qs.exists():
        return

    body_obj = {
        "event": event_type,
        "school_id": school_id,
        "payload": payload,
    }
    body = json.dumps(body_obj, separators=(",", ":"), default=str).encode("utf-8")
    timeout = getattr(settings, "INTEGRATIONS_WEBHOOK_TIMEOUT_SEC", 10)

    for ep in qs:
        try:
            sig = hmac.new(ep.signing_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
            headers = {
                "Content-Type": "application/json",
                "X-Mastex-Event": event_type,
                "X-Mastex-Signature": f"sha256={sig}",
                "User-Agent": "MastexSchoolOS-Webhook/1.0",
            }
            r = requests.post(ep.url, data=body, headers=headers, timeout=timeout)
            if r.status_code >= 400:
                logger.warning(
                    "Webhook delivery HTTP %s for school=%s endpoint=%s url=%s",
                    r.status_code,
                    school_id,
                    ep.pk,
                    ep.url[:80],
                )
        except requests.RequestException as exc:
            logger.warning(
                "Webhook delivery failed school=%s endpoint=%s: %s",
                school_id,
                ep.pk,
                exc,
                exc_info=False,
            )
