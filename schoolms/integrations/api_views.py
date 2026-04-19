from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import (
    can_access_staff_leave_portal,
    can_manage_finance,
    can_review_staff_leave,
    is_school_leadership,
    is_super_admin,
    user_can_manage_school,
)
from integrations.serializers import ExpenseSerializer, MeSerializer, StaffLeaveSerializer
from operations.models import Expense, StaffLeave


class MeAPIView(APIView):
    """Current user and school context (JWT or session)."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={200: MeSerializer})
    def get(self, request):
        u = request.user
        school = getattr(u, "school", None)
        return Response(
            MeSerializer(
                {
                    "id": u.pk,
                    "username": u.username,
                    "email": u.email or "",
                    "role": getattr(u, "role", "") or "",
                    "school": school,
                }
            ).data
        )


@extend_schema(responses={200: StaffLeaveSerializer(many=True)})
class StaffLeaveListAPIView(generics.ListAPIView):
    """Staff leave requests for the user’s school (own rows, or all if reviewer)."""

    serializer_class = StaffLeaveSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not can_access_staff_leave_portal(user):
            raise PermissionDenied("You do not have access to the staff leave portal.")
        school = getattr(user, "school", None)
        if not school:
            raise PermissionDenied("No school is linked to your account.")
        base = StaffLeave.objects.filter(school=school).select_related("staff", "reviewed_by")
        if can_review_staff_leave(user):
            return base.order_by("-start_date", "-created_at")
        return base.filter(staff=user).order_by("-start_date", "-created_at")


@extend_schema(responses={200: ExpenseSerializer(many=True)})
class ExpenseListAPIView(generics.ListAPIView):
    """School expenses — same access as the expenses list (school staff with a linked school)."""

    serializer_class = ExpenseSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not user_can_manage_school(user):
            raise PermissionDenied("You do not have permission to view school expenses.")
        school = getattr(user, "school", None)
        if not school:
            raise PermissionDenied("No school is linked to your account.")
        return (
            Expense.objects.filter(school=school)
            .select_related("category", "recorded_by", "approved_by")
            .order_by("-expense_date", "-id")
        )


class TodayAttendanceSummaryAPIView(APIView):
    """Present / absent / late / excused counts for today (leadership, finance, or platform admin)."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses={
            200: {
                "type": "object",
                "properties": {
                    "date": {"type": "string"},
                    "present": {"type": "integer"},
                    "absent": {"type": "integer"},
                    "late": {"type": "integer"},
                    "excused": {"type": "integer"},
                },
            }
        }
    )
    def get(self, request):
        from django.db.models import Count, Q

        from operations.models import StudentAttendance

        user = request.user
        if not (
            getattr(user, "is_superuser", False)
            or is_super_admin(user)
            or is_school_leadership(user)
            or can_manage_finance(user)
        ):
            return Response({"detail": "Forbidden."}, status=403)
        school = getattr(user, "school", None)
        if not school:
            return Response({"detail": "No school context."}, status=400)
        today = timezone.localdate()
        agg = StudentAttendance.objects.filter(school=school, date=today).aggregate(
            present=Count("id", filter=Q(status="present")),
            absent=Count("id", filter=Q(status="absent")),
            late=Count("id", filter=Q(status="late")),
            excused=Count("id", filter=Q(status="excused")),
        )
        return Response({"date": str(today), **agg})
