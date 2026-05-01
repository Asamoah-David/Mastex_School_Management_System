"""
ERP Enhancement Views — EarlyWarningFlag + CanteenOrder

These views provide basic list/detail/action surfaces for the new
EarlyWarningFlag and CanteenOrder models added in the ERP enhancements batch.

URL registration: operations/urls.py (operations namespace)
"""
import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from schools.features import is_feature_enabled

logger = logging.getLogger(__name__)


def _school(request):
    return getattr(request.user, "school", None)


def _require_roles(request, *roles):
    user = request.user
    if user.is_superuser or getattr(user, "is_super_admin", False):
        return True
    return getattr(user, "role", None) in roles


# ===========================================================================
# Early Warning Flags
# ===========================================================================

@login_required
def early_warning_list(request):
    """List open/acknowledged EarlyWarningFlags for the school."""
    from academics.models import EarlyWarningFlag

    school = _school(request)
    if not school:
        return redirect("home")
    if not is_feature_enabled(request, "early_warning"):
        from django.contrib import messages
        messages.error(request, "Early Warning is not enabled for your school.")
        return redirect("home")

    if not _require_roles(request, "school_admin", "admin", "teacher", "hod", "deputy_head", "counsellor"):
        return HttpResponseForbidden("Access denied.")

    status_filter = request.GET.get("status", "open")
    risk_filter = request.GET.get("risk", "")

    qs = EarlyWarningFlag.objects.filter(school=school).select_related(
        "student", "student__user", "acknowledged_by", "resolved_by"
    ).order_by("-created_at")

    if status_filter and status_filter != "all":
        qs = qs.filter(status=status_filter)
    if risk_filter:
        qs = qs.filter(risk_level=risk_filter)

    counts = {
        "open": EarlyWarningFlag.objects.filter(school=school, status="open").count(),
        "acknowledged": EarlyWarningFlag.objects.filter(school=school, status="acknowledged").count(),
        "resolved": EarlyWarningFlag.objects.filter(school=school, status="resolved").count(),
    }

    return render(request, "operations/early_warning_list.html", {
        "flags": qs[:100],
        "status_filter": status_filter,
        "risk_filter": risk_filter,
        "counts": counts,
    })


@login_required
@require_POST
def early_warning_update_status(request, pk):
    """AJAX/POST — acknowledge or resolve an EarlyWarningFlag."""
    from academics.models import EarlyWarningFlag

    school = _school(request)
    if not school:
        return JsonResponse({"error": "No school context."}, status=400)
    if not is_feature_enabled(request, "early_warning"):
        return JsonResponse({"error": "Feature disabled."}, status=403)

    if not _require_roles(request, "school_admin", "admin", "teacher", "hod", "deputy_head", "counsellor"):
        return JsonResponse({"error": "Access denied."}, status=403)

    flag = get_object_or_404(EarlyWarningFlag, pk=pk, school=school)
    action = request.POST.get("action")
    notes = request.POST.get("notes", "").strip()

    now = timezone.now()
    if action == "acknowledge" and flag.status == "open":
        flag.status = "acknowledged"
        flag.acknowledged_by = request.user
        flag.acknowledged_at = now
        if notes:
            flag.notes = notes
        flag.save(update_fields=["status", "acknowledged_by", "acknowledged_at", "notes", "updated_at"])
    elif action == "resolve" and flag.status in ("open", "acknowledged"):
        flag.status = "resolved"
        flag.resolved_by = request.user
        flag.resolved_at = now
        if notes:
            flag.notes = notes
        flag.save(update_fields=["status", "resolved_by", "resolved_at", "notes", "updated_at"])
    else:
        return JsonResponse({"error": f"Cannot apply action '{action}' to flag with status '{flag.status}'."}, status=400)

    return JsonResponse({"status": flag.status, "updated_at": flag.updated_at.isoformat()})


# ===========================================================================
# Canteen Pre-Orders
# ===========================================================================

@login_required
def canteen_order_list(request):
    """Student: view own orders. Kitchen staff / admin: view all orders for today."""
    from operations.models import CanteenOrder

    school = _school(request)
    if not school:
        return redirect("home")
    if not is_feature_enabled(request, "canteen"):
        from django.contrib import messages
        messages.error(request, "Canteen is not enabled for your school.")
        return redirect("home")

    user = request.user
    role = getattr(user, "role", None)
    today = timezone.localdate()
    date_filter = request.GET.get("date", str(today))

    try:
        from datetime import date
        filter_date = date.fromisoformat(date_filter)
    except (ValueError, TypeError):
        filter_date = today

    is_staff = user.is_superuser or role in ("school_admin", "admin", "canteen_staff", "hod", "deputy_head")

    if is_staff:
        qs = (
            CanteenOrder.objects.filter(school=school, order_date=filter_date)
            .select_related("student", "student__user")
            .prefetch_related("items__item")
            .order_by("status", "-created_at")
        )
    else:
        try:
            from students.models import Student
            student = Student.objects.filter(school=school, user=user).first()
        except Exception:
            student = None
        if not student:
            return redirect("home")
        qs = (
            CanteenOrder.objects.filter(school=school, student=student)
            .prefetch_related("items__item")
            .order_by("-order_date", "-created_at")[:30]
        )

    status_counts = {}
    if is_staff:
        from django.db.models import Count
        rows = CanteenOrder.objects.filter(school=school, order_date=filter_date).values("status").annotate(n=Count("pk"))
        status_counts = {r["status"]: r["n"] for r in rows}

    return render(request, "operations/canteen_order_list.html", {
        "orders": qs,
        "filter_date": filter_date,
        "is_staff": is_staff,
        "status_counts": status_counts,
    })


@login_required
def canteen_order_place(request):
    """Student: place a new pre-order for tomorrow."""
    from operations.models import CanteenItem, CanteenOrder, CanteenOrderItem
    from students.models import Student
    import datetime

    school = _school(request)
    if not school:
        return redirect("home")
    if not is_feature_enabled(request, "canteen"):
        from django.contrib import messages
        messages.error(request, "Canteen is not enabled for your school.")
        return redirect("home")

    student = Student.objects.filter(school=school, user=request.user, status="active").first()
    if not student:
        return HttpResponseForbidden("Only active students can place canteen orders.")

    tomorrow = timezone.localdate() + datetime.timedelta(days=1)
    menu_items = CanteenItem.objects.filter(school=school, is_available=True).order_by("category", "name")

    if request.method == "POST":
        order = CanteenOrder.objects.create(
            school=school,
            student=student,
            order_date=tomorrow,
            order_type="preorder",
            status="pending",
        )
        created_items = 0
        for item in menu_items:
            qty_str = request.POST.get(f"qty_{item.pk}", "0")
            try:
                qty = int(qty_str)
            except ValueError:
                qty = 0
            if qty > 0:
                CanteenOrderItem.objects.create(order=order, item=item, quantity=qty)
                created_items += 1

        if created_items == 0:
            order.delete()
            from django.contrib import messages
            messages.warning(request, "Please select at least one item.")
            return render(request, "operations/canteen_order_place.html", {
                "menu_items": menu_items,
                "tomorrow": tomorrow,
            })

        order.recalculate_total()
        from django.contrib import messages
        messages.success(request, f"Order placed for {tomorrow}. Total: GHS {order.total_amount}")
        return redirect("operations:canteen_order_list")

    return render(request, "operations/canteen_order_place.html", {
        "menu_items": menu_items,
        "tomorrow": tomorrow,
    })


@login_required
@require_POST
def canteen_order_update_status(request, pk):
    """Kitchen staff: advance order status (confirmed → ready → collected)."""
    from operations.models import CanteenOrder

    school = _school(request)
    if not school:
        return JsonResponse({"error": "No school context."}, status=400)
    if not is_feature_enabled(request, "canteen"):
        return JsonResponse({"error": "Feature disabled."}, status=403)

    if not _require_roles(request, "school_admin", "admin", "canteen_staff", "hod", "deputy_head"):
        return JsonResponse({"error": "Access denied."}, status=403)

    order = get_object_or_404(CanteenOrder, pk=pk, school=school)
    action = request.POST.get("action")

    transitions = {
        "confirm": ("pending", "confirmed"),
        "ready": ("confirmed", "ready"),
        "collect": ("ready", "collected"),
        "cancel": (None, "cancelled"),
    }

    if action not in transitions:
        return JsonResponse({"error": "Unknown action."}, status=400)

    expected_from, new_status = transitions[action]
    if expected_from and order.status != expected_from:
        return JsonResponse({"error": f"Order is '{order.status}', cannot apply '{action}'."}, status=400)

    order.status = new_status
    order.save(update_fields=["status", "updated_at"])
    return JsonResponse({"status": order.status})
