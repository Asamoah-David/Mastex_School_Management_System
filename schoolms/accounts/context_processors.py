"""
Inject role-aware boolean flags into every template context so that
templates can use ``{% if can_manage_finance %}`` instead of fragile
inline ``user.role ==`` checks.
"""

from accounts.permissions import (
    is_super_admin,
    is_school_admin,
    is_staff_member,
    can_manage_school,
    can_create_academic_content,
    can_upload_results,
    can_mark_attendance,
    can_view_reports,
    can_manage_finance,
    can_manage_school_expense_records,
    can_manage_library,
    can_manage_admissions,
    can_manage_health,
    can_manage_inventory,
    can_manage_hostel,
    can_manage_transport,
    can_manage_sports,
    can_manage_clubs,
    can_manage_exam_halls,
    can_manage_id_cards,
    can_view_all_departments,
    can_approve_admissions,
    can_export_data,
    user_can_manage_school,
    user_can_access_services_hub,
)


def _cached_pending_essay_attempt_count(school_pk):
    """Count completed attempts with ungraded essays; short-lived cache."""
    from django.core.cache import cache
    from django.db.models import Count, Q

    from core.utils import pending_essay_attempt_cache_key
    from operations.models import ExamAttempt

    ck = pending_essay_attempt_cache_key(school_pk)
    n = cache.get(ck)
    if n is not None:
        return int(n)
    n = (
        ExamAttempt.objects.filter(is_completed=True, exam__school_id=school_pk)
        .annotate(
            pending_essays=Count(
                "answers",
                filter=Q(
                    answers__question__question_type="essay",
                    answers__teacher_reviewed=False,
                ),
            )
        )
        .filter(pending_essays__gt=0)
        .count()
    )
    cache.set(ck, int(n), 60)
    return int(n)


def role_permissions(request):
    """Add permission booleans to the template context."""
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return {}

    from core.utils import get_school

    pending_essay_queue_count = 0
    if user_can_manage_school(user):
        school = get_school(request)
        if school:
            pending_essay_queue_count = _cached_pending_essay_attempt_count(school.pk)

    return {
        "is_super_admin": is_super_admin(user),
        "is_school_admin": is_school_admin(user),
        "is_staff_member": is_staff_member(user),
        "can_manage_school": can_manage_school(user),
        "can_create_academic_content": can_create_academic_content(user),
        "can_upload_results": can_upload_results(user),
        "can_mark_attendance": can_mark_attendance(user),
        "can_view_reports": can_view_reports(user),
        "can_manage_finance": can_manage_finance(user),
        "can_manage_school_expense_records": can_manage_school_expense_records(user),
        "can_manage_library": can_manage_library(user),
        "can_manage_admissions": can_manage_admissions(user),
        "can_manage_health": can_manage_health(user),
        "can_manage_inventory": can_manage_inventory(user),
        "can_manage_hostel": can_manage_hostel(user),
        "can_manage_transport": can_manage_transport(user),
        "can_manage_sports": can_manage_sports(user),
        "can_manage_clubs": can_manage_clubs(user),
        "can_manage_exam_halls": can_manage_exam_halls(user),
        "can_manage_id_cards": can_manage_id_cards(user),
        "can_view_all_departments": can_view_all_departments(user),
        "can_approve_admissions": can_approve_admissions(user),
        "can_export_data": can_export_data(user),
        "can_access_services_hub": user_can_access_services_hub(user),
        "user_can_manage_school": user_can_manage_school(user),
        "pending_essay_queue_count": pending_essay_queue_count,
    }


def current_datetime(request):
    """Server-local date/time for shell chrome (page meta, print headers)."""
    from django.utils import timezone

    return {"now": timezone.localtime(timezone.now())}
