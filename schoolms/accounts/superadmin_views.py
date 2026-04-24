"""Super-admin platform-wide metrics & charts."""
import json
import csv
import logging
from datetime import date, timedelta
from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.utils import timezone

logger = logging.getLogger(__name__)


@login_required
def superadmin_metrics(request):
    """Platform-wide KPI dashboard for super-admins."""
    user = request.user
    if not (user.is_superuser or getattr(user, "is_super_admin", False)):
        return redirect("home")

    from schools.models import School
    from students.models import Student

    schools_qs = School.objects.all()
    today = date.today()

    # ── Annotate each school ──────────────────────────────────────────────────
    schools_data = []
    total_revenue_all = 0
    active_count = 0
    expired_count = 0
    trial_count = 0
    plan_counts = defaultdict(int)

    for s in schools_qs.order_by("name"):
        s.student_count = Student.objects.filter(school=s, status="active").count()
        s.subscription_active = bool(
            s.subscription_end_date and s.subscription_end_date.date() >= today
        )

        # Gather revenue from FeePayment model
        total_rev = 0
        try:
            from finance.models import FeePayment
            total_rev = float(
                FeePayment.objects.filter(fee__school=s, status="completed")
                .aggregate(t=__import__("django.db.models", fromlist=["Sum"]).Sum("amount"))["t"] or 0
            )
        except Exception:
            pass
        s.total_revenue = total_rev
        total_revenue_all += total_rev

        if s.subscription_active:
            active_count += 1
        else:
            expired_count += 1
        plan_counts[s.subscription_plan or "basic"] += 1
        schools_data.append(s)

    # CSV export
    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = "attachment; filename=schools_metrics.csv"
        writer = csv.writer(response)
        writer.writerow(["School", "Plan", "Active", "Students", "Expiry", "Revenue"])
        for s in schools_data:
            writer.writerow([
                s.name, s.subscription_plan or "basic",
                "Yes" if s.subscription_active else "No",
                s.student_count,
                s.subscription_end_date or "",
                s.total_revenue,
            ])
        return response

    # ── Chart data (12 months) ────────────────────────────────────────────────
    months = []
    chart_subs = []
    chart_revenue = []
    for i in range(11, -1, -1):
        mo = today.replace(day=1) - timedelta(days=i * 30)
        months.append(mo.strftime("%b %Y"))
        # Count schools created in this month
        subs = School.objects.filter(
            created_at__year=mo.year, created_at__month=mo.month
        ).count() if hasattr(School, "created_at") else 0
        chart_subs.append(subs)
        # Sum revenue for this month
        rev = 0
        try:
            from finance.models import FeePayment
            from django.db.models import Sum
            rev = float(
                FeePayment.objects.filter(
                    status="completed",
                    paid_at__year=mo.year, paid_at__month=mo.month,
                ).aggregate(t=Sum("amount"))["t"] or 0
            )
        except Exception:
            pass
        chart_revenue.append(rev)

    # ── KPI cards ─────────────────────────────────────────────────────────────
    total_students = Student.objects.filter(status="active").count()
    kpis = [
        {"label": "Total Schools", "value": len(schools_data), "color": "#1e3a5f", "change": None},
        {"label": "Active Subscriptions", "value": active_count, "color": "#16a34a", "change": None},
        {"label": "Expired Subscriptions", "value": expired_count, "color": "#dc2626", "change": None},
        {"label": "Total Students", "value": total_students, "color": "#2563eb", "change": None},
        {"label": "Total Platform Revenue", "value": f"GHS {total_revenue_all:,.2f}", "color": "#d97706", "change": None},
    ]

    plan_labels = list(plan_counts.keys())
    plan_values = list(plan_counts.values())
    status_values = [active_count, expired_count, trial_count]

    return render(request, "accounts/superadmin_metrics.html", {
        "school": None,
        "schools": schools_data,
        "kpis": kpis,
        "chart_months": json.dumps(months),
        "chart_subs": json.dumps(chart_subs),
        "chart_revenue": json.dumps(chart_revenue),
        "plan_labels": json.dumps(plan_labels),
        "plan_values": json.dumps(plan_values),
        "status_values": json.dumps(status_values),
    })
