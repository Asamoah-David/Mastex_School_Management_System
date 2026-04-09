from __future__ import annotations

from django.contrib import messages
from django.shortcuts import redirect

from core.utils import get_effective_school
from .models import SchoolFeature


DEFAULT_FEATURE_KEYS: tuple[str, ...] = (
    # Existing features
    "hostel",
    "library",
    "inventory",
    "messaging",
    "ai_assistant",
    "finance_admin",
    # Academics
    "exams",
    "homework",
    "quiz",
    "results",
    "timetable",
    "performance_analytics",
    # Admissions & Students
    "admission",
    "student_enrollment",
    # Operations
    "attendance",
    "teacher_attendance",
    "bus_transport",
    "canteen",
    "textbooks",
    "certificates",
    "id_cards",
    "health_records",
    "discipline",
    "school_events",
    "sports",
    "clubs",
    "pt_meetings",
    "alumni",
    "documents",
    "announcements",
    "online_exams",
    # Finance
    "fee_management",
    "online_payments",
    "expenses",
    "budgets",
    # HR
    "staff_management",
    "leave_management",
)


def is_feature_enabled(request, key: str) -> bool:
    school = get_effective_school(request)
    if not school:
        return True

    flags = getattr(request, "_feature_flags_cache", None)
    if flags is None:
        flags = dict(
            SchoolFeature.objects.filter(school=school).values_list("key", "enabled")
        )
        request._feature_flags_cache = flags

    enabled = flags.get(key)
    return True if enabled is None else bool(enabled)


def require_feature(request, key: str, fallback_url_name: str = "home"):
    if is_feature_enabled(request, key):
        return None
    try:
        messages.error(request, "This feature is disabled for your school. Please contact the platform administrator.")
    except Exception:
        pass
    return redirect(fallback_url_name)


def ensure_features_exist(school) -> None:
    existing = set(SchoolFeature.objects.filter(school=school).values_list("key", flat=True))
    missing = [k for k in DEFAULT_FEATURE_KEYS if k not in existing]
    if not missing:
        return
    SchoolFeature.objects.bulk_create([SchoolFeature(school=school, key=k, enabled=True) for k in missing])

