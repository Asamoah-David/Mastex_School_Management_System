"""
Shared helpers for the students app.

The canonical way to look up a parent's children is via
``get_children_for_parent()`` which merges the legacy ``Student.parent`` FK
*and* the ``StudentGuardian`` through-table into a single de-duplicated
queryset.
"""

from __future__ import annotations

from django.db.models import QuerySet


def get_children_for_parent(user, *, school=None, active_only: bool = True) -> QuerySet:
    """Return students linked to *user* via legacy FK or StudentGuardian.

    Parameters
    ----------
    user : User
        A parent user instance.
    school : School | None
        When supplied, restrict to this school.
    active_only : bool
        When *True* (default), only return students with ``status='active'``.

    Returns
    -------
    QuerySet[Student]
        De-duplicated, ordered queryset.
    """
    from students.models import Student, StudentGuardian

    if getattr(user, "role", None) != "parent":
        return Student.objects.none()

    legacy_ids = set(
        Student.objects.filter(parent=user).values_list("id", flat=True)
    )
    guardian_ids = set(
        StudentGuardian.objects.filter(guardian=user).values_list("student_id", flat=True)
    )
    all_ids = legacy_ids | guardian_ids
    if not all_ids:
        return Student.objects.none()

    qs = Student.objects.filter(pk__in=all_ids).select_related("user", "school")
    if school:
        qs = qs.filter(school=school)
    if active_only:
        qs = qs.filter(status="active")
    return qs.order_by("class_name", "admission_number")


def parent_is_guardian_of(user, student) -> bool:
    """Return True if *user* is linked to *student* via legacy FK or StudentGuardian."""
    from students.models import StudentGuardian

    if student.parent_id == user.pk:
        return True
    return StudentGuardian.objects.filter(guardian=user, student=student).exists()
