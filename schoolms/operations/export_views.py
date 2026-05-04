"""
Export views for Operations module.
Provides CSV/Excel export functionality for all list views.
"""
import csv

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, F
from django.http import HttpResponse, StreamingHttpResponse
from django.utils import timezone
from datetime import timedelta

from accounts.decorators import role_required, permission_required
from accounts.permissions import can_export_data
from schools.models import School
from students.models import Student
from accounts.models import User
from students.models import StudentDiscipline
from .models import (
    StudentAttendance, TeacherAttendance, Expense, ExpenseCategory,
    LibraryBook, LibraryIssue, InventoryItem,
    InventoryCategory, Announcement, HostelAssignment, HostelFee,
    Certificate, AdmissionApplication, Budget
)
from core.export_utils import _Echo, export_to_csv, export_to_excel, export_to_zip
from core.academic_context import get_current_term_for_school
from .models import CanteenItem, CanteenPayment, BusRoute, BusPayment, Textbook, TextbookSale, HostelFee, HostelAssignment


from core.utils import get_school as _get_school


def _require_school(request):
    school = _get_school(request)
    if not school and not request.user.is_superuser:
        return None
    return school


def _fee_payment_export_scope(request, default_days: int = 90):
    """
    Build a time filter for completed fee payment exports.
    If GET ``start`` and ``end`` are valid ISO dates (YYYY-MM-DD), use inclusive calendar dates (max span 730).
    Otherwise use rolling window ``days`` (1–730, default ``default_days``).
    Returns (filter_callable, filename_tag).
    """
    from django.utils.dateparse import parse_date

    start_s = (request.GET.get("start") or "").strip()
    end_s = (request.GET.get("end") or "").strip()
    today = timezone.localdate()

    if start_s and end_s:
        sd = parse_date(start_s)
        ed = parse_date(end_s)
        if sd and ed:
            if sd > ed:
                sd, ed = ed, sd
            if (ed - sd).days > 730:
                sd = ed - timedelta(days=730)
            if ed > today:
                ed = today
            if sd > ed:
                sd = ed

            def apply_calendar(qs):
                return qs.filter(created_at__date__gte=sd, created_at__date__lte=ed)

            return apply_calendar, f"{sd.isoformat()}_{ed.isoformat()}"

    try:
        days = int(request.GET.get("days", str(default_days)))
        days = max(1, min(days, 730))
    except ValueError:
        days = default_days

    min_dt = timezone.now() - timedelta(days=days)

    def apply_rolling(qs):
        return qs.filter(created_at__gte=min_dt)

    return apply_rolling, f"last{days}d_{timezone.now().date().isoformat()}"


# ==================== EXPORT VIEWS ====================

@login_required
@permission_required(can_export_data)
def export_students(request):
    """Export students list to CSV/Excel."""
    school = _require_school(request)
    if not school:
        return redirect("home")
    
    students = Student.objects.filter(school=school).select_related("user").order_by("class_name", "admission_number")
    
    fields = [
        ("Admission No.", "admission_number"),
        ("First Name", "user__first_name"),
        ("Last Name", "user__last_name"),
        ("Email", "user__email"),
        ("Phone", "user__phone"),
        ("Class", "class_name"),
        ("Gender", "gender"),
        ("Status", "status"),
        ("Date Enrolled", "date_enrolled"),
    ]
    
    fmt = request.GET.get("format", "csv")
    if fmt == "excel":
        return export_to_excel(students, fields, f"students_{school.name.replace(' ', '_')}.xlsx")
    return export_to_csv(students, fields, f"students_{school.name.replace(' ', '_')}.csv")


@login_required
@permission_required(can_export_data)
def export_staff(request):
    """Export staff list to CSV/Excel."""
    school = _require_school(request)
    if not school:
        return redirect("home")
    
    staff = User.objects.filter(school=school).exclude(role="student").exclude(role="parent").select_related().order_by("role", "first_name")
    
    fields = [
        ("Employee ID", "username"),
        ("First Name", "first_name"),
        ("Last Name", "last_name"),
        ("Email", "email"),
        ("Phone", "phone"),
        ("Role", "role"),
        ("Status", "is_active"),
    ]
    
    fmt = request.GET.get("format", "csv")
    if fmt == "excel":
        return export_to_excel(staff, fields, f"staff_{school.name.replace(' ', '_')}.xlsx")
    return export_to_csv(staff, fields, f"staff_{school.name.replace(' ', '_')}.csv")


@login_required
def export_staff_payroll_school(request):
    """CSV export of all staff payroll lines for the school (finance role)."""
    from accounts.permissions import can_manage_finance
    from accounts.hr_models import StaffPayrollPayment
    from accounts.hr_utils import sync_expired_staff_contracts
    from django.utils.dateparse import parse_date
    import csv

    if not can_manage_finance(request.user):
        return redirect("home")
    school = _require_school(request)
    if not school:
        return redirect("home")

    sync_expired_staff_contracts(school=school)
    qs = StaffPayrollPayment.objects.filter(school=school).select_related("user", "recorded_by").order_by(
        "-paid_on", "-id"
    )
    fd = request.GET.get("from")
    td = request.GET.get("to")
    if fd:
        d = parse_date(fd)
        if d:
            qs = qs.filter(paid_on__gte=d)
    if td:
        d = parse_date(td)
        if d:
            qs = qs.filter(paid_on__lte=d)

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    sub = (school.subdomain or str(school.pk)).replace("/", "-")
    response["Content-Disposition"] = f'attachment; filename="staff-payroll-school-{sub}.csv"'
    w = csv.writer(response)
    w.writerow(
        [
            "paid_on",
            "username",
            "staff_name",
            "period_label",
            "amount",
            "currency",
            "method",
            "reference",
            "recorded_by",
            "notes",
        ]
    )
    for p in qs.iterator():
        w.writerow(
            [
                p.paid_on.isoformat(),
                p.user.username,
                p.user.get_full_name() or "",
                p.period_label,
                str(p.amount),
                p.currency,
                p.get_method_display(),
                p.reference,
                (p.recorded_by.get_full_name() or p.recorded_by.username) if p.recorded_by else "",
                (p.notes or "").replace("\n", " ")[:500],
            ]
        )
    return response


@login_required
@permission_required(can_export_data)
def export_attendance(request):
    """Export student attendance to CSV/Excel."""
    school = _require_school(request)
    if not school:
        return redirect("home")
    
    from datetime import datetime, timedelta
    from django.utils.dateparse import parse_date
    
    # Get date filters
    from_date = request.GET.get("from")
    to_date = request.GET.get("to")
    
    qs = StudentAttendance.objects.filter(school=school).select_related("student", "student__user")
    
    if from_date:
        parsed = parse_date(from_date)
        if parsed:
            qs = qs.filter(date__gte=parsed)
    if to_date:
        parsed = parse_date(to_date)
        if parsed:
            qs = qs.filter(date__lte=parsed)
    
    fields = [
        ("Date", "date"),
        ("Admission No.", "student__admission_number"),
        ("Student Name", "student__user__first_name"),
        ("Class", "student__class_name"),
        ("Status", "status"),
        ("Remarks", "remarks"),
    ]
    
    fmt = request.GET.get("format", "csv")
    if fmt == "excel":
        return export_to_excel(qs, fields, "student_attendance.xlsx")
    return export_to_csv(qs, fields, "student_attendance.csv")


@login_required
@permission_required(can_export_data)
def export_expenses(request):
    """Export expenses to CSV/Excel."""
    school = _require_school(request)
    if not school:
        return redirect("home")
    
    expenses = Expense.objects.filter(school=school).select_related("category", "recorded_by").order_by("-expense_date")
    
    fields = [
        ("Date", "expense_date"),
        ("Category", "category__name"),
        ("Description", "description"),
        ("Amount", "amount"),
        ("Vendor", "vendor"),
        ("Payment Method", "payment_method"),
        ("Status", "status"),
    ]
    
    fmt = request.GET.get("format", "csv")
    if fmt == "excel":
        return export_to_excel(expenses, fields, "expenses.xlsx")
    return export_to_csv(expenses, fields, "expenses.csv")


@login_required
@permission_required(can_export_data)
def export_fees(request):
    """Export fees to CSV/Excel."""
    from finance.models import Fee
    
    school = _require_school(request)
    if not school:
        return redirect("home")
    
    fees = Fee.objects.filter(school=school).select_related("student", "student__user").order_by("-id")
    
    fields = [
        ("Admission No.", "student__admission_number"),
        ("Student Name", "student__user__first_name"),
        ("Class", "student__class_name"),
        ("Amount", "amount"),
        ("Term", "term"),
        ("Status", "payment_status_display"),
    ]
    
    fmt = request.GET.get("format", "csv")
    if fmt == "excel":
        return export_to_excel(fees, fields, "school_fees.xlsx")
    return export_to_csv(fees, fields, "school_fees.csv")


@login_required
@permission_required(can_export_data)
def export_fee_payments_ledger(request):
    """
    Completed school fee payments (FeePayment rows) for accounting / reconciliation.
    Includes suggested debit/credit labels for manual GL mapping — not double-entry postings.
    """
    from django.conf import settings

    from finance.models import FeePayment

    school = _require_school(request)
    if not school:
        return redirect("home")

    apply_range, tag = _fee_payment_export_scope(request, default_days=90)
    base = FeePayment.objects.filter(fee__school=school, status="completed").select_related(
        "fee", "fee__student", "fee__student__user", "fee__term", "fee__fee_structure"
    )
    qs = apply_range(base).order_by("created_at", "id")

    currency = getattr(settings, "PAYSTACK_CURRENCY", "GHS") or "GHS"
    safe_sub = "".join(c if c.isalnum() or c in "-_" else "_" for c in (school.subdomain or "school"))[:48]
    filename = f"fee_payments_ledger_{safe_sub}_{tag}.csv"

    echo = _Echo()
    writer = csv.writer(echo)

    headers = [
        "posted_at",
        "currency",
        "payment_id",
        "fee_id",
        "amount_net",
        "amount_gross",
        "payment_method",
        "paystack_reference",
        "paystack_payment_id",
        "student_admission_no",
        "student_name",
        "class_name",
        "term_name",
        "fee_type",
        "suggested_debit_account",
        "suggested_credit_account",
        "memo",
    ]

    def _name(stu):
        if not stu:
            return ""
        u = getattr(stu, "user", None)
        if not u:
            return ""
        fn = (u.get_full_name() or "").strip()
        return fn or (u.username or "")

    def rows():
        yield "\ufeff" + writer.writerow(headers)
        for p in qs.iterator(chunk_size=500):
            fee = p.fee
            stu = fee.student if fee else None
            term = fee.term if fee else None
            fs = fee.fee_structure if fee else None
            ref = (p.paystack_reference or "").strip()
            memo = f"School fee payment{f' ref {ref}' if ref else ''} fee #{fee.pk}" if fee else f"Payment #{p.pk}"
            yield writer.writerow(
                [
                    timezone.localtime(p.created_at).strftime("%Y-%m-%d %H:%M:%S"),
                    currency,
                    p.pk,
                    fee.pk if fee else "",
                    str(p.amount),
                    str(p.gross_amount) if p.gross_amount is not None else "",
                    p.payment_method or "",
                    p.paystack_reference or "",
                    p.paystack_payment_id or "",
                    getattr(stu, "admission_number", "") or "",
                    _name(stu),
                    getattr(stu, "class_name", "") or "",
                    term.name if term else "",
                    fs.name if fs else "",
                    "Bank / clearing (cash)",
                    "Student fees receivable",
                    memo,
                ]
            )

    resp = StreamingHttpResponse(rows(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@login_required
@permission_required(can_export_data)
def export_fee_payments_journal(request):
    """
    Two CSV lines per completed payment: debit cash / clearing, credit receivable.
    Map ``account`` to your chart of accounts in the import tool — labels are suggestions only.
    """
    from django.conf import settings

    from finance.models import FeePayment

    school = _require_school(request)
    if not school:
        return redirect("home")

    apply_range, tag = _fee_payment_export_scope(request, default_days=90)
    base = FeePayment.objects.filter(fee__school=school, status="completed").select_related(
        "fee", "fee__student", "fee__student__user", "fee__term", "fee__fee_structure"
    )
    qs = apply_range(base).order_by("created_at", "id")

    currency = getattr(settings, "PAYSTACK_CURRENCY", "GHS") or "GHS"
    safe_sub = "".join(c if c.isalnum() or c in "-_" else "_" for c in (school.subdomain or "school"))[:48]
    filename = f"fee_payments_journal_{safe_sub}_{tag}.csv"

    echo = _Echo()
    writer = csv.writer(echo)

    headers = [
        "posted_date",
        "journal_reference",
        "account",
        "debit",
        "credit",
        "currency",
        "payment_id",
        "fee_id",
        "memo",
    ]

    def _name(stu):
        if not stu:
            return ""
        u = getattr(stu, "user", None)
        if not u:
            return ""
        fn = (u.get_full_name() or "").strip()
        return fn or (u.username or "")

    dr_acct = "Bank / clearing (cash)"
    cr_acct = "Student fees receivable"

    def rows():
        yield "\ufeff" + writer.writerow(headers)
        for p in qs.iterator(chunk_size=500):
            fee = p.fee
            stu = fee.student if fee else None
            ref = (p.paystack_reference or "").strip()
            jref = f"FEE-PAY-{p.pk}"
            posted = timezone.localtime(p.created_at).strftime("%Y-%m-%d")
            memo = f"Fee payment {jref}"
            if ref:
                memo += f" ref {ref}"
            if stu:
                memo += f" — {_name(stu)}"
            amt = str(p.amount)
            yield writer.writerow([posted, jref, dr_acct, amt, "", currency, p.pk, fee.pk if fee else "", memo])
            yield writer.writerow([posted, jref, cr_acct, "", amt, currency, p.pk, fee.pk if fee else "", memo])

    resp = StreamingHttpResponse(rows(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@login_required
@permission_required(can_export_data)
def export_open_fee_balances(request):
    """Open fee lines (amount still owed) for AR / aging alignment outside the app."""
    from finance.models import Fee

    school = _require_school(request)
    if not school:
        return redirect("home")

    qs = (
        Fee.objects.filter(school=school)
        .filter(amount_paid__lt=F("amount"))
        .select_related("student", "student__user", "term", "fee_structure")
        .order_by("created_at", "id")
    )

    safe_sub = "".join(c if c.isalnum() or c in "-_" else "_" for c in (school.subdomain or "school"))[:48]
    filename = f"open_fee_balances_{safe_sub}_{timezone.now().date()}.csv"

    echo = _Echo()
    writer = csv.writer(echo)

    headers = [
        "fee_id",
        "invoice_date",
        "currency",
        "fee_amount",
        "amount_paid",
        "outstanding",
        "student_admission_no",
        "student_name",
        "class_name",
        "term_name",
        "fee_type",
        "suggested_balance_sheet_line",
        "memo",
    ]

    def _name(stu):
        if not stu:
            return ""
        u = getattr(stu, "user", None)
        if not u:
            return ""
        fn = (u.get_full_name() or "").strip()
        return fn or (u.username or "")

    currency = "GHS"

    def rows():
        yield "\ufeff" + writer.writerow(headers)
        for fee in qs.iterator(chunk_size=500):
            stu = fee.student
            out = float(fee.amount) - float(fee.amount_paid or 0)
            term = fee.term
            fs = fee.fee_structure
            yield writer.writerow(
                [
                    fee.pk,
                    timezone.localtime(fee.created_at).strftime("%Y-%m-%d"),
                    currency,
                    str(fee.amount),
                    str(fee.amount_paid),
                    f"{out:.2f}",
                    getattr(stu, "admission_number", "") if stu else "",
                    _name(stu),
                    getattr(stu, "class_name", "") if stu else "",
                    term.name if term else "",
                    fs.name if fs else "",
                    "Student fees receivable",
                    f"Open fee #{fee.pk}",
                ]
            )

    resp = StreamingHttpResponse(rows(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@login_required
@permission_required(can_export_data)
def export_library_books(request):
    """Export library books to CSV/Excel."""
    school = _require_school(request)
    if not school:
        return redirect("home")
    
    books = LibraryBook.objects.filter(school=school).order_by("title")
    
    fields = [
        ("ISBN", "isbn"),
        ("Title", "title"),
        ("Author", "author"),
        ("Publisher", "publisher"),
        ("Category", "category"),
        ("Total Copies", "total_copies"),
        ("Available", "available_copies"),
    ]
    
    fmt = request.GET.get("format", "csv")
    if fmt == "excel":
        return export_to_excel(books, fields, "library_books.xlsx")
    return export_to_csv(books, fields, "library_books.csv")


@login_required
@permission_required(can_export_data)
def export_library_issues(request):
    """Export library issues to CSV/Excel."""
    school = _require_school(request)
    if not school:
        return redirect("home")
    
    issues = LibraryIssue.objects.filter(school=school).select_related("student", "student__user", "book").order_by("-issue_date")
    
    fields = [
        ("Issue Date", "issue_date"),
        ("Due Date", "due_date"),
        ("Return Date", "return_date"),
        ("Student", "student__user__first_name"),
        ("Admission No.", "student__admission_number"),
        ("Book", "book__title"),
        ("Status", "status"),
    ]
    
    fmt = request.GET.get("format", "csv")
    if fmt == "excel":
        return export_to_excel(issues, fields, "library_issues.xlsx")
    return export_to_csv(issues, fields, "library_issues.csv")


@login_required
@permission_required(can_export_data)
def export_discipline(request):
    """Export discipline records to CSV/Excel."""
    school = _require_school(request)
    if not school:
        return redirect("home")
    
    incidents = StudentDiscipline.objects.filter(school=school).select_related("student", "student__user", "reported_by").order_by("-incident_date")
    
    fields = [
        ("Date", "incident_date"),
        ("Student", "student__user__first_name"),
        ("Admission No.", "student__admission_number"),
        ("Class", "student__class_name"),
        ("Type", "title"),
        ("Severity", "incident_type"),
        ("Description", "description"),
    ]
    
    fmt = request.GET.get("format", "csv")
    if fmt == "excel":
        return export_to_excel(incidents, fields, "discipline_records.xlsx")
    return export_to_csv(incidents, fields, "discipline_records.csv")


@login_required
@permission_required(can_export_data)
def export_inventory(request):
    """Export inventory items to CSV/Excel."""
    school = _require_school(request)
    if not school:
        return redirect("home")
    
    items = InventoryItem.objects.filter(school=school).select_related("category").order_by("name")
    
    fields = [
        ("Name", "name"),
        ("Category", "category__name"),
        ("Quantity", "quantity"),
        ("Min Quantity", "min_quantity"),
        ("Unit Cost", "unit_cost"),
        ("Condition", "condition"),
        ("Location", "location"),
    ]
    
    fmt = request.GET.get("format", "csv")
    if fmt == "excel":
        return export_to_excel(items, fields, "inventory.xlsx")
    return export_to_csv(items, fields, "inventory.csv")


@login_required
@permission_required(can_export_data)
def export_announcements(request):
    """Export announcements to CSV/Excel."""
    school = _require_school(request)
    if not school:
        return redirect("home")
    
    announcements = Announcement.objects.filter(school=school).select_related("created_by").order_by("-created_at")
    
    fields = [
        ("Date", "created_at"),
        ("Title", "title"),
        ("Content", "content"),
        ("Audience", "target_audience"),
        ("Created By", "created_by__first_name"),
        ("Pinned", "is_pinned"),
    ]
    
    fmt = request.GET.get("format", "csv")
    if fmt == "excel":
        return export_to_excel(announcements, fields, "announcements.xlsx")
    return export_to_csv(announcements, fields, "announcements.csv")


@login_required
@permission_required(can_export_data)
def export_admissions(request):
    """Export admission applications to CSV/Excel."""
    school = _require_school(request)
    if not school:
        return redirect("home")
    
    apps = AdmissionApplication.objects.all()
    if school:
        apps = apps.filter(school=school)
    
    apps = apps.select_related("school", "reviewed_by").order_by("-applied_at")
    
    fields = [
        ("Reference", "public_reference"),
        ("Applied At", "applied_at"),
        ("First Name", "first_name"),
        ("Last Name", "last_name"),
        ("Date of Birth", "date_of_birth"),
        ("Class Applied", "class_applied_for"),
        ("Parent Name", "parent_first_name"),
        ("Parent Phone", "parent_phone"),
        ("Status", "status"),
    ]
    
    fmt = request.GET.get("format", "csv")
    if fmt == "excel":
        return export_to_excel(apps, fields, "admissions.xlsx")
    return export_to_csv(apps, fields, "admissions.csv")


@login_required
@permission_required(can_export_data)
def export_health_records(request):
    """Export health records to CSV/Excel."""
    from .models import HealthVisit
    school = _require_school(request)
    if not school:
        return redirect("home")
    
    records = HealthVisit.objects.filter(school=school).select_related("student", "student__user").order_by("-visit_date")
    
    fields = [
        ("Date", "visit_date"),
        ("Student", "student__user__first_name"),
        ("Admission No.", "student__admission_number"),
        ("Reason", "reason"),
        ("Action Taken", "action_taken"),
        ("Notes", "notes"),
    ]
    
    fmt = request.GET.get("format", "csv")
    if fmt == "excel":
        return export_to_excel(records, fields, "health_records.xlsx")
    return export_to_csv(records, fields, "health_records.csv")


@login_required
@permission_required(can_export_data)
def export_budgets(request):
    """Export budgets to CSV/Excel."""
    school = _require_school(request)
    if not school:
        return redirect("home")
    
    budgets = Budget.objects.filter(school=school).select_related("category").order_by("-created_at")
    
    fields = [
        ("Category", "category__name"),
        ("Academic Year", "academic_year"),
        ("Term", "term"),
        ("Allocated Amount", "allocated_amount"),
        ("Spent Amount", "spent_amount"),
    ]
    
    fmt = request.GET.get("format", "csv")
    if fmt == "excel":
        return export_to_excel(budgets, fields, "budgets.xlsx")
    return export_to_csv(budgets, fields, "budgets.csv")


@login_required
@permission_required(can_export_data)
def export_online_exams(request):
    """Export online exams to CSV/Excel."""
    from .models import OnlineExam
    school = _require_school(request)
    if not school:
        return redirect("home")
    
    exams = OnlineExam.objects.filter(school=school).select_related("subject", "created_by").order_by("-created_at")
    
    fields = [
        ("Title", "title"),
        ("Subject", "subject__name"),
        ("Class", "class_level"),
        ("Duration (min)", "duration_minutes"),
        ("Total Marks", "total_marks"),
        ("Status", "status"),
        ("Created", "created_at"),
    ]
    
    fmt = request.GET.get("format", "csv")
    if fmt == "excel":
        return export_to_excel(exams, fields, "online_exams.xlsx")
    return export_to_csv(exams, fields, "online_exams.csv")


@login_required
@permission_required(can_export_data)
def export_all_data(request):
    """Export all school data as a ZIP file."""
    school = _require_school(request)
    if not school:
        return redirect("home")
    
    # Gather all data
    students = Student.objects.filter(school=school).select_related("user")
    staff = User.objects.filter(school=school).exclude(role="student").exclude(role="parent")
    fees = Fee.objects.filter(school=school).select_related("student")
    expenses = Expense.objects.filter(school=school).select_related("category")
    
    from finance.models import Fee
    
    exports = []
    
    # Students
    exports.append({
        "queryset": students,
        "fields": [
            ("Admission No.", "admission_number"),
            ("First Name", "user__first_name"),
            ("Last Name", "user__last_name"),
            ("Class", "class_name"),
            ("Status", "status"),
        ],
        "name": "students",
        "format": request.GET.get("format", "csv")
    })
    
    # Staff
    exports.append({
        "queryset": staff,
        "fields": [
            ("Name", "first_name"),
            ("Role", "role"),
            ("Email", "email"),
        ],
        "name": "staff",
        "format": request.GET.get("format", "csv")
    })
    
    # Fees
    exports.append({
        "queryset": fees,
        "fields": [
            ("Student", "student__user__first_name"),
            ("Amount", "amount"),
            ("Term", "term"),
            ("Status", "payment_status"),
        ],
        "name": "fees",
        "format": request.GET.get("format", "csv")
    })
    
    # Expenses
    exports.append({
        "queryset": expenses,
        "fields": [
            ("Date", "expense_date"),
            ("Description", "description"),
            ("Amount", "amount"),
        ],
        "name": "expenses",
        "format": request.GET.get("format", "csv")
    })

    from accounts.permissions import can_manage_finance
    if can_manage_finance(request.user):
        from accounts.hr_models import StaffPayrollPayment

        payroll = StaffPayrollPayment.objects.filter(school=school).select_related("user", "recorded_by")
        exports.append(
            {
                "queryset": payroll,
                "fields": [
                    ("Paid on", "paid_on"),
                    ("Username", "user__username"),
                    ("Period", "period_label"),
                    ("Amount", "amount"),
                    ("Currency", "currency"),
                    ("Method", "method"),
                ],
                "name": "staff_payroll",
                "format": request.GET.get("format", "csv"),
            }
        )

    return export_to_zip(exports, f"{school.name.replace(' ', '_')}_export.zip")


# ==================== PAYMENT EXPORT VIEWS ====================

def _filter_by_date(queryset, request, date_field='created_at'):
    """Apply day/month/year filtering to queryset."""
    from django.utils.dateparse import parse_date
    from datetime import datetime
    
    # Day filter (single date)
    day = request.GET.get("day")
    # Month filter (month number or year-month)
    month = request.GET.get("month")
    # Year filter
    year = request.GET.get("year")
    # From date
    from_date = request.GET.get("from")
    # To date
    to_date = request.GET.get("to")
    
    # If specific day is provided
    if day:
        parsed = parse_date(day)
        if parsed:
            queryset = queryset.filter(**{f"{date_field}__date": parsed})
    
    # If month is provided
    if month:
        if '-' in str(month):
            # Year-Month format
            parts = month.split('-')
            if len(parts) == 2:
                queryset = queryset.filter(**{
                    f"{date_field}__year": int(parts[0]),
                    f"{date_field}__month": int(parts[1])
                })
        else:
            # Just month number - need year context
            if year:
                queryset = queryset.filter(**{
                    f"{date_field}__year": int(year),
                    f"{date_field}__month": int(month)
                })
    
    # If only year is provided
    if year and not month:
        queryset = queryset.filter(**{f"{date_field}__year": int(year)})
    
    # From date filter
    if from_date:
        parsed = parse_date(from_date)
        if parsed:
            queryset = queryset.filter(**{f"{date_field}__gte": parsed})
    
    # To date filter
    if to_date:
        parsed = parse_date(to_date)
        if parsed:
            # End of day
            from datetime import timedelta
            end_date = parsed + timedelta(days=1)
            queryset = queryset.filter(**{f"{date_field}__lt": end_date})
    
    return queryset


@login_required
@permission_required(can_export_data)
def export_canteen_payments(request):
    """Export canteen payments to CSV/Excel with date filtering."""
    school = _require_school(request)
    if not school:
        return redirect("home")
    
    payments = CanteenPayment.objects.filter(school=school).select_related("student", "student__user", "recorded_by").order_by("-payment_date")
    payments = _filter_by_date(payments, request, 'payment_date')
    
    fields = [
        ("Date", "payment_date"),
        ("Student", "student__user__first_name"),
        ("Admission No.", "student__admission_number"),
        ("Description", "description"),
        ("Amount (GHS)", "amount"),
        ("Status", "payment_status"),
        ("Payment Ref", "payment_reference"),
    ]
    
    fmt = request.GET.get("format", "csv")
    if fmt == "excel":
        return export_to_excel(payments, fields, "canteen_payments.xlsx")
    return export_to_csv(payments, fields, "canteen_payments.csv")


@login_required
@permission_required(can_export_data)
def export_bus_payments(request):
    """Export bus/transport payments to CSV/Excel with date filtering."""
    school = _require_school(request)
    if not school:
        return redirect("home")
    
    payments = BusPayment.objects.filter(school=school).select_related("student", "student__user", "route").order_by("-payment_date")
    payments = _filter_by_date(payments, request, 'payment_date')
    
    fields = [
        ("Date", "payment_date"),
        ("Student", "student__user__first_name"),
        ("Admission No.", "student__admission_number"),
        ("Route", "route__name"),
        ("Amount (GHS)", "amount"),
        ("Status", "payment_status"),
        ("Paid", "paid"),
        ("Payment Ref", "payment_reference"),
    ]
    
    fmt = request.GET.get("format", "csv")
    if fmt == "excel":
        return export_to_excel(payments, fields, "bus_payments.xlsx")
    return export_to_csv(payments, fields, "bus_payments.csv")


@login_required
@permission_required(can_export_data)
def export_textbook_sales(request):
    """Export textbook sales to CSV/Excel with date filtering."""
    school = _require_school(request)
    if not school:
        return redirect("home")
    
    sales = TextbookSale.objects.filter(school=school).select_related("student", "student__user", "textbook").order_by("-sale_date")
    sales = _filter_by_date(sales, request, 'sale_date')
    
    fields = [
        ("Date", "sale_date"),
        ("Student", "student__user__first_name"),
        ("Admission No.", "student__admission_number"),
        ("Textbook", "textbook__title"),
        ("Quantity", "quantity"),
        ("Amount (GHS)", "amount"),
        ("Status", "payment_status"),
        ("Payment Ref", "payment_reference"),
    ]
    
    fmt = request.GET.get("format", "csv")
    if fmt == "excel":
        return export_to_excel(sales, fields, "textbook_sales.xlsx")
    return export_to_csv(sales, fields, "textbook_sales.csv")


@login_required
@permission_required(can_export_data)
def export_hostel_fees(request):
    """Export hostel fees to CSV/Excel with date filtering."""
    school = _require_school(request)
    if not school:
        return redirect("home")
    
    fees = HostelFee.objects.filter(school=school).select_related("student", "student__user", "hostel", "hostel__hostel").order_by("-payment_date")
    fees = _filter_by_date(fees, request, 'payment_date')
    
    fields = [
        ("Date", "payment_date"),
        ("Student", "student__user__first_name"),
        ("Admission No.", "student__admission_number"),
        ("Hostel", "hostel__hostel__name"),
        ("Room", "hostel__room_number"),
        ("Amount (GHS)", "amount"),
        ("Term", "term"),
        ("Amount Paid", "amount_paid"),
        ("Status", "payment_status_display"),
        ("Paid", "paid"),
    ]
    
    fmt = request.GET.get("format", "csv")
    if fmt == "excel":
        return export_to_excel(fees, fields, "hostel_fees.xlsx")
    return export_to_csv(fees, fields, "hostel_fees.csv")


@login_required
@permission_required(can_export_data)
def export_all_payments(request):
    """Export all payment types to CSV/Excel with date filtering."""
    school = _require_school(request)
    if not school:
        return redirect("home")
    
    from finance.models import Fee, FeePayment
    
    # Get payment type filter
    payment_type = request.GET.get('payment_type', 'all')
    
    # Get date filter (for compatibility with payment dashboard)
    date_filter = request.GET.get('date_filter', 'all')
    start_date = request.GET.get('start_date') or request.GET.get('from')
    end_date = request.GET.get('end_date') or request.GET.get('to')
    
    # Helper function to apply date filter
    def apply_date_filter(queryset, date_field):
        from django.utils import timezone
        if date_filter == 'today':
            today = timezone.now().date()
            return queryset.filter(**{f"{date_field}__date": today})
        elif date_filter == 'week':
            week_ago = (timezone.now() - timezone.timedelta(days=7)).date()
            return queryset.filter(**{f"{date_field}__gte": week_ago})
        elif date_filter == 'month':
            month_ago = (timezone.now() - timezone.timedelta(days=30)).date()
            return queryset.filter(**{f"{date_field}__gte": month_ago})
        elif date_filter == 'term':
            current_term = get_current_term_for_school(school)
            if current_term and current_term.start_date:
                queryset = queryset.filter(**{f"{date_field}__gte": current_term.start_date})
                if current_term.end_date:
                    queryset = queryset.filter(**{f"{date_field}__lte": current_term.end_date})
            return queryset
        elif start_date:
            from django.utils.dateparse import parse_date
            parsed = parse_date(start_date)
            if parsed:
                queryset = queryset.filter(**{f"{date_field}__date__gte": parsed})
        if end_date:
            from django.utils.dateparse import parse_date
            from datetime import timedelta
            parsed = parse_date(end_date)
            if parsed:
                end_with_time = parsed + timedelta(days=1)
                queryset = queryset.filter(**{f"{date_field}__lt": end_with_time})
        return queryset
    
    # Get all payment types based on filter (only completed payments)
    canteen_payments = CanteenPayment.objects.filter(school=school, payment_status='completed').select_related("student", "student__user", "recorded_by")
    bus_payments = BusPayment.objects.filter(school=school, paid=True).select_related("student", "student__user", "route")
    textbook_sales = TextbookSale.objects.filter(school=school, payment_status='completed').select_related("student", "student__user", "textbook")
    hostel_fees = HostelFee.objects.filter(school=school, paid=True).select_related("student", "student__user")
    school_fees = Fee.objects.filter(school=school).select_related("student", "student__user")
    fee_payments = FeePayment.objects.filter(fee__school=school).select_related("fee", "fee__student", "fee__student__user")
    
    # Apply date filtering - use appropriate date fields for each payment type
    canteen_payments = apply_date_filter(canteen_payments, 'payment_date')
    bus_payments = apply_date_filter(bus_payments, 'payment_date')
    textbook_sales = apply_date_filter(textbook_sales, 'sale_date')
    hostel_fees = apply_date_filter(hostel_fees, 'payment_date')
    school_fees = apply_date_filter(school_fees, 'created_at')
    fee_payments = apply_date_filter(fee_payments, 'created_at')
    
    # Combine all payments into one list with type annotation
    all_payments = []
    
    # Add canteen payments if 'all' or 'canteen' is selected
    if payment_type in ['all', 'canteen']:
        for p in canteen_payments:
            all_payments.append({
                'date': p.payment_date,
                'student': p.student.user.get_full_name() if p.student and p.student.user else '',
                'admission_no': p.student.admission_number if p.student else '',
                'type': 'Canteen',
                'description': p.description,
                'amount': float(p.amount),
                'status': p.payment_status,
            })
    
    # Add bus payments if 'all' or 'bus' is selected
    if payment_type in ['all', 'bus']:
        for p in bus_payments:
            # Use payment_date if available, otherwise try created_at as fallback
            payment_date = p.payment_date if p.payment_date else getattr(p, 'created_at', None)
            all_payments.append({
                'date': payment_date,
                'student': p.student.user.get_full_name() if p.student and p.student.user else '',
                'admission_no': p.student.admission_number if p.student else '',
                'type': 'Bus',
                'description': p.route.name if p.route else '',
                'amount': float(p.amount),
                'status': p.payment_status,
            })
    
    # Add textbook sales if 'all' or 'textbook' is selected
    if payment_type in ['all', 'textbook']:
        for p in textbook_sales:
            # Use sale_date if available, otherwise try created_at as fallback
            sale_date = p.sale_date if p.sale_date else getattr(p, 'created_at', None)
            all_payments.append({
                'date': sale_date,
                'student': p.student.user.get_full_name() if p.student and p.student.user else '',
                'admission_no': p.student.admission_number if p.student else '',
                'type': 'Textbook',
                'description': p.textbook.title if p.textbook else '',
                'amount': float(p.amount),
                'status': p.payment_status,
            })
    
    # Add hostel fees if 'all' or 'hostel' is selected
    if payment_type in ['all', 'hostel']:
        for p in hostel_fees:
            # Use payment_date if available, otherwise try created_at as fallback
            payment_date = p.payment_date if p.payment_date else getattr(p, 'created_at', None)
            all_payments.append({
                'date': payment_date,
                'student': p.student.user.get_full_name() if p.student and p.student.user else '',
                'admission_no': p.student.admission_number if p.student else '',
                'type': 'Hostel',
                'description': f"{p.hostel.hostel.name} - {p.hostel.room_number}" if p.hostel else '',
                'amount': float(p.amount),
                'status': 'Paid' if p.paid else 'Unpaid',
            })
    
    # Add school fee payments if 'all' or 'school_fees' is selected
    if payment_type in ['all', 'school_fees']:
        for p in fee_payments:
            # Use created_at for FeePayment (this is the correct field)
            payment_date = p.created_at if hasattr(p, 'created_at') and p.created_at else None
            all_payments.append({
                'date': payment_date,
                'student': p.fee.student.user.get_full_name() if p.fee and p.fee.student and p.fee.student.user else '',
                'admission_no': p.fee.student.admission_number if p.fee and p.fee.student else '',
                'type': 'School Fee',
                'description': (p.fee.fee_structure.name if p.fee.fee_structure else '') if p.fee else '',
                'amount': float(p.amount),
                'status': 'Completed',
            })
    
    # Sort by date descending
    all_payments.sort(key=lambda x: x['date'] if x['date'] else '', reverse=True)
    
    fields = [
        ("Date", "date"),
        ("Student Name", "student"),
        ("Admission No.", "admission_no"),
        ("Payment Type", "type"),
        ("Description", "description"),
        ("Amount (GHS)", "amount"),
        ("Status", "status"),
    ]
    
    fmt = request.GET.get("format", "csv")
    if fmt == "excel":
        return export_to_excel(all_payments, fields, "all_payments.xlsx")
    return export_to_csv(all_payments, fields, "all_payments.csv")
