from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q
from django.db import models
from django.utils.dateparse import parse_date
from django.utils import timezone
from django.http import HttpResponse

from schools.models import School
from students.models import Student
from accounts.models import User
from .models import (
    StudentAttendance,
    TeacherAttendance,
    AcademicCalendar,
    CanteenItem,
    CanteenPayment,
    BusRoute,
    BusPayment,
    Textbook,
    TextbookSale,
    Announcement,
    StaffLeave,
    ActivityLog,
    LibraryBook,
    LibraryIssue,
    Hostel,
    HostelRoom,
    HostelAssignment,
    HostelFee,
    AdmissionApplication,
    Certificate,
    ExpenseCategory,
    Expense,
    Budget,
    DisciplineIncident,
    BehaviorPoint,
    StudentDocument,
    Alumni,
    AlumniEvent,
    TimetableSlot,
    TimetableConflict,
    StudentIDCard,
    PTMeeting,
    PTMeetingBooking,
    Sport,
    Club,
    StudentSport,
    StudentClub,
    ExamHall,
    SeatingPlan,
    SeatAssignment,
    StudentHealth,
    HealthVisit,
    InventoryCategory,
    InventoryItem,
    InventoryTransaction,
    SchoolEvent,
    EventRSVP,
    AssignmentSubmission,
    OnlineExam,
    ExamQuestion,
    ExamAttempt,
    ExamAnswer,
)


def _get_school(request):
    """Current user's school (school admin or teacher). Platform superadmin has no school."""
    if not request.user.is_authenticated:
        return None
    return getattr(request.user, "school", None)


@login_required
def _require_school(request):
    school = _get_school(request)
    if not school and not request.user.is_superuser:
        return None
    return school


def _parse_date(value, default):
    if not value:
        return default
    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        return value
    parsed = parse_date(str(value))
    return parsed or default


@login_required
def attendance_list(request):
    school = _require_school(request)
    if not school:
        return redirect("home")
    from django.contrib import messages
    default_day = timezone.now().date()
    raw_from = request.GET.get("from")
    raw_to = request.GET.get("to")
    from_date = _parse_date(raw_from, default_day)
    to_date = _parse_date(raw_to, default_day)
    if raw_from and from_date == default_day and str(raw_from) != str(default_day):
        messages.warning(request, "Invalid 'from' date; showing today's records instead.")
    if raw_to and to_date == default_day and str(raw_to) != str(default_day):
        messages.warning(request, "Invalid 'to' date; showing today's records instead.")
    qs = StudentAttendance.objects.filter(school=school, date__gte=from_date, date__lte=to_date).select_related(
        "student", "student__user"
    )
    return render(
        request,
        "operations/attendance_list.html",
        {"attendances": qs, "school": school, "from_date": from_date, "to_date": to_date},
    )


@login_required
def attendance_mark(request):
    school = _require_school(request)
    if not school:
        return redirect("home")
    if request.method == "POST":
        from django.contrib import messages
        default_day = timezone.now().date()
        raw_date = request.POST.get("date")
        date = _parse_date(raw_date, default_day)
        if raw_date and date == default_day and str(raw_date) != str(default_day):
            messages.warning(request, "Invalid attendance date; saved for today instead.")
        for key, value in request.POST.items():
            if key.startswith("status_"):
                try:
                    student_id = key.replace("status_", "")
                    student = Student.objects.get(id=student_id, school=school)
                    StudentAttendance.objects.update_or_create(
                        student=student, date=date, defaults={"school": school, "status": value, "marked_by": request.user}
                    )
                except (Student.DoesNotExist, ValueError):
                    pass
        return redirect("operations:attendance_list")
    from django.contrib import messages
    default_day = timezone.now().date()
    raw_date = request.GET.get("date")
    date = _parse_date(raw_date, default_day)
    if raw_date and date == default_day and str(raw_date) != str(default_day):
        messages.warning(request, "Invalid date; showing today's attendance sheet instead.")
    students = list(Student.objects.filter(school=school).select_related("user").order_by("class_name", "admission_number"))
    existing = {a.student_id: a.status for a in StudentAttendance.objects.filter(school=school, date=date)}
    for s in students:
        s.attendance_status = existing.get(s.id, "present")
    return render(
        request,
        "operations/attendance_mark.html",
        {"students": students, "school": school, "date": date},
    )


@login_required
def canteen_list(request):
    school = _get_school(request)
    if not school:
        return redirect("home")
    items = CanteenItem.objects.filter(school=school)
    return render(request, "operations/canteen_list.html", {"items": items, "school": school})


@login_required
def bus_list(request):
    school = _get_school(request)
    if not school:
        return redirect("home")
    routes = BusRoute.objects.filter(school=school)
    return render(request, "operations/bus_list.html", {"routes": routes, "school": school})


@login_required
def textbook_list(request):
    school = _get_school(request)
    if not school:
        return redirect("home")
    books = Textbook.objects.filter(school=school)
    return render(request, "operations/textbook_list.html", {"books": books, "school": school})


@login_required
def attendance_edit(request, pk):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not user_can_manage_school(request.user):
        return redirect("operations:attendance_list")
    attendance = get_object_or_404(StudentAttendance, pk=pk, school=school)
    if request.method == "POST":
        status = request.POST.get("status")
        if status in ["present", "absent", "late", "excused"]:
            attendance.status = status
            attendance.save()
            from django.contrib import messages
            messages.success(request, "Attendance updated successfully!")
            return redirect("operations:attendance_list")
    return render(request, "operations/attendance_edit.html", {"attendance": attendance, "school": school})


@login_required
def attendance_delete(request, pk):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not user_can_manage_school(request.user):
        return redirect("operations:attendance_list")
    attendance = get_object_or_404(StudentAttendance, pk=pk, school=school)
    if request.method == "POST":
        attendance.delete()
        from django.contrib import messages
        messages.success(request, "Attendance record deleted successfully!")
        return redirect("operations:attendance_list")
    return render(request, "operations/confirm_delete.html", {"object": attendance, "type": "attendance record"})


@login_required
def teacher_attendance_list(request):
    school = _get_school(request)
    if not school:
        return redirect("home")
    from django.contrib import messages
    default_day = timezone.now().date()
    raw_from = request.GET.get("from")
    raw_to = request.GET.get("to")
    from_date = _parse_date(raw_from, default_day)
    to_date = _parse_date(raw_to, default_day)
    qs = TeacherAttendance.objects.filter(school=school, date__gte=from_date, date__lte=to_date).select_related(
        "teacher", "marked_by"
    )
    return render(
        request,
        "operations/teacher_attendance_list.html",
        {"attendances": qs, "school": school, "from_date": from_date, "to_date": to_date},
    )


# Academic Calendar Views
@login_required
def calendar_list(request):
    school = _get_school(request)
    if not school:
        return redirect("home")
    events = AcademicCalendar.objects.filter(school=school).order_by("start_date")
    return render(request, "operations/calendar_list.html", {"events": events, "school": school})


# Announcements
@login_required
def announcement_list(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not user_can_manage_school(request.user):
        return redirect("home")
    announcements = Announcement.objects.filter(school=school).select_related("created_by").order_by("-is_pinned", "-created_at")
    return render(request, "operations/announcement_list.html", {"announcements": announcements, "school": school})


# Staff Leave
@login_required
def staff_leave_list(request):
    school = _get_school(request)
    if not school:
        return redirect("home")
    from accounts.permissions import user_can_manage_school, is_school_admin
    if not user_can_manage_school(request.user):
        return redirect("home")
    is_admin = request.user.is_superuser or is_school_admin(request.user)
    if is_admin:
        leaves = StaffLeave.objects.filter(school=school).select_related("staff", "reviewed_by").order_by("-start_date")
    else:
        leaves = StaffLeave.objects.filter(school=school, staff=request.user).select_related("staff", "reviewed_by").order_by("-start_date")
    return render(request, "operations/staff_leave_list.html", {"leaves": leaves, "school": school, "is_admin": is_admin})


# Activity Log
@login_required
def activity_log_list(request):
    from accounts.permissions import is_school_admin
    school = _get_school(request)
    if request.user.is_superuser or getattr(request.user, "is_super_admin", False):
        logs = ActivityLog.objects.select_related("user", "school").order_by("-created_at")[:300]
        return render(request, "operations/activity_log_list.html", {"logs": logs, "school": None})
    if not school:
        return redirect("home")
    if not is_school_admin(request.user):
        return redirect("accounts:school_dashboard")
    logs = ActivityLog.objects.filter(school=school).select_related("user").order_by("-created_at")[:200]
    return render(request, "operations/activity_log_list.html", {"logs": logs, "school": school})


# Library
@login_required
def library_catalog(request):
    school = _get_school(request)
    if not school:
        return redirect("home")
    books = LibraryBook.objects.filter(school=school).order_by("title", "author")[:500]
    from accounts.permissions import user_can_manage_school
    can_manage = user_can_manage_school(request.user) or request.user.is_superuser
    return render(request, "operations/library_catalog.html", {"books": books, "school": school, "can_manage": can_manage})


@login_required
def library_manage(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not (request.user.is_superuser or user_can_manage_school(request.user)):
        return redirect("operations:library_catalog")
    books = LibraryBook.objects.filter(school=school).order_by("-created_at")[:500]
    return render(request, "operations/library_manage.html", {"books": books, "school": school})


@login_required
def library_issues(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not (request.user.is_superuser or user_can_manage_school(request.user)):
        return redirect("operations:library_catalog")
    qs = LibraryIssue.objects.filter(school=school).select_related("student", "student__user", "book", "issued_by").order_by("-issue_date")[:300]
    return render(request, "operations/library_issues.html", {"issues": qs, "school": school})


@login_required
def library_my_issues(request):
    school = _get_school(request)
    if not school:
        return redirect("home")
    role = getattr(request.user, "role", None)
    if role == "student":
        student = Student.objects.filter(user=request.user, school=school).first()
        issues = LibraryIssue.objects.filter(school=school, student=student).select_related("book").order_by("-issue_date")[:200] if student else []
        return render(request, "operations/library_my_issues.html", {"issues": issues, "school": school, "mode": "student"})
    if role == "parent":
        children = Student.objects.filter(parent=request.user, school=school)
        issues = LibraryIssue.objects.filter(school=school, student__in=children).select_related("book", "student", "student__user").order_by("-issue_date")[:300]
        return render(request, "operations/library_my_issues.html", {"issues": issues, "school": school, "mode": "parent"})
    return redirect("home")


# Hostel
@login_required
def hostel_list(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return redirect("home")
    hostels = Hostel.objects.filter(school=school).order_by("name")
    can_manage = request.user.is_superuser or user_can_manage_school(request.user)
    return render(request, "operations/hostel_list.html", {"hostels": hostels, "school": school, "can_manage": can_manage})


@login_required
def hostel_fees(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not (request.user.is_superuser or user_can_manage_school(request.user)):
        return redirect("home")
    fees = HostelFee.objects.filter(school=school).select_related("student", "student__user", "hostel").order_by("-id")[:400]
    return render(request, "operations/hostel_fees.html", {"fees": fees, "school": school})


@login_required
def hostel_my(request):
    school = _get_school(request)
    if not school:
        return redirect("home")
    role = getattr(request.user, "role", None)
    if role == "student":
        student = Student.objects.filter(user=request.user, school=school).first()
        assignment = HostelAssignment.objects.filter(school=school, student=student, is_active=True).select_related("hostel", "room").first() if student else None
        fees = HostelFee.objects.filter(school=school, student=student).select_related("hostel").order_by("-id")[:200] if student else []
        return render(request, "operations/hostel_my.html", {"school": school, "mode": "student", "student": student, "assignment": assignment, "fees": fees})
    if role == "parent":
        children = list(Student.objects.filter(parent=request.user, school=school).select_related("user").order_by("class_name", "admission_number"))
        assignments = HostelAssignment.objects.filter(school=school, student__in=children, is_active=True).select_related("student", "student__user", "hostel", "room")
        fees = HostelFee.objects.filter(school=school, student__in=children).select_related("student", "student__user", "hostel").order_by("-id")[:400] if children else []
        return render(request, "operations/hostel_my.html", {"school": school, "mode": "parent", "children": children, "assignments": assignments, "fees": fees})
    return redirect("home")


# ==================== ADMISSION APPLICATIONS ====================

def admission_apply(request):
    from schools.models import School
    schools = School.objects.filter(is_active=True).order_by('name')
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        dob = request.POST.get('date_of_birth', '').strip()
        gender = request.POST.get('gender', '').strip()
        previous_school = request.POST.get('previous_school', '').strip()
        class_applied = request.POST.get('class_applied_for', '').strip()
        parent_first = request.POST.get('parent_first_name', '').strip()
        parent_last = request.POST.get('parent_last_name', '').strip()
        parent_phone = request.POST.get('parent_phone', '').strip()
        parent_email = request.POST.get('parent_email', '').strip()
        address = request.POST.get('address', '').strip()
        school_id = request.POST.get('school')
        
        if first_name and last_name and dob and gender and class_applied and parent_first and parent_last and parent_phone and address:
            try:
                from datetime import datetime
                dob_date = datetime.strptime(dob, '%Y-%m-%d').date()
                school = None
                if school_id:
                    school = School.objects.filter(id=school_id, is_active=True).first()
                application = AdmissionApplication.objects.create(
                    school=school, first_name=first_name, last_name=last_name, date_of_birth=dob_date,
                    gender=gender, previous_school=previous_school, class_applied_for=class_applied,
                    parent_first_name=parent_first, parent_last_name=parent_last, parent_phone=parent_phone,
                    parent_email=parent_email, address=address, status='pending'
                )
                return render(request, 'operations/admission_success.html', {'application': application, 'schools': schools})
            except ValueError:
                pass
    return render(request, 'operations/admission_apply.html', {'schools': schools})


@login_required
def admission_list(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not user_can_manage_school(request.user) and not getattr(request.user, 'is_super_admin', False):
        return redirect('home')
    qs = AdmissionApplication.objects.all()
    if school:
        qs = qs.filter(school=school)
    applications = qs.select_related('school', 'reviewed_by').order_by('-applied_at')[:200]
    return render(request, 'operations/admission_list.html', {'applications': applications, 'school': school})


@login_required
def admission_detail(request, pk):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not user_can_manage_school(request.user) and not getattr(request.user, 'is_super_admin', False):
        return redirect('home')
    application = get_object_or_404(AdmissionApplication, pk=pk)
    if school and application.school and application.school != school:
        return redirect('home')
    return render(request, 'operations/admission_detail.html', {'application': application, 'school': school})


@login_required
def admission_approve(request, pk):
    from accounts.permissions import user_can_manage_school
    from django.contrib.auth.hashers import make_password
    school = _get_school(request)
    if not user_can_manage_school(request.user) and not getattr(request.user, 'is_super_admin', False):
        return redirect('home')
    application = get_object_or_404(AdmissionApplication, pk=pk)
    if school and application.school and application.school != school:
        return redirect('home')
    if request.method == 'POST':
        application.status = 'approved'
        application.reviewed_by = request.user
        application.reviewed_at = timezone.now()
        application.save()
        from django.contrib import messages
        messages.success(request, 'Application approved!')
        return redirect('operations:admission_list')
    return render(request, 'operations/admission_approve.html', {'application': application, 'school': school})


@login_required
def admission_reject(request, pk):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not user_can_manage_school(request.user) and not getattr(request.user, 'is_super_admin', False):
        return redirect('home')
    application = get_object_or_404(AdmissionApplication, pk=pk)
    if request.method == 'POST':
        application.status = 'rejected'
        application.reviewed_by = request.user
        application.reviewed_at = timezone.now()
        application.save()
        from django.contrib import messages
        messages.success(request, 'Application rejected.')
        return redirect('operations:admission_list')
    return render(request, 'operations/admission_reject.html', {'application': application})


# ==================== CERTIFICATES ====================

@login_required
def certificate_list(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not user_can_manage_school(request.user):
        return redirect('home')
    certificates = Certificate.objects.filter(school=school).select_related('student', 'student__user', 'created_by').order_by('-issued_date')[:200]
    return render(request, 'operations/certificate_list.html', {'certificates': certificates, 'school': school})


@login_required
def certificate_create(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not user_can_manage_school(request.user):
        return redirect('home')
    students = Student.objects.filter(school=school).select_related('user').order_by('class_name', 'admission_number')
    if request.method == 'POST':
        student_id = request.POST.get('student')
        cert_type = request.POST.get('certificate_type')
        title = request.POST.get('title', '').strip()
        issued_date = request.POST.get('issued_date')
        academic_year = request.POST.get('academic_year', '').strip()
        student = Student.objects.filter(id=student_id, school=school).first()
        if student and cert_type and title and issued_date and academic_year:
            try:
                from datetime import datetime
                issued = datetime.strptime(issued_date, '%Y-%m-%d').date()
                Certificate.objects.create(
                    student=student, school=school, certificate_type=cert_type, title=title,
                    issued_date=issued, academic_year=academic_year, created_by=request.user
                )
                from django.contrib import messages
                messages.success(request, f'Certificate created for {student.user.get_full_name()}')
                return redirect('operations:certificate_list')
            except ValueError:
                pass
    return render(request, 'operations/certificate_form.html', {'students': students, 'school': school})


@login_required
def certificate_view(request, pk):
    school = _get_school(request)
    certificate = get_object_or_404(Certificate, pk=pk)
    if school and certificate.school != school:
        return redirect('home')
    from accounts.permissions import user_can_manage_school
    can_view = user_can_manage_school(request.user) or request.user.is_superuser
    can_view = can_view or (certificate.student and certificate.student.user == request.user)
    if not can_view:
        return redirect('home')
    return render(request, 'operations/certificate_view.html', {'certificate': certificate, 'school': school, 'can_manage': can_view})


# ==================== EXPENSE TRACKING ====================

@login_required
def expense_list(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    expenses = Expense.objects.filter(school=school).select_related('category', 'recorded_by').order_by('-expense_date')[:200]
    total = expenses.aggregate(Sum('amount'))['amount__sum'] or 0
    return render(request, 'operations/expense_list.html', {'expenses': expenses, 'school': school, 'total': total})


@login_required
def expense_category_list(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    categories = ExpenseCategory.objects.filter(school=school).order_by('name')
    return render(request, 'operations/expense_category_list.html', {'categories': categories, 'school': school})


@login_required
def budget_list(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    budgets = Budget.objects.filter(school=school).select_related('category').order_by('-academic_year')
    return render(request, 'operations/budget_list.html', {'budgets': budgets, 'school': school})


# ==================== DISCIPLINE ====================

@login_required
def discipline_list(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    incidents = DisciplineIncident.objects.filter(school=school).select_related('student', 'student__user', 'reported_by').order_by('-incident_date')[:200]
    return render(request, 'operations/discipline_list.html', {'incidents': incidents, 'school': school})


@login_required
def behavior_points_list(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    students_with_points = Student.objects.filter(school=school).annotate(
        total_positive=Sum('behavior_points__points', filter=Q(behavior_points__point_type='positive')),
        total_negative=Sum('behavior_points__points', filter=Q(behavior_points__point_type='negative'))
    ).select_related('user')
    return render(request, 'operations/behavior_points_list.html', {'students': students_with_points, 'school': school})


# ==================== DOCUMENTS ====================

@login_required
def document_list(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return redirect('home')
    role = getattr(request.user, 'role', None)
    if role == 'student':
        student = Student.objects.filter(user=request.user, school=school).first()
        documents = StudentDocument.objects.filter(student=student).order_by('-uploaded_at') if student else []
    elif role == 'parent':
        children = Student.objects.filter(parent=request.user, school=school)
        documents = StudentDocument.objects.filter(student__in=children).select_related('student', 'student__user').order_by('-uploaded_at')[:200]
    elif user_can_manage_school(request.user) or request.user.is_superuser:
        documents = StudentDocument.objects.filter(school=school).select_related('student', 'student__user', 'uploaded_by').order_by('-uploaded_at')[:200]
    else:
        return redirect('home')
    return render(request, 'operations/document_list.html', {'documents': documents, 'school': school})


# ==================== ALUMNI ====================

@login_required
def alumni_list(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not (user_can_manage_school(request.user) or request.user.is_superuser):
        return redirect('home')
    alumni = Alumni.objects.filter(school=school).order_by('-graduation_year')[:200]
    return render(request, 'operations/alumni_list.html', {'alumni': alumni, 'school': school})


@login_required
def alumni_event_list(request):
    school = _get_school(request)
    if not school:
        return redirect('home')
    events = AlumniEvent.objects.filter(school=school).order_by('-event_date')[:50]
    return render(request, 'operations/alumni_event_list.html', {'events': events, 'school': school})


# ==================== TIMETABLE ====================

@login_required
def timetable_view(request):
    school = _get_school(request)
    if not school:
        return redirect('home')
    class_filter = request.GET.get('class')
    day_filter = request.GET.get('day')
    slots = TimetableSlot.objects.filter(school=school, is_active=True)
    if class_filter:
        slots = slots.filter(class_name=class_filter)
    if day_filter:
        slots = slots.filter(day=day_filter)
    slots = slots.select_related('subject', 'teacher').order_by('day', 'period_number')
    classes = sorted(set(TimetableSlot.objects.filter(school=school, is_active=True).values_list('class_name', flat=True)))
    return render(request, 'operations/timetable_view.html', {'slots': slots, 'school': school, 'classes': classes, 'class_filter': class_filter, 'day_filter': day_filter})


# ==================== STUDENT ID CARDS ====================

@login_required
def id_card_list(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    id_cards = StudentIDCard.objects.filter(school=school).select_related('student', 'student__user', 'created_by').order_by('-created_at')[:200]
    return render(request, 'operations/id_card_list.html', {'id_cards': id_cards, 'school': school})


# ==================== SPORTS & CLUBS ====================

@login_required
def sport_list(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return redirect('home')
    sports = Sport.objects.filter(school=school).select_related('coach').order_by('name')
    can_manage = user_can_manage_school(request.user) or request.user.is_superuser
    return render(request, 'operations/sport_list.html', {'sports': sports, 'school': school, 'can_manage': can_manage})


@login_required
def club_list(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return redirect('home')
    clubs = Club.objects.filter(school=school).select_related('sponsor').order_by('name')
    can_manage = user_can_manage_school(request.user) or request.user.is_superuser
    return render(request, 'operations/club_list.html', {'clubs': clubs, 'school': school, 'can_manage': can_manage})


# ==================== EXAM HALLS & SEATING ====================

@login_required
def exam_hall_list(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    halls = ExamHall.objects.filter(school=school).order_by('name')
    return render(request, 'operations/exam_hall_list.html', {'halls': halls, 'school': school})


@login_required
def seating_plan_list(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    plans = SeatingPlan.objects.filter(school=school).select_related('exam_schedule', 'exam_schedule__subject', 'hall', 'created_by').order_by('-created_at')[:100]
    return render(request, 'operations/seating_plan_list.html', {'plans': plans, 'school': school})


# ==================== PT MEETINGS ====================

@login_required
def pt_meeting_list(request):
    school = _get_school(request)
    if not school:
        return redirect('home')
    meetings = PTMeeting.objects.filter(school=school).order_by('-meeting_date')[:50]
    return render(request, 'operations/pt_meeting_list.html', {'meetings': meetings, 'school': school})


# ==================== HEALTH RECORDS ====================

@login_required
def health_record_list(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    records = StudentHealth.objects.filter(school=school).select_related('student', 'student__user').order_by('-last_updated')[:200]
    return render(request, 'operations/health_record_list.html', {'records': records, 'school': school})


@login_required
def health_visit_list(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    visits = HealthVisit.objects.filter(school=school).select_related('student', 'student__user', 'visited_by').order_by('-visit_date')[:200]
    return render(request, 'operations/health_visit_list.html', {'visits': visits, 'school': school})


# ==================== INVENTORY MANAGEMENT ====================

@login_required
def inventory_category_list(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    categories = InventoryCategory.objects.filter(school=school).order_by('name')
    return render(request, 'operations/inventory_category_list.html', {'categories': categories, 'school': school})


@login_required
def inventory_item_list(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    items = InventoryItem.objects.filter(school=school).select_related('category').order_by('name')[:300]
    return render(request, 'operations/inventory_item_list.html', {'items': items, 'school': school})


# ==================== SCHOOL EVENTS ====================

@login_required
def school_event_list(request):
    school = _get_school(request)
    if not school:
        return redirect('home')
    events = SchoolEvent.objects.filter(school=school).order_by('-start_date')[:100]
    return render(request, 'operations/school_event_list.html', {'events': events, 'school': school})


# ==================== ASSIGNMENT SUBMISSIONS ====================

@login_required
def assignment_submission_list(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    submissions = AssignmentSubmission.objects.filter(homework__subject__school=school).select_related('homework', 'homework__subject', 'student', 'student__user', 'graded_by').order_by('-submitted_at')[:200]
    return render(request, 'operations/assignment_submission_list.html', {'submissions': submissions, 'school': school})


@login_required
def my_submissions(request):
    school = _get_school(request)
    if not school:
        return redirect('home')
    role = getattr(request.user, 'role', None)
    if role != 'student':
        return redirect('home')
    student = Student.objects.filter(user=request.user, school=school).first()
    if not student:
        return redirect('home')
    submissions = AssignmentSubmission.objects.filter(student=student).select_related('homework', 'homework__subject').order_by('-submitted_at')[:100]
    return render(request, 'operations/my_submissions.html', {'submissions': submissions, 'school': school})


# ==================== ONLINE EXAMS ====================

@login_required
def online_exam_list(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    exams = OnlineExam.objects.filter(school=school).select_related('subject', 'created_by').order_by('-start_time')[:100]
    return render(request, 'operations/online_exam_list.html', {'exams': exams, 'school': school})


@login_required
def online_exam_take(request, pk):
    school = _get_school(request)
    if not school:
        return redirect('home')
    role = getattr(request.user, 'role', None)
    if role != 'student':
        return redirect('home')
    exam = get_object_or_404(OnlineExam, pk=pk, school=school)
    student = Student.objects.filter(user=request.user, school=school).first()
    if not student:
        return redirect('home')
    attempt = ExamAttempt.objects.filter(exam=exam, student=student).first()
    if attempt and attempt.is_completed:
        from django.contrib import messages
        messages.warning(request, 'You have already completed this exam.')
        return redirect('operations:online_exam_result', pk=attempt.pk)
    if not attempt:
        attempt = ExamAttempt.objects.create(exam=exam, student=student)
    questions = ExamQuestion.objects.filter(exam=exam).order_by('order')
    if request.method == 'POST':
        for key, value in request.POST.items():
            if key.startswith('answer_'):
                q_id = key.replace('answer_', '')
                question = ExamQuestion.objects.filter(id=q_id, exam=exam).first()
                if question:
                    is_correct = (value.upper() == question.correct_answer.upper())
                    marks = question.marks if is_correct else 0
                    ExamAnswer.objects.update_or_create(
                        attempt=attempt, question=question,
                        defaults={'answer_given': value, 'is_correct': is_correct, 'marks_obtained': marks}
                    )
        total = attempt.answers.aggregate(Sum('marks_obtained'))['marks_obtained__sum'] or 0
        attempt.score = total
        attempt.is_completed = True
        attempt.submitted_at = timezone.now()
        attempt.save()
        from django.contrib import messages
        messages.success(request, f'Exam submitted! Score: {total}')
        return redirect('operations:online_exam_result', pk=attempt.pk)
    return render(request, 'operations/online_exam_take.html', {'exam': exam, 'questions': questions, 'attempt': attempt, 'school': school})


@login_required
def online_exam_result(request, pk):
    school = _get_school(request)
    if not school:
        return redirect('home')
    attempt = get_object_or_404(ExamAttempt, pk=pk)
    from accounts.permissions import user_can_manage_school
    if attempt.student.user != request.user and not user_can_manage_school(request.user):
        return redirect('home')
    answers = ExamAnswer.objects.filter(attempt=attempt).select_related('question')
    return render(request, 'operations/online_exam_result.html', {'attempt': attempt, 'answers': answers, 'school': school})
