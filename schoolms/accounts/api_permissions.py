"""
DRF permission classes for the Mastex School Management System.

Usage in API views::

    from accounts.api_permissions import IsSchoolStaff, IsSchoolAdmin

    class FeeListView(generics.ListAPIView):
        permission_classes = [IsSchoolStaff]
"""

from rest_framework.permissions import BasePermission
from accounts.permissions import (
    is_super_admin,
    is_school_admin,
    is_staff_member,
    belongs_to_school,
    can_manage_finance,
    can_manage_library,
    can_manage_admissions,
    can_manage_health,
    can_create_academic_content,
    can_upload_results,
    can_export_data,
)


class IsSuperAdmin(BasePermission):
    """Platform super-admin only."""

    def has_permission(self, request, view):
        return bool(request.user and is_super_admin(request.user))


class IsSchoolAdmin(BasePermission):
    """Headteacher / school admin (or super admin)."""

    def has_permission(self, request, view):
        return bool(request.user and (is_super_admin(request.user) or is_school_admin(request.user)))


class IsSchoolStaff(BasePermission):
    """Any staff member belonging to a school (or super admin)."""

    def has_permission(self, request, view):
        return bool(request.user and is_staff_member(request.user))


class IsSchoolMember(BasePermission):
    """Any user belonging to a school — staff, students, or parents."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return is_super_admin(request.user) or bool(getattr(request.user, "school_id", None))


class BelongsToSchool(BasePermission):
    """
    Object-level: the object's ``school`` must match the requesting user's school.
    Falls back to view-level True if the user is a super admin.
    """

    def has_object_permission(self, request, view, obj):
        if is_super_admin(request.user):
            return True
        obj_school = getattr(obj, "school", None) or getattr(obj, "school_id", None)
        if obj_school is None:
            return True
        return belongs_to_school(request.user, obj_school)


class CanManageFinance(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and can_manage_finance(request.user))


class CanManageLibrary(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and can_manage_library(request.user))


class CanManageAdmissions(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and can_manage_admissions(request.user))


class CanManageHealth(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and can_manage_health(request.user))


class CanCreateAcademicContent(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and can_create_academic_content(request.user))


class CanUploadResults(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and can_upload_results(request.user))


class CanExportData(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and can_export_data(request.user))
