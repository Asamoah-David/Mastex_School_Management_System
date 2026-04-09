"""Aggregated metrics for school and teacher dashboards (charts + KPIs)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Avg, Count, DecimalField, ExpressionWrapper, F, FloatField, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone


def build_attendance_trend(school, days: int = 14) -> dict[str, Any]:
    """Daily present/absent counts and approximate attendance rate for charting."""
    from operations.models import StudentAttendance

    today = timezone.now().date()
    start = today - timedelta(days=days - 1)
    rows = (
        StudentAttendance.objects.filter(school=school, date__gte=start, date__lte=today)
        .values("date")
        .annotate(
            present=Count("id", filter=Q(status="present")),
            absent=Count("id", filter=Q(status="absent")),
            late=Count("id", filter=Q(status="late")),
            excused=Count("id", filter=Q(status="excused")),
        )
        .order_by("date")
    )
    by_date = {r["date"]: r for r in rows}
    labels: list[str] = []
    rates: list[float] = []
    present_series: list[int] = []
    absent_series: list[int] = []
    d = start
    while d <= today:
        labels.append(d.strftime("%b %d"))
        row = by_date.get(d)
        p = (row or {}).get("present") or 0
        a = (row or {}).get("absent") or 0
        l = (row or {}).get("late") or 0
        e = (row or {}).get("excused") or 0
        marked = p + a + l + e
        rates.append(round((p / marked) * 100, 1) if marked else 0.0)
        present_series.append(p)
        absent_series.append(a)
        d += timedelta(days=1)
    has_data = any(present_series) or any(absent_series)
    return {
        "labels": labels,
        "rates": rates,
        "present": present_series,
        "absent": absent_series,
        "has_data": has_data,
    }


def teacher_student_scope(school, user) -> tuple[set[str], set[int]]:
    """
    Class names and SchoolClass PKs for students tied to this teacher:
    homeroom (class teacher), timetable rows, homework, and quizzes they created.
    """
    from academics.models import Homework, Quiz, Timetable
    from students.models import SchoolClass

    class_names: set[str] = set()
    school_class_ids: set[int] = set()

    for name in SchoolClass.objects.filter(school=school, class_teacher=user).values_list("name", flat=True):
        if name:
            class_names.add(str(name).strip())

    tt = Timetable.objects.filter(school=school, teacher=user).values_list("class_name", "school_class_id")
    for cn, scid in tt:
        if cn:
            class_names.add(str(cn).strip())
        if scid:
            school_class_ids.add(int(scid))

    hw = Homework.objects.filter(school=school, created_by=user).values_list("class_name", "school_class_id")
    for cn, scid in hw:
        if cn:
            class_names.add(str(cn).strip())
        if scid:
            school_class_ids.add(int(scid))

    qz = Quiz.objects.filter(school=school, created_by=user).values_list("class_name", "school_class_id")
    for cn, scid in qz:
        if cn:
            class_names.add(str(cn).strip())
        if scid:
            school_class_ids.add(int(scid))

    return class_names, school_class_ids


def build_teacher_attendance_trend(school, user, days: int = 14) -> dict[str, Any]:
    """Attendance trend for students in this teacher's homeroom, timetable, homework, and quiz classes."""
    from operations.models import StudentAttendance

    class_names, school_class_ids = teacher_student_scope(school, user)
    if not class_names and not school_class_ids:
        return {"labels": [], "rates": [], "present": [], "absent": [], "has_data": False}

    scope_q = Q()
    if class_names:
        scope_q |= Q(student__class_name__in=class_names)
    if school_class_ids:
        scope_q |= Q(student__school_class_id__in=school_class_ids)

    today = timezone.now().date()
    start = today - timedelta(days=days - 1)
    rows = (
        StudentAttendance.objects.filter(
            school=school,
            date__gte=start,
            date__lte=today,
        )
        .filter(scope_q)
        .values("date")
        .annotate(
            present=Count("id", filter=Q(status="present")),
            absent=Count("id", filter=Q(status="absent")),
            late=Count("id", filter=Q(status="late")),
            excused=Count("id", filter=Q(status="excused")),
        )
        .order_by("date")
    )
    by_date = {r["date"]: r for r in rows}
    labels: list[str] = []
    rates: list[float] = []
    present_series: list[int] = []
    absent_series: list[int] = []
    d = start
    while d <= today:
        labels.append(d.strftime("%b %d"))
        row = by_date.get(d)
        p = (row or {}).get("present") or 0
        a = (row or {}).get("absent") or 0
        l = (row or {}).get("late") or 0
        e = (row or {}).get("excused") or 0
        marked = p + a + l + e
        rates.append(round((p / marked) * 100, 1) if marked else 0.0)
        present_series.append(p)
        absent_series.append(a)
        d += timedelta(days=1)
    has_data = any(present_series) or any(absent_series)
    return {
        "labels": labels,
        "rates": rates,
        "present": present_series,
        "absent": absent_series,
        "has_data": has_data,
    }


def _term_for_school_performance(school):
    from academics.models import Result, Term

    t = Term.objects.filter(school=school, is_current=True).first()
    if t:
        return t
    last_tid = (
        Result.objects.filter(student__school=school, term__isnull=False)
        .order_by("-term_id")
        .values_list("term_id", flat=True)
        .first()
    )
    if last_tid:
        return Term.objects.filter(pk=last_tid, school=school).first()
    return Term.objects.filter(school=school).order_by("-id").first()


def build_academic_insights(school) -> dict[str, Any]:
    """School-wide averages for the current (or latest) term with results."""
    from academics.models import Result

    term = _term_for_school_performance(school)
    if not term:
        return {
            "has_data": False,
            "term_label": "",
            "result_count": 0,
            "avg_pct": None,
            "below_threshold": 0,
            "subject_avgs": [],
        }

    pct = ExpressionWrapper(F("score") * 100.0 / F("total_score"), output_field=FloatField())
    base = Result.objects.filter(student__school=school, term=term).exclude(total_score__lte=0)
    result_count = base.count()
    if not result_count:
        return {
            "has_data": False,
            "term_label": term.name,
            "result_count": 0,
            "avg_pct": None,
            "below_threshold": 0,
            "subject_avgs": [],
        }

    agg = base.aggregate(avg_pct=Avg(pct))
    avg_pct = round(agg["avg_pct"], 1) if agg["avg_pct"] is not None else None
    below_threshold = base.annotate(_p=pct).filter(_p__lt=50).count()
    subject_rows = (
        base.values("subject__name")
        .annotate(avg_pct=Avg(pct))
        .order_by("-avg_pct")[:6]
    )
    subject_avgs = [
        {"name": row["subject__name"] or "—", "avg_pct": round(row["avg_pct"], 1) if row["avg_pct"] is not None else 0}
        for row in subject_rows
    ]
    return {
        "has_data": True,
        "term_label": term.name,
        "result_count": result_count,
        "avg_pct": avg_pct,
        "below_threshold": below_threshold,
        "subject_avgs": subject_avgs,
    }


def build_teacher_academic_insights(school, subject_ids: list[int], term) -> dict[str, Any]:
    """Average scores for this teacher's subjects in the given term."""
    from academics.models import Result

    if not term or not subject_ids:
        return {
            "has_data": False,
            "avg_pct": None,
            "result_count": 0,
            "below_threshold": 0,
            "subject_avgs": [],
        }
    pct = ExpressionWrapper(F("score") * 100.0 / F("total_score"), output_field=FloatField())
    base = (
        Result.objects.filter(student__school=school, term=term, subject_id__in=subject_ids)
        .exclude(total_score__lte=0)
    )
    result_count = base.count()
    if not result_count:
        return {
            "has_data": False,
            "avg_pct": None,
            "result_count": 0,
            "below_threshold": 0,
            "subject_avgs": [],
        }
    agg = base.aggregate(avg_pct=Avg(pct))
    avg_pct = round(agg["avg_pct"], 1) if agg["avg_pct"] is not None else None
    below_threshold = base.annotate(_p=pct).filter(_p__lt=50).count()
    subject_rows = (
        base.values("subject__name").annotate(avg_pct=Avg(pct)).order_by("-avg_pct")[:8]
    )
    subject_avgs = [
        {"name": row["subject__name"] or "—", "avg_pct": round(row["avg_pct"], 1) if row["avg_pct"] is not None else 0}
        for row in subject_rows
    ]
    return {
        "has_data": True,
        "avg_pct": avg_pct,
        "result_count": result_count,
        "below_threshold": below_threshold,
        "subject_avgs": subject_avgs,
    }


def build_finance_insights(school, total_fees: float, paid_fees: float) -> dict[str, Any]:
    """Unpaid/partial counts and recent collection (completed payments)."""
    from finance.models import Fee, FeePayment

    fee_qs = Fee.objects.filter(school=school)
    unpaid_invoices = fee_qs.filter(paid=False).count()
    partial_invoices = fee_qs.filter(paid=False, amount_paid__gt=0).count()
    bal_expr = ExpressionWrapper(
        F("amount") - F("amount_paid"),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )
    outstanding_agg = fee_qs.filter(paid=False).aggregate(total=Coalesce(Sum(bal_expr), Decimal("0")))
    outstanding_balance = float(outstanding_agg["total"] or 0)

    week_ago = timezone.now() - timedelta(days=7)
    week_pay = (
        FeePayment.objects.filter(fee__school=school, status="completed", created_at__gte=week_ago).aggregate(
            s=Sum("amount")
        )["s"]
    )
    week_collection = float(week_pay or 0)
    week_payment_count = FeePayment.objects.filter(
        fee__school=school, status="completed", created_at__gte=week_ago
    ).count()

    denom = float(total_fees) if total_fees else 0.0
    collection_rate_pct = round((float(paid_fees) / denom) * 100, 1) if denom > 0 else None

    return {
        "unpaid_invoices": unpaid_invoices,
        "partial_invoices": partial_invoices,
        "outstanding_balance": outstanding_balance,
        "week_collection": week_collection,
        "week_payment_count": week_payment_count,
        "collection_rate_pct": collection_rate_pct,
    }
