"""Validation helpers for student absence requests."""

from __future__ import annotations

from datetime import date


def absence_range_end(start: date, end: date | None) -> date:
    return end if end else start


def ranges_overlap(a_start: date, a_end: date, b_start: date, b_end: date) -> bool:
    return a_start <= b_end and b_start <= a_end


def pending_absence_overlaps(student, start: date, end: date, exclude_pk: int | None = None) -> bool:
    """True if another pending request for this student overlaps [start, end] inclusive."""
    from students.models import AbsenceRequest

    qs = AbsenceRequest.objects.filter(student=student, status="pending")
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    for req in qs.only("id", "date", "end_date"):
        r_start = req.date
        r_end = absence_range_end(req.date, req.end_date)
        if ranges_overlap(start, end, r_start, r_end):
            return True
    return False
