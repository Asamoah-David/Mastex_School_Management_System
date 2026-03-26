"""
Role-Based Access Control for Mastex School Management System

School Hierarchy:
- Headteacher / School Admin → Full school management
- Deputy Headteacher → Monitor teachers, view reports, academic oversight
- Head of Department (HOD) → Department management, view department results
- Class Teacher → ONE assigned class - attendance, homework, results for their class
- Subject Teacher → MULTIPLE subjects - results for assigned subjects only
- Administration Staff → Specific department (Finance, Library, Admissions, Health)
- Students → Own data only
- Parents → Children's data only
"""

from functools import wraps


def is_school_admin(user):
    """Headteacher/School Admin - Full management access"""
    if getattr(user, "role", None) == "school_admin":
        return True
    # Check secondary roles
    if hasattr(user, 'secondary_roles'):
        return user.secondary_roles.filter(role__in=("school_admin",)).exists()
    return False


def is_deputy_head(user):
    """Deputy Headteacher - Monitor teachers, view reports"""
    return getattr(user, "role", None) == "deputy_head"


def is_hod(user):
    """Head of Department - Department management"""
    return getattr(user, "role", None) == "hod"


def is_teacher(user):
    """Any teacher role"""
    return getattr(user, "role", None) == "teacher"


def is_class_teacher(user):
    """Class Teacher - Has assigned class"""
    if not is_teacher(user):
        return False
    # Check if user has classes_taught relationship
    if hasattr(user, 'classes_taught'):
        return user.classes_taught.exists()
    return False


def is_subject_teacher(user):
    """Subject Teacher - Has assigned subjects but no class"""
    if not is_teacher(user):
        return False
    if hasattr(user, 'assigned_subjects') and user.assigned_subjects.exists():
        return True
    # Check if no class assigned
    if hasattr(user, 'classes_taught') and not user.classes_taught.exists():
        return True
    return False


def is_admin_staff(user):
    """Administration staff (Accountant, Librarian, Nurse, etc.)"""
    return getattr(user, "role", None) in (
        "accountant", "librarian", "admission_officer",
        "school_nurse", "admin_assistant", "staff"
    )


def is_parent(user):
    """Parent - Access children's data only"""
    return getattr(user, "role", None) == "parent"


def is_student(user):
    """Student - Own data only"""
    return getattr(user, "role", None) == "student"


def is_super_admin(user):
    """Platform Super Admin - Full system access"""
    return getattr(user, "role", None) == "super_admin" or getattr(user, "is_superuser", False)


def can_manage_school(user):
    """
    Can manage school features (create, edit, delete).
    Includes: Headteacher, Deputy, HOD, Class Teachers
    Excludes: Subject Teachers (can only upload own results), Admin Staff
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if is_super_admin(user):
        return True
    if is_school_admin(user):
        return True
    if is_deputy_head(user):
        return True
    if is_hod(user):
        return True
    # Class teachers can manage their class
    if is_class_teacher(user):
        return True
    return False


def can_create_academic_content(user):
    """
    Can create academic content (homework, exams, etc.)
    Includes: Headteacher, Deputy, HOD, Teachers with subjects
    Excludes: Admin staff, Class-only teachers
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if is_super_admin(user):
        return True
    if is_school_admin(user):
        return True
    if is_deputy_head(user):
        return True
    if is_hod(user):
        return True
    # Subject teachers can create for their subjects
    if is_subject_teacher(user):
        return True
    # Class teachers can create homework for their class
    if is_class_teacher(user):
        return True
    return False


def can_upload_results(user):
    """
    Can upload student results.
    Subject teachers: own subjects only
    Class teachers: own class only
    Admins: all
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if is_super_admin(user) or is_school_admin(user) or is_deputy_head(user) or is_hod(user):
        return True
    if is_teacher(user):
        # Teachers can upload results for their assigned subjects or class
        if hasattr(user, 'assigned_subjects') and user.assigned_subjects.exists():
            return True
        if is_class_teacher(user):
            return True
    return False


def can_mark_attendance(user):
    """
    Can mark student attendance.
    Class teachers: their class only
    Subject teachers: their classes
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if is_super_admin(user) or is_school_admin(user):
        return True
    if is_deputy_head(user):
        return True
    if is_teacher(user):
        return True
    return False


def can_view_reports(user):
    """
    Can view academic reports and analytics.
    Includes: All academic staff + Admin staff (for monitoring)
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if is_super_admin(user) or is_school_admin(user):
        return True
    if is_deputy_head(user):
        return True
    if is_hod(user):
        return True
    if is_teacher(user):
        return True
    if is_admin_staff(user):
        return True  # Admin can monitor academic performance
    return False


def can_manage_finance(user):
    """Can manage finances - Accountant, Bursar, Headteacher"""
    if not getattr(user, "is_authenticated", False):
        return False
    if is_super_admin(user) or is_school_admin(user):
        return True
    if getattr(user, "role", None) in ("accountant",):
        return True
    return False


def can_manage_library(user):
    """Can manage library - Librarian, Headteacher"""
    if not getattr(user, "is_authenticated", False):
        return False
    if is_super_admin(user) or is_school_admin(user):
        return True
    if getattr(user, "role", None) in ("librarian",):
        return True
    return False


def can_manage_admissions(user):
    """Can manage admissions - Admission Officer, Headteacher"""
    if not getattr(user, "is_authenticated", False):
        return False
    if is_super_admin(user) or is_school_admin(user):
        return True
    if getattr(user, "role", None) in ("admission_officer",):
        return True
    return False


def can_manage_health(user):
    """Can manage health records - School Nurse, Headteacher"""
    if not getattr(user, "is_authenticated", False):
        return False
    if is_super_admin(user) or is_school_admin(user):
        return True
    if getattr(user, "role", None) in ("school_nurse",):
        return True
    return False


def can_manage_inventory(user):
    """Can manage inventory - Admin Assistant, Headteacher"""
    if not getattr(user, "is_authenticated", False):
        return False
    if is_super_admin(user) or is_school_admin(user):
        return True
    if getattr(user, "role", None) in ("admin_assistant",):
        return True
    return False


def user_can_manage_school(user):
    """
    Legacy function - for backward compatibility.
    Treats teachers as school managers.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if is_super_admin(user):
        return True
    return getattr(user, "role", None) in (
        "school_admin", "deputy_head", "hod",
        "teacher", "accountant", "librarian",
        "admission_officer", "school_nurse", "admin_assistant", "staff"
    ) and bool(getattr(user, "school_id", None))


def can_manage_hostel(user):
    """Can manage hostel - Admin Assistant, Headteacher, Deputy"""
    if not getattr(user, "is_authenticated", False):
        return False
    if is_super_admin(user) or is_school_admin(user):
        return True
    if is_deputy_head(user):
        return True
    if getattr(user, "role", None) in ("admin_assistant",):
        return True
    return False


def can_manage_transport(user):
    """Can manage transport/bus - Admin Assistant, Headteacher"""
    if not getattr(user, "is_authenticated", False):
        return False
    if is_super_admin(user) or is_school_admin(user):
        return True
    if is_deputy_head(user):
        return True
    if getattr(user, "role", None) in ("admin_assistant",):
        return True
    return False


def can_manage_sports(user):
    """Can manage sports activities - PE Teacher, Headteacher"""
    if not getattr(user, "is_authenticated", False):
        return False
    if is_super_admin(user) or is_school_admin(user):
        return True
    if is_deputy_head(user):
        return True
    if is_hod(user):
        return True
    # Teachers can manage sports if assigned
    if is_teacher(user):
        return True
    return False


def can_manage_clubs(user):
    """Can manage clubs and activities - Teachers, Headteacher"""
    if not getattr(user, "is_authenticated", False):
        return False
    if is_super_admin(user) or is_school_admin(user):
        return True
    if is_deputy_head(user):
        return True
    if is_hod(user):
        return True
    if is_teacher(user):
        return True
    return False


def can_manage_exam_halls(user):
    """Can manage exam halls and seating plans - Admin, Deputy, HOD"""
    if not getattr(user, "is_authenticated", False):
        return False
    if is_super_admin(user) or is_school_admin(user):
        return True
    if is_deputy_head(user):
        return True
    if is_hod(user):
        return True
    return False


def can_manage_id_cards(user):
    """Can manage ID cards - Admin Assistant, Admission Officer, Headteacher"""
    if not getattr(user, "is_authenticated", False):
        return False
    if is_super_admin(user) or is_school_admin(user):
        return True
    if is_deputy_head(user):
        return True
    if getattr(user, "role", None) in ("admin_assistant", "admission_officer"):
        return True
    return False


def can_view_all_departments(user):
    """Can view all department data - School Admin, Deputy Head"""
    if not getattr(user, "is_authenticated", False):
        return False
    if is_super_admin(user) or is_school_admin(user):
        return True
    if is_deputy_head(user):
        return True
    return False


def can_approve_admissions(user):
    """Can approve admission applications - School Admin, Admission Officer"""
    if not getattr(user, "is_authenticated", False):
        return False
    if is_super_admin(user) or is_school_admin(user):
        return True
    if getattr(user, "role", None) in ("admission_officer",):
        return True
    return False
