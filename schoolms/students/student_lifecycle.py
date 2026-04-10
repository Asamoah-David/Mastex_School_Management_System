"""
Student exit / reactivation and linked parent account rules.

Parents are deactivated only when they have no remaining active children at the
same school. Reactivation can restore parent login when at least one child is
active again.
"""

from __future__ import annotations

from accounts.models import User


def parent_has_other_active_children_at_school(
    parent: User | None, school, *, exclude_student_pk: int | None = None
) -> bool:
    if not parent:
        return False
    from students.models import Student

    qs = Student.objects.filter(parent=parent, school=school, status="active")
    if exclude_student_pk is not None:
        qs = qs.exclude(pk=exclude_student_pk)
    return qs.exists()


def deactivate_parent_if_no_active_children(
    parent: User | None, school, *, exclude_student_pk: int | None = None
) -> bool:
    """
    Deactivate the parent user when they have no active children left at this school.
    Returns True if the parent account was deactivated by this call.
    """
    if not parent or not parent.is_active:
        return False
    if parent_has_other_active_children_at_school(
        parent, school, exclude_student_pk=exclude_student_pk
    ):
        return False
    parent.is_active = False
    parent.save(update_fields=["is_active"])
    return True


def reactivate_parent_if_has_active_children(parent: User | None, school) -> bool:
    """
    Turn parent login back on when they have at least one active child at the school.
    Returns True if the parent account was reactivated by this call.
    """
    if not parent or parent.is_active:
        return False
    from students.models import Student

    if not Student.objects.filter(
        parent=parent, school=school, status="active"
    ).exists():
        return False
    parent.is_active = True
    parent.save(update_fields=["is_active"])
    return True


def bulk_exit_reason_for_status(status: str) -> str:
    """Map bulk status dropdown to Student.exit_reason codes (match student_exit)."""
    return {
        "graduated": "graduated",
        "withdrawn": "left",
        "dismissed": "expelled",
    }.get(status, "")
