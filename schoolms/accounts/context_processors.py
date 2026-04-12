"""
Inject role-aware boolean flags into every template context so that
templates can use ``{% if can_manage_finance %}`` instead of fragile
inline ``user.role ==`` checks.
"""

from accounts.permissions import (
    is_super_admin,
    is_school_admin,
    is_school_leadership,
    is_staff_member,
    is_student,
    is_parent,
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
    can_review_absence_requests,
    can_review_staff_leave,
    can_access_staff_leave_portal,
    can_manage_school_programming,
)


def _nav_staff_profile(user):
    """
    Which staff sidebar to show. Uses User.has_role (primary + secondary).
    None for portal users (student/parent) and unauthenticated users.
    """
    if not getattr(user, "is_authenticated", False):
        return None
    if is_super_admin(user):
        return None
    if is_school_leadership(user):
        return "leadership"
    if hasattr(user, "has_role"):
        for key in (
            "accountant",
            "librarian",
            "admission_officer",
            "school_nurse",
            "admin_assistant",
        ):
            if user.has_role(key):
                return key
        if user.has_role("teacher"):
            return "teacher"
        if user.has_role("staff"):
            return "staff"
    return None


def _nav_portal_profile(user, staff_prof):
    """student / parent sidebar when not in staff ERP nav."""
    if staff_prof is not None or not getattr(user, "is_authenticated", False):
        return None
    if is_super_admin(user):
        return None
    if is_student(user):
        return "student"
    if is_parent(user):
        return "parent"
    return None


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
    from datetime import timedelta

    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return {}

    from core.utils import get_school

    pending_essay_queue_count = 0
    school = get_school(request) if getattr(user, "is_authenticated", False) else None
    if user_can_manage_school(user):
        if school:
            pending_essay_queue_count = _cached_pending_essay_attempt_count(school.pk)

    nav_staff_profile = _nav_staff_profile(user)
    nav_portal_profile = _nav_portal_profile(user, nav_staff_profile)

    subscription_banner = None
    if school and getattr(user, "is_authenticated", False) and not is_super_admin(user):
        from django.conf import settings
        from django.utils import timezone as dj_tz

        if getattr(school, "subscription_status", None) == "cancelled":
            subscription_banner = {
                "level": "error",
                "text": "This school's subscription was cancelled. Some actions may be limited until billing is restored.",
            }
        elif school.subscription_end_date:
            end = school.subscription_end_date
            grace_days = getattr(school, "subscription_grace_days", None)
            if grace_days is None:
                grace_days = int(getattr(settings, "SUBSCRIPTION_DEFAULT_GRACE_DAYS", 7))
            now = dj_tz.now()
            if now > end:
                grace_end = end + timedelta(days=grace_days)
                if now <= grace_end:
                    subscription_banner = {
                        "level": "warning",
                        "text": f"Your subscription ended on {end.date()}. You are in a grace period until {grace_end.date()}. Renew soon to avoid interruption.",
                    }

    return {
        "is_super_admin": is_super_admin(user),
        "is_school_admin": is_school_admin(user),
        "is_school_leadership": is_school_leadership(user),
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
        "can_review_absence_requests": can_review_absence_requests(user),
        "can_review_staff_leave": can_review_staff_leave(user),
        "can_access_staff_leave_portal": can_access_staff_leave_portal(user),
        "can_manage_school_programming": can_manage_school_programming(user),
        "pending_essay_queue_count": pending_essay_queue_count,
        "nav_staff_profile": nav_staff_profile,
        "nav_portal_profile": nav_portal_profile,
        "subscription_banner": subscription_banner,
        "show_setup_checklist": (
            getattr(user, "is_authenticated", False)
            and is_staff_member(user)
            and getattr(user, "school_id", None)
            and not getattr(user, "setup_checklist_dismissed", False)
        ),
    }


def current_datetime(request):
    """Server-local date/time for shell chrome (page meta, print headers)."""
    from django.utils import timezone

    return {"now": timezone.localtime(timezone.now())}
