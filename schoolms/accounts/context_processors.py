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
)


def role_permissions(request):
    """Add permission booleans to the template context."""
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return {}

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
    }
