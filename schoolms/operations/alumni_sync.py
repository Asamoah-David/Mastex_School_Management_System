"""Create or update ``Alumni`` rows when students graduate."""

from __future__ import annotations

from django.utils import timezone


def sync_alumni_from_graduated_student(student):
    """
    Idempotent: ensure there is an alumni profile for a graduated student.

    Uses ``(school, student)`` as the natural key when the student row still exists.
    """
    from operations.models import Alumni

    if getattr(student, "status", None) != "graduated":
        return None

    user = getattr(student, "user", None)
    if not user:
        return None

    exit_d = student.exit_date or timezone.now().date()
    gy = exit_d.year
    fn = (getattr(user, "first_name", None) or "").strip() or "Unknown"
    ln = (getattr(user, "last_name", None) or "").strip()

    alumni, _created = Alumni.objects.update_or_create(
        school=student.school,
        student=student,
        defaults={
            "first_name": fn[:100],
            "last_name": ln[:100],
            "admission_number": (student.admission_number or "")[:50],
            "class_name": (student.class_name or "")[:50],
            "school_class": getattr(student, "school_class", None),
            "graduation_year": gy,
            "graduation_date": exit_d,
        },
    )
    return alumni
