"""Per-request school feature flags for templates (nav visibility)."""

from schools.features import is_feature_enabled


def school_feature_flags(request):
    if not getattr(request.user, "is_authenticated", False):
        return {}
    return {
        "feature_academic_calendar": is_feature_enabled(request, "academic_calendar"),
        "feature_school_events": is_feature_enabled(request, "school_events"),
        "feature_pt_meetings": is_feature_enabled(request, "pt_meetings"),
        "feature_sports": is_feature_enabled(request, "sports"),
        "feature_clubs": is_feature_enabled(request, "clubs"),
    }
