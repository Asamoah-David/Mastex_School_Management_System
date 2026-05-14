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

from schools.features import require_feature

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
    redir = require_feature(request, "fee_management", "accounts:dashboard")
    if redir:
        return redir
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
    redir = require_feature(request, "fee_management", "accounts:dashboard")
    if redir:
        return redir
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
    redir = require_feature(request, "fee_management", "accounts:dashboard")
    if redir:
        return redir
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
    redir = require_feature(request, "fee_management", "accounts:dashboard")
    if redir:
        return redir
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
    redir = require_feature(request, "fee_management", "accounts:dashboard")
    if redir:
        return redir
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
    from django.db import transaction

    from finance.models import FeeInstallmentPlan, Fee
    import django.db.models as _m
    school = _school(request)
    if not school:
        return redirect("home")
    if not _is_finance_admin(request):
        return HttpResponseForbidden("Access denied.")
    redir = require_feature(request, "fee_management", "accounts:dashboard")
    if redir:
        return redir
    installment = get_object_or_404(FeeInstallmentPlan, pk=pk, school=school)
    if installment.status == "paid":
        messages.info(request, "This installment is already marked paid.")
        return redirect("finance:fee_installment_list")
    # Credit applied to the parent Fee must be the unpaid slice *before* we
    # zero the installment balance.  (Previously we set amount_paid first,
    # then read ``installment.balance``, which was always 0 — so the fee
    # ledger never moved.)
    credit = installment.balance
    if credit <= Decimal("0"):
        messages.warning(request, "Nothing to credit for this installment.")
        return redirect("finance:fee_installment_list")
    fee = installment.fee
    with transaction.atomic():
        inst = FeeInstallmentPlan.objects.select_for_update().get(pk=installment.pk)
        if inst.status == "paid":
            messages.info(request, "This installment is already marked paid.")
            return redirect("finance:fee_installment_list")
        credit = inst.balance
        if credit <= Decimal("0"):
            messages.warning(request, "Nothing to credit for this installment.")
            return redirect("finance:fee_installment_list")
        inst.amount_paid = inst.amount_due
        inst.status = "paid"
        inst.save(update_fields=["amount_paid", "status", "updated_at"])
        Fee.objects.filter(pk=fee.pk).update(amount_paid=_m.F("amount_paid") + credit)
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
    redir = require_feature(request, "finance_admin", "accounts:dashboard")
    if redir:
        return redir
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
    redir = require_feature(request, "finance_admin", "accounts:dashboard")
    if redir:
        return redir

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
    redir = require_feature(request, "finance_admin", "accounts:dashboard")
    if redir:
        return redir
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
    redir = require_feature(request, "finance_admin", "accounts:dashboard")
    if redir:
        return redir
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
    redir = require_feature(request, "finance_admin", "accounts:dashboard")
    if redir:
        return redir

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
    redir = require_feature(request, "finance_admin", "accounts:dashboard")
    if redir:
        return redir
    account = get_object_or_404(BankAccount, pk=pk, school=school)
    account.is_active = not account.is_active
    account.save(update_fields=["is_active"])
    messages.success(request, f"Account {'activated' if account.is_active else 'deactivated'}.")
    return redirect("finance:bank_account_list")


# ---------------------------------------------------------------------------
# Bulk Fee Generation
# ---------------------------------------------------------------------------

@login_required
def bulk_fee_generate(request):
    """Generate Fee records for every student in a class from a FeeStructure.

    GET  — display form (fee_structure selector + optional due_date + dry-run toggle).
    POST — create fees, skip students who already have a fee from this structure
           for the selected term.  Returns a summary of created / skipped counts.
    """
    from finance.models import FeeStructure, Fee
    from students.models import Student
    from django.db import transaction

    school = _school(request)
    if not school:
        return redirect("home")
    if not _is_finance_admin(request):
        return HttpResponseForbidden("Access denied.")
    redir = require_feature(request, "fee_management", "accounts:dashboard")
    if redir:
        return redir

    structures = FeeStructure.objects.filter(school=school, is_active=True).order_by("name")

    result = None
    if request.method == "POST":
        structure_pk = request.POST.get("fee_structure")
        due_date_raw = request.POST.get("due_date") or None
        dry_run = request.POST.get("dry_run") == "1"

        structure = get_object_or_404(FeeStructure, pk=structure_pk, school=school)

        # Student model uses a `status` CharField, not `is_active` boolean.
        # Bug fix: previously filtered `is_active=True` -> FieldError 500 on every POST.
        student_qs = Student.objects.filter(school=school, status="active")
        if structure.school_class_id:
            student_qs = student_qs.filter(school_class_id=structure.school_class_id)
        elif structure.class_name:
            student_qs = student_qs.filter(class_name__iexact=structure.class_name)

        created, skipped = 0, 0
        with transaction.atomic():
            for student in student_qs.iterator():
                already_exists = Fee.objects.filter(
                    school=school,
                    student=student,
                    fee_structure=structure,
                    deleted_at__isnull=True,
                ).exists()
                if already_exists:
                    skipped += 1
                    continue
                if not dry_run:
                    Fee.objects.create(
                        school=school,
                        student=student,
                        fee_structure=structure,
                        term=structure.term_fk,
                        amount=structure.amount,
                        description=f"{structure.name} — bulk generated",
                        due_date=due_date_raw or None,
                        is_active=True,
                    )
                created += 1
            if dry_run:
                transaction.set_rollback(True)

        result = {
            "structure": structure,
            "created": created,
            "skipped": skipped,
            "total": created + skipped,
            "dry_run": dry_run,
        }
        if not dry_run:
            messages.success(
                request,
                f"Generated {created} fee records from '{structure.name}'. "
                f"{skipped} students already had this fee."
            )

    return render(request, "finance/bulk_fee_generate.html", {
        "structures": structures,
        "result": result,
    })
