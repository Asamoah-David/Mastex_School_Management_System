from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
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
    """
    Parse a date value from querystring/POST.
    Accepts ISO date strings (YYYY-MM-DD) or a date object.
    """
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
def canteen_create(request):
    """Create a new canteen item."""
    from accounts.permissions import is_school_admin
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect("operations:canteen_list")
    
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        price = request.POST.get("price")
        is_available = request.POST.get("is_available") == "on"
        
        if name and price:
            try:
                CanteenItem.objects.create(
                    school=school,
                    name=name,
                    price=price,
                    is_available=is_available
                )
                from django.contrib import messages
                messages.success(request, "Canteen item created successfully!")
                return redirect("operations:canteen_list")
            except ValueError:
                pass
    
    return render(request, "operations/canteen_form.html", {"school": school})


@login_required
def canteen_payments(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not user_can_manage_school(request.user):
        return redirect("operations:canteen_list")
    payments = CanteenPayment.objects.filter(school=school).select_related("student", "student__user")[:200]
    return render(request, "operations/canteen_payments.html", {"payments": payments, "school": school})


@login_required
def bus_list(request):
    school = _get_school(request)
    if not school:
        return redirect("home")
    routes = BusRoute.objects.filter(school=school)
    return render(request, "operations/bus_list.html", {"routes": routes, "school": school})


@login_required
def bus_create(request):
    """Create a new bus route."""
    from accounts.permissions import is_school_admin
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect("operations:bus_list")
    
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        fee_per_term = request.POST.get("fee_per_term")
        
        if name and fee_per_term:
            try:
                BusRoute.objects.create(
                    school=school,
                    name=name,
                    fee_per_term=fee_per_term
                )
                from django.contrib import messages
                messages.success(request, "Bus route created successfully!")
                return redirect("operations:bus_list")
            except ValueError:
                pass
    
    return render(request, "operations/bus_form.html", {"school": school})


@login_required
def bus_payments(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not user_can_manage_school(request.user):
        return redirect("operations:bus_list")
    payments = BusPayment.objects.filter(school=school).select_related("student", "student__user", "route")[:200]
    return render(request, "operations/bus_payments.html", {"payments": payments, "school": school})


@login_required
def textbook_list(request):
    school = _get_school(request)
    if not school:
        return redirect("home")
    books = Textbook.objects.filter(school=school)
    return render(request, "operations/textbook_list.html", {"books": books, "school": school})


@login_required
def textbook_create(request):
    """Create a new textbook."""
    from accounts.permissions import is_school_admin
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect("operations:textbook_list")
    
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        price = request.POST.get("price")
        stock = request.POST.get("stock", 0)
        isbn = request.POST.get("isbn", "").strip()
        
        if title and price:
            try:
                Textbook.objects.create(
                    school=school,
                    title=title,
                    price=price,
                    stock=stock or 0,
                    isbn=isbn
                )
                from django.contrib import messages
                messages.success(request, "Textbook created successfully!")
                return redirect("operations:textbook_list")
            except ValueError:
                pass
    
    return render(request, "operations/textbook_form.html", {"school": school})


@login_required
def textbook_sales(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not user_can_manage_school(request.user):
        return redirect("operations:textbook_list")
    sales = TextbookSale.objects.filter(school=school).select_related("student", "student__user", "textbook")[:200]
    return render(request, "operations/textbook_sales.html", {"sales": sales, "school": school})


@login_required
def canteen_item_delete(request, pk):
    """Delete a canteen item."""
    from accounts.permissions import is_school_admin
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect("operations:canteen_list")
    item = get_object_or_404(CanteenItem, pk=pk, school=school)
    if request.method == "POST":
        item.delete()
        from django.contrib import messages
        messages.success(request, "Canteen item deleted successfully!")
        return redirect("operations:canteen_list")
    return render(request, "operations/confirm_delete.html", {"object": item, "type": "canteen item"})


@login_required
def bus_route_delete(request, pk):
    """Delete a bus route."""
    from accounts.permissions import is_school_admin
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect("operations:bus_list")
    route = get_object_or_404(BusRoute, pk=pk, school=school)
    if request.method == "POST":
        route.delete()
        from django.contrib import messages
        messages.success(request, "Bus route deleted successfully!")
        return redirect("operations:bus_list")
    return render(request, "operations/confirm_delete.html", {"object": route, "type": "bus route"})


@login_required
def textbook_delete(request, pk):
    """Delete a textbook."""
    from accounts.permissions import is_school_admin
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect("operations:textbook_list")
    book = get_object_or_404(Textbook, pk=pk, school=school)
    if request.method == "POST":
        book.delete()
        from django.contrib import messages
        messages.success(request, "Textbook deleted successfully!")
        return redirect("operations:textbook_list")
    return render(request, "operations/confirm_delete.html", {"object": book, "type": "textbook"})


@login_required
def attendance_edit(request, pk):
    """Edit an attendance record."""
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
    """Delete an attendance record."""
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


# Teacher Attendance Views
@login_required
def teacher_attendance_list(request):
    """List teacher attendance records."""
    school = _get_school(request)
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
    qs = TeacherAttendance.objects.filter(school=school, date__gte=from_date, date__lte=to_date).select_related(
        "teacher", "marked_by"
    )
    return render(
        request,
        "operations/teacher_attendance_list.html",
        {"attendances": qs, "school": school, "from_date": from_date, "to_date": to_date},
    )


@login_required
def teacher_attendance_mark(request):
    """Mark teacher attendance (School Admin only)."""
    school = _get_school(request)
    if not school:
        return redirect("home")
    
    # Only school admins can mark teacher attendance
    from accounts.permissions import is_school_admin
    if not (request.user.is_superuser or is_school_admin(request.user)):
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
                    teacher_id = key.replace("status_", "")
                    teacher = User.objects.get(id=teacher_id, school=school, role="teacher")
                    TeacherAttendance.objects.update_or_create(
                        teacher=teacher, date=date, defaults={"school": school, "status": value, "marked_by": request.user}
                    )
                except (User.DoesNotExist, ValueError):
                    pass
        return redirect("operations:teacher_attendance_list")
    
    from django.contrib import messages
    default_day = timezone.now().date()
    raw_date = request.GET.get("date")
    date = _parse_date(raw_date, default_day)
    if raw_date and date == default_day and str(raw_date) != str(default_day):
        messages.warning(request, "Invalid date; showing today's attendance sheet instead.")
    teachers = list(User.objects.filter(school=school, role="teacher").order_by("first_name", "last_name"))
    existing = {a.teacher_id: a.status for a in TeacherAttendance.objects.filter(school=school, date=date)}
    for t in teachers:
        t.attendance_status = existing.get(t.id, "present")
    
    return render(
        request,
        "operations/teacher_attendance_mark.html",
        {"teachers": teachers, "school": school, "date": date},
    )


# Academic Calendar Views
@login_required
def calendar_list(request):
    """List academic calendar events."""
    school = _get_school(request)
    if not school:
        return redirect("home")
    events = AcademicCalendar.objects.filter(school=school).order_by("start_date")
    return render(request, "operations/calendar_list.html", {"events": events, "school": school})


@login_required
def calendar_create(request):
    """Create academic calendar event."""
    school = _get_school(request)
    if not school:
        return redirect("home")
    
    # Only school admins can create calendar events
    from accounts.permissions import is_school_admin
    if not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect("home")
    
    if request.method == "POST":
        title = request.POST.get("title")
        event_type = request.POST.get("event_type")
        start_date = request.POST.get("start_date")
        end_date = request.POST.get("end_date") or None
        description = request.POST.get("description", "")
        
        if title and event_type and start_date:
            AcademicCalendar.objects.create(
                school=school,
                title=title,
                event_type=event_type,
                start_date=start_date,
                end_date=end_date,
                description=description,
            )
            from django.contrib import messages
            messages.success(request, "Calendar event created successfully!")
            return redirect("operations:calendar_list")
    
    return render(request, "operations/calendar_form.html", {"school": school})


@login_required
def calendar_delete(request, pk):
    """Delete academic calendar event."""
    school = _get_school(request)
    if not school:
        return redirect("home")
    
    # Only school admins can delete calendar events
    from accounts.permissions import is_school_admin
    if not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect("home")
    
    event = get_object_or_404(AcademicCalendar, pk=pk, school=school)
    if request.method == "POST":
        event.delete()
        from django.contrib import messages
        messages.success(request, "Calendar event deleted successfully!")
        return redirect("operations:calendar_list")
    return render(request, "operations/confirm_delete.html", {"object": event, "type": "calendar event"})


def _redirect_no_school(request):
    return redirect("accounts:dashboard") if request.user.is_authenticated else redirect("home")


# Announcements
@login_required
def announcement_list(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return _redirect_no_school(request)
    if not user_can_manage_school(request.user):
        return redirect("home")
    announcements = Announcement.objects.filter(school=school).select_related("created_by").order_by("-is_pinned", "-created_at")
    return render(request, "operations/announcement_list.html", {"announcements": announcements, "school": school})


@login_required
def announcement_create(request):
    school = _get_school(request)
    if not school:
        return _redirect_no_school(request)
    from accounts.permissions import is_school_admin
    if not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect("operations:announcement_list")
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        content = request.POST.get("content", "").strip()
        target = request.POST.get("target_audience", "all")
        is_pinned = request.POST.get("is_pinned") == "on"
        if title and content:
            ann = Announcement.objects.create(
                school=school, title=title, content=content,
                target_audience=target, is_pinned=is_pinned, created_by=request.user
            )
            from django.contrib import messages
            messages.success(request, "Announcement created.")
            if target in ("all", "parents"):
                try:
                    from messaging.utils import send_sms
                    recipients = (
                        User.objects.filter(school=school, role="parent")
                        .exclude(phone__isnull=True)
                        .exclude(phone__exact="")
                        .values_list("phone", flat=True)
                    )
                    phones = sorted({p.strip() for p in recipients if p and str(p).strip()})
                    sms = f"{school.name} Announcement: {ann.title}\n{ann.content}".strip()
                    if len(sms) > 480:
                        sms = sms[:477].rstrip() + "..."
                    sent = 0
                    for phone in phones:
                        try:
                            send_sms(phone, sms)
                            sent += 1
                        except Exception:
                            continue
                    if phones and sent == 0:
                        messages.warning(request, "Announcement saved, but SMS could not be sent to parents.")
                    elif sent and sent < len(phones):
                        messages.warning(request, f"Announcement saved. SMS sent to {sent} of {len(phones)} parents.")
                    elif sent:
                        messages.success(request, f"SMS sent to {sent} parents.")
                except Exception:
                    messages.warning(request, "Announcement saved, but SMS sending failed.")
            return redirect("operations:announcement_list")
    return render(request, "operations/announcement_form.html", {"school": school})


@login_required
def announcement_delete(request, pk):
    school = _get_school(request)
    if not school:
        return _redirect_no_school(request)
    from accounts.permissions import is_school_admin
    if not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect("operations:announcement_list")
    ann = get_object_or_404(Announcement, pk=pk, school=school)
    if request.method == "POST":
        ann.delete()
        from django.contrib import messages
        messages.success(request, "Announcement deleted.")
        return redirect("operations:announcement_list")
    return render(request, "operations/confirm_delete.html", {"object": ann, "type": "announcement"})


# Staff Leave
@login_required
def staff_leave_list(request):
    school = _get_school(request)
    if not school:
        return _redirect_no_school(request)
    from accounts.permissions import user_can_manage_school
    if not user_can_manage_school(request.user):
        return redirect("home")
    from accounts.permissions import is_school_admin
    is_admin = request.user.is_superuser or is_school_admin(request.user)
    if is_admin:
        leaves = StaffLeave.objects.filter(school=school).select_related("staff", "reviewed_by").order_by("-start_date")
    else:
        leaves = StaffLeave.objects.filter(school=school, staff=request.user).select_related("staff", "reviewed_by").order_by("-start_date")
    return render(request, "operations/staff_leave_list.html", {"leaves": leaves, "school": school, "is_admin": is_admin})


@login_required
def staff_leave_create(request):
    school = _get_school(request)
    if not school:
        return _redirect_no_school(request)
    from accounts.permissions import user_can_manage_school
    if not user_can_manage_school(request.user):
        return redirect("home")
    if request.method == "POST":
        start = request.POST.get("start_date")
        end = request.POST.get("end_date")
        reason = request.POST.get("reason", "").strip()
        if start and end:
            try:
                from datetime import datetime
                start_d = datetime.strptime(start, "%Y-%m-%d").date()
                end_d = datetime.strptime(end, "%Y-%m-%d").date()
                if start_d <= end_d:
                    StaffLeave.objects.create(
                        school=school, staff=request.user,
                        start_date=start_d, end_date=end_d, reason=reason
                    )
                    from django.contrib import messages
                    messages.success(request, "Leave request submitted.")
                    return redirect("operations:staff_leave_list")
            except ValueError:
                pass
    return render(request, "operations/staff_leave_form.html", {"school": school})


@login_required
def staff_leave_review(request, pk):
    school = _get_school(request)
    if not school:
        return _redirect_no_school(request)
    from accounts.permissions import is_school_admin
    if not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect("operations:staff_leave_list")
    leave = get_object_or_404(StaffLeave, pk=pk, school=school)
    if request.method == "POST":
        action = request.POST.get("action")
        if action in ("approved", "rejected"):
            leave.status = action
            leave.reviewed_by = request.user
            leave.reviewed_at = timezone.now()
            leave.save()
            from django.contrib import messages
            messages.success(request, f"Leave {action}.")
            return redirect("operations:staff_leave_list")
    return redirect("operations:staff_leave_list")


# Activity Log (admin only)
@login_required
def activity_log_list(request):
    from accounts.permissions import is_school_admin
    school = _get_school(request)

    # Platform admins: see logs across all schools.
    if request.user.is_superuser or getattr(request.user, "is_super_admin", False):
        logs = ActivityLog.objects.select_related("user", "school").order_by("-created_at")[:300]
        return render(request, "operations/activity_log_list.html", {"logs": logs, "school": None})

    # School admins: see logs for their school.
    if not school:
        return _redirect_no_school(request)
    if not is_school_admin(request.user):
        return redirect("accounts:school_dashboard")
    logs = ActivityLog.objects.filter(school=school).select_related("user").order_by("-created_at")[:200]
    return render(request, "operations/activity_log_list.html", {"logs": logs, "school": school})


# Library
@login_required
def library_catalog(request):
    """
    Read-only catalog for students/parents; staff see same list plus manage link.
    """
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
def library_book_create(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not (request.user.is_superuser or user_can_manage_school(request.user)):
        return redirect("operations:library_catalog")
    if request.method == "POST":
        isbn = (request.POST.get("isbn") or "").strip()
        title = (request.POST.get("title") or "").strip()
        author = (request.POST.get("author") or "").strip()
        publisher = (request.POST.get("publisher") or "").strip()
        category = (request.POST.get("category") or "").strip()
        shelf_location = (request.POST.get("shelf_location") or "").strip()
        try:
            total_copies = int(request.POST.get("total_copies") or 1)
        except ValueError:
            total_copies = 1
        if isbn and title and author and total_copies > 0:
            obj, created = LibraryBook.objects.get_or_create(
                school=school,
                isbn=isbn,
                defaults={
                    "title": title,
                    "author": author,
                    "publisher": publisher,
                    "category": category,
                    "shelf_location": shelf_location,
                    "total_copies": total_copies,
                    "available_copies": total_copies,
                },
            )
            if not created:
                old_total = obj.total_copies
                old_available = obj.available_copies
                obj.title = title
                obj.author = author
                obj.publisher = publisher
                obj.category = category
                obj.shelf_location = shelf_location
                obj.total_copies = total_copies
                # Adjust availability intelligently when total copies change.
                # If total increases, add the difference to available copies.
                # If total decreases, cap available copies at new total.
                diff = total_copies - old_total
                if diff > 0:
                    obj.available_copies = min(total_copies, old_available + diff)
                else:
                    obj.available_copies = min(total_copies, old_available)
                obj.save()
            from django.contrib import messages
            messages.success(request, "Library book saved.")
            return redirect("operations:library_manage")
        from django.contrib import messages
        messages.error(request, "Please fill ISBN, title, author, and total copies.")
    return render(request, "operations/library_book_form.html", {"school": school})


@login_required
def library_book_delete(request, pk):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not (request.user.is_superuser or user_can_manage_school(request.user)):
        return redirect("operations:library_catalog")
    book = get_object_or_404(LibraryBook, pk=pk, school=school)
    if request.method == "POST":
        book.delete()
        from django.contrib import messages
        messages.success(request, "Book deleted.")
        return redirect("operations:library_manage")
    return render(request, "operations/confirm_delete.html", {"object": book, "type": "library book"})


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
def library_issue_create(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not (request.user.is_superuser or user_can_manage_school(request.user)):
        return redirect("operations:library_catalog")
    students = Student.objects.filter(school=school).select_related("user").order_by("class_name", "admission_number")
    books = LibraryBook.objects.filter(school=school).order_by("title", "author")
    if request.method == "POST":
        from datetime import datetime, timedelta
        student_id = request.POST.get("student")
        book_id = request.POST.get("book")
        issue_date_str = (request.POST.get("issue_date") or "").strip()
        due_date_str = (request.POST.get("due_date") or "").strip()
        notes = (request.POST.get("notes") or "").strip()
        try:
            issue_date = datetime.strptime(issue_date_str, "%Y-%m-%d").date() if issue_date_str else timezone.now().date()
        except ValueError:
            issue_date = timezone.now().date()
        try:
            due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date() if due_date_str else (issue_date + timedelta(days=14))
        except ValueError:
            due_date = issue_date + timedelta(days=14)
        student = Student.objects.filter(id=student_id, school=school).first()
        book = LibraryBook.objects.filter(id=book_id, school=school).first()
        if not student or not book:
            from django.contrib import messages
            messages.error(request, "Invalid student or book.")
        elif book.available_copies <= 0:
            from django.contrib import messages
            messages.error(request, "No copies available.")
        else:
            LibraryIssue.objects.create(
                school=school,
                student=student,
                book=book,
                issue_date=issue_date,
                due_date=due_date,
                status="issued",
                issued_by=request.user,
                notes=notes,
            )
            book.available_copies = max(0, book.available_copies - 1)
            book.save(update_fields=["available_copies"])
            from django.contrib import messages
            messages.success(request, "Book issued.")
            return redirect("operations:library_issues")
    return render(request, "operations/library_issue_form.html", {"school": school, "students": students, "books": books})


@login_required
def library_issue_return(request, pk):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not (request.user.is_superuser or user_can_manage_school(request.user)):
        return redirect("operations:library_catalog")
    issue = get_object_or_404(LibraryIssue, pk=pk, school=school)
    if request.method == "POST":
        issue.status = "returned"
        issue.return_date = timezone.now().date()
        issue.save(update_fields=["status", "return_date"])
        book = issue.book
        book.available_copies = min(book.total_copies, book.available_copies + 1)
        book.save(update_fields=["available_copies"])
        from django.contrib import messages
        messages.success(request, "Book returned.")
        return redirect("operations:library_issues")
    return render(request, "operations/confirm_delete.html", {"object": issue, "type": "return this book"})


@login_required
def library_my_issues(request):
    """
    Student/parent view: show borrowed books.
    - student: their own issues
    - parent: issues for their children
    """
    school = _get_school(request)
    if not school:
        return redirect("home")
    role = getattr(request.user, "role", None)
    if role == "student":
        student = Student.objects.filter(user=request.user, school=school).first()
        issues = (
            LibraryIssue.objects.filter(school=school, student=student)
            .select_related("book")
            .order_by("-issue_date")[:200]
            if student
            else []
        )
        return render(request, "operations/library_my_issues.html", {"issues": issues, "school": school, "mode": "student"})
    if role == "parent":
        children = Student.objects.filter(parent=request.user, school=school)
        issues = (
            LibraryIssue.objects.filter(school=school, student__in=children)
            .select_related("book", "student", "student__user")
            .order_by("-issue_date")[:300]
        )
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
def hostel_create(request):
    from accounts.permissions import is_school_admin
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect("operations:hostel_list")
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        hostel_type = (request.POST.get("type") or "").strip()
        warden_name = (request.POST.get("warden_name") or "").strip()
        warden_phone = (request.POST.get("warden_phone") or "").strip()
        total_beds = int(request.POST.get("total_beds") or 0)
        fee_per_term = request.POST.get("fee_per_term") or 0
        if name and hostel_type:
            Hostel.objects.create(
                school=school,
                name=name,
                type=hostel_type,
                total_beds=max(0, total_beds),
                warden_name=warden_name,
                warden_phone=warden_phone,
                fee_per_term=fee_per_term,
            )
            from django.contrib import messages
            messages.success(request, "Hostel created.")
            return redirect("operations:hostel_list")
    return render(request, "operations/hostel_form.html", {"school": school})


@login_required
def hostel_rooms(request, pk):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return redirect("home")
    hostel = get_object_or_404(Hostel, pk=pk, school=school)
    rooms = HostelRoom.objects.filter(hostel=hostel).order_by("floor", "room_number")
    can_manage = request.user.is_superuser or user_can_manage_school(request.user)
    return render(request, "operations/hostel_rooms.html", {"hostel": hostel, "rooms": rooms, "school": school, "can_manage": can_manage})


@login_required
def hostel_room_create(request, pk):
    from accounts.permissions import is_school_admin
    school = _get_school(request)
    if not school:
        return redirect("home")
    hostel = get_object_or_404(Hostel, pk=pk, school=school)
    if not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect("operations:hostel_rooms", pk=hostel.pk)
    if request.method == "POST":
        room_number = (request.POST.get("room_number") or "").strip()
        floor = int(request.POST.get("floor") or 1)
        total_beds = int(request.POST.get("total_beds") or 4)
        if room_number:
            HostelRoom.objects.get_or_create(
                hostel=hostel,
                room_number=room_number,
                defaults={"floor": max(1, floor), "total_beds": max(1, total_beds), "current_occupancy": 0},
            )
            from django.contrib import messages
            messages.success(request, "Room saved.")
            return redirect("operations:hostel_rooms", pk=hostel.pk)
    return render(request, "operations/hostel_room_form.html", {"school": school, "hostel": hostel})


@login_required
def hostel_assignments(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not (request.user.is_superuser or user_can_manage_school(request.user)):
        return redirect("home")
    qs = HostelAssignment.objects.filter(school=school).select_related("student", "student__user", "hostel", "room").order_by("-start_date")[:300]
    return render(request, "operations/hostel_assignments.html", {"assignments": qs, "school": school})


@login_required
def hostel_assignment_create(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not (request.user.is_superuser or user_can_manage_school(request.user)):
        return redirect("home")
    students = Student.objects.filter(school=school).select_related("user").order_by("class_name", "admission_number")
    hostels = Hostel.objects.filter(school=school).order_by("name")
    rooms = HostelRoom.objects.filter(hostel__school=school).select_related("hostel").order_by("hostel__name", "floor", "room_number")
    if request.method == "POST":
        from datetime import datetime
        student_id = request.POST.get("student")
        hostel_id = request.POST.get("hostel")
        room_id = request.POST.get("room") or None
        bed_number = (request.POST.get("bed_number") or "").strip()
        start_str = (request.POST.get("start_date") or "").strip()
        end_str = (request.POST.get("end_date") or "").strip()
        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d").date() if start_str else timezone.now().date()
        except ValueError:
            start_date = timezone.now().date()
        end_date = None
        if end_str:
            try:
                end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
            except ValueError:
                end_date = None
        student = Student.objects.filter(id=student_id, school=school).first()
        hostel = Hostel.objects.filter(id=hostel_id, school=school).first()
        room = None
        if room_id:
            room = HostelRoom.objects.filter(id=room_id, hostel=hostel).first()
        if not student or not hostel:
            from django.contrib import messages
            messages.error(request, "Invalid student/hostel.")
        else:
            # End any existing active assignment
            HostelAssignment.objects.filter(school=school, student=student, is_active=True).update(is_active=False, end_date=start_date)
            ass = HostelAssignment.objects.create(
                school=school,
                student=student,
                hostel=hostel,
                room=room,
                bed_number=bed_number,
                start_date=start_date,
                end_date=end_date,
                is_active=True if not end_date else False,
            )
            if room:
                room.current_occupancy = min(room.total_beds, room.current_occupancy + 1)
                room.save(update_fields=["current_occupancy"])
            from django.contrib import messages
            messages.success(request, "Hostel assignment saved.")
            return redirect("operations:hostel_assignments")
    return render(request, "operations/hostel_assignment_form.html", {"school": school, "students": students, "hostels": hostels, "rooms": rooms})


@login_required
def hostel_assignment_end(request, pk):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not (request.user.is_superuser or user_can_manage_school(request.user)):
        return redirect("home")
    assignment = get_object_or_404(HostelAssignment, pk=pk, school=school)
    if request.method == "POST":
        assignment.is_active = False
        assignment.end_date = timezone.now().date()
        assignment.save(update_fields=["is_active", "end_date"])
        if assignment.room:
            room = assignment.room
            room.current_occupancy = max(0, room.current_occupancy - 1)
            room.save(update_fields=["current_occupancy"])
        from django.contrib import messages
        messages.success(request, "Assignment ended.")
        return redirect("operations:hostel_assignments")
    return render(request, "operations/confirm_delete.html", {"object": assignment, "type": "end this assignment"})


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
def hostel_fee_create(request):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not (request.user.is_superuser or user_can_manage_school(request.user)):
        return redirect("home")
    students = Student.objects.filter(school=school).select_related("user").order_by("class_name", "admission_number")
    hostels = Hostel.objects.filter(school=school).order_by("name")
    if request.method == "POST":
        student_id = request.POST.get("student")
        hostel_id = request.POST.get("hostel")
        term = (request.POST.get("term") or "").strip()
        amount = request.POST.get("amount") or 0
        student = Student.objects.filter(id=student_id, school=school).first()
        hostel = Hostel.objects.filter(id=hostel_id, school=school).first()
        if student and hostel and term:
            HostelFee.objects.update_or_create(
                school=school,
                student=student,
                hostel=hostel,
                term=term,
                defaults={"amount": amount, "paid": False, "payment_date": None},
            )
            from django.contrib import messages
            messages.success(request, "Hostel fee saved.")
            return redirect("operations:hostel_fees")
        from django.contrib import messages
        messages.error(request, "Please select student, hostel and term.")
    return render(request, "operations/hostel_fee_form.html", {"school": school, "students": students, "hostels": hostels})


@login_required
def hostel_fee_mark_paid(request, pk):
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not (request.user.is_superuser or user_can_manage_school(request.user)):
        return redirect("home")
    fee = get_object_or_404(HostelFee, pk=pk, school=school)
    if request.method == "POST":
        fee.paid = True
        fee.payment_date = timezone.now().date()
        fee.save(update_fields=["paid", "payment_date"])
        from django.contrib import messages
        messages.success(request, "Marked as paid.")
        return redirect("operations:hostel_fees")
    return render(request, "operations/confirm_delete.html", {"object": fee, "type": "mark fee as paid"})


@login_required
def hostel_my(request):
    """
    Student/parent view: current hostel assignment + fee status.
    """
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
    """
    Public admission form - no login required.
    Parents/guardians can submit applications online.
    """
    from schools.models import School
    
    # Get active schools for dropdown
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
        parent_occupation = request.POST.get('parent_occupation', '').strip()
        address = request.POST.get('address', '').strip()
        medical = request.POST.get('medical_conditions', '').strip()
        reason = request.POST.get('reason_for_applying', '').strip()
        school_id = request.POST.get('school')
        
        if first_name and last_name and dob and gender and class_applied and parent_first and parent_last and parent_phone and address:
            try:
                from datetime import datetime
                dob_date = datetime.strptime(dob, '%Y-%m-%d').date()
                
                school = None
                if school_id:
                    school = School.objects.filter(id=school_id, is_active=True).first()
                
                application = AdmissionApplication.objects.create(
                    school=school,
                    first_name=first_name,
                    last_name=last_name,
                    date_of_birth=dob_date,
                    gender=gender,
                    previous_school=previous_school,
                    class_applied_for=class_applied,
                    parent_first_name=parent_first,
                    parent_last_name=parent_last,
                    parent_phone=parent_phone,
                    parent_email=parent_email,
                    parent_occupation=parent_occupation,
                    address=address,
                    medical_conditions=medical,
                    reason_for_applying=reason,
                    status='pending'
                )
                
                # Try to send SMS notification to school admin
                try:
                    from messaging.utils import send_sms
                    msg = f"New Admission Application: {first_name} {last_name} for {class_applied}"
                    if school:
                        admins = User.objects.filter(school=school, role='admin')
                        for admin in admins:
                            if admin.phone:
                                send_sms(admin.phone, msg)
                except:
                    pass
                
                return render(request, 'operations/admission_success.html', {
                    'application': application,
                    'schools': schools
                })
            except ValueError:
                pass
    
    return render(request, 'operations/admission_apply.html', {'schools': schools})


@login_required
def admission_list(request):
    """Admin view: list all admission applications."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    
    if not user_can_manage_school(request.user) and not getattr(request.user, 'is_super_admin', False):
        return redirect('home')
    
    status_filter = request.GET.get('status', '')
    qs = AdmissionApplication.objects.all()
    
    if school:
        qs = qs.filter(school=school)
    
    if status_filter:
        qs = qs.filter(status=status_filter)
    
    applications = qs.select_related('school', 'reviewed_by').order_by('-applied_at')[:200]
    
    return render(request, 'operations/admission_list.html', {
        'applications': applications,
        'school': school,
        'status_filter': status_filter
    })


@login_required
def admission_detail(request, pk):
    """Admin view: review application details."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    
    if not user_can_manage_school(request.user) and not getattr(request.user, 'is_super_admin', False):
        return redirect('home')
    
    application = get_object_or_404(AdmissionApplication, pk=pk)
    
    if school and application.school and application.school != school:
        return redirect('home')
    
    return render(request, 'operations/admission_detail.html', {
        'application': application,
        'school': school
    })


@login_required
def admission_approve(request, pk):
    """Approve application and optionally create student account."""
    from accounts.permissions import user_can_manage_school
    from django.contrib.auth.hashers import make_password
    
    school = _get_school(request)
    
    if not user_can_manage_school(request.user) and not getattr(request.user, 'is_super_admin', False):
        return redirect('home')
    
    application = get_object_or_404(AdmissionApplication, pk=pk)
    
    if school and application.school and application.school != school:
        return redirect('home')
    
    if request.method == 'POST':
        create_account = request.POST.get('create_account') == 'on'
        admission_number = request.POST.get('admission_number', '').strip()
        initial_password = request.POST.get('initial_password', '').strip()
        
        # Approve the application
        application.status = 'approved'
        application.reviewed_by = request.user
        application.reviewed_at = timezone.now()
        application.save()
        
        student = None
        
        # Create student account if requested
        if create_account and application.school:
            # Generate admission number if not provided
            if not admission_number:
                last_student = Student.objects.filter(school=application.school).order_by('-id').first()
                next_num = int(last_student.admission_number.split('-')[-1]) + 1 if last_student and last_student.admission_number else 1
                admission_number = f"{application.school.name[:3].upper()}-{timezone.now().year}-{next_num:04d}"
            
            # Create parent user account
            username = f"parent{application.id}"
            parent_user = User.objects.create(
                username=username,
                first_name=application.parent_first_name,
                last_name=application.parent_last_name,
                email=application.parent_email or f"{username}@school.local",
                phone=application.parent_phone,
                role='parent',
                school=application.school,
                password=make_password(initial_password or 'Welcome123')
            )
            
            # Create student record
            student_user = User.objects.create(
                username=f"student{application.id}",
                first_name=application.first_name,
                last_name=application.last_name,
                role='student',
                school=application.school,
                password=make_password(initial_password or 'Student123')
            )
            
            student = Student.objects.create(
                user=student_user,
                school=application.school,
                admission_number=admission_number,
                class_name=application.class_applied_for,
                parent=parent_user,
                date_enrolled=timezone.now().date()
            )
            
            application.created_student = student
            application.save()
            
            # Send SMS with login details
            try:
                from messaging.utils import send_sms
                msg = f"Welcome! Your child has been admitted to {application.school.name}. Login: {username}, Password: {initial_password or 'Welcome123'}"
                send_sms(application.parent_phone, msg)
            except:
                pass
        
        from django.contrib import messages
        messages.success(request, f'Application approved! {"Student account created." if student else ""}')
        return redirect('operations:admission_list')
    
    return render(request, 'operations/admission_approve.html', {
        'application': application,
        'school': school
    })


@login_required
def admission_reject(request, pk):
    """Reject an admission application."""
    from accounts.permissions import user_can_manage_school
    
    school = _get_school(request)
    
    if not user_can_manage_school(request.user) and not getattr(request.user, 'is_super_admin', False):
        return redirect('home')
    
    application = get_object_or_404(AdmissionApplication, pk=pk)
    
    if school and application.school and application.school != school:
        return redirect('home')
    
    if request.method == 'POST':
        reason = request.POST.get('rejection_reason', '').strip()
        
        application.status = 'rejected'
        application.reviewed_by = request.user
        application.reviewed_at = timezone.now()
        application.rejection_reason = reason
        application.save()
        
        # Notify parent
        try:
            from messaging.utils import send_sms
            msg = f"Admission Update: Your application for {application.first_name} has been declined. Reason: {reason or 'Please contact school for details.'}"
            send_sms(application.parent_phone, msg)
        except:
            pass
        
        from django.contrib import messages
        messages.success(request, 'Application rejected.')
        return redirect('operations:admission_list')
    
    return render(request, 'operations/admission_reject.html', {
        'application': application
    })


# ==================== CERTIFICATES ====================

@login_required
def certificate_list(request):
    """List certificates for the school."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    
    if not user_can_manage_school(request.user):
        return redirect('home')
    
    certificates = Certificate.objects.filter(school=school).select_related('student', 'student__user', 'created_by').order_by('-issued_date')[:200]
    
    return render(request, 'operations/certificate_list.html', {
        'certificates': certificates,
        'school': school
    })


@login_required
def certificate_create(request):
    """Create a new certificate for a student."""
    from accounts.permissions import user_can_manage_school
    
    school = _get_school(request)
    
    if not user_can_manage_school(request.user):
        return redirect('home')
    
    students = Student.objects.filter(school=school).select_related('user').order_by('class_name', 'admission_number')
    
    if request.method == 'POST':
        student_id = request.POST.get('student')
        cert_type = request.POST.get('certificate_type')
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        issued_date = request.POST.get('issued_date')
        academic_year = request.POST.get('academic_year', '').strip()
        term = request.POST.get('term', '').strip()
        
        student = Student.objects.filter(id=student_id, school=school).first()
        
        if student and cert_type and title and issued_date and academic_year:
            try:
                from datetime import datetime
                issued = datetime.strptime(issued_date, '%Y-%m-%d').date()
                
                cert = Certificate.objects.create(
                    student=student,
                    school=school,
                    certificate_type=cert_type,
                    title=title,
                    description=description,
                    issued_date=issued,
                    academic_year=academic_year,
                    term=term,
                    created_by=request.user
                )
                
                from django.contrib import messages
                messages.success(request, f'Certificate created for {student.user.get_full_name()}')
                return redirect('operations:certificate_list')
            except ValueError:
                pass
    
    return render(request, 'operations/certificate_form.html', {
        'students': students,
        'school': school
    })


@login_required
def certificate_view(request, pk):
    """View certificate details."""
    from accounts.permissions import user_can_manage_school
    from academics.models import Result
    
    school = _get_school(request)
    
    certificate = get_object_or_404(Certificate, pk=pk)
    
    # Check permission
    if school and certificate.school != school:
        return redirect('home')
    
    can_manage = user_can_manage_school(request.user) or request.user.is_superuser
    can_view = can_manage or (certificate.student and certificate.student.user == request.user)
    
    if not can_view:
        return redirect('home')
    
    # Get student's academic record for the certificate
    results = None
    if school:
        results = Result.objects.filter(student=certificate.student, term__name__icontains=certificate.term or '').select_related('subject', 'term')[:20]
    
    return render(request, 'operations/certificate_view.html', {
        'certificate': certificate,
        'school': school,
        'results': results,
        'can_manage': can_manage
    })


@login_required
def certificate_delete(request, pk):
    """Delete a certificate."""
    from accounts.permissions import user_can_manage_school
    
    school = _get_school(request)
    
    if not user_can_manage_school(request.user):
        return redirect('home')
    
    certificate = get_object_or_404(Certificate, pk=pk, school=school)
    
    if request.method == 'POST':
        certificate.delete()
        from django.contrib import messages
        messages.success(request, 'Certificate deleted.')
        return redirect('operations:certificate_list')
    
    return render(request, 'operations/confirm_delete.html', {
        'object': certificate,
        'type': 'certificate'
    })


# ==================== EXPENSE TRACKING ====================

@login_required
def expense_list(request):
    """List all expenses."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    
    expenses = Expense.objects.filter(school=school).select_related('category', 'recorded_by').order_by('-expense_date')[:200]
    total = expenses.aggregate(Sum('amount'))['amount__sum'] or 0
    
    return render(request, 'operations/expense_list.html', {
        'expenses': expenses,
        'school': school,
        'total': total
    })


@login_required
def expense_create(request):
    """Create a new expense."""
    from accounts.permissions import is_school_admin
    school = _get_school(request)
    if not school or not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect('operations:expense_list')
    
    categories = ExpenseCategory.objects.filter(school=school)
    
    if request.method == 'POST':
        category_id = request.POST.get('category')
        description = request.POST.get('description', '').strip()
        amount = request.POST.get('amount')
        expense_date = request.POST.get('expense_date')
        vendor = request.POST.get('vendor', '').strip()
        payment_method = request.POST.get('payment_method', 'cash')
        receipt_number = request.POST.get('receipt_number', '').strip()
        
        if description and amount and expense_date:
            try:
                category = ExpenseCategory.objects.get(id=category_id, school=school) if category_id else None
                Expense.objects.create(
                    school=school,
                    category=category,
                    description=description,
                    amount=amount,
                    expense_date=expense_date,
                    vendor=vendor,
                    payment_method=payment_method,
                    receipt_number=receipt_number,
                    recorded_by=request.user
                )
                from django.contrib import messages
                messages.success(request, 'Expense recorded successfully!')
                return redirect('operations:expense_list')
            except ValueError:
                pass
    
    return render(request, 'operations/expense_form.html', {
        'school': school,
        'categories': categories
    })


@login_required
def expense_detail(request, pk):
    """View expense details."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    
    expense = get_object_or_404(Expense, pk=pk, school=school)
    
    return render(request, 'operations/expense_detail.html', {
        'expense': expense,
        'school': school
    })


@login_required
def budget_list(request):
    """List budgets."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    
    budgets = Budget.objects.filter(school=school).select_related('category').order_by('-academic_year')
    
    return render(request, 'operations/budget_list.html', {
        'budgets': budgets,
        'school': school
    })


@login_required
def budget_create(request):
    """Create a new budget."""
    from accounts.permissions import is_school_admin
    school = _get_school(request)
    if not school or not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect('operations:budget_list')
    
    categories = ExpenseCategory.objects.filter(school=school)
    
    if request.method == 'POST':
        category_id = request.POST.get('category')
        academic_year = request.POST.get('academic_year', '').strip()
        term = request.POST.get('term', '').strip()
        allocated_amount = request.POST.get('allocated_amount')
        
        if academic_year and allocated_amount:
            try:
                category = ExpenseCategory.objects.get(id=category_id, school=school) if category_id else None
                Budget.objects.create(
                    school=school,
                    category=category,
                    academic_year=academic_year,
                    term=term,
                    allocated_amount=allocated_amount
                )
                from django.contrib import messages
                messages.success(request, 'Budget created successfully!')
                return redirect('operations:budget_list')
            except ValueError:
                pass
    
    return render(request, 'operations/budget_form.html', {
        'school': school,
        'categories': categories
    })


# ==================== DISCIPLINE ====================

@login_required
def discipline_list(request):
    """List discipline incidents."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    
    incidents = DisciplineIncident.objects.filter(school=school).select_related('student', 'student__user', 'reported_by').order_by('-incident_date')[:200]
    
    return render(request, 'operations/discipline_list.html', {
        'incidents': incidents,
        'school': school
    })


@login_required
def discipline_create(request):
    """Create a new discipline incident."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('operations:discipline_list')
    
    students = Student.objects.filter(school=school).select_related('user').order_by('class_name', 'admission_number')
    
    if request.method == 'POST':
        student_id = request.POST.get('student')
        incident_type = request.POST.get('incident_type', '').strip()
        severity = request.POST.get('severity', 'minor')
        description = request.POST.get('description', '').strip()
        action_taken = request.POST.get('action_taken', '').strip()
        
        if student_id and incident_type and description:
            student = Student.objects.filter(id=student_id, school=school).first()
            if student:
                DisciplineIncident.objects.create(
                    school=school,
                    student=student,
                    incident_date=timezone.now(),
                    incident_type=incident_type,
                    severity=severity,
                    description=description,
                    action_taken=action_taken,
                    reported_by=request.user
                )
                from django.contrib import messages
                messages.success(request, 'Incident recorded successfully!')
                return redirect('operations:discipline_list')
    
    return render(request, 'operations/discipline_form.html', {
        'school': school,
        'students': students
    })


@login_required
def discipline_detail(request, pk):
    """View discipline incident details."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    
    incident = get_object_or_404(DisciplineIncident, pk=pk, school=school)
    
    return render(request, 'operations/discipline_detail.html', {
        'incident': incident,
        'school': school
    })


@login_required
def behavior_points_list(request):
    """List behavior points."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    
    # Get students with their total points
    from django.db.models import Sum, Case, When, IntegerField
    students_with_points = Student.objects.filter(school=school).annotate(
        total_positive=Sum('behavior_points__points', filter=models.Q(behavior_points__point_type='positive')),
        total_negative=Sum('behavior_points__points', filter=models.Q(behavior_points__point_type='negative'))
    ).select_related('user')
    
    return render(request, 'operations/behavior_points_list.html', {
        'students': students_with_points,
        'school': school
    })


@login_required
def behavior_points_create(request):
    """Award behavior points."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('operations:behavior_points_list')
    
    students = Student.objects.filter(school=school).select_related('user').order_by('class_name', 'admission_number')
    
    if request.method == 'POST':
        student_id = request.POST.get('student')
        point_type = request.POST.get('point_type')
        points = request.POST.get('points')
        reason = request.POST.get('reason', '').strip()
        
        if student_id and points and reason:
            student = Student.objects.filter(id=student_id, school=school).first()
            if student:
                BehaviorPoint.objects.create(
                    school=school,
                    student=student,
                    point_type=point_type,
                    points=int(points),
                    reason=reason,
                    awarded_by=request.user
                )
                from django.contrib import messages
                messages.success(request, 'Points awarded successfully!')
                return redirect('operations:behavior_points_list')
    
    return render(request, 'operations/behavior_points_form.html', {
        'school': school,
        'students': students
    })


# ==================== DOCUMENTS ====================

@login_required
def document_list(request):
    """List student documents."""
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
    
    return render(request, 'operations/document_list.html', {
        'documents': documents,
        'school': school
    })


@login_required
def document_upload(request):
    """Upload a student document."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return redirect('home')
    
    # Only admins or the student/parent themselves can upload
    role = getattr(request.user, 'role', None)
    students = []
    
    if role == 'student':
        students = [Student.objects.filter(user=request.user, school=school).first()]
    elif role == 'parent':
        students = list(Student.objects.filter(parent=request.user, school=school))
    elif user_can_manage_school(request.user) or request.user.is_superuser:
        students = list(Student.objects.filter(school=school).select_related('user').order_by('class_name', 'admission_number')[:100])
    else:
        return redirect('home')
    
    students = [s for s in students if s]
    
    if request.method == 'POST':
        student_id = request.POST.get('student')
        document_type = request.POST.get('document_type')
        title = request.POST.get('title', '').strip()
        
        if student_id and document_type and title:
            student = Student.objects.filter(id=student_id, school=school).first()
            if student:
                # In a real app, you'd handle file upload here
                StudentDocument.objects.create(
                    student=student,
                    school=school,
                    document_type=document_type,
                    title=title,
                    file_path=f"documents/{student_id}/{title}",
                    uploaded_by=request.user
                )
                from django.contrib import messages
                messages.success(request, 'Document uploaded successfully!')
                return redirect('operations:document_list')
    
    return render(request, 'operations/document_upload.html', {
        'school': school,
        'students': students
    })


# ==================== ALUMNI ====================

@login_required
def alumni_list(request):
    """List alumni."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return redirect('home')
    
    if not user_can_manage_school(request.user) and not request.user.is_superuser:
        return redirect('home')
    
    alumni = Alumni.objects.filter(school=school).order_by('-graduation_year')[:200]
    
    return render(request, 'operations/alumni_list.html', {
        'alumni': alumni,
        'school': school
    })


@login_required
def alumni_create(request):
    """Add a new alumni record."""
    from accounts.permissions import is_school_admin
    school = _get_school(request)
    if not school or not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect('operations:alumni_list')
    
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        admission_number = request.POST.get('admission_number', '').strip()
        class_name = request.POST.get('class_name', '').strip()
        graduation_year = request.POST.get('graduation_year')
        current_occupation = request.POST.get('current_occupation', '').strip()
        current_institution = request.POST.get('current_institution', '').strip()
        contact_phone = request.POST.get('contact_phone', '').strip()
        contact_email = request.POST.get('contact_email', '').strip()
        
        if first_name and last_name and graduation_year:
            try:
                Alumni.objects.create(
                    school=school,
                    first_name=first_name,
                    last_name=last_name,
                    admission_number=admission_number,
                    class_name=class_name,
                    graduation_year=int(graduation_year),
                    current_occupation=current_occupation,
                    current_institution=current_institution,
                    contact_phone=contact_phone,
                    contact_email=contact_email
                )
                from django.contrib import messages
                messages.success(request, 'Alumni record added successfully!')
                return redirect('operations:alumni_list')
            except ValueError:
                pass
    
    return render(request, 'operations/alumni_form.html', {
        'school': school
    })


@login_required
def alumni_detail(request, pk):
    """View alumni details."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not (user_can_manage_school(request.user) or request.user.is_superuser):
        return redirect('home')
    
    alumni = get_object_or_404(Alumni, pk=pk, school=school)
    
    return render(request, 'operations/alumni_detail.html', {
        'alumni': alumni,
        'school': school
    })


@login_required
def alumni_event_list(request):
    """List alumni events."""
    school = _get_school(request)
    if not school:
        return redirect('home')
    
    events = AlumniEvent.objects.filter(school=school).order_by('-event_date')[:50]
    
    return render(request, 'operations/alumni_event_list.html', {
        'events': events,
        'school': school
    })


# ==================== TIMETABLE ====================

@login_required
def timetable_view(request):
    """View class timetable."""
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
    
    # Get unique classes for filter
    classes = sorted(set(TimetableSlot.objects.filter(school=school, is_active=True).values_list('class_name', flat=True)))
    
    return render(request, 'operations/timetable_view.html', {
        'slots': slots,
        'school': school,
        'classes': classes,
        'class_filter': class_filter,
        'day_filter': day_filter
    })


@login_required
def timetable_create(request):
    """Create timetable slot."""
    from accounts.permissions import is_school_admin
    from academics.models import Subject
    
    school = _get_school(request)
    if not school or not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect('operations:timetable_view')
    
    subjects = Subject.objects.filter(school=school).order_by('name')
    teachers = User.objects.filter(school=school, role='teacher').order_by('first_name', 'last_name')
    
    if request.method == 'POST':
        class_name = request.POST.get('class_name', '').strip()
        day = request.POST.get('day')
        period_number = request.POST.get('period_number')
        subject_id = request.POST.get('subject')
        teacher_id = request.POST.get('teacher')
        start_time = request.POST.get('start_time')
        end_time = request.POST.get('end_time')
        room = request.POST.get('room', '').strip()
        
        if class_name and day and period_number and subject_id and start_time and end_time:
            try:
                subject = Subject.objects.get(id=subject_id, school=school)
                teacher = User.objects.get(id=teacher_id) if teacher_id else None
                
                TimetableSlot.objects.create(
                    school=school,
                    class_name=class_name,
                    day=day,
                    period_number=int(period_number),
                    subject=subject,
                    teacher=teacher,
                    start_time=start_time,
                    end_time=end_time,
                    room=room
                )
                from django.contrib import messages
                messages.success(request, 'Timetable slot created!')
                return redirect('operations:timetable_view')
            except Exception:
                pass
    
    return render(request, 'operations/timetable_form.html', {
        'school': school,
        'subjects': subjects,
        'teachers': teachers
    })


@login_required
def timetable_conflicts(request):
    """View timetable conflicts."""
    from accounts.permissions import is_school_admin
    school = _get_school(request)
    if not school or not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect('home')
    
    conflicts = TimetableConflict.objects.filter(school=school, is_resolved=False).select_related('slot_1', 'slot_2').order_by('-created_at')
    
    return render(request, 'operations/timetable_conflicts.html', {
        'conflicts': conflicts,
        'school': school
    })


# ==================== STUDENT ID CARDS ====================

@login_required
def id_card_list(request):
    """List all student ID cards."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    
    id_cards = StudentIDCard.objects.filter(school=school).select_related('student', 'student__user', 'created_by').order_by('-created_at')[:200]
    
    return render(request, 'operations/id_card_list.html', {
        'id_cards': id_cards,
        'school': school
    })


@login_required
def id_card_create(request):
    """Create a new student ID card."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('operations:id_card_list')
    
    students = Student.objects.filter(school=school).exclude(id_card__isnull=False).select_related('user').order_by('class_name', 'admission_number')
    
    if request.method == 'POST':
        student_id = request.POST.get('student')
        card_number = request.POST.get('card_number', '').strip()
        issue_date = request.POST.get('issue_date')
        expiry_date = request.POST.get('expiry_date') or None
        
        if student_id and card_number and issue_date:
            student = Student.objects.filter(id=student_id, school=school).first()
            if student:
                try:
                    StudentIDCard.objects.create(
                        student=student,
                        school=school,
                        card_number=card_number,
                        issue_date=issue_date,
                        expiry_date=expiry_date,
                        created_by=request.user
                    )
                    from django.contrib import messages
                    messages.success(request, 'ID Card created successfully!')
                    return redirect('operations:id_card_list')
                except Exception:
                    pass
    
    return render(request, 'operations/id_card_form.html', {
        'school': school,
        'students': students
    })


@login_required
def id_card_view(request, pk):
    """View ID card details."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return redirect('home')
    
    id_card = get_object_or_404(StudentIDCard, pk=pk)
    
    # Check permission
    if school and id_card.school != school:
        return redirect('home')
    
    can_view = user_can_manage_school(request.user) or request.user.is_superuser
    can_view = can_view or (id_card.student and id_card.student.user == request.user)
    
    if not can_view:
        return redirect('home')
    
    return render(request, 'operations/id_card_view.html', {
        'id_card': id_card,
        'school': school
    })


@login_required
def id_card_print(request, pk):
    """Print ID card (returns printable view)."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return redirect('home')
    
    id_card = get_object_or_404(StudentIDCard, pk=pk, school=school)
    
    return render(request, 'operations/id_card_print.html', {
        'id_card': id_card,
        'school': school
    })


# ==================== SPORTS & CLUBS ====================

@login_required
def sport_list(request):
    """List all sports."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return redirect('home')
    
    sports = Sport.objects.filter(school=school).select_related('coach').order_by('name')
    can_manage = user_can_manage_school(request.user) or request.user.is_superuser
    
    return render(request, 'operations/sport_list.html', {
        'sports': sports,
        'school': school,
        'can_manage': can_manage
    })


@login_required
def sport_create(request):
    """Create a new sport."""
    from accounts.permissions import is_school_admin
    school = _get_school(request)
    if not school or not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect('operations:sport_list')
    
    teachers = User.objects.filter(school=school, role='teacher').order_by('first_name', 'last_name')
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        coach_id = request.POST.get('coach')
        description = request.POST.get('description', '').strip()
        is_active = request.POST.get('is_active') == 'on'
        
        if name:
            coach = User.objects.filter(id=coach_id, school=school).first() if coach_id else None
            Sport.objects.create(
                school=school,
                name=name,
                coach=coach,
                description=description,
                is_active=is_active
            )
            from django.contrib import messages
            messages.success(request, 'Sport created successfully!')
            return redirect('operations:sport_list')
    
    return render(request, 'operations/sport_form.html', {
        'school': school,
        'teachers': teachers
    })


@login_required
def sport_detail(request, pk):
    """View sport details with members."""
    school = _get_school(request)
    if not school:
        return redirect('home')
    
    sport = get_object_or_404(Sport, pk=pk, school=school)
    members = StudentSport.objects.filter(sport=sport, is_active=True).select_related('student', 'student__user')[:100]
    
    return render(request, 'operations/sport_detail.html', {
        'sport': sport,
        'members': members,
        'school': school
    })


@login_required
def sport_add_member(request, pk):
    """Add student to sport."""
    from accounts.permissions import is_school_admin
    school = _get_school(request)
    if not school or not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect('home')
    
    sport = get_object_or_404(Sport, pk=pk, school=school)
    students = Student.objects.filter(school=school).exclude(
        id__in=StudentSport.objects.filter(sport=sport, is_active=True).values_list('student_id', flat=True)
    ).select_related('user').order_by('class_name', 'admission_number')
    
    if request.method == 'POST':
        student_id = request.POST.get('student')
        jersey_number = request.POST.get('jersey_number', '').strip()
        position = request.POST.get('position', '').strip()
        
        if student_id:
            student = Student.objects.filter(id=student_id, school=school).first()
            if student:
                StudentSport.objects.create(
                    student=student,
                    sport=sport,
                    jersey_number=jersey_number,
                    position=position
                )
                from django.contrib import messages
                messages.success(request, 'Member added successfully!')
                return redirect('operations:sport_detail', pk=sport.pk)
    
    return render(request, 'operations/sport_add_member.html', {
        'sport': sport,
        'students': students,
        'school': school
    })


@login_required
def club_list(request):
    """List all clubs."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return redirect('home')
    
    clubs = Club.objects.filter(school=school).select_related('sponsor').order_by('name')
    can_manage = user_can_manage_school(request.user) or request.user.is_superuser
    
    return render(request, 'operations/club_list.html', {
        'clubs': clubs,
        'school': school,
        'can_manage': can_manage
    })


@login_required
def club_create(request):
    """Create a new club."""
    from accounts.permissions import is_school_admin
    school = _get_school(request)
    if not school or not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect('operations:club_list')
    
    teachers = User.objects.filter(school=school, role='teacher').order_by('first_name', 'last_name')
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        category = request.POST.get('category', 'other')
        sponsor_id = request.POST.get('sponsor')
        description = request.POST.get('description', '').strip()
        meeting_day = request.POST.get('meeting_day', '').strip()
        meeting_time = request.POST.get('meeting_time') or None
        is_active = request.POST.get('is_active') == 'on'
        
        if name:
            sponsor = User.objects.filter(id=sponsor_id, school=school).first() if sponsor_id else None
            Club.objects.create(
                school=school,
                name=name,
                category=category,
                sponsor=sponsor,
                description=description,
                meeting_day=meeting_day,
                meeting_time=meeting_time,
                is_active=is_active
            )
            from django.contrib import messages
            messages.success(request, 'Club created successfully!')
            return redirect('operations:club_list')
    
    return render(request, 'operations/club_form.html', {
        'school': school,
        'teachers': teachers
    })


@login_required
def club_detail(request, pk):
    """View club details with members."""
    school = _get_school(request)
    if not school:
        return redirect('home')
    
    club = get_object_or_404(Club, pk=pk, school=school)
    members = StudentClub.objects.filter(club=club, is_active=True).select_related('student', 'student__user')[:100]
    
    return render(request, 'operations/club_detail.html', {
        'club': club,
        'members': members,
        'school': school
    })


@login_required
def club_add_member(request, pk):
    """Add student to club."""
    from accounts.permissions import is_school_admin
    school = _get_school(request)
    if not school or not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect('home')
    
    club = get_object_or_404(Club, pk=pk, school=school)
    students = Student.objects.filter(school=school).exclude(
        id__in=StudentClub.objects.filter(club=club, is_active=True).values_list('student_id', flat=True)
    ).select_related('user').order_by('class_name', 'admission_number')
    
    if request.method == 'POST':
        student_id = request.POST.get('student')
        role = request.POST.get('role', 'member')
        
        if student_id:
            student = Student.objects.filter(id=student_id, school=school).first()
            if student:
                StudentClub.objects.create(
                    student=student,
                    club=club,
                    role=role
                )
                from django.contrib import messages
                messages.success(request, 'Member added successfully!')
                return redirect('operations:club_detail', pk=club.pk)
    
    return render(request, 'operations/club_add_member.html', {
        'club': club,
        'students': students,
        'school': school
    })


@login_required
def my_activities(request):
    """Student's sports and clubs."""
    school = _get_school(request)
    if not school:
        return redirect('home')
    
    role = getattr(request.user, 'role', None)
    
    if role == 'student':
        student = Student.objects.filter(user=request.user, school=school).first()
        if student:
            sports = StudentSport.objects.filter(student=student, is_active=True).select_related('sport')
            clubs = StudentClub.objects.filter(student=student, is_active=True).select_related('club')
            return render(request, 'operations/my_activities.html', {
                'sports': sports,
                'clubs': clubs,
                'school': school
            })
    
    return redirect('home')


# ==================== EXAM HALLS & SEATING ====================

@login_required
def exam_hall_list(request):
    """List exam halls."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    
    halls = ExamHall.objects.filter(school=school).order_by('name')
    
    return render(request, 'operations/exam_hall_list.html', {
        'halls': halls,
        'school': school
    })


@login_required
def exam_hall_create(request):
    """Create exam hall."""
    from accounts.permissions import is_school_admin
    school = _get_school(request)
    if not school or not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect('operations:exam_hall_list')
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        rows = request.POST.get('rows')
        seats_per_row = request.POST.get('seats_per_row')
        description = request.POST.get('description', '').strip()
        
        if name and rows and seats_per_row:
            ExamHall.objects.create(
                school=school,
                name=name,
                rows=int(rows),
                seats_per_row=int(seats_per_row),
                description=description
            )
            from django.contrib import messages
            messages.success(request, 'Exam hall created!')
            return redirect('operations:exam_hall_list')
    
    return render(request, 'operations/exam_hall_form.html', {
        'school': school
    })


@login_required
def seating_plan_list(request):
    """List seating plans."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    
    plans = SeatingPlan.objects.filter(school=school).select_related('exam_schedule', 'exam_schedule__subject', 'hall', 'created_by').order_by('-created_at')[:100]
    
    return render(request, 'operations/seating_plan_list.html', {
        'plans': plans,
        'school': school
    })


@login_required
def seating_plan_create(request):
    """Create seating plan."""
    from accounts.permissions import is_school_admin
    from academics.models import ExamSchedule
    school = _get_school(request)
    if not school or not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect('operations:seating_plan_list')
    
    exams = ExamSchedule.objects.filter(school=school).select_related('subject').order_by('-exam_date')[:50]
    halls = ExamHall.objects.filter(school=school).order_by('name')
    
    if request.method == 'POST':
        exam_id = request.POST.get('exam')
        hall_id = request.POST.get('hall')
        
        if exam_id and hall_id:
            exam = ExamSchedule.objects.filter(id=exam_id, school=school).first()
            hall = ExamHall.objects.filter(id=hall_id, school=school).first()
            if exam and hall:
                SeatingPlan.objects.create(
                    school=school,
                    exam_schedule=exam,
                    hall=hall,
                    created_by=request.user
                )
                from django.contrib import messages
                messages.success(request, 'Seating plan created!')
                return redirect('operations:seating_plan_list')
    
    return render(request, 'operations/seating_plan_form.html', {
        'school': school,
        'exams': exams,
        'halls': halls
    })


@login_required
def seating_plan_view(request, pk):
    """View seating plan."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    
    plan = get_object_or_404(SeatingPlan, pk=pk, school=school)
    assignments = SeatAssignment.objects.filter(seating_plan=plan).select_related('student', 'student__user').order_by('row_number', 'seat_number')
    
    return render(request, 'operations/seating_plan_view.html', {
        'plan': plan,
        'assignments': assignments,
        'school': school
    })


# ==================== EXPENSE CATEGORIES ====================

@login_required
def expense_category_list(request):
    """List expense categories."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    
    categories = ExpenseCategory.objects.filter(school=school).order_by('name')
    
    return render(request, 'operations/expense_category_list.html', {
        'categories': categories,
        'school': school
    })


@login_required
def expense_category_create(request):
    """Create expense category."""
    from accounts.permissions import is_school_admin
    school = _get_school(request)
    if not school or not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect('operations:expense_category_list')
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        
        if name:
            ExpenseCategory.objects.create(
                school=school,
                name=name,
                description=description
            )
            from django.contrib import messages
            messages.success(request, 'Category created!')
            return redirect('operations:expense_category_list')
    
    return render(request, 'operations/expense_category_form.html', {
        'school': school
    })


# ==================== PT MEETINGS ====================

@login_required
def pt_meeting_list(request):
    """List PT meetings."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school:
        return redirect('home')
    
    meetings = PTMeeting.objects.filter(school=school).order_by('-meeting_date')[:50]
    
    return render(request, 'operations/pt_meeting_list.html', {
        'meetings': meetings,
        'school': school
    })


@login_required
def pt_meeting_create(request):
    """Create PT meeting."""
    from accounts.permissions import is_school_admin
    school = _get_school(request)
    if not school or not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect('operations:pt_meeting_list')
    
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        meeting_date = request.POST.get('meeting_date')
        location = request.POST.get('location', '').strip()
        max_slots = request.POST.get('max_slots') or 20
        
        if title and meeting_date and location:
            PTMeeting.objects.create(
                school=school,
                title=title,
                description=description,
                meeting_date=meeting_date,
                location=location,
                max_slots=int(max_slots),
                created_by=request.user
            )
            from django.contrib import messages
            messages.success(request, 'Meeting scheduled!')
            return redirect('operations:pt_meeting_list')
    
    return render(request, 'operations/pt_meeting_form.html', {
        'school': school
    })


@login_required
def pt_meeting_detail(request, pk):
    """View PT meeting details and bookings."""
    school = _get_school(request)
    if not school:
        return redirect('home')
    
    meeting = get_object_or_404(PTMeeting, pk=pk, school=school)
    bookings = PTMeetingBooking.objects.filter(meeting=meeting).select_related('parent', 'student', 'student__user')[:100]
    
    return render(request, 'operations/pt_meeting_detail.html', {
        'meeting': meeting,
        'bookings': bookings,
        'school': school
    })


@login_required
def pt_meeting_book(request, pk):
    """Book PT meeting slot (for parents)."""
    school = _get_school(request)
    if not school:
        return redirect('home')
    
    role = getattr(request.user, 'role', None)
    if role != 'parent':
        return redirect('home')
    
    meeting = get_object_or_404(PTMeeting, pk=pk, school=school)
    children = Student.objects.filter(parent=request.user, school=school).select_related('user')
    
    if request.method == 'POST':
        student_id = request.POST.get('student')
        preferred_time = request.POST.get('preferred_time') or None
        topics = request.POST.get('topics_to_discuss', '').strip()
        
        if student_id:
            student = Student.objects.filter(id=student_id, school=school, parent=request.user).first()
            if student and meeting.available_slots > 0:
                PTMeetingBooking.objects.create(
                    meeting=meeting,
                    parent=request.user,
                    student=student,
                    preferred_time=preferred_time,
                    topics_to_discuss=topics
                )
                from django.contrib import messages
                messages.success(request, 'Booking confirmed!')
                return redirect('operations:pt_meeting_detail', pk=meeting.pk)
    
    return render(request, 'operations/pt_meeting_book.html', {
        'meeting': meeting,
        'children': children,
        'school': school
    })


# ==================== HEALTH RECORDS ====================

@login_required
def health_record_list(request):
    """List student health records."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    
    records = StudentHealth.objects.filter(school=school).select_related('student', 'student__user').order_by('-last_updated')[:200]
    
    return render(request, 'operations/health_record_list.html', {
        'records': records,
        'school': school
    })


@login_required
def health_record_create(request):
    """Create or update student health record."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    
    students = Student.objects.filter(school=school).exclude(
        health_record__isnull=False
    ).select_related('user').order_by('class_name', 'admission_number')
    
    if request.method == 'POST':
        student_id = request.POST.get('student')
        blood_type = request.POST.get('blood_type', '').strip()
        allergies = request.POST.get('allergies', '').strip()
        conditions = request.POST.get('medical_conditions', '').strip()
        medications = request.POST.get('medications', '').strip()
        emergency_contact = request.POST.get('emergency_contact', '').strip()
        emergency_name = request.POST.get('emergency_contact_name', '').strip()
        doctor_name = request.POST.get('doctor_name', '').strip()
        doctor_phone = request.POST.get('doctor_phone', '').strip()
        
        if student_id:
            student = Student.objects.filter(id=student_id, school=school).first()
            if student:
                StudentHealth.objects.update_or_create(
                    student=student,
                    school=school,
                    defaults={
                        'blood_type': blood_type,
                        'allergies': allergies,
                        'medical_conditions': conditions,
                        'medications': medications,
                        'emergency_contact': emergency_contact,
                        'emergency_contact_name': emergency_name,
                        'doctor_name': doctor_name,
                        'doctor_phone': doctor_phone,
                    }
                )
                from django.contrib import messages
                messages.success(request, 'Health record saved!')
                return redirect('operations:health_record_list')
    
    return render(request, 'operations/health_record_form.html', {
        'school': school,
        'students': students
    })


@login_required
def health_visit_list(request):
    """List health clinic visits."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    
    visits = HealthVisit.objects.filter(school=school).select_related('student', 'student__user', 'visited_by').order_by('-visit_date')[:200]
    
    return render(request, 'operations/health_visit_list.html', {
        'visits': visits,
        'school': school
    })


@login_required
def health_visit_create(request):
    """Record a health clinic visit."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    
    students = Student.objects.filter(school=school).select_related('user').order_by('class_name', 'admission_number')
    
    if request.method == 'POST':
        student_id = request.POST.get('student')
        complaint = request.POST.get('complaint', '').strip()
        diagnosis = request.POST.get('diagnosis', '').strip()
        treatment = request.POST.get('treatment', '').strip()
        is_follow_up = request.POST.get('is_follow_up') == 'on'
        
        if student_id and complaint:
            student = Student.objects.filter(id=student_id, school=school).first()
            if student:
                HealthVisit.objects.create(
                    school=school,
                    student=student,
                    complaint=complaint,
                    diagnosis=diagnosis,
                    treatment=treatment,
                    visited_by=request.user,
                    is_follow_up=is_follow_up
                )
                from django.contrib import messages
                messages.success(request, 'Visit recorded!')
                return redirect('operations:health_visit_list')
    
    return render(request, 'operations/health_visit_form.html', {
        'school': school,
        'students': students
    })


# ==================== INVENTORY MANAGEMENT ====================

@login_required
def inventory_category_list(request):
    """List inventory categories."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    
    categories = InventoryCategory.objects.filter(school=school).order_by('name')
    
    return render(request, 'operations/inventory_category_list.html', {
        'categories': categories,
        'school': school
    })


@login_required
def inventory_category_create(request):
    """Create inventory category."""
    from accounts.permissions import is_school_admin
    school = _get_school(request)
    if not school or not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect('home')
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        
        if name:
            InventoryCategory.objects.create(school=school, name=name, description=description)
            from django.contrib import messages
            messages.success(request, 'Category created!')
            return redirect('operations:inventory_category_list')
    
    return render(request, 'operations/inventory_category_form.html', {'school': school})


@login_required
def inventory_item_list(request):
    """List inventory items."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    
    items = InventoryItem.objects.filter(school=school).select_related('category').order_by('name')[:300]
    
    return render(request, 'operations/inventory_item_list.html', {
        'items': items,
        'school': school
    })


@login_required
def inventory_item_create(request):
    """Create inventory item."""
    from accounts.permissions import is_school_admin
    school = _get_school(request)
    if not school or not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect('home')
    
    categories = InventoryCategory.objects.filter(school=school)
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        category_id = request.POST.get('category')
        quantity = request.POST.get('quantity', 0)
        min_quantity = request.POST.get('min_quantity', 5)
        unit_cost = request.POST.get('unit_cost', 0)
        condition = request.POST.get('condition', 'new')
        location = request.POST.get('location', '').strip()
        description = request.POST.get('description', '').strip()
        serial = request.POST.get('serial_number', '').strip()
        
        if name:
            category = InventoryCategory.objects.get(id=category_id, school=school) if category_id else None
            InventoryItem.objects.create(
                school=school, name=name, category=category,
                quantity=int(quantity), min_quantity=int(min_quantity),
                unit_cost=unit_cost, condition=condition,
                location=location, description=description, serial_number=serial
            )
            from django.contrib import messages
            messages.success(request, 'Item added!')
            return redirect('operations:inventory_item_list')
    
    return render(request, 'operations/inventory_item_form.html', {
        'school': school, 'categories': categories
    })


@login_required
def inventory_transaction_list(request):
    """List inventory transactions."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    
    transactions = InventoryTransaction.objects.filter(school=school).select_related('item', 'recorded_by').order_by('-created_at')[:200]
    
    return render(request, 'operations/inventory_transaction_list.html', {
        'transactions': transactions,
        'school': school
    })


@login_required
def inventory_transaction_create(request):
    """Record inventory transaction."""
    from accounts.permissions import is_school_admin
    school = _get_school(request)
    if not school or not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect('home')
    
    items = InventoryItem.objects.filter(school=school).order_by('name')
    
    if request.method == 'POST':
        item_id = request.POST.get('item')
        trans_type = request.POST.get('transaction_type')
        quantity = request.POST.get('quantity')
        notes = request.POST.get('notes', '').strip()
        
        if item_id and trans_type and quantity:
            item = InventoryItem.objects.filter(id=item_id, school=school).first()
            if item:
                qty = int(quantity)
                if trans_type in ('usage', 'damage'):
                    qty = -abs(qty)
                
                InventoryTransaction.objects.create(
                    school=school, item=item, transaction_type=trans_type,
                    quantity=qty, notes=notes, recorded_by=request.user
                )
                
                # Update item quantity
                item.quantity = max(0, item.quantity + qty)
                item.save(update_fields=['quantity', 'last_updated'])
                
                from django.contrib import messages
                messages.success(request, 'Transaction recorded!')
                return redirect('operations:inventory_transaction_list')
    
    return render(request, 'operations/inventory_transaction_form.html', {
        'school': school, 'items': items
    })


# ==================== SCHOOL EVENTS ====================

@login_required
def school_event_list(request):
    """List school events."""
    school = _get_school(request)
    if not school:
        return redirect('home')
    
    events = SchoolEvent.objects.filter(school=school).order_by('-start_date')[:100]
    
    return render(request, 'operations/school_event_list.html', {
        'events': events,
        'school': school
    })


@login_required
def school_event_create(request):
    """Create school event."""
    from accounts.permissions import is_school_admin
    school = _get_school(request)
    if not school or not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect('home')
    
    if request.method == 'POST':
        from datetime import datetime
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        event_type = request.POST.get('event_type', 'other')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date') or None
        location = request.POST.get('location', '').strip()
        target = request.POST.get('target_audience', 'all')
        mandatory = request.POST.get('is_mandatory') == 'on'
        
        if title and start_date:
            try:
                start = datetime.strptime(start_date, '%Y-%m-%dT%H:%M')
            except:
                try:
                    start = datetime.strptime(start_date, '%Y-%m-%d')
                except:
                    start = timezone.now()
            
            end = None
            if end_date:
                try:
                    end = datetime.strptime(end_date, '%Y-%m-%dT%H:%M')
                except:
                    try:
                        end = datetime.strptime(end_date, '%Y-%m-%d')
                    except:
                        end = None
            
            SchoolEvent.objects.create(
                school=school, title=title, description=description,
                event_type=event_type, start_date=start, end_date=end,
                location=location, target_audience=target,
                is_mandatory=mandatory, created_by=request.user
            )
            from django.contrib import messages
            messages.success(request, 'Event created!')
            return redirect('operations:school_event_list')
    
    return render(request, 'operations/school_event_form.html', {'school': school})


@login_required
def school_event_detail(request, pk):
    """View event details and RSVPs."""
    school = _get_school(request)
    if not school:
        return redirect('home')
    
    event = get_object_or_404(SchoolEvent, pk=pk, school=school)
    rsvps = EventRSVP.objects.filter(event=event).select_related('student', 'student__user')[:200]
    
    return render(request, 'operations/school_event_detail.html', {
        'event': event,
        'rsvps': rsvps,
        'school': school
    })


@login_required
def school_event_rsvp(request, pk):
    """RSVP for an event (students/parents)."""
    school = _get_school(request)
    if not school:
        return redirect('home')
    
    role = getattr(request.user, 'role', None)
    if role not in ('student', 'parent'):
        return redirect('home')
    
    event = get_object_or_404(SchoolEvent, pk=pk, school=school)
    
    if role == 'student':
        student = Student.objects.filter(user=request.user, school=school).first()
        if student:
            EventRSVP.objects.update_or_create(
                event=event, student=student,
                defaults={'is_attending': True}
            )
    else:
        children = Student.objects.filter(parent=request.user, school=school)
        for child in children:
            EventRSVP.objects.update_or_create(
                event=event, student=child,
                defaults={'is_attending': True}
            )
    
    from django.contrib import messages
    messages.success(request, 'RSVP confirmed!')
    return redirect('operations:school_event_detail', pk=event.pk)


# ==================== HOMEWORK FOR STUDENTS & PARENTS ====================

@login_required
def homework_for_student(request):
    """Student sees homework and can submit. Parent sees children's homework."""
    from django.contrib import messages
    school = _get_school(request)
    if not school:
        return redirect('home')

    role = getattr(request.user, 'role', None)
    if role not in ['student', 'parent']:
        return redirect('home')

    from academics.models import Homework

    if role == 'student':
        student = Student.objects.filter(user=request.user, school=school).first()
        if not student:
            return redirect('home')
        students = [student]
        is_parent = False
    else:
        children = Student.objects.filter(parent=request.user, school=school)
        students = list(children)
        is_parent = True

    homeworks = []
    for student in students:
        hw_list = Homework.objects.filter(school=school, class_name=student.class_name).select_related('subject').order_by('-due_date')
        for hw in hw_list:
            submission = AssignmentSubmission.objects.filter(homework=hw, student=student).first()
            homeworks.append({
                'homework': hw,
                'student': student,
                'submission': submission,
                'is_submitted': submission is not None,
                'is_graded': submission.grade is not None if submission else False
            })

    return render(request, 'operations/homework_for_student.html', {
        'homeworks': homeworks,
        'school': school,
        'is_parent': is_parent
    })


@login_required
def homework_submit(request, homework_id):
    """Student submits homework."""
    from django.contrib import messages
    school = _get_school(request)
    if not school:
        return redirect('home')

    role = getattr(request.user, 'role', None)
    if role != 'student':
        return redirect('home')

    student = Student.objects.filter(user=request.user, school=school).first()
    if not student:
        return redirect('home')

    from academics.models import Homework
    homework = Homework.objects.filter(id=homework_id, school=school).first()
    if not homework:
        messages.error(request, 'Homework not found.')
        return redirect('operations:homework_for_student')

    existing = AssignmentSubmission.objects.filter(homework=homework, student=student).first()
    if existing:
        messages.error(request, 'You have already submitted this homework.')
        return redirect('operations:homework_for_student')

    if request.method == 'POST':
        submission_text = request.POST.get('submission_text', '').strip()
        file = request.FILES.get('file')

        if submission_text or file:
            AssignmentSubmission.objects.create(
                homework=homework,
                student=student,
                submission_text=submission_text,
                file=file,
                submitted_at=timezone.now()
            )
            messages.success(request, 'Homework submitted successfully!')
            return redirect('operations:homework_for_student')
        else:
            messages.error(request, 'Please provide text or upload a file.')

    return render(request, 'operations/homework_submit.html', {
        'homework': homework,
        'student': student,
        'school': school
    })


# ==================== ASSIGNMENT SUBMISSIONS ====================

@login_required
def assignment_submission_list(request):
    """List assignment submissions (teachers)."""
    from accounts.permissions import user_can_manage_school
    from academics.models import Homework
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    
    submissions = AssignmentSubmission.objects.filter(
        homework__subject__school=school
    ).select_related('homework', 'homework__subject', 'student', 'student__user', 'graded_by').order_by('-submitted_at')[:200]
    
    return render(request, 'operations/assignment_submission_list.html', {
        'submissions': submissions,
        'school': school
    })


@login_required
def assignment_submission_grade(request, pk):
    """Grade an assignment submission."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    
    submission = get_object_or_404(AssignmentSubmission, pk=pk)
    
    # Check school permission
    if submission.homework.subject.school != school:
        return redirect('home')
    
    if request.method == 'POST':
        grade = request.POST.get('grade')
        feedback = request.POST.get('feedback', '').strip()
        
        if grade:
            submission.grade = grade
            submission.feedback = feedback
            submission.status = 'graded'
            submission.graded_by = request.user
            submission.graded_at = timezone.now()
            submission.save()
            
            from django.contrib import messages
            messages.success(request, 'Submission graded!')
            return redirect('operations:assignment_submission_list')
    
    return render(request, 'operations/assignment_submission_grade.html', {
        'submission': submission,
        'school': school
    })


@login_required
def my_submissions(request):
    """Student's assignment submissions."""
    school = _get_school(request)
    if not school:
        return redirect('home')
    
    role = getattr(request.user, 'role', None)
    if role != 'student':
        return redirect('home')
    
    student = Student.objects.filter(user=request.user, school=school).first()
    if not student:
        return redirect('home')
    
    submissions = AssignmentSubmission.objects.filter(student=student).select_related(
        'homework', 'homework__subject'
    ).order_by('-submitted_at')[:100]
    
    return render(request, 'operations/my_submissions.html', {
        'submissions': submissions,
        'school': school
    })


# ==================== ONLINE EXAMS ====================

@login_required
def online_exam_list(request):
    """List online exams."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    
    exams = OnlineExam.objects.filter(school=school).select_related('subject', 'created_by').order_by('-start_time')[:100]
    
    return render(request, 'operations/online_exam_list.html', {
        'exams': exams,
        'school': school
    })


@login_required
def online_exam_create(request):
    """Create online exam."""
    from accounts.permissions import is_school_admin
    from academics.models import Subject
    school = _get_school(request)
    if not school or not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect('home')
    
    subjects = Subject.objects.filter(school=school).order_by('name')
    
    if request.method == 'POST':
        from datetime import datetime
        title = request.POST.get('title', '').strip()
        subject_id = request.POST.get('subject')
        class_level = request.POST.get('class_level', '').strip()
        exam_type = request.POST.get('exam_type', 'quiz')
        duration = request.POST.get('duration_minutes', 30)
        total_marks = request.POST.get('total_marks', 100)
        passing = request.POST.get('passing_marks', 50)
        start_time = request.POST.get('start_time')
        end_time = request.POST.get('end_time')
        
        if title and subject_id and start_time and end_time:
            subject = Subject.objects.filter(id=subject_id, school=school).first()
            if subject:
                try:
                    start = datetime.strptime(start_time, '%Y-%m-%dT%H:%M')
                    end = datetime.strptime(end_time, '%Y-%m-%dT%H:%M')
                    
                    exam = OnlineExam.objects.create(
                        school=school, title=title, subject=subject,
                        class_level=class_level, exam_type=exam_type,
                        duration_minutes=int(duration), total_marks=total_marks,
                        passing_marks=passing, start_time=start, end_time=end,
                        created_by=request.user, status='draft'
                    )
                    from django.contrib import messages
                    messages.success(request, 'Exam created! Add questions next.')
                    return redirect('operations:online_exam_detail', pk=exam.pk)
                except Exception:
                    pass
    
    return render(request, 'operations/online_exam_form.html', {
        'school': school, 'subjects': subjects
    })


@login_required
def online_exam_detail(request, pk):
    """View exam details and questions."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    
    exam = get_object_or_404(OnlineExam, pk=pk, school=school)
    questions = ExamQuestion.objects.filter(exam=exam).order_by('order')
    
    return render(request, 'operations/online_exam_detail.html', {
        'exam': exam,
        'questions': questions,
        'school': school
    })


@login_required
def online_exam_add_question(request, pk):
    """Add question to online exam."""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect('home')
    
    exam = get_object_or_404(OnlineExam, pk=pk, school=school)
    
    if request.method == 'POST':
        question_text = request.POST.get('question_text', '').strip()
        q_type = request.POST.get('question_type', 'multiple_choice')
        marks = request.POST.get('marks', 1)
        option_a = request.POST.get('option_a', '').strip()
        option_b = request.POST.get('option_b', '').strip()
        option_c = request.POST.get('option_c', '').strip()
        option_d = request.POST.get('option_d', '').strip()
        correct = request.POST.get('correct_answer', '').strip()
        order = exam.questions.count() + 1
        
        if question_text:
            ExamQuestion.objects.create(
                exam=exam, question_text=question_text, question_type=q_type,
                marks=marks, option_a=option_a, option_b=option_b,
                option_c=option_c, option_d=option_d, correct_answer=correct.upper(),
                order=order
            )
            from django.contrib import messages
            messages.success(request, 'Question added!')
            return redirect('operations:online_exam_detail', pk=exam.pk)
    
    return render(request, 'operations/online_exam_question_form.html', {
        'exam': exam, 'school': school
    })


@login_required
def online_exam_take(request, pk):
    """Take online exam (students)."""
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
    
    # Check if already attempted
    attempt = ExamAttempt.objects.filter(exam=exam, student=student).first()
    if attempt and attempt.is_completed:
        from django.contrib import messages
        messages.warning(request, 'You have already completed this exam.')
        return redirect('operations:online_exam_result', pk=attempt.pk)
    
    # Create attempt if not exists
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
        
        # Calculate total score
        total = attempt.answers.aggregate(Sum('marks_obtained'))['marks_obtained__sum'] or 0
        attempt.score = total
        attempt.is_completed = True
        attempt.submitted_at = timezone.now()
        attempt.save()
        
        from django.contrib import messages
        messages.success(request, f'Exam submitted! Score: {total}')
        return redirect('operations:online_exam_result', pk=attempt.pk)
    
    return render(request, 'operations/online_exam_take.html', {
        'exam': exam, 'questions': questions, 'attempt': attempt, 'school': school
    })


@login_required
def online_exam_result(request, pk):
    """View exam attempt result."""
    school = _get_school(request)
    if not school:
        return redirect('home')
    
    attempt = get_object_or_404(ExamAttempt, pk=pk)
    
    if attempt.student.user != request.user and not user_can_manage_school(request.user):
        return redirect('home')
    
    answers = ExamAnswer.objects.filter(attempt=attempt).select_related('question')
    
    return render(request, 'operations/online_exam_result.html', {
        'attempt': attempt, 'answers': answers, 'school': school
    })


# Import models at module level for annotations
from django.db import models
