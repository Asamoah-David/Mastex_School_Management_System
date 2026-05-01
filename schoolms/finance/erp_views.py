"""
Finance ERP views — FeeDiscount, FeeInstallmentPlan, PurchaseOrder, BankAccount.
Guarded to school_admin / finance / accountant roles.
"""
import logging
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)


def _school(request):
    return getattr(request.user, "school", None)


def _is_finance_admin(request):
    user = request.user
    if user.is_superuser or getattr(user, "is_super_admin", False):
        return True
    return getattr(user, "role", None) in (
        "school_admin", "admin", "bursar", "finance", "accountant", "deputy_head",
    )


# ===========================================================================
# FeeDiscount
# ===========================================================================

@login_required
def fee_discount_list(request):
    from finance.models import FeeDiscount
    school = _school(request)
    if not school:
        return redirect("home")
    if not _is_finance_admin(request):
        return HttpResponseForbidden("Access denied.")
    discounts = (
        FeeDiscount.objects.filter(school=school)
        .select_related("fee", "fee__student", "fee__student__user", "approved_by")
        .order_by("-created_at")
    )
    return render(request, "finance/fee_discount_list.html", {"discounts": discounts})


@login_required
def fee_discount_create(request, fee_id):
    """Apply a discount to a specific fee."""
    from finance.models import Fee, FeeDiscount
    school = _school(request)
    if not school:
        return redirect("home")
    if not _is_finance_admin(request):
        return HttpResponseForbidden("Access denied.")
    fee = get_object_or_404(Fee, pk=fee_id, school=school)

    if request.method == "POST":
        discount_type = request.POST.get("discount_type", "other")
        percentage = request.POST.get("percentage") or None
        fixed_amount = request.POST.get("fixed_amount") or None
        reason = request.POST.get("reason", "")

        if not percentage and not fixed_amount:
            messages.error(request, "Provide either a percentage or fixed amount.")
            return render(request, "finance/fee_discount_form.html", {
                "fee": fee, "discount_types": FeeDiscount.DISCOUNT_TYPES, "post": request.POST,
            })
        try:
            discount = FeeDiscount.objects.create(
                school=school,
                fee=fee,
                discount_type=discount_type,
                percentage=Decimal(percentage) if percentage else None,
                fixed_amount=Decimal(fixed_amount) if fixed_amount else None,
                reason=reason,
                approved_by=request.user,
                is_active=True,
            )
            credit = discount.discount_amount
            if credit and credit > Decimal("0"):
                import django.db.models as _m
                Fee.objects.filter(pk=fee.pk).update(
                    amount_paid=_m.F("amount_paid") + credit
                )
                fee.refresh_from_db()
                fee.save()
            messages.success(request, f"Discount of {credit} applied to fee.")
        except (InvalidOperation, Exception) as exc:
            logger.exception("fee_discount_create error fee=%s", fee_id)
            messages.error(request, f"Error: {exc}")
        return redirect("finance:fee_list")

    return render(request, "finance/fee_discount_form.html", {
        "fee": fee,
        "discount_types": FeeDiscount.DISCOUNT_TYPES,
    })


@login_required
@require_POST
def fee_discount_deactivate(request, pk):
    from finance.models import FeeDiscount
    school = _school(request)
    if not school:
        return redirect("home")
    if not _is_finance_admin(request):
        return HttpResponseForbidden("Access denied.")
    discount = get_object_or_404(FeeDiscount, pk=pk, school=school)
    discount.is_active = False
    discount.save(update_fields=["is_active"])
    messages.success(request, "Discount deactivated.")
    return redirect("finance:fee_discount_list")


# ===========================================================================
# FeeInstallmentPlan
# ===========================================================================

@login_required
def fee_installment_list(request):
    from finance.models import FeeInstallmentPlan
    school = _school(request)
    if not school:
        return redirect("home")
    if not _is_finance_admin(request):
        return HttpResponseForbidden("Access denied.")
    student_id = request.GET.get("student")
    status_filter = request.GET.get("status")
    qs = (
        FeeInstallmentPlan.objects.filter(school=school)
        .select_related("fee", "fee__student", "fee__student__user")
        .order_by("due_date")
    )
    if student_id:
        qs = qs.filter(fee__student_id=student_id)
    if status_filter:
        qs = qs.filter(status=status_filter)
    return render(request, "finance/fee_installment_list.html", {
        "installments": qs,
        "status_filter": status_filter,
    })


@login_required
def fee_installment_create(request, fee_id):
    """Create one or more installments for a fee by splitting it evenly."""
    from finance.models import Fee, FeeInstallmentPlan
    school = _school(request)
    if not school:
        return redirect("home")
    if not _is_finance_admin(request):
        return HttpResponseForbidden("Access denied.")
    fee = get_object_or_404(Fee, pk=fee_id, school=school)

    if request.method == "POST":
        count_raw = request.POST.get("count", "1")
        try:
            count = max(1, int(count_raw))
        except ValueError:
            count = 1
        import datetime
        from dateutil.relativedelta import relativedelta
        start_date_raw = request.POST.get("start_date", "")
        try:
            start = datetime.date.fromisoformat(start_date_raw)
        except ValueError:
            start = datetime.date.today()
        freq = request.POST.get("frequency", "monthly")

        base_amount = (fee.amount / count).quantize(Decimal("0.01"))
        remainder = fee.amount - base_amount * count

        existing_max = (
            FeeInstallmentPlan.objects.filter(fee=fee)
            .aggregate(m=__import__("django.db.models", fromlist=["Max"]).Max("installment_number"))
        )["m"] or 0

        for i in range(count):
            if freq == "weekly":
                due = start + datetime.timedelta(weeks=i)
            elif freq == "fortnightly":
                due = start + datetime.timedelta(weeks=i * 2)
            else:
                due = start + relativedelta(months=i)
            amt = base_amount + (remainder if i == count - 1 else Decimal("0"))
            FeeInstallmentPlan.objects.get_or_create(
                fee=fee,
                installment_number=existing_max + i + 1,
                defaults={"school": school, "due_date": due, "amount_due": amt},
            )
        messages.success(request, f"{count} installment(s) created for this fee.")
        return redirect("finance:fee_installment_list")

    return render(request, "finance/fee_installment_form.html", {"fee": fee})


@login_required
@require_POST
def fee_installment_mark_paid(request, pk):
    from finance.models import FeeInstallmentPlan, Fee
    import django.db.models as _m
    school = _school(request)
    if not school:
        return redirect("home")
    if not _is_finance_admin(request):
        return HttpResponseForbidden("Access denied.")
    installment = get_object_or_404(FeeInstallmentPlan, pk=pk, school=school)
    installment.amount_paid = installment.amount_due
    installment.status = "paid"
    installment.save(update_fields=["amount_paid", "status", "updated_at"])
    fee = installment.fee
    Fee.objects.filter(pk=fee.pk).update(
        amount_paid=_m.F("amount_paid") + installment.balance
    )
    fee.refresh_from_db()
    fee.save()
    messages.success(request, f"Installment #{installment.installment_number} marked paid.")
    return redirect("finance:fee_installment_list")


# ===========================================================================
# PurchaseOrder
# ===========================================================================

@login_required
def purchase_order_list(request):
    from finance.models import PurchaseOrder
    school = _school(request)
    if not school:
        return redirect("home")
    if not _is_finance_admin(request):
        return HttpResponseForbidden("Access denied.")
    status_filter = request.GET.get("status", "")
    qs = PurchaseOrder.objects.filter(school=school).order_by("-created_at")
    if status_filter:
        qs = qs.filter(status=status_filter)
    return render(request, "finance/purchase_order_list.html", {
        "orders": qs,
        "status_filter": status_filter,
        "status_choices": PurchaseOrder.STATUS_CHOICES,
    })


@login_required
def purchase_order_create(request):
    from finance.models import PurchaseOrder
    school = _school(request)
    if not school:
        return redirect("home")
    if not _is_finance_admin(request):
        return HttpResponseForbidden("Access denied.")

    if request.method == "POST":
        supplier_name = request.POST.get("supplier_name", "").strip()
        supplier_contact = request.POST.get("supplier_contact", "").strip()
        notes = request.POST.get("notes", "").strip()
        if not supplier_name:
            messages.error(request, "Supplier name is required.")
        else:
            import uuid
            po = PurchaseOrder.objects.create(
                school=school,
                po_number=f"PO-{uuid.uuid4().hex[:8].upper()}",
                supplier_name=supplier_name,
                supplier_contact=supplier_contact,
                notes=notes,
                status="draft",
                created_by=request.user,
            )
            messages.success(request, f"Purchase order {po.po_number} created.")
            return redirect("finance:purchase_order_detail", pk=po.pk)

    return render(request, "finance/purchase_order_form.html", {"action": "Create"})


@login_required
def purchase_order_detail(request, pk):
    from finance.models import PurchaseOrder, PurchaseOrderItem
    school = _school(request)
    if not school:
        return redirect("home")
    if not _is_finance_admin(request):
        return HttpResponseForbidden("Access denied.")
    po = get_object_or_404(PurchaseOrder, pk=pk, school=school)
    items = po.items.all().order_by("id")

    if request.method == "POST":
        form_type = request.POST.get("form_type")
        if form_type == "add_item":
            description = request.POST.get("description", "").strip()
            qty = request.POST.get("quantity", "1")
            unit_price = request.POST.get("unit_price", "0")
            try:
                PurchaseOrderItem.objects.create(
                    purchase_order=po,
                    school=school,
                    description=description,
                    quantity=int(qty),
                    unit_price=Decimal(unit_price),
                    total_price=Decimal(unit_price) * int(qty),
                )
                po.recalculate_totals()
                messages.success(request, "Item added.")
            except (ValueError, InvalidOperation):
                messages.error(request, "Invalid quantity or price.")
        elif form_type == "advance_status":
            action = request.POST.get("action")
            transitions = {
                "submit": ("draft", "submitted"),
                "approve": ("submitted", "approved"),
                "order": ("approved", "ordered"),
                "receive": ("ordered", "received"),
                "pay": ("received", "paid"),
                "cancel": (None, "cancelled"),
            }
            if action in transitions:
                from_status, to_status = transitions[action]
                if from_status is None or po.status == from_status:
                    po.status = to_status
                    po.save(update_fields=["status"])
                    messages.success(request, f"PO status updated to {to_status}.")
        return redirect("finance:purchase_order_detail", pk=pk)

    return render(request, "finance/purchase_order_detail.html", {"po": po, "items": items})


# ===========================================================================
# BankAccount
# ===========================================================================

@login_required
def bank_account_list(request):
    from finance.models import BankAccount
    school = _school(request)
    if not school:
        return redirect("home")
    if not _is_finance_admin(request):
        return HttpResponseForbidden("Access denied.")
    accounts = BankAccount.objects.filter(school=school).order_by("-is_primary", "bank_name")
    return render(request, "finance/bank_account_list.html", {"accounts": accounts})


@login_required
def bank_account_create(request):
    from finance.models import BankAccount
    school = _school(request)
    if not school:
        return redirect("home")
    if not _is_finance_admin(request):
        return HttpResponseForbidden("Access denied.")

    if request.method == "POST":
        bank_name = request.POST.get("bank_name", "").strip()
        account_number = request.POST.get("account_number", "").strip()
        account_name = request.POST.get("account_name", "").strip()
        account_type = request.POST.get("account_type", "current")
        currency = request.POST.get("currency", "GHS")
        is_primary = request.POST.get("is_primary") == "on"
        if not bank_name or not account_number:
            messages.error(request, "Bank name and account number are required.")
        else:
            if is_primary:
                BankAccount.objects.filter(school=school, is_primary=True).update(is_primary=False)
            BankAccount.objects.create(
                school=school,
                bank_name=bank_name,
                account_number=account_number,
                account_name=account_name,
                account_type=account_type,
                currency=currency,
                is_primary=is_primary,
                is_active=True,
            )
            messages.success(request, f"Bank account '{bank_name}' added.")
            return redirect("finance:bank_account_list")

    from finance.models import BankAccount as BA
    return render(request, "finance/bank_account_form.html", {
        "account_types": BA.ACCOUNT_TYPES,
    })


@login_required
@require_POST
def bank_account_toggle(request, pk):
    from finance.models import BankAccount
    school = _school(request)
    if not school:
        return redirect("home")
    if not _is_finance_admin(request):
        return HttpResponseForbidden("Access denied.")
    account = get_object_or_404(BankAccount, pk=pk, school=school)
    account.is_active = not account.is_active
    account.save(update_fields=["is_active"])
    messages.success(request, f"Account {'activated' if account.is_active else 'deactivated'}.")
    return redirect("finance:bank_account_list")
