"""Shared HR helpers (contract state, etc.)."""

from __future__ import annotations

from django.utils import timezone

from accounts.hr_models import StaffContract


def sync_expired_staff_contracts(*, school=None) -> int:
    """
    Mark active contracts as expired when end_date is before today.
    Returns the number of rows updated.
    """
    today = timezone.localdate()
    qs = StaffContract.objects.filter(
        status="active",
        end_date__isnull=False,
        end_date__lt=today,
    )
    if school is not None:
        qs = qs.filter(school=school)
    return qs.update(status="expired")
