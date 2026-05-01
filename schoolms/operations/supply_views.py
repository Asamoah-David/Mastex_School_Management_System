"""Class Supply / Contribution Tracker views."""
from __future__ import annotations

import csv
import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.permissions import is_parent, user_can_manage_school
from schools.features import is_feature_enabled
from students.models import SchoolClass, Student

from .models.supply import ClassSupplyItem, ClassSupplyRequest, StudentSupplyContribution


def _school(request):
    return getattr(request.user, "school", None)


# ---------------------------------------------------------------------------
# Staff views
# ---------------------------------------------------------------------------

@login_required
def supply_list(request):
    """List all supply requests for this school."""
    school = _school(request)
    if not school:
        return redirect("home")
    if not user_can_manage_school(request.user):
        messages.error(request, "Access denied.")
        return redirect("home")
    if not is_feature_enabled(request, "class_supplies"):
        messages.error(request, "Class Supply Tracker is not enabled for your school.")
        return redirect("accounts:school_dashboard")

    class_filter = request.GET.get("class", "")
    qs = (
        ClassSupplyRequest.objects.filter(school=school)
        .select_related("school_class", "created_by")
        .prefetch_related("items")
        .order_by("-created_at")
    )
    if class_filter:
        qs = qs.filter(school_class_id=class_filter)

    classes = SchoolClass.objects.filter(school=school).order_by("name")
    return render(request, "operations/supply_list.html", {
        "requests": qs,
        "classes": classes,
        "class_filter": class_filter,
    })


@login_required
def supply_create(request):
    """Create a new supply request for a class."""
    school = _school(request)
    if not school:
        return redirect("home")
    if not user_can_manage_school(request.user):
        messages.error(request, "Access denied.")
        return redirect("home")
    if not is_feature_enabled(request, "class_supplies"):
        messages.error(request, "Class Supply Tracker is not enabled for your school.")
        return redirect("accounts:school_dashboard")

    classes = SchoolClass.objects.filter(school=school).order_by("name")

    if request.method == "POST":
        class_pk = request.POST.get("school_class", "")
        title = request.POST.get("title", "").strip()
        academic_year = request.POST.get("academic_year", "").strip()
        description = request.POST.get("description", "").strip()
        deadline_raw = request.POST.get("deadline", "")
        notify = request.POST.get("notify_parents") == "on"

        if not class_pk or not title:
            messages.error(request, "Class and title are required.")
            return render(request, "operations/supply_form.html", {"classes": classes, "post": request.POST})

        school_class = get_object_or_404(SchoolClass, pk=class_pk, school=school)
        deadline = None
        if deadline_raw:
            try:
                deadline = datetime.date.fromisoformat(deadline_raw)
            except ValueError:
                pass

        supply_req = ClassSupplyRequest.objects.create(
            school=school,
            school_class=school_class,
            title=title,
            academic_year=academic_year,
            description=description,
            deadline=deadline,
            notify_parents=notify,
            created_by=request.user,
        )

        if notify:
            _notify_parents(request, supply_req)

        messages.success(request, f"Supply request '{title}' created for {school_class.name}.")
        return redirect("operations:supply_detail", pk=supply_req.pk)

    return render(request, "operations/supply_form.html", {"classes": classes})


def _notify_parents(request, supply_req):
    """Send in-app notification to parents/guardians of students in the class.

    NOTE: Called after items have been added (via supply_notify) or at creation
    with a generic message since items may not exist yet.
    """
    try:
        from notifications.models import Notification
        from students.models import StudentGuardian
        import logging as _logging
        _log = _logging.getLogger(__name__)

        students = list(Student.objects.filter(
            school_class=supply_req.school_class,
            school=supply_req.school,
            deleted_at__isnull=True,
            status="active",
        ).select_related("parent", "user"))

        deadline_str = supply_req.deadline.strftime("%d %b %Y") if supply_req.deadline else "soon"
        item_names = list(supply_req.items.values_list("name", flat=True))
        if item_names:
            item_preview = ", ".join(item_names[:4]) + ("..." if len(item_names) > 4 else "")
        else:
            item_preview = None

        # Build a set of (parent_pk, student) tuples to notify
        student_ids = [s.pk for s in students]
        guardian_map: dict[int, list] = {}  # student_pk → [guardian_user, ...]
        for sg in StudentGuardian.objects.filter(
            student_id__in=student_ids
        ).select_related("guardian"):
            guardian_map.setdefault(sg.student_id, []).append(sg.guardian)

        parents_notified: set[int] = set()
        for student in students:
            recipients = []
            if student.parent_id and student.parent_id not in parents_notified:
                recipients.append(student.parent)
            for guardian in guardian_map.get(student.pk, []):
                if guardian.pk not in parents_notified:
                    recipients.append(guardian)
            if not recipients:
                continue
            if item_preview:
                body = (
                    f"Please arrange for {student.user.get_full_name()} to bring the following "
                    f"to school by {deadline_str}: {item_preview}. "
                    f"Check the parent portal for the full list."
                )
            else:
                body = (
                    f"A new supply request has been created for {supply_req.school_class.name} "
                    f"({supply_req.title}). Please check the parent portal for the full list of "
                    f"required items (deadline: {deadline_str})."
                )
            for parent in recipients:
                try:
                    Notification.create_notification(
                        user=parent,
                        title=f"Supply Request — {supply_req.school_class.name}",
                        message=body,
                        notification_type="info",
                        school=supply_req.school,
                    )
                    parents_notified.add(parent.pk)
                except Exception:
                    _log.exception("Supply notification failed for user %s", parent.pk)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Supply parent notification failed")


@login_required
def supply_detail(request, pk):
    """Detail view: items + contribution grid."""
    school = _school(request)
    if not school:
        return redirect("home")
    if not user_can_manage_school(request.user):
        messages.error(request, "Access denied.")
        return redirect("home")
    if not is_feature_enabled(request, "class_supplies"):
        messages.error(request, "Class Supply Tracker is not enabled for your school.")
        return redirect("accounts:school_dashboard")

    supply_req = get_object_or_404(
        ClassSupplyRequest.objects.select_related("school_class", "created_by"),
        pk=pk, school=school,
    )
    items = supply_req.items.prefetch_related("contributions__student__user").order_by("order", "name")
    students = Student.objects.filter(
        school_class=supply_req.school_class,
        school=school,
        deleted_at__isnull=True,
        status="active",
    ).select_related("user").order_by("user__last_name", "user__first_name")

    contributed_map = {}
    for item in items:
        contributed_map[item.pk] = set(
            item.contributions.values_list("student_id", flat=True)
        )

    return render(request, "operations/supply_detail.html", {
        "supply_req": supply_req,
        "items": items,
        "students": students,
        "contributed_map": contributed_map,
    })


@login_required
@require_POST
def supply_item_add(request, pk):
    """Add an item to an existing supply request."""
    school = _school(request)
    if not school or not user_can_manage_school(request.user):
        messages.error(request, "Access denied.")
        return redirect("home")
    supply_req = get_object_or_404(ClassSupplyRequest, pk=pk, school=school)
    name = request.POST.get("name", "").strip()
    if not name:
        messages.error(request, "Item name is required.")
        return redirect("operations:supply_detail", pk=pk)

    try:
        qty = max(1, int(request.POST.get("quantity_per_student", 1) or 1))
    except (ValueError, TypeError):
        qty = 1
    unit = request.POST.get("unit", "piece")
    notes = request.POST.get("notes", "").strip()

    ClassSupplyItem.objects.create(
        request=supply_req,
        name=name,
        quantity_per_student=qty,
        unit=unit,
        notes=notes,
        order=supply_req.items.count(),
    )
    messages.success(request, f"'{name}' added to supply list.")
    return redirect("operations:supply_detail", pk=pk)


@login_required
@require_POST
def supply_mark(request, item_pk, student_pk):
    """Mark that a student has brought a supply item."""
    school = _school(request)
    if not school or not user_can_manage_school(request.user):
        messages.error(request, "Access denied.")
        return redirect("home")
    item = get_object_or_404(ClassSupplyItem, pk=item_pk, request__school=school)
    student = get_object_or_404(Student, pk=student_pk, school=school)
    qty = int(request.POST.get("quantity_brought", 1) or 1)
    notes = request.POST.get("notes", "").strip()

    obj, created = StudentSupplyContribution.objects.get_or_create(
        item=item,
        student=student,
        defaults=dict(
            quantity_brought=qty,
            brought_date=timezone.now().date(),
            recorded_by=request.user,
            notes=notes,
        ),
    )
    if not created:
        obj.quantity_brought = qty
        obj.brought_date = timezone.now().date()
        obj.recorded_by = request.user
        obj.notes = notes
        obj.save(update_fields=["quantity_brought", "brought_date", "recorded_by", "notes"])

    return redirect("operations:supply_detail", pk=item.request_id)


@login_required
@require_POST
def supply_unmark(request, item_pk, student_pk):
    """Remove a student's contribution record."""
    school = _school(request)
    if not school or not user_can_manage_school(request.user):
        messages.error(request, "Access denied.")
        return redirect("home")
    item = get_object_or_404(ClassSupplyItem, pk=item_pk, request__school=school)
    student = get_object_or_404(Student, pk=student_pk, school=school)
    StudentSupplyContribution.objects.filter(item=item, student=student).delete()
    return redirect("operations:supply_detail", pk=item.request_id)


@login_required
def supply_export_csv(request, pk):
    """Export contribution status as CSV."""
    school = _school(request)
    if not school or not user_can_manage_school(request.user):
        messages.error(request, "Access denied.")
        return redirect("home")
    supply_req = get_object_or_404(ClassSupplyRequest, pk=pk, school=school)
    items = supply_req.items.prefetch_related("contributions__student__user").order_by("order", "name")
    students = Student.objects.filter(
        school_class=supply_req.school_class, school=school,
        deleted_at__isnull=True, status="active",
    ).select_related("user").order_by("user__last_name", "user__first_name")

    contributed_map = {}
    for item in items:
        contributed_map[item.pk] = set(item.contributions.values_list("student_id", flat=True))

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="supply_{supply_req.school_class.name}_{supply_req.pk}.csv"'
    )
    writer = csv.writer(response)
    header = ["Student Name", "Admission No"] + [f"{i.name} ({i.quantity_per_student} {i.unit})" for i in items]
    writer.writerow(header)
    for student in students:
        row = [student.user.get_full_name(), student.admission_number]
        for item in items:
            row.append("Yes" if student.pk in contributed_map.get(item.pk, set()) else "No")
        writer.writerow(row)
    return response


@login_required
@require_POST
def supply_notify(request, pk):
    """(Re-)send parent notifications for a supply request after items have been added."""
    school = _school(request)
    if not school or not user_can_manage_school(request.user):
        messages.error(request, "Access denied.")
        return redirect("home")
    supply_req = get_object_or_404(ClassSupplyRequest, pk=pk, school=school)
    _notify_parents(request, supply_req)
    messages.success(request, "Notifications sent to parents/guardians.")
    return redirect("operations:supply_detail", pk=pk)


@login_required
@require_POST
def supply_toggle(request, pk):
    """Activate / deactivate a supply request."""
    school = _school(request)
    if not school or not user_can_manage_school(request.user):
        messages.error(request, "Access denied.")
        return redirect("home")
    supply_req = get_object_or_404(ClassSupplyRequest, pk=pk, school=school)
    supply_req.is_active = not supply_req.is_active
    supply_req.save(update_fields=["is_active"])
    state = "activated" if supply_req.is_active else "closed"
    messages.success(request, f"Supply request '{supply_req.title}' {state}.")
    return redirect("operations:supply_list")


# ---------------------------------------------------------------------------
# Parent portal view
# ---------------------------------------------------------------------------

@login_required
def parent_supply_list(request):
    """Parent sees pending supply items for their child/children."""
    if not is_parent(request.user):
        messages.error(request, "Access denied.")
        return redirect("home")

    children = Student.objects.filter(
        parent=request.user, deleted_at__isnull=True, status="active"
    ).select_related("school_class", "school", "user")

    from students.models import StudentGuardian
    guardian_children_pks = set(
        StudentGuardian.objects.filter(guardian=request.user).values_list("student_id", flat=True)
    )
    if guardian_children_pks:
        extra = Student.objects.filter(
            pk__in=guardian_children_pks, deleted_at__isnull=True, status="active"
        ).select_related("school_class", "school", "user")
        children = list(children) + [s for s in extra if s.pk not in {c.pk for c in children}]

    child_data = []
    for child in children:
        if not child.school_class_id:
            continue
        pending_items = []
        for req in ClassSupplyRequest.objects.filter(
            school_class=child.school_class,
            school=child.school,
            is_active=True,
        ).prefetch_related("items__contributions"):
            for item in req.items.all():
                already_brought = item.contributions.filter(student=child).exists()
                if not already_brought:
                    pending_items.append({"item": item, "request": req})
        if pending_items:
            child_data.append({"child": child, "pending": pending_items})

    return render(request, "operations/parent_supply_list.html", {"child_data": child_data})
