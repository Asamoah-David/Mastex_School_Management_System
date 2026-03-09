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
    school = _require_school(request)
    if not school:
        return redirect("home")
    items = CanteenItem.objects.filter(school=school)
    return render(request, "operations/canteen_list.html", {"items": items, "school": school})


@login_required
def canteen_payments(request):
    school = _require_school(request)
    if not school:
        return redirect("home")
    payments = CanteenPayment.objects.filter(school=school).select_related("student", "student__user")[:200]
    return render(request, "operations/canteen_payments.html", {"payments": payments, "school": school})


@login_required
def bus_list(request):
    school = _require_school(request)
    if not school:
        return redirect("home")
    routes = BusRoute.objects.filter(school=school)
    return render(request, "operations/bus_list.html", {"routes": routes, "school": school})


@login_required
def bus_payments(request):
    school = _require_school(request)
    if not school:
        return redirect("home")
    payments = BusPayment.objects.filter(school=school).select_related("student", "student__user", "route")[:200]
    return render(request, "operations/bus_payments.html", {"payments": payments, "school": school})


@login_required
def textbook_list(request):
    school = _require_school(request)
    if not school:
        return redirect("home")
    books = Textbook.objects.filter(school=school)
    return render(request, "operations/textbook_list.html", {"books": books, "school": school})


@login_required
def textbook_sales(request):
    school = _require_school(request)
    if not school:
        return redirect("home")
    sales = TextbookSale.objects.filter(school=school).select_related("student", "student__user", "textbook")[:200]
    return render(request, "operations/textbook_sales.html", {"sales": sales, "school": school})


@login_required
def canteen_item_delete(request, pk):
    """Delete a canteen item."""
    school = _require_school(request)
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
    school = _require_school(request)
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
    school = _require_school(request)
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
    school = _require_school(request)
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
    school = _require_school(request)
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
    school = _require_school(request)
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
    school = _require_school(request)
    if not school:
        return redirect("home")
    events = AcademicCalendar.objects.filter(school=school).order_by("start_date")
    return render(request, "operations/calendar_list.html", {"events": events, "school": school})


@login_required
def calendar_create(request):
    """Create academic calendar event."""
    school = _require_school(request)
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
    school = _require_school(request)
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
