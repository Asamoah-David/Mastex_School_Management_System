"""
Flexible / Partial Payment Views
==================================
Handles partial payments for any fee type:
  school_fees, bus, hostel, canteen, textbook, library, etc.

Parents & students can pay any amount they can afford, on any schedule.
Bus payments support daily/weekly/monthly/termly periods.
"""
import logging
from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone

logger = logging.getLogger(__name__)

FEE_LABELS = {
    "school_fees": "School Fees",
    "bus": "Bus / Transport",
    "hostel": "Hostel / Boarding",
    "canteen": "Canteen",
    "textbook": "Textbook",
    "library": "Library Fee",
    "pta": "PTA Dues",
    "exam": "Exam Fee",
    "uniform": "Uniform",
    "other": "Other Fee",
}

PERIOD_LABELS = {
    "daily": "Daily",
    "weekly": "Weekly",
    "monthly": "Monthly",
    "termly": "Full Term",
    "custom": "Custom",
}


def _get_school(request):
    school = getattr(request.user, "school", None)
    if school:
        return school
    if request.user.is_superuser or getattr(request.user, "is_super_admin", False):
        from schools.models import School
        sid = request.session.get("current_school_id")
        if sid:
            return School.objects.filter(pk=sid).first()
    return None


def _get_fee_record(student, fee_type, school):
    """Return (total_fee, paid, balance, fee_record) for a student+fee_type."""
    from django.apps import apps
    total_fee = Decimal("0")
    paid = Decimal("0")

    # Try FeeStructure for total
    try:
        from finance.models import FeeStructure
        fs = FeeStructure.objects.filter(
            school=school, fee_type=fee_type,
            class_name__in=[student.class_name, "ALL", ""],
        ).first()
        if fs:
            total_fee = Decimal(str(fs.amount))
    except Exception:
        pass

    # Sum all paid payments
    try:
        from finance.models import FeePayment
        agg = FeePayment.objects.filter(
            student=student, fee_type=fee_type, school=school, status="paid"
        ).aggregate(t=__import__("django.db.models", fromlist=["Sum"]).Sum("amount"))["t"]
        paid = Decimal(str(agg or 0))
    except Exception:
        pass

    balance = max(total_fee - paid, Decimal("0"))
    return total_fee, paid, balance


def _compute_rates(fee_type, total_fee, term_weeks=13):
    """Compute daily/weekly/monthly rates for bus-like fees."""
    if total_fee <= 0:
        return Decimal("0"), Decimal("0"), Decimal("0"), total_fee
    daily = round(total_fee / (term_weeks * 5), 2)   # 5 school days/week
    weekly = round(total_fee / term_weeks, 2)
    monthly = round(total_fee / 3, 2)                # ~3 months per term
    return daily, weekly, monthly, total_fee


@login_required
def partial_payment_page(request, fee_type="school_fees"):
    """Flexible payment page for any fee type."""
    school = _get_school(request)
    if not school:
        messages.error(request, "School not found.")
        return redirect("home")

    user = request.user
    role = getattr(user, "role", None)
    currency = getattr(school, "currency", None) or "GHS"

    # Determine student
    student = None
    if role == "student":
        try:
            from students.models import Student
            student = Student.objects.get(user=user, school=school)
        except Exception:
            pass
    elif role == "parent":
        student_id = request.GET.get("student") or request.POST.get("student_id")
        if student_id:
            from students.models import Student
            student = Student.objects.filter(pk=student_id, school=school).first()
    else:
        # Staff / admin: student_id required
        student_id = request.GET.get("student") or request.POST.get("student_id")
        if student_id:
            from students.models import Student
            student = Student.objects.filter(pk=student_id, school=school).first()

    if not student:
        messages.error(request, "Student not found.")
        return redirect("home")

    total_fee, total_paid, balance = _get_fee_record(student, fee_type, school)
    daily_rate, weekly_rate, monthly_rate, termly_rate = _compute_rates(fee_type, total_fee)
    half_balance = round(balance / 2, 2)

    # History
    payments = []
    try:
        from finance.models import FeePayment
        payments = list(
            FeePayment.objects.filter(student=student, fee_type=fee_type, school=school)
            .order_by("-created_at")[:20]
        )
    except Exception:
        pass

    back_url = request.META.get("HTTP_REFERER", "/")

    if request.method == "POST":
        amount_str = request.POST.get("amount", "0")
        method = request.POST.get("method", "cash")
        period = request.POST.get("period", "custom")
        notes = request.POST.get("notes", "")

        try:
            amount = Decimal(amount_str)
            if amount <= 0:
                raise ValueError("Amount must be positive")
            if amount > balance:
                amount = balance  # cap at balance
        except (ValueError, Exception) as exc:
            messages.error(request, f"Invalid amount: {exc}")
        else:
            period_label = PERIOD_LABELS.get(period, period)
            if method == "paystack":
                # Redirect to Paystack flow
                from django.urls import reverse
                return redirect(
                    f"/finance/pay/?fee_type={fee_type}&amount={amount}"
                    f"&student={student.id}&period={period}&notes={notes}"
                )
            else:
                # Record cash/manual payment
                try:
                    from finance.models import FeePayment
                    FeePayment.objects.create(
                        school=school,
                        student=student,
                        fee_type=fee_type,
                        amount=amount,
                        method=method,
                        period_label=period_label,
                        notes=notes,
                        status="paid",
                        paid_at=timezone.now(),
                        recorded_by=user,
                    )
                    messages.success(
                        request,
                        f"Payment of {currency} {amount} recorded successfully for {FEE_LABELS.get(fee_type, fee_type)}."
                    )
                    return redirect(request.path + f"?student={student.id}")
                except Exception as exc:
                    logger.exception("Failed to record payment: %s", exc)
                    messages.error(request, f"Failed to record payment: {exc}")

    return render(request, "operations/partial_payment.html", {
        "school": school,
        "student": student,
        "fee_type": fee_type,
        "fee_type_label": FEE_LABELS.get(fee_type, fee_type),
        "currency": currency,
        "total_fee": total_fee,
        "total_paid": total_paid,
        "balance": balance,
        "half_balance": half_balance,
        "daily_rate": daily_rate,
        "weekly_rate": weekly_rate,
        "monthly_rate": monthly_rate,
        "termly_rate": termly_rate,
        "payments": payments,
        "back_url": back_url,
    })
