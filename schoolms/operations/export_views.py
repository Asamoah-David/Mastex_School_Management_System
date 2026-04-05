"""
Export views for Operations module.
Provides CSV/Excel export functionality for all list views.
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpResponse

from accounts.decorators import role_required
from schools.models import School
from students.models import Student
from accounts.models import User
from .models import (
    StudentAttendance, TeacherAttendance, Expense, ExpenseCategory,
    DisciplineIncident, LibraryBook, LibraryIssue, InventoryItem,
    InventoryCategory, Announcement, HostelAssignment, HostelFee,
    Certificate, AdmissionApplication, Budget
)
from core.export_utils import export_to_csv, export_to_excel, export_to_zip
from .models import CanteenItem, CanteenPayment, BusRoute, BusPayment, Textbook, TextbookSale, HostelFee, HostelAssignment


def _get_school(request):
    """Get current user's school."""
    if not request.user.is_authenticated:
        return None
    return getattr(request.user, "school", None)


def _require_school(request):
    school = _get_school(request)
    if not school and not request.user.is_superuser:
        return None
    return school


# ==================== EXPORT VIEWS ====================

@login_required
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
        ("Status", "payment_status"),
    ]
    
    fmt = request.GET.get("format", "csv")
    if fmt == "excel":
        return export_to_excel(fees, fields, "school_fees.xlsx")
    return export_to_csv(fees, fields, "school_fees.csv")


@login_required
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
def export_discipline(request):
    """Export discipline records to CSV/Excel."""
    school = _require_school(request)
    if not school:
        return redirect("home")
    
    incidents = DisciplineIncident.objects.filter(school=school).select_related("student", "student__user", "reported_by").order_by("-incident_date")
    
    fields = [
        ("Date", "incident_date"),
        ("Student", "student__user__first_name"),
        ("Admission No.", "student__admission_number"),
        ("Class", "student__class_name"),
        ("Type", "incident_type"),
        ("Severity", "severity"),
        ("Description", "description"),
    ]
    
    fmt = request.GET.get("format", "csv")
    if fmt == "excel":
        return export_to_excel(incidents, fields, "discipline_records.xlsx")
    return export_to_csv(incidents, fields, "discipline_records.csv")


@login_required
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
            week_ago = timezone.now() - timezone.timedelta(days=7)
            return queryset.filter(**{f"{date_field}__gte": week_ago})
        elif date_filter == 'month':
            month_ago = timezone.now() - timezone.timedelta(days=30)
            return queryset.filter(**{f"{date_field}__gte": month_ago})
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
            all_payments.append({
                'date': p.payment_date,
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
            all_payments.append({
                'date': p.sale_date,
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
            all_payments.append({
                'date': p.payment_date,
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
            all_payments.append({
                'date': p.created_at,
                'student': p.fee.student.user.get_full_name() if p.fee and p.fee.student and p.fee.student.user else '',
                'admission_no': p.fee.student.admission_number if p.fee and p.fee.student else '',
                'type': 'School Fee',
                'description': p.fee.fee_type if p.fee else '',
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
