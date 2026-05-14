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
    can_api_list_schoolwide_published_results,
    can_manage_finance,
    can_review_staff_leave,
    is_parent,
    is_school_leadership,
    is_student,
    is_super_admin,
    user_can_manage_school,
)
from integrations.serializers import ExpenseSerializer, MeSerializer, StaffLeaveSerializer
from operations.models import Expense, StaffLeave
from schools.features import is_feature_enabled
import logging

logger = logging.getLogger(__name__)


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
        if not is_feature_enabled(self.request, "leave_management"):
            raise PermissionDenied("Leave management is disabled for your school.")
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
        if not is_feature_enabled(self.request, "expenses"):
            raise PermissionDenied("Expenses are disabled for your school.")
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

        if not is_feature_enabled(request, "attendance"):
            return Response({"detail": "Attendance is disabled for your school."}, status=403)
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
        if not is_feature_enabled(request, "student_enrollment"):
            return Response({"detail": "Student enrollment is disabled for your school."}, status=403)

        qs = (
            Student.objects.filter(school=school, status="active")
            .select_related("user", "school_class")
            .order_by("user__last_name", "user__first_name")
        )
        class_filter = request.query_params.get("class")
        if class_filter:
            qs = qs.filter(school_class__name__icontains=class_filter)

        try:
            cap = min(int(request.query_params.get("limit", "500")), 2000)
        except (TypeError, ValueError):
            cap = 500
        cap = max(1, cap)

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
            for s in qs[:cap]
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
        from django.db.models import Sum
        user = request.user
        school = _require_school(user)

        if not (can_manage_finance(user) or getattr(user, "is_superuser", False)):
            raise PermissionDenied("Finance access required.")
        if not is_feature_enabled(request, "fee_management"):
            return Response({"detail": "Fee management is disabled for your school."}, status=403)

        qs = (
            Fee.objects.filter(school=school, is_active=True, deleted_at__isnull=True)
            .values("student__id", "student__user__first_name", "student__user__last_name",
                    "student__admission_number")
            .annotate(
                total_billed=Sum("amount"),
                total_paid=Sum("amount_paid"),
            )
            .order_by("student__user__last_name")
        )
        try:
            cap = min(int(request.query_params.get("limit", "500")), 2000)
        except (TypeError, ValueError):
            cap = 500
        cap = max(1, cap)
        rows = list(qs[:cap])
        data = [
            {
                "student_id": r["student__id"],
                "admission_number": r["student__admission_number"],
                "full_name": f"{r['student__user__first_name']} {r['student__user__last_name']}",
                "total_billed": float(r["total_billed"] or 0),
                "total_paid": float(r["total_paid"] or 0),
                "outstanding": float((r["total_billed"] or 0) - (r["total_paid"] or 0)),
            }
            for r in rows
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
        from students.models import Student
        from students.utils import get_children_for_parent

        user = request.user
        school = _require_school(user)
        if not is_feature_enabled(request, "results"):
            return Response({"detail": "Results are disabled for your school."}, status=403)

        qs = Result.objects.filter(
            school=school, is_published=True, deleted_at__isnull=True
        ).select_related("student__user", "subject", "term")

        if can_api_list_schoolwide_published_results(user):
            pass
        elif is_parent(user):
            child_ids = list(get_children_for_parent(user, school=school).values_list("id", flat=True))
            qs = qs.filter(student_id__in=child_ids) if child_ids else qs.none()
        elif is_student(user):
            stu = Student.objects.filter(user=user, school=school).first()
            if not stu:
                raise PermissionDenied("Student profile not found for this account.")
            qs = qs.filter(student=stu)
        else:
            raise PermissionDenied("You do not have permission to list published results.")

        term_id = request.query_params.get("term_id")
        if term_id:
            qs = qs.filter(term_id=term_id)
        class_filter = request.query_params.get("class_name")
        if class_filter:
            qs = qs.filter(student__class_name__icontains=class_filter)

        try:
            limit = min(int(request.query_params.get("limit", "500")), 1000)
        except (TypeError, ValueError):
            limit = 500
        limit = max(1, limit)

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
            for r in qs[:limit]
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
        from django.db.models import Q

        from academics.models import Timetable
        from students.models import Student
        from students.utils import get_children_for_parent

        user = request.user
        school = _require_school(user)
        if not is_feature_enabled(request, "timetable"):
            return Response({"detail": "Timetable is disabled for your school."}, status=403)

        qs = Timetable.objects.filter(school=school).select_related("subject", "teacher", "school_class")
        class_filter = request.query_params.get("class_name")
        if class_filter:
            qs = qs.filter(class_name__icontains=class_filter)

        if can_api_list_schoolwide_published_results(user) or is_super_admin(user):
            pass
        elif is_parent(user):
            children = get_children_for_parent(user, school=school)
            class_names = {n for n in children.values_list("class_name", flat=True) if n}
            sc_ids = {i for i in children.values_list("school_class_id", flat=True) if i}
            qfilt = Q()
            if class_names:
                qfilt |= Q(class_name__in=class_names)
            if sc_ids:
                qfilt |= Q(school_class_id__in=sc_ids)
            qs = qs.filter(qfilt) if qfilt else qs.none()
        elif is_student(user):
            stu = Student.objects.filter(user=user, school=school).first()
            if not stu:
                raise PermissionDenied("Student profile not found for this account.")
            qfilt = Q()
            if stu.class_name:
                qfilt |= Q(class_name=stu.class_name)
            if stu.school_class_id:
                qfilt |= Q(school_class_id=stu.school_class_id)
            qs = qs.filter(qfilt) if qfilt else qs.none()
        else:
            raise PermissionDenied("You do not have permission to view the school timetable.")

        data = [
            {
                "id": t.pk,
                "class_name": t.class_name,
                "day": t.day_of_week,
                "period": "",
                "subject": t.subject.name if t.subject_id else "",
                "teacher": t.teacher.get_full_name() if t.teacher_id else "",
                "start_time": str(t.start_time) if t.start_time else "",
                "end_time": str(t.end_time) if t.end_time else "",
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
        from students.utils import parent_is_guardian_of

        user = request.user
        school = _require_school(user)
        if not is_feature_enabled(request, "results"):
            return Response({"detail": "Results are disabled for your school."}, status=403)

        student = Student.objects.filter(pk=student_id, school=school).first()
        if not student:
            return Response({"detail": "Student not found."}, status=status.HTTP_404_NOT_FOUND)

        staff_wide = (
            is_super_admin(user)
            or getattr(user, "is_superuser", False)
            or can_api_list_schoolwide_published_results(user)
        )
        if not staff_wide:
            if is_parent(user):
                if not parent_is_guardian_of(user, student):
                    return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
            elif is_student(user):
                if student.user_id != user.pk:
                    return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
            else:
                return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        qs = StudentTranscript.objects.filter(student=student, school=school).select_related(
            "academic_year", "term"
        ).order_by("-academic_year__start_date", "term__id")
        if not staff_wide:
            qs = qs.filter(is_published=True)

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
        try:
            generate_gdpr_export.delay(export_req.pk)
        except Exception as exc:
            export_req.status = "failed"
            export_req.error_message = f"Failed to queue export job: {str(exc)[:200]}"
            export_req.save(update_fields=["status", "error_message"])
            logger.warning("GDPR export queue failed request_id=%s", export_req.pk, exc_info=True)
            return Response(
                {"detail": "Export queue is currently unavailable. Please try again shortly."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
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
