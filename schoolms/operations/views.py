from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.utils import timezone

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


@login_required
def attendance_list(request):
    school = _require_school(request)
    if not school:
        return redirect("home")
    from_date = request.GET.get("from") or timezone.now().date()
    to_date = request.GET.get("to") or timezone.now().date()
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
        date = request.POST.get("date") or timezone.now().date()
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
    date = request.GET.get("date") or timezone.now().date()
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
    school = _get_school(request)
    if not school:
        return redirect("home")
    
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
    school = _get_school(request)
    if not school:
        return redirect("home")
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
    school = _get_school(request)
    if not school:
        return redirect("home")
    
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
    school = _get_school(request)
    if not school:
        return redirect("home")
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
    school = _get_school(request)
    if not school:
        return redirect("home")
    
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
    school = _get_school(request)
    if not school:
        return redirect("home")
    sales = TextbookSale.objects.filter(school=school).select_related("student", "student__user", "textbook")[:200]
    return render(request, "operations/textbook_sales.html", {"sales": sales, "school": school})


@login_required
def canteen_item_delete(request, pk):
    """Delete a canteen item."""
    school = _get_school(request)
    if not school:
        return redirect("home")
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
    school = _get_school(request)
    if not school:
        return redirect("home")
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
    school = _get_school(request)
    if not school:
        return redirect("home")
    book = get_object_or_404(Textbook, pk=pk, school=school)
    if request.method == "POST":
        book.delete()
        from django.contrib import messages
        messages.success(request, "Textbook deleted successfully!")
        return redirect("operations:textbook_list")
    return render(request, "operations/confirm_delete.html", {"object": book, "type": "textbook"})


@login_required
def attendance_delete(request, pk):
    """Delete an attendance record."""
    school = _get_school(request)
    if not school:
        return redirect("home")
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
    from_date = request.GET.get("from") or timezone.now().date()
    to_date = request.GET.get("to") or timezone.now().date()
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
    if not request.user.is_school_admin and not request.user.is_superuser:
        return redirect("home")
    
    if request.method == "POST":
        date = request.POST.get("date") or timezone.now().date()
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
    
    date = request.GET.get("date") or timezone.now().date()
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
    if not request.user.is_school_admin and not request.user.is_superuser:
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
    if not request.user.is_school_admin and not request.user.is_superuser:
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
    school = _get_school(request)
    if not school:
        return _redirect_no_school(request)
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
            Announcement.objects.create(
                school=school, title=title, content=content,
                target_audience=target, is_pinned=is_pinned, created_by=request.user
            )
            from django.contrib import messages
            messages.success(request, "Announcement created.")
            return redirect("operations:announcement_list")
    return render(request, "operations/announcement_form.html", {"school": school})


@login_required
def announcement_delete(request, pk):
    school = _get_school(request)
    if not school:
        return _redirect_no_school(request)
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
    school = _get_school(request)
    if not school:
        return _redirect_no_school(request)
    from accounts.permissions import is_school_admin
    if not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect("accounts:school_dashboard")
    logs = ActivityLog.objects.filter(school=school).select_related("user").order_by("-created_at")[:200]
    return render(request, "operations/activity_log_list.html", {"logs": logs, "school": school})
