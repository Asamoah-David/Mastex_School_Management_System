"""
Role-Based Access Control for Mastex School Management System
==============================================================

Role Hierarchy (highest → lowest):
    super_admin          Platform owner — unrestricted
    school_admin         Headteacher — full school management
    deputy_head          Deputy — academic & operational oversight
    hod                  Head of Department — department scope
    teacher              Class/Subject teacher — classroom scope
    accountant           Finance management
    librarian            Library management
    admission_officer    Admissions management
    school_nurse         Health records
    admin_assistant      General admin / inventory / hostel / transport
    staff                Generic staff — limited access
    student              Own data only
    parent               Children's data only

Every capability function follows the pattern:
    1. Deny unauthenticated users.
    2. Allow super_admin unconditionally.
    3. Check primary role **and** secondary roles via ``has_role()``.

School scoping is orthogonal — it is enforced by decorators and middleware,
*not* inside these predicate functions (they only answer "does the user have
this capability?").
"""

from accounts.models import STAFF_ROLES, MANAGEMENT_ROLES, ACADEMIC_ROLES

# ---------------------------------------------------------------------------
#  Tier constants — exported for use in decorators, templates, and views
# ---------------------------------------------------------------------------

PLATFORM_ROLES = ("super_admin",)

SCHOOL_MANAGEMENT_ROLES = MANAGEMENT_ROLES  # school_admin, deputy_head, hod

TEACHING_ROLES = ACADEMIC_ROLES  # school_admin, deputy_head, hod, teacher

ALL_STAFF_ROLES = STAFF_ROLES

PORTAL_ROLES = ("student", "parent")

# ---------------------------------------------------------------------------
#  Low-level role predicates
# ---------------------------------------------------------------------------

def _has(user, role_value):
    """Check primary **or** secondary role."""
    if hasattr(user, "has_role"):
        return user.has_role(role_value)
    return getattr(user, "role", None) == role_value


def _has_any(user, *role_values):
    """Return True if the user holds **any** of the listed roles."""
    return any(_has(user, r) for r in role_values)


def _is_authenticated(user):
    return getattr(user, "is_authenticated", False)


# ---------------------------------------------------------------------------
#  Identity predicates
# ---------------------------------------------------------------------------

def is_super_admin(user):
    """Platform Super Admin — full system access."""
    return _is_authenticated(user) and (
        getattr(user, "is_superuser", False) or _has(user, "super_admin")
    )


def is_school_admin(user):
    """Headteacher / School Admin — full school management."""
    return _is_authenticated(user) and _has(user, "school_admin")


def is_school_leadership(user):
    """
    School-level executive roles: headteacher, deputy head, HOD.
    Use for ERP actions where authority should be delegated beyond the headteacher alone.
    Platform super-admins and Django superusers are included.
    """
    if not _is_authenticated(user):
        return False
    if is_super_admin(user) or getattr(user, "is_superuser", False):
        return True
    return _has_any(user, "school_admin", "deputy_head", "hod")


def is_deputy_head(user):
    return _is_authenticated(user) and _has(user, "deputy_head")


def is_hod(user):
    return _is_authenticated(user) and _has(user, "hod")


def is_teacher(user):
    return _is_authenticated(user) and _has(user, "teacher")


def is_class_teacher(user):
    if not is_teacher(user):
        return False
    return hasattr(user, "classes_taught") and user.classes_taught.exists()


def is_subject_teacher(user):
    if not is_teacher(user):
        return False
    return hasattr(user, "assigned_subjects") and user.assigned_subjects.exists()


def is_admin_staff(user):
    """Non-teaching admin staff (accountant, librarian, nurse …)."""
    return _is_authenticated(user) and _has_any(
        user, "accountant", "librarian", "admission_officer",
        "school_nurse", "admin_assistant", "staff",
    )


def is_parent(user):
    return _is_authenticated(user) and _has(user, "parent")


def is_student(user):
    return _is_authenticated(user) and _has(user, "student")


def has_school_wide_class_scope(user):
    """
    May act on any class in the school (attendance pickers, school-wide result snippets).

    Super admins / superusers, head, deputy, and HOD (primary or secondary role).
    """
    if not _is_authenticated(user):
        return False
    if is_super_admin(user):
        return True
    if getattr(user, "is_superuser", False):
        return True
    return _has_any(user, "school_admin", "deputy_head", "hod")


def is_staff_member(user):
    """Any school staff (teaching + admin)."""
    return _is_authenticated(user) and (
        is_super_admin(user) or _has_any(user, *ALL_STAFF_ROLES)
    )


# ---------------------------------------------------------------------------
#  Capability predicates
# ---------------------------------------------------------------------------

def can_manage_school(user):
    """
    Can perform school-wide CRUD — Headteacher, Deputy, HOD, class teachers.
    Does NOT include admin-only staff (accountant, nurse, etc.).
    """
    if not _is_authenticated(user):
        return False
    if is_super_admin(user):
        return True
    return _has_any(user, "school_admin", "deputy_head", "hod") or is_class_teacher(user)


def user_can_manage_school(user):
    """
    Legacy wide-net helper kept for backward compatibility.
    Returns True for any staff member attached to a school.
    Prefer the narrower ``can_manage_school`` for new code.
    """
    if not _is_authenticated(user):
        return False
    if is_super_admin(user):
        return True
    return _has_any(user, *ALL_STAFF_ROLES) and bool(getattr(user, "school_id", None))


def can_manage_school_programming(user):
    """
    Academic calendar entries, school-wide events, and PT meeting schedules.
    Same role set as ``is_school_leadership``.
    """
    return is_school_leadership(user)


def can_bulk_promote_students(user):
    """
    Whole-class cohort actions: promote all active students to another class_name,
    or graduate an entire class. Restricted to senior leadership — not general staff
    or class teachers alone.
    """
    if not _is_authenticated(user):
        return False
    return is_school_leadership(user)


# --- Academic content -------------------------------------------------

def can_create_academic_content(user):
    """Create homework, exams, online meetings, etc."""
    if not _is_authenticated(user):
        return False
    if is_super_admin(user):
        return True
    return _has_any(user, *TEACHING_ROLES)


def can_upload_results(user):
    """Upload / edit student results."""
    if not _is_authenticated(user):
        return False
    if is_super_admin(user):
        return True
    if _has_any(user, "school_admin", "deputy_head", "hod"):
        return True
    if is_teacher(user):
        return (
            (hasattr(user, "assigned_subjects") and user.assigned_subjects.exists())
            or is_class_teacher(user)
        )
    return False


def can_mark_attendance(user):
    if not _is_authenticated(user):
        return False
    if is_super_admin(user):
        return True
    return _has_any(user, "school_admin", "deputy_head", "hod", "teacher")


def can_view_reports(user):
    """View academic analytics / reports."""
    if not _is_authenticated(user):
        return False
    if is_super_admin(user):
        return True
    return _has_any(user, *ALL_STAFF_ROLES)


# --- Department-specific capabilities --------------------------------

def can_review_absence_requests(user):
    """Approve or reject student absence — leadership and class teachers (not e.g. librarian-only)."""
    if not _is_authenticated(user):
        return False
    if is_super_admin(user) or getattr(user, "is_superuser", False):
        return True
    return can_manage_school(user)


def can_review_staff_leave(user):
    """Approve or reject staff leave — leadership roles."""
    if not _is_authenticated(user):
        return False
    if is_super_admin(user) or getattr(user, "is_superuser", False):
        return True
    return _has_any(user, "school_admin", "deputy_head", "hod")


def can_access_staff_leave_portal(user):
    """Submit and track own leave — any school staff with a linked school."""
    if not _is_authenticated(user) or not getattr(user, "school_id", None):
        return False
    if _has(user, "student") or _has(user, "parent"):
        return False
    return is_staff_member(user)


def can_manage_finance(user):
    if not _is_authenticated(user):
        return False
    if is_super_admin(user) or is_school_leadership(user):
        return True
    return _has(user, "accountant")


def can_manage_school_expense_records(user):
    """
    ERP: post and adjust payables — expenses, budgets, expense categories.
    Headteacher / accountant / platform admin; not general teaching staff.
    """
    if not _is_authenticated(user):
        return False
    if getattr(user, "is_superuser", False) or is_super_admin(user):
        return True
    return can_manage_finance(user)


def can_manage_library(user):
    if not _is_authenticated(user):
        return False
    if is_super_admin(user) or is_school_leadership(user):
        return True
    return _has(user, "librarian")


def can_manage_admissions(user):
    if not _is_authenticated(user):
        return False
    if is_super_admin(user) or is_school_leadership(user):
        return True
    return _has(user, "admission_officer")


def can_manage_health(user):
    if not _is_authenticated(user):
        return False
    if is_super_admin(user) or is_school_leadership(user):
        return True
    return _has(user, "school_nurse")


def can_manage_inventory(user):
    if not _is_authenticated(user):
        return False
    if is_super_admin(user) or is_school_leadership(user):
        return True
    return _has(user, "admin_assistant")


def can_manage_hostel(user):
    if not _is_authenticated(user):
        return False
    if is_super_admin(user) or is_school_leadership(user):
        return True
    return _has(user, "admin_assistant")


def can_manage_transport(user):
    if not _is_authenticated(user):
        return False
    if is_super_admin(user) or is_school_leadership(user):
        return True
    return _has(user, "admin_assistant")


def user_can_access_services_hub(user):
    """
    Staff hub for canteen, transport, textbooks, hostel, library, and school fees.
    Excludes parent/student portal roles.
    """
    if not _is_authenticated(user):
        return False
    if is_super_admin(user) or getattr(user, "is_superuser", False):
        return True
    return bool(
        user_can_manage_school(user)
        or can_manage_finance(user)
        or can_manage_library(user)
        or can_manage_hostel(user)
        or can_manage_transport(user)
        or can_manage_inventory(user)
    )


def can_manage_sports(user):
    if not _is_authenticated(user):
        return False
    if is_super_admin(user):
        return True
    return _has_any(user, "school_admin", "deputy_head", "hod", "teacher")


def can_manage_clubs(user):
    if not _is_authenticated(user):
        return False
    if is_super_admin(user):
        return True
    return _has_any(user, "school_admin", "deputy_head", "hod", "teacher")


def can_manage_exam_halls(user):
    if not _is_authenticated(user):
        return False
    if is_super_admin(user):
        return True
    return _has_any(user, "school_admin", "deputy_head", "hod")


def can_manage_id_cards(user):
    if not _is_authenticated(user):
        return False
    if is_super_admin(user) or is_school_leadership(user):
        return True
    return _has_any(user, "admin_assistant", "admission_officer")


def can_view_all_departments(user):
    if not _is_authenticated(user):
        return False
    if is_super_admin(user):
        return True
    return is_school_leadership(user)


def can_approve_admissions(user):
    if not _is_authenticated(user):
        return False
    if is_super_admin(user) or is_school_leadership(user):
        return True
    return _has(user, "admission_officer")


def can_export_data(user):
    """Can export school data (CSV, Excel, PDF)."""
    if not _is_authenticated(user):
        return False
    if is_super_admin(user):
        return True
    return _has_any(user, *SCHOOL_MANAGEMENT_ROLES, "accountant")


def can_access_school_dashboard(user):
    """
    Staff dashboard at /accounts/school-dashboard/.
    Any primary or secondary staff role attached to a school may enter.
    Superusers and platform super_admin use the platform dashboard instead.
    """
    if not _is_authenticated(user):
        return False
    if getattr(user, "is_superuser", False) or _has(user, "super_admin"):
        return True
    if not getattr(user, "school_id", None):
        return False
    return _has_any(user, *ALL_STAFF_ROLES)


# ---------------------------------------------------------------------------
#  School scoping helpers
# ---------------------------------------------------------------------------

def get_user_school(user):
    """Return the user's school or None. Safe for unauthenticated users."""
    if not _is_authenticated(user):
        return None
    return getattr(user, "school", None)


def belongs_to_school(user, school):
    """True if the user belongs to the given school (or is a super admin)."""
    if is_super_admin(user):
        return True
    user_school = get_user_school(user)
    if user_school is None or school is None:
        return False
    return user_school.pk == (school.pk if hasattr(school, "pk") else school)
