"""Shared subscription / grace-period rules for middleware and UI."""
from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone


def subscription_grace_days_for_school(school) -> int:
    if school is None:
        return int(getattr(settings, "SUBSCRIPTION_DEFAULT_GRACE_DAYS", 7))
    gd = getattr(school, "subscription_grace_days", None)
    if gd is not None:
        return int(gd)
    return int(getattr(settings, "SUBSCRIPTION_DEFAULT_GRACE_DAYS", 7))


def subscription_hard_block_applies(school, now=None) -> bool:
    """
    True when the school should see the subscription expired / locked screen.
    Cancelled always blocks. Otherwise block only after subscription_end_date + grace.
    """
    if school is None:
        return False
    now = now or timezone.now()
    if getattr(school, "subscription_status", None) == "cancelled":
        return True
    end = school.subscription_end_date
    if not end:
        return getattr(school, "subscription_status", None) == "expired"
    grace = subscription_grace_days_for_school(school)
    return now > end + timedelta(days=grace)


def subscription_in_grace_period(school, now=None) -> bool:
    """Past end date but still within grace (full access, banner only)."""
    if school is None or not school.subscription_end_date:
        return False
    now = now or timezone.now()
    end = school.subscription_end_date
    if now <= end:
        return False
    grace = subscription_grace_days_for_school(school)
    return end < now <= end + timedelta(days=grace)


def maybe_update_subscription_status_from_dates(school, now=None) -> None:
    """
    Move active/trial schools to expired only after grace has fully elapsed.
    """
    from schools.models import School

    if school is None or not school.pk:
        return
    now = now or timezone.now()
    end = school.subscription_end_date
    if not end:
        return
    grace = subscription_grace_days_for_school(school)
    if now <= end + timedelta(days=grace):
        return
    st = getattr(school, "subscription_status", None)
    if st in ("active", "trial"):
        School.objects.filter(pk=school.pk).update(subscription_status="expired")
        school.subscription_status = "expired"
