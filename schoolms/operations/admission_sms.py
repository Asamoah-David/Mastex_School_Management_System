"""
Length-safe SMS copy for admission flows.

Gateways (e.g. MNotify) bill by segment; very long hosts or school names can
produce oversized bodies or awkward splits. We prefer a single message with a
clickable link when it fits ``ADMISSION_SMS_MAX_CHARS``, otherwise a
reference-only message (never truncate mid-URL).
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.conf import settings
from django.urls import reverse


def _sms_char_budget() -> int:
    try:
        n = int(getattr(settings, "ADMISSION_SMS_MAX_CHARS", 300))
    except (TypeError, ValueError):
        n = 300
    return max(120, min(640, n))


def _truncate_label(text: str, max_len: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    if max_len < 2:
        return text[:max_len]
    return text[: max_len - 1].rstrip() + "…"


def admission_track_url(request, public_reference: str) -> str:
    """Absolute track URL, using ADMISSION_SMS_PUBLIC_BASE_URL when set (shorter prod domain)."""
    path = reverse("operations:admission_track") + "?" + urlencode({"ref": public_reference.strip()})
    base = getattr(settings, "ADMISSION_SMS_PUBLIC_BASE_URL", None)
    if isinstance(base, str):
        base = base.strip().rstrip("/")
    if base:
        return f"{base}{path}"
    return request.build_absolute_uri(path)


def admission_parent_confirmation_message(request, school_name: str, public_reference: str) -> str:
    """
    One SMS body: include track URL if the full text fits the budget; else
    instruct the parent to use the reference on the site's track page (no URL).
    """
    budget = _sms_char_budget()
    school_short = _truncate_label(school_name, 40)
    ref = public_reference.strip()
    track_url = admission_track_url(request, ref)

    candidates = [
        f"{school_short}: application received. Ref {ref}. Track: {track_url}",
        f"Ref {ref} — {school_short}. Track: {track_url}",
        f"{school_short}: received. Ref {ref}. Track: {track_url}",
    ]
    for body in candidates:
        if len(body) <= budget:
            return body

    no_url = (
        f"{school_short}: application received. Save ref {ref}. "
        "Open the same website you used to apply, go to Admissions, then Track, and enter that ref."
    )
    if len(no_url) <= budget:
        return no_url

    return _truncate_label(no_url, budget)


def admission_admin_new_application_message(
    public_reference: str,
    student_first: str,
    student_last: str,
    class_applied: str,
) -> str:
    """Notify school admins; trim names/class if the line exceeds the SMS budget."""
    budget = _sms_char_budget()
    fn = _truncate_label(student_first, 28)
    ln = _truncate_label(student_last, 28)
    cl = _truncate_label(class_applied, 24)
    msg = f"New admission {public_reference.strip()}: {fn} {ln} ({cl})"
    if len(msg) <= budget:
        return msg
    return _truncate_label(msg, budget)
