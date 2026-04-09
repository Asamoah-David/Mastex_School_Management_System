"""
Reusable view decorators for role-based access control.

All decorators:
    - Redirect to ``login`` if unauthenticated.
    - Always allow ``is_superuser``.
    - Respect both primary and secondary roles via ``has_role()``.
    - Show a user-friendly error and redirect to ``home`` on denial.
"""

from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


# ---------------------------------------------------------------------------
#  Core primitives
# ---------------------------------------------------------------------------

def login_required(view_func):
    """Redirect to login page if the user is not authenticated."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        return view_func(request, *args, **kwargs)
    return wrapper


def _deny(request, msg="You do not have permission to access this page."):
    messages.error(request, msg)
    return redirect("home")


# ---------------------------------------------------------------------------
#  Generic role / permission decorators
# ---------------------------------------------------------------------------

def role_required(*allowed_roles):
    """
    Allow access if the user holds **any** of *allowed_roles* as a primary
    **or** secondary role, or is a superuser.

    Usage::

        @role_required("school_admin", "deputy_head")
        def my_view(request): ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("login")
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            user = request.user
            if hasattr(user, "has_role"):
                if any(user.has_role(r) for r in allowed_roles):
                    return view_func(request, *args, **kwargs)
            elif getattr(user, "role", None) in allowed_roles:
                return view_func(request, *args, **kwargs)
            return _deny(request)
        return wrapper
    return decorator


def permission_required(perm_func):
    """
    Allow access if *perm_func(request.user)* returns True.

    Usage::

        from accounts.permissions import can_manage_finance
        @permission_required(can_manage_finance)
        def fee_list(request): ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("login")
            if perm_func(request.user):
                return view_func(request, *args, **kwargs)
            return _deny(request)
        return wrapper
    return decorator


def school_scoped(view_func):
    """
    Require that the authenticated user belongs to a school.
    Superusers bypass the check (they operate across schools).
    Sets ``request.current_school`` for convenience.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        if request.user.is_superuser:
            request.current_school = getattr(request, "school", None) or getattr(request.user, "school", None)
            return view_func(request, *args, **kwargs)
        school = getattr(request.user, "school", None)
        if not school:
            messages.error(request, "Your account is not associated with a school.")
            return redirect("home")
        request.current_school = school
        return view_func(request, *args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
#  Convenience shortcuts (use permission_required for new code)
# ---------------------------------------------------------------------------

def admin_required(view_func):
    """School admin, deputy head, or superuser."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        from .permissions import _has_any
        if _has_any(request.user, "school_admin", "deputy_head"):
            return view_func(request, *args, **kwargs)
        return _deny(request)
    return wrapper


def teacher_required(view_func):
    """Any academic role (admin, deputy, hod, teacher) or superuser."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        from .permissions import TEACHING_ROLES, _has_any
        if _has_any(request.user, *TEACHING_ROLES):
            return view_func(request, *args, **kwargs)
        return _deny(request)
    return wrapper


def school_required(view_func):
    """Alias for ``school_scoped``."""
    return school_scoped(view_func)


def finance_required(view_func):
    return permission_required(
        __import__("accounts.permissions", fromlist=["can_manage_finance"]).can_manage_finance
    )(view_func)


def library_required(view_func):
    return permission_required(
        __import__("accounts.permissions", fromlist=["can_manage_library"]).can_manage_library
    )(view_func)


def health_required(view_func):
    return permission_required(
        __import__("accounts.permissions", fromlist=["can_manage_health"]).can_manage_health
    )(view_func)


def admissions_required(view_func):
    return permission_required(
        __import__("accounts.permissions", fromlist=["can_manage_admissions"]).can_manage_admissions
    )(view_func)


def hostel_required(view_func):
    return permission_required(
        __import__("accounts.permissions", fromlist=["can_manage_hostel"]).can_manage_hostel
    )(view_func)


def academic_required(view_func):
    return permission_required(
        __import__("accounts.permissions", fromlist=["can_create_academic_content"]).can_create_academic_content
    )(view_func)


def results_upload_required(view_func):
    return permission_required(
        __import__("accounts.permissions", fromlist=["can_upload_results"]).can_upload_results
    )(view_func)


def student_required(view_func):
    """Student or parent."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        from .permissions import _has_any
        if _has_any(request.user, "student", "parent"):
            return view_func(request, *args, **kwargs)
        return _deny(request, "You must be a student or parent to access this page.")
    return wrapper


def parent_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        from .permissions import _has
        if _has(request.user, "parent"):
            return view_func(request, *args, **kwargs)
        return _deny(request, "You must be a parent to access this page.")
    return wrapper
