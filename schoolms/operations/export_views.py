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
