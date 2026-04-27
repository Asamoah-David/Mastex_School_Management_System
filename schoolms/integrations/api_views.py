from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import generics, permissions, serializers as drf_serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from rest_framework_simplejwt.tokens import RefreshToken

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


# ---------------------------------------------------------------------------
# Per-school / per-tenant throttle (Fix #20)
# ---------------------------------------------------------------------------

class SchoolScopedThrottle(UserRateThrottle):
    """200 requests/minute per authenticated user.  Override via DRF THROTTLE_RATES."""
    rate = "200/min"
    scope = "school_api"

    def get_cache_key(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return None
        school_id = getattr(getattr(user, "school", None), "pk", "none")
        return f"throttle_school_{school_id}_user_{user.pk}"


def _require_school(user):
    school = getattr(user, "school", None)
    if not school:
        raise PermissionDenied("No school is linked to your account.")
    return school


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


# ---------------------------------------------------------------------------
# Fix #22 — JWT Logout / token blacklist endpoint
# ---------------------------------------------------------------------------

class JWTLogoutAPIView(APIView):
    """Blacklist a refresh token on logout so it cannot be reused."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"detail": "Refresh token required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({"detail": "Token blacklisted. Logged out."}, status=status.HTTP_205_RESET_CONTENT)
        except (TokenError, InvalidToken) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Fix #19 — Students API
# ---------------------------------------------------------------------------

class StudentListAPIView(APIView):
    """List students for the authenticated user's school."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [SchoolScopedThrottle]

    def get(self, request):
        from students.models import Student
        user = request.user
        school = _require_school(user)
        if not (user_can_manage_school(user) or getattr(user, "is_superuser", False)):
            raise PermissionDenied("Staff or admin access required.")

        qs = (
            Student.objects.filter(school=school, status="active")
            .select_related("user", "school_class")
            .order_by("user__last_name", "user__first_name")
        )
        class_filter = request.query_params.get("class")
        if class_filter:
            qs = qs.filter(school_class__name__icontains=class_filter)

        data = [
            {
                "id": s.pk,
                "admission_number": s.admission_number,
                "full_name": s.user.get_full_name(),
                "email": s.user.email or "",
                "class": s.school_class.name if s.school_class else s.class_name,
                "status": s.status,
                "date_enrolled": s.date_enrolled,
            }
            for s in qs
        ]
        return Response({"count": len(data), "results": data})


# ---------------------------------------------------------------------------
# Fix #19 — Fees API
# ---------------------------------------------------------------------------

class FeeStatusAPIView(APIView):
    """Outstanding fee summary per student."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [SchoolScopedThrottle]

    def get(self, request):
        from finance.models import Fee
        from django.db.models import Sum, F as DBF
        user = request.user
        school = _require_school(user)

        if not (can_manage_finance(user) or getattr(user, "is_superuser", False)):
            raise PermissionDenied("Finance access required.")

        qs = (
            Fee.objects.filter(school=school, is_active=True)
            .values("student__id", "student__user__first_name", "student__user__last_name",
                    "student__admission_number")
            .annotate(
                total_billed=Sum("amount"),
                total_paid=Sum("amount_paid"),
            )
            .order_by("student__user__last_name")
        )
        data = [
            {
                "student_id": r["student__id"],
                "admission_number": r["student__admission_number"],
                "full_name": f"{r['student__user__first_name']} {r['student__user__last_name']}",
                "total_billed": float(r["total_billed"] or 0),
                "total_paid": float(r["total_paid"] or 0),
                "outstanding": float((r["total_billed"] or 0) - (r["total_paid"] or 0)),
            }
            for r in qs
        ]
        return Response({"count": len(data), "results": data})


# ---------------------------------------------------------------------------
# Fix #19 — Results API
# ---------------------------------------------------------------------------

class ResultListAPIView(APIView):
    """Published results for a given term, optionally filtered by class."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [SchoolScopedThrottle]

    @extend_schema(parameters=[
        OpenApiParameter("term_id", int, description="Filter by Term PK"),
        OpenApiParameter("class_name", str, description="Filter by class name"),
    ])
    def get(self, request):
        from academics.models import Result
        user = request.user
        school = _require_school(user)

        qs = Result.objects.filter(school=school, is_published=True).select_related(
            "student__user", "subject", "term"
        )
        term_id = request.query_params.get("term_id")
        if term_id:
            qs = qs.filter(term_id=term_id)
        class_filter = request.query_params.get("class_name")
        if class_filter:
            qs = qs.filter(student__class_name__icontains=class_filter)

        data = [
            {
                "id": r.pk,
                "student_id": r.student_id,
                "student_name": r.student.user.get_full_name(),
                "subject": r.subject.name,
                "term": str(r.term) if r.term_id else "",
                "score": float(r.score) if r.score is not None else None,
                "grade": getattr(r, "grade", ""),
                "remarks": getattr(r, "remarks", ""),
            }
            for r in qs[:500]
        ]
        return Response({"count": len(data), "results": data})


# ---------------------------------------------------------------------------
# Fix #19 — Timetable API
# ---------------------------------------------------------------------------

class TimetableAPIView(APIView):
    """Timetable slots for the authenticated user's school."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [SchoolScopedThrottle]

    def get(self, request):
        from academics.models import Timetable
        user = request.user
        school = _require_school(user)

        qs = Timetable.objects.filter(school=school).select_related("subject", "teacher")
        class_filter = request.query_params.get("class_name")
        if class_filter:
            qs = qs.filter(class_name__icontains=class_filter)

        data = [
            {
                "id": t.pk,
                "class_name": t.class_name,
                "day": t.day,
                "period": t.period,
                "subject": t.subject.name if t.subject_id else "",
                "teacher": t.teacher.get_full_name() if t.teacher_id else "",
                "start_time": str(t.start_time) if hasattr(t, "start_time") and t.start_time else "",
                "end_time": str(t.end_time) if hasattr(t, "end_time") and t.end_time else "",
            }
            for t in qs[:200]
        ]
        return Response({"count": len(data), "results": data})


# ---------------------------------------------------------------------------
# Fix #26 — Student Transcripts API
# ---------------------------------------------------------------------------

class StudentTranscriptAPIView(APIView):
    """Published transcripts for a student."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [SchoolScopedThrottle]

    def get(self, request, student_id: int):
        from academics.models import StudentTranscript
        from students.models import Student
        user = request.user
        school = _require_school(user)

        student = Student.objects.filter(pk=student_id, school=school).first()
        if not student:
            return Response({"detail": "Student not found."}, status=status.HTTP_404_NOT_FOUND)

        qs = StudentTranscript.objects.filter(student=student, school=school).select_related(
            "academic_year", "term"
        ).order_by("-academic_year__start_date", "term__order")

        data = [
            {
                "id": t.pk,
                "academic_year": str(t.academic_year),
                "term": str(t.term) if t.term_id else "Full Year",
                "average_score": float(t.average_score),
                "gpa": float(t.gpa),
                "subjects_passed": t.subjects_passed,
                "total_subjects": t.total_subjects,
                "class_rank": t.class_rank,
                "is_published": t.is_published,
            }
            for t in qs
        ]
        return Response({"student_id": student_id, "transcripts": data})


# ---------------------------------------------------------------------------
# Fix #34 — GDPR Data Export request endpoint
# ---------------------------------------------------------------------------

class GDPRExportRequestAPIView(APIView):
    """Initiate a GDPR data export for the authenticated user.

    POST  — queue a new export (returns 202).
    GET   — check status of the latest export for the current user.
    """

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [SchoolScopedThrottle]

    def get(self, request):
        from audit.models import GDPRExportRequest
        from django.utils import timezone as _tz
        user = request.user
        latest = GDPRExportRequest.objects.filter(subject_user=user).order_by("-requested_at").first()
        if not latest:
            return Response({"detail": "No export requests found."}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            "id": latest.pk,
            "status": latest.status,
            "requested_at": latest.requested_at.isoformat(),
            "completed_at": latest.completed_at.isoformat() if latest.completed_at else None,
            "expires_at": latest.expires_at.isoformat() if latest.expires_at else None,
            "download_url": f"/api/v1/gdpr/export/{latest.pk}/download/" if latest.status == "ready" else None,
        })

    def post(self, request):
        from audit.models import GDPRExportRequest
        from django.utils import timezone as _tz
        user = request.user
        school = getattr(user, "school", None)

        pending = GDPRExportRequest.objects.filter(
            subject_user=user, status__in=["pending", "processing"]
        ).exists()
        if pending:
            return Response(
                {"detail": "An export is already pending. Please wait for it to complete."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        export_req = GDPRExportRequest.objects.create(
            school=school,
            requested_by=user,
            subject_user=user,
            status="pending",
            expires_at=_tz.now() + __import__("datetime").timedelta(days=7),
        )
        from core.tasks import generate_gdpr_export
        generate_gdpr_export.delay(export_req.pk)
        return Response(
            {"detail": "Export request created. You will be notified when ready.", "id": export_req.pk},
            status=status.HTTP_202_ACCEPTED,
        )


class GDPRExportDownloadAPIView(APIView):
    """Return the completed GDPR export as a JSON file download."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, export_id: int):
        import json as _json
        from django.http import HttpResponse
        from audit.models import GDPRExportRequest
        from django.utils import timezone as _tz
        user = request.user
        try:
            req = GDPRExportRequest.objects.get(pk=export_id, subject_user=user)
        except GDPRExportRequest.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if req.status != "ready":
            return Response({"detail": f"Export is not ready (status: {req.status})."}, status=status.HTTP_409_CONFLICT)
        if req.expires_at and _tz.now() > req.expires_at:
            return Response({"detail": "Export link has expired."}, status=status.HTTP_410_GONE)
        if not req.export_payload:
            return Response({"detail": "Export payload not available."}, status=status.HTTP_404_NOT_FOUND)
        payload_str = _json.dumps(req.export_payload, indent=2, default=str).encode("utf-8")
        filename = f"mastex_gdpr_export_{user.pk}_{req.pk}.json"
        req.status = "downloaded"
        req.save(update_fields=["status"])
        response = HttpResponse(payload_str, content_type="application/json")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Content-Length"] = len(payload_str)
        return response
