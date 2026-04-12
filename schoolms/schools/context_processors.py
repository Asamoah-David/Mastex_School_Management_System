"""Per-request school feature flags for templates (nav visibility)."""

from schools.features import DEFAULT_FEATURE_KEYS, is_feature_enabled


def school_feature_flags(request):
    if not getattr(request.user, "is_authenticated", False):
        return {}
    return {f"feature_{key}": is_feature_enabled(request, key) for key in DEFAULT_FEATURE_KEYS}
