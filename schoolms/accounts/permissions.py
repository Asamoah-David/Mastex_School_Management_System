def is_school_admin(user):
    return getattr(user, "role", None) in ("admin", "school_admin")


def is_teacher(user):
    return getattr(user, "role", None) == "teacher"


def is_parent(user):
    return getattr(user, "role", None) == "parent"


def user_can_manage_school(user):
    """
    Central permission helper used across apps.

    A user can manage a school if:
    - They are a platform superuser / super_admin, OR
    - They are a school-scoped role (admin, school_admin, teacher, staff)
      and are attached to a school.
    """
    if not getattr(user, "is_authenticated", False):
        return False

    # Platform-level admin
    if getattr(user, "is_superuser", False) or getattr(user, "is_super_admin", False):
        return True

    return getattr(user, "role", None) in ("admin", "school_admin", "teacher", "staff") and bool(
        getattr(user, "school_id", None)
    )