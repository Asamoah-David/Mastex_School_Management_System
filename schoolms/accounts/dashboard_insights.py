"""Aggregated metrics for school and teacher dashboards (charts + KPIs)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import (
    Avg,
    Case,
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    FloatField,
    Q,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce, TruncDate, TruncMonth
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
    homeroom ∪ timetable (via ``teacher_attendance_classes_qs``), plus homework
    and quiz classes they created (broader chart scope than attendance marking).
    """
    from academics.models import Homework, Quiz, Timetable
    from accounts.teaching_scope import teacher_attendance_classes_qs

    class_names: set[str] = set()
    school_class_ids: set[int] = set()

    for name, sc_pk in teacher_attendance_classes_qs(school, user).values_list("name", "id"):
        if name:
            class_names.add(str(name).strip())
        if sc_pk:
            school_class_ids.add(int(sc_pk))

    # Timetable FK to SchoolClass (e.g. named slots) — keep ids even if name matching differs
    for scid in Timetable.objects.filter(school=school, teacher=user).values_list(
        "school_class_id", flat=True
    ):
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


def build_fee_collection_trend(school=None, days: int = 30) -> dict[str, Any]:
    """
    Daily sum of completed FeePayment amounts for ERP cashflow-style charting.
    If ``school`` is None, aggregates across all schools (platform dashboard).
    """
    from finance.models import FeePayment

    today = timezone.now().date()
    start = today - timedelta(days=days - 1)
    qs = FeePayment.objects.filter(status="completed", created_at__date__gte=start, created_at__date__lte=today)
    if school is not None:
        qs = qs.filter(fee__school=school)
    rows = (
        qs.annotate(d=TruncDate("created_at"))
        .values("d")
        .annotate(total=Coalesce(Sum("amount"), Decimal("0")))
        .order_by("d")
    )
    # Normalise keys to ISO date strings (SQLite may return str; Postgres date).
    by_date: dict[str, float] = {}
    for r in rows:
        raw = r["d"]
        if raw is None:
            continue
        if hasattr(raw, "isoformat"):
            key = raw.isoformat()[:10]
        else:
            key = str(raw)[:10]
        by_date[key] = float(r["total"] or 0)
    labels: list[str] = []
    amounts: list[float] = []
    d = start
    while d <= today:
        labels.append(d.strftime("%b %d"))
        amounts.append(round(by_date.get(d.isoformat(), 0.0), 2))
        d += timedelta(days=1)
    has_data = any(a > 0 for a in amounts)
    return {"labels": labels, "amounts": amounts, "has_data": has_data, "days": days}


def build_ar_aging_chart(school=None) -> dict[str, Any]:
    """
    Outstanding fee balance by age of invoice (Fee.created_at), ERP-style buckets.
    If ``school`` is None, aggregates across all schools (platform dashboard).
    """
    from finance.models import Fee

    now = timezone.now()
    cut30 = now - timedelta(days=30)
    cut60 = now - timedelta(days=60)
    cut90 = now - timedelta(days=90)

    rem = ExpressionWrapper(
        F("amount") - F("amount_paid"),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )
    qs = Fee.objects.filter(paid=False).annotate(_rem=rem).filter(_rem__gt=0)
    if school is not None:
        qs = qs.filter(school=school)

    df = DecimalField(max_digits=16, decimal_places=2)
    zero = Value(Decimal("0"), output_field=df)
    agg = qs.aggregate(
        b0_30=Coalesce(
            Sum(Case(When(created_at__gte=cut30, then=F("_rem")), default=zero, output_field=df)),
            Decimal("0"),
        ),
        b31_60=Coalesce(
            Sum(
                Case(
                    When(Q(created_at__lt=cut30) & Q(created_at__gte=cut60), then=F("_rem")),
                    default=zero,
                    output_field=df,
                )
            ),
            Decimal("0"),
        ),
        b61_90=Coalesce(
            Sum(
                Case(
                    When(Q(created_at__lt=cut60) & Q(created_at__gte=cut90), then=F("_rem")),
                    default=zero,
                    output_field=df,
                )
            ),
            Decimal("0"),
        ),
        b90p=Coalesce(
            Sum(Case(When(created_at__lt=cut90, then=F("_rem")), default=zero, output_field=df)),
            Decimal("0"),
        ),
    )
    labels = ["0-30 days", "31-60 days", "61-90 days", "Over 90 days"]
    amounts = [
        float(agg["b0_30"] or 0),
        float(agg["b31_60"] or 0),
        float(agg["b61_90"] or 0),
        float(agg["b90p"] or 0),
    ]
    amounts = [round(x, 2) for x in amounts]
    has_data = sum(amounts) > 0.005
    return {"labels": labels, "amounts": amounts, "has_data": has_data}


def _month_start_series(months: int) -> list[date]:
    months = max(1, int(months or 1))
    today = timezone.now().date()
    current = date(today.year, today.month, 1)
    series: list[date] = []
    for _ in range(months):
        series.append(current)
        if current.month == 1:
            current = date(current.year - 1, 12, 1)
        else:
            current = date(current.year, current.month - 1, 1)
    series.reverse()
    return series


def _next_month_start(month_start: date) -> date:
    if month_start.month == 12:
        return date(month_start.year + 1, 1, 1)
    return date(month_start.year, month_start.month + 1, 1)


def _aware_start_of_day(day: date) -> datetime:
    dt = datetime.combine(day, time.min)
    if timezone.is_naive(dt):
        return timezone.make_aware(dt)
    return dt


def build_subscription_revenue_trend(months: int = 12) -> dict[str, Any]:
    from finance.models import SubscriptionPayment

    month_starts = _month_start_series(months)
    if not month_starts:
        zero = Decimal("0")
        return {
            "labels": [],
            "values": [],
            "has_data": False,
            "total": zero,
            "last_30_days": zero,
            "recent_month": zero,
            "previous_month": zero,
        }

    window_start = month_starts[0]
    window_end = _next_month_start(month_starts[-1])
    window_start_dt = _aware_start_of_day(window_start)
    window_end_dt = _aware_start_of_day(window_end)
    aggregates = (
        SubscriptionPayment.objects.filter(
            status="completed", created_at__gte=window_start_dt, created_at__lt=window_end_dt
        )
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(total=Coalesce(Sum("amount"), Decimal("0")))
    )
    month_totals: dict[date, Decimal] = {}
    for row in aggregates:
        month = row.get("month")
        if not month:
            continue
        month_totals[month.date()] = row.get("total") or Decimal("0")

    labels: list[str] = []
    values_decimal: list[Decimal] = []
    for start in month_starts:
        labels.append(start.strftime("%b %Y"))
        values_decimal.append(month_totals.get(start, Decimal("0")))

    values = [float(v) for v in values_decimal]
    has_data = any(v > 0 for v in values)
    total = sum(values_decimal, Decimal("0"))
    last_30_days = (
        SubscriptionPayment.objects.filter(
            status="completed", created_at__gte=timezone.now() - timedelta(days=30)
        ).aggregate(total=Coalesce(Sum("amount"), Decimal("0")))
        ["total"]
        or Decimal("0")
    )
    recent_month = values_decimal[-1] if values_decimal else Decimal("0")
    previous_month = values_decimal[-2] if len(values_decimal) >= 2 else Decimal("0")

    mom_delta = recent_month - previous_month
    mom_percent = Decimal("0")
    if previous_month > 0:
        mom_percent = (mom_delta / previous_month) * Decimal("100")

    return {
        "labels": labels,
        "values": values,
        "has_data": has_data,
        "total": total,
        "last_30_days": last_30_days,
        "recent_month": recent_month,
        "previous_month": previous_month,
        "mom_delta": mom_delta,
        "mom_percent": mom_percent,
    }


def build_registration_trend(months: int = 6) -> dict[str, Any]:
    from schools.models import School

    month_starts = _month_start_series(months)
    if not month_starts:
        return {"labels": [], "values": [], "has_data": False}

    window_start = month_starts[0]
    window_end = _next_month_start(month_starts[-1])
    window_start_dt = _aware_start_of_day(window_start)
    window_end_dt = _aware_start_of_day(window_end)
    aggregates = (
        School.objects.filter(created_at__gte=window_start_dt, created_at__lt=window_end_dt)
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(total=Count("id"))
    )
    month_totals: dict[date, int] = {}
    for row in aggregates:
        month = row.get("month")
        if not month:
            continue
        month_totals[month.date()] = int(row.get("total") or 0)

    labels: list[str] = []
    values: list[int] = []
    for start in month_starts:
        labels.append(start.strftime("%b %Y"))
        values.append(month_totals.get(start, 0))

    return {"labels": labels, "values": values, "has_data": any(values)}


def build_term_collections_chart(school, limit: int = 8) -> dict[str, Any]:
    """Sum of amount_paid on fee lines per academic term (recognized revenue by term)."""
    from finance.models import Fee

    rows = (
        Fee.objects.filter(school=school, term__isnull=False)
        .values("term_id", "term__name", "term__start_date")
        .annotate(collected=Coalesce(Sum("amount_paid"), Decimal("0")))
        .order_by("-term__start_date", "-term_id")[:limit]
    )
    labels: list[str] = []
    amounts: list[float] = []
    for row in rows:
        name = row["term__name"] or f"Term #{row['term_id']}"
        labels.append(name[:28] + ("…" if len(name) > 28 else ""))
        amounts.append(round(float(row["collected"] or 0), 2))
    return {"labels": labels, "amounts": amounts, "has_data": bool(labels)}


def build_enrollment_by_class_chart(school, limit: int = 12) -> dict[str, Any]:
    """Active students per class name (top ``limit``) for capacity / planning charts."""
    from students.models import Student

    rows = (
        Student.objects.filter(school=school, status="active")
        .values("class_name")
        .annotate(c=Count("id"))
        .order_by("-c", "class_name")[:limit]
    )
    labels: list[str] = []
    values: list[int] = []
    for row in rows:
        labels.append(row["class_name"] or "—")
        values.append(int(row["c"]))
    return {"labels": labels, "values": values, "has_data": bool(labels)}


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


def build_teacher_students_by_class_chart(school, user) -> dict[str, Any]:
    """
    Active student counts per class name within this teacher's scope
    (homeroom, timetable, homework, quiz — same scope as attendance trend).
    """
    from django.db.models import Count, Q

    from students.models import Student

    class_names, school_class_ids = teacher_student_scope(school, user)
    if not class_names and not school_class_ids:
        return {"labels": [], "values": [], "has_data": False, "total_students": 0}

    scope_q = Q()
    if class_names:
        scope_q |= Q(class_name__in=class_names)
    if school_class_ids:
        scope_q |= Q(school_class_id__in=school_class_ids)

    rows = (
        Student.objects.filter(school=school, status="active")
        .filter(scope_q)
        .values("class_name")
        .annotate(c=Count("id"))
        .order_by("-c", "class_name")
    )
    labels: list[str] = []
    values: list[int] = []
    total = 0
    for row in rows:
        cn = row["class_name"] or "—"
        labels.append(cn)
        n = int(row["c"])
        values.append(n)
        total += n
    return {
        "labels": labels,
        "values": values,
        "has_data": bool(labels),
        "total_students": total,
    }
