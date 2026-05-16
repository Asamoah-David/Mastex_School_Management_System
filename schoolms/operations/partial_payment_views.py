"""Flexible / partial-payment hub.

This module provides:
  1. ``partial_payment_page`` — a read-only summary of a student's
     outstanding charges for any fee type, with per-row "Pay online" links.
  2. ``partial_payment_dispatch`` — a POST endpoint that, given a
     ``(fee_type, item_id)`` pair, initialises a Paystack charge directly
     and redirects to the Paystack authorisation URL.  This is the
     "single-click pay" entry point used by the per-row buttons on the
     hub page.

We deliberately do NOT write to any payment table from the page itself —
the dispatch view only sets a ``payment_reference`` on the existing row,
which the relevant ``*_payment_verify`` endpoint will then complete.

Supported fee_types:
  - school_fees  (finance.Fee + FeePayment)
  - bus          (operations.BusPayment)
  - hostel       (operations.HostelFee)
  - canteen      (operations.CanteenPayment)
  - textbook     (operations.TextbookSale)
  - library      (operations.LibraryFine)
  - other        (generic — empty rows; user is told to contact the bursar)
"""
import logging
import uuid
from decimal import Decimal
from typing import Iterable, Optional, Tuple

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Case, DecimalField, F, Sum, Value, When
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PARTIAL_HUB_HISTORY_LINE_CAP = 50

FEE_LABELS = {
    "school_fees": "School Fees",
    "bus": "Bus / Transport",
    "hostel": "Hostel / Boarding",
    "canteen": "Canteen",
    "textbook": "Textbook",
    "library": "Library Fines",
    "pta": "PTA Dues",
    "exam": "Exam Fee",
    "uniform": "Uniform",
    "other": "Other Fee",
}

# fee_type -> (online_url_name, redirect_url_name_for_full_portal)
PORTAL_URLS = {
    "school_fees": (None, "finance:parent_fee_list"),
    "school_fee": (None, "finance:parent_fee_list"),
    "bus": ("operations:bus_initiate_payment", "operations:bus_my"),
    "hostel": ("operations:hostel_initiate_payment", "operations:hostel_my"),
    "canteen": ("operations:canteen_initiate_payment", "operations:canteen_my"),
    "textbook": ("operations:textbook_initiate_payment", "operations:textbook_my"),
    "library": (None, "operations:library_fine_list"),
}

# fee_type (lower) -> SchoolFeature registry key for the partial-payment hub
PARTIAL_HUB_FEE_TYPE_FEATURES = {
    "school_fees": "fee_management",
    "school_fee": "fee_management",
    "bus": "bus_transport",
    "hostel": "hostel",
    "canteen": "canteen",
    "textbook": "textbooks",
    "library": "library",
    "pta": "fee_management",
    "exam": "fee_management",
    "uniform": "fee_management",
    "other": "fee_management",
}


def _partial_hub_product_gate(request, school, fee_type: str, *, require_online_paystack: bool):
    """Return redirect if tenant feature flags block this hub/dispatch path."""
    from schools.features import is_feature_enabled_for_school

    ft = (fee_type or "school_fees").lower()
    key = PARTIAL_HUB_FEE_TYPE_FEATURES.get(ft, "fee_management")
    if not is_feature_enabled_for_school(school.pk, key):
        messages.error(request, "This fee area is disabled for your school.")
        return redirect("home")
    if require_online_paystack and not is_feature_enabled_for_school(school.pk, "online_payments"):
        messages.error(request, "Online payments are disabled for your school.")
        return redirect("home")
    return None


PERIOD_LABELS = {
    "daily": "Daily",
    "weekly": "Weekly",
    "monthly": "Monthly",
    "termly": "Full Term",
    "custom": "Custom",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_school(request: HttpRequest):
    school = getattr(request.user, "school", None)
    if school:
        return school
    if request.user.is_superuser or getattr(request.user, "is_super_admin", False):
        from schools.models import School
        sid = request.session.get("current_school_id")
        if sid:
            return School.objects.filter(pk=sid).first()
    return None


def _resolve_student(request: HttpRequest, school):
    """Resolve which Student record the request applies to, with authorization.

    Returns (student, error_response_or_none).
    """
    user = request.user
    role = getattr(user, "role", None)
    raw_id = request.GET.get("student") or request.POST.get("student_id")

    from students.models import Student

    if role == "student":
        student = Student.objects.filter(user=user, school=school).first()
        if not student:
            messages.error(request, "Student record not found.")
            return None, redirect("home")
        return student, None

    if role == "parent":
        # Parent must own the student
        if raw_id:
            student = (
                user.children.filter(id=raw_id, school=school).select_related("user", "school").first()
            )
        else:
            student = user.children.filter(school=school).select_related("user", "school").first()
        if not student:
            messages.error(request, "Student not found or not linked to your account.")
            return None, redirect("home")
        return student, None

    # Staff / admin: must supply student_id and student must belong to the same school
    if not raw_id:
        messages.error(request, "Please pick a student.")
        return None, redirect("home")
    student = Student.objects.filter(pk=raw_id, school=school).select_related("user", "school").first()
    if not student:
        messages.error(request, "Student not found in this school.")
        return None, redirect("home")
    return student, None


# ---------------------------------------------------------------------------
# Per-fee-type row collectors
#
# Each collector returns:
#   total_billed: Decimal
#   total_paid:   Decimal
#   balance:      Decimal
#   rows:         list[dict(label, amount, paid, balance, action_url, action_label, kind)]
# ---------------------------------------------------------------------------

_ZERO = Decimal("0")


def _collect_school_fees(school, student) -> Tuple[Decimal, Decimal, Decimal, list, dict]:
    try:
        from finance.models import Fee, FeePayment
    except Exception:
        logger.exception("partial_payment: finance models unavailable")
        return _ZERO, _ZERO, _ZERO, [], {}

    fees = (
        Fee.objects.filter(school=school, student=student, is_active=True, deleted_at__isnull=True)
        .order_by("-created_at")
    )
    rows = []
    total_billed = _ZERO
    total_paid = _ZERO
    for fee in fees:
        amt = Decimal(str(fee.amount or 0))
        paid_agg = FeePayment.objects.filter(
            fee=fee, status="completed", voided_at__isnull=True,
        ).aggregate(t=Sum("amount"))["t"] or 0
        paid = Decimal(str(paid_agg))
        balance = max(amt - paid, _ZERO)
        total_billed += amt
        total_paid += paid
        rows.append({
            "id": fee.id,
            "label": fee.description or (fee.fee_structure.name if fee.fee_structure_id else "School Fee"),
            "term": getattr(fee.term, "name", "") if fee.term_id else "",
            "amount": amt,
            "paid": paid,
            "balance": balance,
            "action_label": "Pay online" if balance > 0 else "Paid",
            "kind": "school_fees",
        })
    return total_billed, total_paid, max(total_billed - total_paid, _ZERO), rows, {}


def _collect_bus(school, student) -> Tuple[Decimal, Decimal, Decimal, list, dict]:
    try:
        from operations.models import BusPayment
    except Exception:
        logger.exception("partial_payment: BusPayment model unavailable")
        return _ZERO, _ZERO, _ZERO, [], {}

    qs = (
        BusPayment.objects.filter(school=school, student=student)
        .select_related("route")
        .order_by("-id")
    )
    rows = []
    total_billed = _ZERO
    total_paid = _ZERO
    for bp in qs:
        amt = Decimal(str(bp.amount or 0))
        paid = Decimal(str(bp.amount_paid or 0)) if bp.payment_status != "completed" else amt
        # Completed bus payments often have amount_paid==0 in legacy rows; treat as fully paid.
        if bp.payment_status == "completed":
            paid = amt
        balance = max(amt - paid, _ZERO)
        total_billed += amt
        total_paid += paid
        rows.append({
            "id": bp.id,
            "label": f"Bus — {bp.route.name if bp.route_id else 'Route removed'} ({bp.term_period or '—'})",
            "term": bp.term_period or "",
            "amount": amt,
            "paid": paid,
            "balance": balance,
            "status": bp.payment_status,
            "action_label": "Pay online" if balance > 0 else "Paid",
            "kind": "bus",
        })
    return total_billed, total_paid, max(total_billed - total_paid, _ZERO), rows, {}


def _collect_hostel(school, student) -> Tuple[Decimal, Decimal, Decimal, list, dict]:
    try:
        from operations.models import HostelFee
    except Exception:
        logger.exception("partial_payment: HostelFee model unavailable")
        return _ZERO, _ZERO, _ZERO, [], {}

    qs = (
        HostelFee.objects.filter(school=school, student=student)
        .select_related("hostel")
        .order_by("-id")
    )
    rows = []
    total_billed = _ZERO
    total_paid = _ZERO
    for hf in qs:
        amt = Decimal(str(hf.amount or 0))
        paid = Decimal(str(hf.amount_paid or 0))
        if hf.paid:
            paid = amt
        balance = max(amt - paid, _ZERO)
        total_billed += amt
        total_paid += paid
        rows.append({
            "id": hf.id,
            "label": f"Hostel — {hf.hostel.name if hf.hostel_id else 'Hostel removed'} ({hf.term or '—'})",
            "term": hf.term or "",
            "amount": amt,
            "paid": paid,
            "balance": balance,
            "status": hf.payment_status,
            "action_label": "Pay online" if balance > 0 else "Paid",
            "kind": "hostel",
        })
    return total_billed, total_paid, max(total_billed - total_paid, _ZERO), rows, {}


def _collect_canteen(school, student) -> Tuple[Decimal, Decimal, Decimal, list, dict]:
    try:
        from operations.models import CanteenPayment
    except Exception:
        logger.exception("partial_payment: CanteenPayment model unavailable")
        return _ZERO, _ZERO, _ZERO, [], {}

    D = DecimalField(max_digits=16, decimal_places=2)
    base = CanteenPayment.objects.filter(school=school, student=student)
    agg = base.aggregate(
        total_billed=Coalesce(Sum("amount"), Value(0, output_field=D), output_field=D),
        total_paid=Coalesce(
            Sum(
                Case(
                    When(payment_status="completed", then=F("amount")),
                    default=Coalesce(F("amount_paid"), Value(0, output_field=D)),
                    output_field=D,
                )
            ),
            Value(0, output_field=D),
            output_field=D,
        ),
    )
    total_billed = Decimal(str(agg["total_billed"] or 0))
    total_paid = Decimal(str(agg["total_paid"] or 0))
    balance = max(total_billed - total_paid, _ZERO)

    cap = PARTIAL_HUB_HISTORY_LINE_CAP
    slice_objs = list(base.order_by("-id")[: cap + 1])
    truncated = len(slice_objs) > cap
    slice_objs = slice_objs[:cap]
    rows = []
    for cp in slice_objs:
        amt = Decimal(str(cp.amount or 0))
        if cp.payment_status == "completed":
            paid = amt
        else:
            paid = Decimal(str(cp.amount_paid or 0))
        balance_row = max(amt - paid, _ZERO)
        rows.append({
            "id": cp.id,
            "label": f"Canteen — {cp.description or 'Meal'}",
            "term": "",
            "amount": amt,
            "paid": paid,
            "balance": balance_row,
            "status": cp.payment_status,
            "action_label": "Pay online" if balance_row > 0 else "Paid",
            "kind": "canteen",
        })
    meta = {}
    if truncated:
        meta["line_history_cap"] = cap
        meta["line_history_truncated"] = True
    return total_billed, total_paid, balance, rows, meta


def _collect_textbook(school, student) -> Tuple[Decimal, Decimal, Decimal, list, dict]:
    try:
        from operations.models import TextbookSale
    except Exception:
        logger.exception("partial_payment: TextbookSale model unavailable")
        return _ZERO, _ZERO, _ZERO, [], {}

    D = DecimalField(max_digits=16, decimal_places=2)
    base = TextbookSale.objects.filter(school=school, student=student).select_related("textbook")
    agg = base.aggregate(
        total_billed=Coalesce(Sum("amount"), Value(0, output_field=D), output_field=D),
        total_paid=Coalesce(
            Sum(
                Case(
                    When(payment_status="completed", then=F("amount")),
                    default=Value(0, output_field=D),
                    output_field=D,
                )
            ),
            Value(0, output_field=D),
            output_field=D,
        ),
    )
    total_billed = Decimal(str(agg["total_billed"] or 0))
    total_paid = Decimal(str(agg["total_paid"] or 0))
    balance = max(total_billed - total_paid, _ZERO)

    cap = PARTIAL_HUB_HISTORY_LINE_CAP
    slice_objs = list(base.order_by("-id")[: cap + 1])
    truncated = len(slice_objs) > cap
    slice_objs = slice_objs[:cap]
    rows = []
    for ts in slice_objs:
        amt = Decimal(str(ts.amount or 0))
        paid = amt if ts.payment_status == "completed" else _ZERO
        balance_row = amt - paid
        rows.append({
            "id": ts.id,
            "label": f"Textbook — {ts.textbook.title if ts.textbook_id else 'Book removed'} × {ts.quantity}",
            "term": "",
            "amount": amt,
            "paid": paid,
            "balance": balance_row,
            "status": ts.payment_status,
            "action_label": "Pay online" if balance_row > 0 else "Paid",
            "kind": "textbook",
        })
    meta = {}
    if truncated:
        meta["line_history_cap"] = cap
        meta["line_history_truncated"] = True
    return total_billed, total_paid, balance, rows, meta


def _collect_library(school, student) -> Tuple[Decimal, Decimal, Decimal, list, dict]:
    try:
        from operations.models import LibraryFine
    except Exception:
        logger.exception("partial_payment: LibraryFine model unavailable")
        return _ZERO, _ZERO, _ZERO, [], {}

    qs = (
        LibraryFine.objects.filter(school=school, issue__student=student)
        .exclude(status="waived")
        .select_related("issue", "issue__book")
        .order_by("-created_at")
    )
    rows = []
    total_billed = _ZERO
    total_paid = _ZERO
    for lf in qs:
        amt = Decimal(str(lf.fine_amount or 0))
        paid = Decimal(str(lf.amount_paid or 0))
        balance = max(amt - paid, _ZERO)
        total_billed += amt
        total_paid += paid
        rows.append({
            "id": lf.id,
            "label": f"Library fine — {lf.issue.book.title if lf.issue.book_id else 'Book removed'}",
            "term": "",
            "amount": amt,
            "paid": paid,
            "balance": balance,
            "status": lf.status,
            "action_label": "Pay in person" if balance > 0 else "Paid",
            "kind": "library",
        })
    return total_billed, total_paid, max(total_billed - total_paid, _ZERO), rows, {}


COLLECTORS = {
    "school_fees": _collect_school_fees,
    "school_fee": _collect_school_fees,  # legacy alias
    "bus": _collect_bus,
    "hostel": _collect_hostel,
    "canteen": _collect_canteen,
    "textbook": _collect_textbook,
    "library": _collect_library,
}


def _compute_rates(total_fee: Decimal, term_weeks: int = 13):
    if total_fee <= 0:
        return _ZERO, _ZERO, _ZERO, total_fee
    daily = (total_fee / Decimal(term_weeks * 5)).quantize(Decimal("0.01"))
    weekly = (total_fee / Decimal(term_weeks)).quantize(Decimal("0.01"))
    monthly = (total_fee / Decimal(3)).quantize(Decimal("0.01"))
    return daily, weekly, monthly, total_fee


# ---------------------------------------------------------------------------
# Main view
# ---------------------------------------------------------------------------

@login_required
def partial_payment_page(request: HttpRequest, fee_type: str = "school_fees") -> HttpResponse:
    school = _get_school(request)
    if not school:
        messages.error(request, "School not found.")
        return redirect("home")

    fee_type = (fee_type or "school_fees").lower()
    if fee_type not in COLLECTORS and fee_type not in FEE_LABELS:
        messages.error(request, "Unknown fee type.")
        return redirect("home")

    if (redir := _partial_hub_product_gate(request, school, fee_type, require_online_paystack=False)):
        return redir

    role = getattr(request.user, "role", None)
    raw_stu = (request.GET.get("student") or request.POST.get("student_id") or "").strip()
    if role not in ("student", "parent"):
        from accounts.permissions import can_manage_finance, user_can_manage_school

        if not (
            user_can_manage_school(request.user)
            or can_manage_finance(request.user)
            or getattr(request.user, "is_superuser", False)
            or getattr(request.user, "is_super_admin", False)
        ):
            messages.error(request, "You do not have access to this payment hub.")
            return redirect("home")
        if not raw_stu:
            from students.models import Student

            pick_cap = 400
            st_qs = Student.objects.filter(school=school).select_related("user").order_by(
                "class_name", "admission_number"
            )
            st_pref = list(st_qs[: pick_cap + 1])
            staff_pick_students_truncated = len(st_pref) > pick_cap
            staff_pick_students = st_pref[:pick_cap]
            return render(
                request,
                "operations/partial_payment.html",
                {
                    "school": school,
                    "staff_student_pick_required": True,
                    "fee_type": fee_type,
                    "fee_type_label": FEE_LABELS.get(fee_type, fee_type),
                    "staff_pick_students": staff_pick_students,
                    "staff_pick_students_truncated": staff_pick_students_truncated,
                    "staff_pick_cap": pick_cap,
                },
            )

    student, err = _resolve_student(request, school)
    if err is not None:
        return err

    currency = getattr(school, "currency", None) or "GHS"

    collector = COLLECTORS.get(fee_type)
    if collector is None:
        # Generic fee_type with no underlying model (e.g. "uniform", "exam") —
        # show empty summary and direct user to bursar / Record Payment.
        total_billed = total_paid = balance = _ZERO
        rows: list = []
        hub_notes: dict = {}
    else:
        try:
            total_billed, total_paid, balance, rows, hub_notes = collector(school, student)
        except Exception:
            logger.exception("partial_payment_page: collector failed for fee_type=%s student=%s",
                             fee_type, getattr(student, "id", None))
            total_billed = total_paid = balance = _ZERO
            rows = []
            hub_notes = {}
            messages.error(request, "Could not load fees. Please try again or contact the bursar.")

    daily_rate, weekly_rate, monthly_rate, termly_rate = _compute_rates(balance)
    half_balance = (balance / Decimal(2)).quantize(Decimal("0.01")) if balance > 0 else _ZERO

    payments: list = []
    if fee_type in ("school_fees", "school_fee"):
        try:
            from finance.models import FeePayment
            payments = list(
                FeePayment.objects.filter(
                    fee__student=student, fee__school=school,
                ).order_by("-created_at")[:20]
            )
        except Exception:
            logger.exception("partial_payment_page: failed to load FeePayment history")

    if request.method == "POST":
        method = request.POST.get("method", "cash")
        # The POST is intentionally a *route* — the page itself never writes
        # to any payment table.  Each fee type has its own initiate/verify
        # endpoint that handles online payment, idempotency and stock/refund.
        portal_pair = PORTAL_URLS.get(fee_type, (None, None))
        portal_name = portal_pair[1]
        if method == "paystack" and portal_name:
            messages.info(
                request,
                f"Pick the specific {FEE_LABELS.get(fee_type, fee_type).lower()} item below "
                "and click ‘Pay online’ to complete the payment.",
            )
            try:
                return redirect(portal_name)
            except Exception:
                logger.warning("partial_payment_page: redirect to %s failed", portal_name)
        else:
            messages.info(
                request,
                "Cash, bank transfer and Mobile Money payments are recorded by school staff "
                "from Operations → Record Payment. Please ask the bursar's office to record this payment.",
            )
        # Fall through to re-render the same page with the message.

    back_url = request.META.get("HTTP_REFERER", "/")

    return render(request, "operations/partial_payment.html", {
        "school": school,
        "student": student,
        "fee_type": fee_type,
        "fee_type_label": FEE_LABELS.get(fee_type, fee_type),
        "currency": currency,
        "total_fee": total_billed,
        "total_paid": total_paid,
        "balance": balance,
        "half_balance": half_balance,
        "daily_rate": daily_rate,
        "weekly_rate": weekly_rate,
        "monthly_rate": monthly_rate,
        "termly_rate": termly_rate,
        "outstanding_rows": rows,
        "payments": payments,
        "back_url": back_url,
        "hub_notes": hub_notes,
        "staff_student_pick_required": False,
    })


# ---------------------------------------------------------------------------
# Single-click Paystack dispatch
# ---------------------------------------------------------------------------

# fee_type -> (model_dotted_path, reference_prefix, verify_url_name, portal_url_name)
_DISPATCH_TABLE = {
    "bus": ("operations.models.BusPayment", "BUS", "operations:bus_payment_verify", "operations:bus_my"),
    "hostel": ("operations.models.HostelFee", "HOSTEL", "operations:hostel_payment_verify", "operations:hostel_my"),
    "canteen": ("operations.models.CanteenPayment", "CANTEEN", "operations:canteen_payment_verify", "operations:canteen_my"),
    "textbook": ("operations.models.TextbookSale", "TEXTBOOK", "operations:textbook_payment_verify", "operations:textbook_my"),
}


def _load_model(dotted: str):
    module_path, _, cls_name = dotted.rpartition(".")
    from importlib import import_module
    return getattr(import_module(module_path), cls_name)


def _row_student_id(row) -> Optional[int]:
    """Return the Student PK linked to a payment row (varies per model)."""
    return getattr(row, "student_id", None)


def _row_owner_check(user, row, school) -> bool:
    """Return True if user is allowed to charge this row."""
    if not row or getattr(row, "school_id", None) != school.id:
        return False
    student_id = _row_student_id(row)
    if not student_id:
        return False
    role = getattr(user, "role", None)
    if role == "student":
        from students.models import Student
        return Student.objects.filter(user=user, school=school, id=student_id).exists()
    if role == "parent":
        return user.children.filter(id=student_id).exists()
    # Staff/admin: must belong to the same school as the row.
    if user.is_superuser:
        return True
    user_school = getattr(user, "school", None)
    if user_school and user_school.id == school.id:
        # Staff initiating payment on behalf of a student/parent is allowed.
        return True
    return False


@login_required
@require_POST
def partial_payment_dispatch(request: HttpRequest, fee_type: str, item_id: int) -> HttpResponse:
    """Initialize Paystack for a single outstanding row, then redirect.

    POST-only.  For school_fees we hand off to the canonical
    ``finance:pay`` view.  For library fines (no online flow) we redirect
    to the fines list with a message.  For bus/hostel/canteen/textbook we
    initialize a Paystack charge directly against the existing row and
    redirect to the authorisation URL — on success, the existing
    ``*_payment_verify`` endpoint will mark the row complete.
    """
    fee_type = (fee_type or "").lower()
    school = _get_school(request)
    if not school:
        messages.error(request, "School not found.")
        return redirect("home")

    require_online = fee_type != "library"
    if (redir := _partial_hub_product_gate(request, school, fee_type, require_online_paystack=require_online)):
        return redir

    # ---- school_fees: just hand off to the canonical Paystack view -----
    if fee_type in ("school_fees", "school_fee"):
        try:
            from finance.models import Fee
            fee = Fee.objects.filter(pk=item_id, school=school).first()
        except Exception:
            fee = None
        if not fee:
            messages.error(request, "Fee not found.")
            return redirect("operations:partial_payment", fee_type="school_fees")
        if not _row_owner_check(request.user, fee, school):
            messages.error(request, "You are not authorised to pay this fee.")
            return redirect("operations:partial_payment", fee_type="school_fees")
        return redirect("finance:pay", fee_id=fee.id)

    # ---- library: no online flow ----------------------------------------
    if fee_type == "library":
        messages.info(
            request,
            "Library fines are paid in person at the library office. "
            "Please bring the displayed amount.",
        )
        try:
            return redirect("operations:library_fine_list")
        except Exception:
            return redirect("operations:partial_payment", fee_type="library")

    # ---- bus / hostel / canteen / textbook ------------------------------
    table = _DISPATCH_TABLE.get(fee_type)
    if not table:
        messages.error(request, "Unsupported fee type for online payment.")
        return redirect("operations:partial_payment", fee_type=fee_type or "school_fees")

    model_path, ref_prefix, verify_name, portal_name = table

    try:
        Model = _load_model(model_path)
    except Exception:
        logger.exception("partial_payment_dispatch: cannot load model %s", model_path)
        messages.error(request, "Payment module unavailable.")
        return redirect("operations:partial_payment", fee_type=fee_type)

    row = Model.objects.filter(pk=item_id, school=school).select_related("student").first()
    if not row:
        messages.error(request, "Payment record not found.")
        return redirect("operations:partial_payment", fee_type=fee_type)

    if not _row_owner_check(request.user, row, school):
        messages.error(request, "You are not authorised to pay this record.")
        return redirect("operations:partial_payment", fee_type=fee_type)

    status = (getattr(row, "payment_status", "") or "").lower()
    if status == "completed" or getattr(row, "paid", False):
        messages.info(request, "This payment has already been completed.")
        try:
            return redirect(portal_name)
        except Exception:
            return redirect("operations:partial_payment", fee_type=fee_type)

    if status == "partial":
        # Partial-credit rows must go through the model-specific portal
        # (which uses ``add_payment`` to credit deltas correctly).  We do
        # NOT charge full amount here because the verify endpoints mark
        # the whole row as paid without crediting partial deltas.
        messages.info(
            request,
            "This record has partial payments already. Please continue from "
            "the dedicated portal so the balance is credited correctly.",
        )
        try:
            return redirect(portal_name)
        except Exception:
            return redirect("operations:partial_payment", fee_type=fee_type)

    # School must have payout setup configured
    if not getattr(school, "is_payout_setup_active", False):
        messages.error(
            request,
            "Online payments are not yet available for this school. "
            "Please use cash / bank transfer recorded by the bursar.",
        )
        return redirect("operations:partial_payment", fee_type=fee_type)

    amount = Decimal(str(getattr(row, "amount", 0) or 0)).quantize(Decimal("0.01"))
    if amount <= 0:
        messages.error(request, "This record has no chargeable amount.")
        return redirect("operations:partial_payment", fee_type=fee_type)

    # Reuse the row's existing reference for idempotency; allocate one if absent.
    existing_ref = getattr(row, "payment_reference", "") or ""
    reference = existing_ref or f"{ref_prefix}_{uuid.uuid4().hex[:12].upper()}"
    if reference != existing_ref:
        try:
            with transaction.atomic():
                Model.objects.filter(pk=row.pk).update(payment_reference=reference)
        except Exception:
            logger.exception("partial_payment_dispatch: failed to persist reference fee_type=%s row=%s",
                             fee_type, row.pk)

    student = row.student
    parent_email = None
    if getattr(request.user, "role", None) == "parent" and request.user.email:
        parent_email = request.user.email
    if not parent_email and student and getattr(student, "user", None) and student.user.email:
        parent_email = student.user.email
    if not parent_email and request.user.email:
        parent_email = request.user.email
    if not parent_email:
        messages.error(
            request,
            "No email address on file for online payment. "
            "Please update your account email and try again.",
        )
        return redirect("operations:partial_payment", fee_type=fee_type)

    try:
        callback_url = request.build_absolute_uri(
            reverse(verify_name) + f"?payment_id={row.pk}"
        )
    except Exception:
        logger.exception("partial_payment_dispatch: could not build callback url for %s", verify_name)
        messages.error(request, "Payment system temporarily unavailable.")
        return redirect("operations:partial_payment", fee_type=fee_type)

    metadata = {
        "payment_type": fee_type,
        "payment_id": str(row.pk),
        "student_id": str(_row_student_id(row) or ""),
        "school_id": str(school.id),
        "source": "partial_payment_hub",
    }

    school_subaccount = (
        school.paystack_subaccount_code
        if getattr(school, "is_payout_setup_active", False)
        else None
    )
    currency = getattr(settings, "PAYSTACK_CURRENCY", None) or getattr(school, "currency", None) or "GHS"

    try:
        from finance.paystack_service import paystack_service
        result = paystack_service.initialize_payment(
            email=parent_email,
            amount=float(amount),
            callback_url=callback_url,
            reference=reference,
            metadata=metadata,
            subaccount=school_subaccount,
            currency=currency,
        )
    except Exception:
        logger.exception("partial_payment_dispatch: paystack init failed fee_type=%s row=%s",
                         fee_type, row.pk)
        messages.error(request, "Could not start online payment. Please try again.")
        return redirect("operations:partial_payment", fee_type=fee_type)

    if not result or not result.get("status"):
        err = (result or {}).get("message") if isinstance(result, dict) else None
        messages.error(request, err or "Payment initialisation failed. Please try again.")
        return redirect("operations:partial_payment", fee_type=fee_type)

    auth_url = (result.get("data") or {}).get("authorization_url")
    if not auth_url:
        messages.error(request, "Payment initialisation returned no URL. Please try again.")
        return redirect("operations:partial_payment", fee_type=fee_type)

    return redirect(auth_url)
