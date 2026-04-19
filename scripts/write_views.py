"""Write all new backend view files."""
import pathlib

BASE = pathlib.Path(__file__).resolve().parent.parent / "schoolms"


def w(rel, content):
    p = BASE / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    print(f"  wrote {rel}")


# ─────────────────────────────────────────────────────────────────────────────
# 1.  AI Comment views  (academics/ai_comment_views.py)
# ─────────────────────────────────────────────────────────────────────────────
w("academics/ai_comment_views.py", '''"""
AI Comment Generation Views
============================
Provides views for generating and saving AI-powered teacher comments
that appear on student report cards.
"""
import logging
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages

logger = logging.getLogger(__name__)


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


def _build_student_summary(student, term, school):
    """Build a text summary of the student's performance for the AI prompt."""
    from academics.models import StudentResultSummary, AssessmentScore, ExamScore, GradingPolicy
    lines = []
    lines.append(f"Student: {student.user.get_full_name() or student.user.username}")
    lines.append(f"Class: {student.class_name or 'N/A'}")
    if term:
        lines.append(f"Term: {term.name}")

    # Get scores
    summaries = []
    if term:
        summaries = list(
            StudentResultSummary.objects.filter(student=student, term=term)
            .select_related("subject")
        )
    if summaries:
        lines.append("Subjects and scores:")
        for s in summaries:
            lines.append(
                f"  {s.subject.name}: CA={s.ca_score:.0f}, Exam={s.exam_score:.0f}, "
                f"Final={s.final_score:.0f}, Grade={s.grade}"
            )
        avg = sum(s.final_score for s in summaries) / len(summaries)
        lines.append(f"Overall average: {avg:.1f}")
    else:
        lines.append("No detailed scores available for this term.")

    # Attendance
    try:
        from operations.models import StudentAttendance
        att = StudentAttendance.objects.filter(student=student)
        if term and hasattr(term, "start_date") and term.start_date:
            att = att.filter(date__gte=term.start_date)
        total = att.count()
        present = att.filter(status="present").count()
        if total:
            lines.append(f"Attendance: {present}/{total} days ({present*100//total}%)")
    except Exception:
        pass

    return "\\n".join(lines)


@login_required
def ai_comment_page(request):
    """Generate and save AI teacher comments for a student."""
    from students.models import Student
    from academics.models import Term, AIStudentComment

    school = _get_school(request)
    if not school:
        messages.error(request, "No school found.")
        return redirect("home")

    user = request.user
    role = getattr(user, "role", None)
    if not (user.is_superuser or role in ("school_admin", "admin", "teacher", "hod", "deputy_head")):
        messages.error(request, "Access denied.")
        return redirect("home")

    student_id = request.GET.get("student") or request.POST.get("student_id")
    student = get_object_or_404(Student, pk=student_id, school=school)

    terms = Term.objects.filter(school=school).order_by("-name")
    saved_comment = AIStudentComment.objects.filter(student=student, school=school).order_by("-created_at").first()

    context = {
        "school": school,
        "student": student,
        "terms": terms,
        "saved_comment": saved_comment,
        "can_manage": True,
        "generated_comment": None,
        "error": None,
    }

    if request.method == "POST":
        action = request.POST.get("action", "generate")
        term_id = request.POST.get("term_id")
        instructions = request.POST.get("instructions", "")
        term = None
        if term_id:
            term = Term.objects.filter(pk=term_id, school=school).first()

        if action == "save":
            # Save the previously generated comment
            generated = request.POST.get("generated_comment", "").strip()
            if generated:
                AIStudentComment.objects.update_or_create(
                    student=student,
                    school=school,
                    term=term.name if term else "",
                    defaults={"content": generated, "generated_by": "ai"},
                )
                messages.success(request, "AI comment saved to report card.")
                return redirect(f"/academics/report-card/{student.id}/enhanced/")
            else:
                context["error"] = "No comment to save."
        else:
            # Generate comment via AI
            summary = _build_student_summary(student, term, school)
            prompt = (
                f"Write a short, professional, encouraging teacher comment (3-4 sentences) "
                f"for the following student report card.\\n\\n{summary}"
            )
            if instructions:
                prompt += f"\\n\\nAdditional instructions: {instructions}"
            prompt += (
                "\\n\\nThe comment should:\\n"
                "- Be warm and encouraging\\n"
                "- Mention specific academic strengths\\n"
                "- Note any areas for improvement politely\\n"
                "- Be suitable for parents to read\\n"
                "- NOT include the student\\'s name (it will be added separately)\\n"
                "Output only the comment text, nothing else."
            )
            try:
                from ai_assistant.utils import ask_ai_with_context
                generated = ask_ai_with_context(
                    prompt=prompt,
                    school_name=school.name,
                    user_name=user.get_full_name() or user.username,
                    user_role=role or "teacher",
                )
                context["generated_comment"] = generated
            except Exception as exc:
                logger.warning("AI comment generation failed: %s", exc)
                context["error"] = f"AI generation failed: {exc}"

    return render(request, "academics/ai_comment.html", context)
''')


# ─────────────────────────────────────────────────────────────────────────────
# 2.  Super-admin metrics view  (accounts/superadmin_views.py)
# ─────────────────────────────────────────────────────────────────────────────
w("accounts/superadmin_views.py", '''"""Super-admin platform-wide metrics & charts."""
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
            s.subscription_expiry and s.subscription_expiry >= today
        )

        # Gather revenue from FeePayment model
        total_rev = 0
        try:
            from finance.models import FeePayment
            total_rev = float(
                FeePayment.objects.filter(school=s, status="paid")
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
                s.subscription_expiry or "",
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
                    status="paid",
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
''')


# ─────────────────────────────────────────────────────────────────────────────
# 3.  Receipt PDF view  (operations/receipt_views.py)
# ─────────────────────────────────────────────────────────────────────────────
w("operations/receipt_views.py", '''"""Receipt views: HTML display + PDF download."""
import io
import logging
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render, redirect

logger = logging.getLogger(__name__)


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


def _get_payment(pk, user, school):
    """Find payment across FeePayment / StudentPayment models."""
    from django.apps import apps
    for model_name in ("FeePayment", "StudentPayment", "Payment"):
        try:
            Model = apps.get_model("finance", model_name)
            obj = Model.objects.filter(pk=pk).first()
            if obj:
                return obj
        except Exception:
            pass
    for model_name in ("FeePayment", "StudentPayment", "Payment"):
        try:
            Model = apps.get_model("operations", model_name)
            obj = Model.objects.filter(pk=pk).first()
            if obj:
                return obj
        except Exception:
            pass
    return None


@login_required
def receipt_view(request, payment_id):
    """HTML receipt page."""
    school = _get_school(request)
    payment = _get_payment(payment_id, request.user, school)
    if not payment:
        from django.http import Http404
        raise Http404("Payment not found")
    return render(request, "operations/receipt.html", {"payment": payment, "school": school})


@login_required
def receipt_pdf_view(request, payment_id):
    """Download PDF receipt."""
    school = _get_school(request)
    payment = _get_payment(payment_id, request.user, school)
    if not payment:
        return HttpResponse("Payment not found", status=404)

    try:
        pdf_bytes = _build_receipt_pdf(payment, school)
    except Exception as exc:
        logger.exception("Receipt PDF failed for payment %s: %s", payment_id, exc)
        return HttpResponse(f"PDF generation failed: {exc}", status=500, content_type="text/plain")

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f\'attachment; filename="receipt_{payment_id}.pdf"\'
    return response


def _build_receipt_pdf(payment, school):
    """Build PDF bytes for a payment receipt."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A5
    from reportlab.lib.units import cm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A5,
                             rightMargin=1.5*cm, leftMargin=1.5*cm,
                             topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()
    normal = ParagraphStyle("N", parent=styles["Normal"], fontSize=9, leading=13)
    center = ParagraphStyle("C", parent=normal, alignment=TA_CENTER)
    heading = ParagraphStyle("H", parent=styles["Heading2"], fontSize=12,
                              textColor=colors.HexColor("#1e3a5f"), alignment=TA_CENTER)

    school_name = school.name if school else "School"
    elements = []
    elements.append(Paragraph(school_name.upper(), heading))
    if school and school.address:
        elements.append(Paragraph(school.address, center))
    elements.append(Spacer(1, 4))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1e3a5f")))
    elements.append(Paragraph("OFFICIAL RECEIPT", ParagraphStyle("RC", parent=heading, fontSize=11,
                               spaceAfter=4, spaceBefore=4)))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc")))
    elements.append(Spacer(1, 8))

    # Details grid
    currency = school.currency if school and hasattr(school, "currency") and school.currency else "GHS"
    student_name = ""
    if hasattr(payment, "student") and payment.student:
        student_name = payment.student.user.get_full_name() or str(payment.student)

    fee_type = ""
    if hasattr(payment, "get_fee_type_display"):
        try:
            fee_type = payment.get_fee_type_display()
        except Exception:
            fee_type = getattr(payment, "fee_type", "")

    paid_at = getattr(payment, "paid_at", None) or getattr(payment, "created_at", None)
    paid_at_str = paid_at.strftime("%d %b %Y %H:%M") if paid_at else "N/A"

    info = [
        ["Receipt No.:", f"#{payment.id}", "Date:", paid_at_str],
        ["Student:", student_name, "Fee Type:", fee_type],
    ]
    info_table = Table(info, colWidths=[2.5*cm, 4*cm, 2.5*cm, 4*cm])
    info_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#1e3a5f")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dddddd")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.HexColor("#f7f9fc"), colors.white]),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 10))

    # Amount
    amount = float(getattr(payment, "amount", 0) or 0)
    amount_data = [
        [Paragraph("<b>Description</b>", normal), Paragraph("<b>Amount</b>", normal)],
        [Paragraph(fee_type or "Payment", normal), Paragraph(f"<b>{currency} {amount:,.2f}</b>",
              ParagraphStyle("Amt", parent=normal, fontSize=11, textColor=colors.HexColor("#1e3a5f")))],
    ]
    amount_table = Table(amount_data, colWidths=[8*cm, 5*cm])
    amount_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f0f4f8")]),
    ]))
    elements.append(amount_table)
    elements.append(Spacer(1, 10))

    # Status
    status = getattr(payment, "status", "paid")
    status_color = colors.HexColor("#16a34a") if status == "paid" else colors.HexColor("#ca8a04")
    status_text = "PAYMENT CONFIRMED" if status == "paid" else "PENDING"
    elements.append(Paragraph(f"✓ {status_text}", ParagraphStyle(
        "ST", parent=center, fontSize=11, textColor=status_color, spaceBefore=4
    )))

    elements.append(Spacer(1, 14))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc")))
    from datetime import date
    elements.append(Paragraph(
        f"Thank you for your payment. Official receipt from {school_name}. "
        f"Generated {date.today().strftime(\'%d %b %Y\')} by Mastex SchoolOS.",
        ParagraphStyle("FT", parent=center, fontSize=7.5, textColor=colors.HexColor("#aaaaaa"), spaceBefore=4)
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer.read()
''')


# ─────────────────────────────────────────────────────────────────────────────
# 4.  Partial payment view  (operations/partial_payment_views.py)
# ─────────────────────────────────────────────────────────────────────────────
w("operations/partial_payment_views.py", '''"""
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
''')


# ─────────────────────────────────────────────────────────────────────────────
# 5.  URL patches
# ─────────────────────────────────────────────────────────────────────────────

# Patch academics/urls.py – add download_report_card + ai_comment_page
academics_urls_path = BASE / "academics" / "urls.py"
original = academics_urls_path.read_text(encoding="utf-8")

additions = """
# ── Auto-added by write_views.py ─────────────────────────────────────────────
from academics.pdf_report import generate_report_card_pdf, generate_bulk_report_cards
from academics.ai_comment_views import ai_comment_page
"""

if "download_report_card" not in original:
    # Append new patterns at the end
    new_patterns = """
    path('report-card/<int:student_id>/pdf/', generate_report_card_pdf, name='download_report_card'),
    path('report-card/<int:student_id>/enhanced/', lambda req, student_id: __import__('academics.views', fromlist=['enhanced_report_card']).enhanced_report_card(req, student_id), name='enhanced_report_card'),
    path('report-cards/bulk/', generate_bulk_report_cards, name='bulk_report_cards'),
    path('ai-comment/', ai_comment_page, name='ai_comment_page'),
"""
    # Insert before the closing bracket
    if "urlpatterns = [" in original:
        idx = original.rfind("]")
        patched = original[:idx] + new_patterns + original[idx:]
        # Also add the imports at the top
        patched = patched.replace(
            "from django.urls import path",
            "from django.urls import path\n" + additions.strip(),
            1
        )
        academics_urls_path.write_text(patched, encoding="utf-8")
        print("  patched academics/urls.py")
    else:
        print("  WARNING: could not patch academics/urls.py – urlpatterns not found")
else:
    print("  academics/urls.py already has download_report_card")

# Patch accounts/urls.py – add superadmin_metrics
accounts_urls_path = BASE / "accounts" / "urls.py"
accounts_original = accounts_urls_path.read_text(encoding="utf-8")
if "superadmin_metrics" not in accounts_original:
    from_line = "from accounts.superadmin_views import superadmin_metrics\n"
    new_url = "    path('super/metrics/', superadmin_metrics, name='superadmin_metrics'),\n"
    patched = accounts_original.replace(
        "from django.urls import path",
        "from django.urls import path\n" + from_line,
        1
    )
    idx = patched.rfind("]")
    patched = patched[:idx] + new_url + patched[idx:]
    accounts_urls_path.write_text(patched, encoding="utf-8")
    print("  patched accounts/urls.py")
else:
    print("  accounts/urls.py already has superadmin_metrics")

# Patch operations/urls.py – add receipt + partial payment
ops_urls_path = BASE / "operations" / "urls.py"
ops_original = ops_urls_path.read_text(encoding="utf-8")
if "receipt_pdf" not in ops_original:
    from_line = (
        "from operations.receipt_views import receipt_view, receipt_pdf_view\n"
        "from operations.partial_payment_views import partial_payment_page\n"
    )
    new_urls = (
        "    path('receipt/<int:payment_id>/', receipt_view, name='receipt'),\n"
        "    path('receipt/<int:payment_id>/pdf/', receipt_pdf_view, name='receipt_pdf'),\n"
        "    path('pay/<str:fee_type>/', partial_payment_page, name='partial_payment'),\n"
        "    path('pay/', partial_payment_page, name='partial_payment_default'),\n"
    )
    patched = ops_original.replace(
        "from django.urls import path",
        "from django.urls import path\n" + from_line,
        1
    )
    idx = patched.rfind("]")
    patched = patched[:idx] + new_urls + patched[idx:]
    ops_urls_path.write_text(patched, encoding="utf-8")
    print("  patched operations/urls.py")
else:
    print("  operations/urls.py already has receipt_pdf")

print("\\nAll view files and URL patches written successfully.")
