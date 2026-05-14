import uuid
import json
import requests
from datetime import timedelta
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.db import models, transaction
from django.db.models import Prefetch
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils import timezone
from django.core.cache import cache

from urllib.parse import urlparse
from django.contrib.auth.decorators import login_required
from accounts.permissions import can_export_data, is_school_leadership, user_can_manage_school, can_manage_finance
from .forms import FeeStructureForm


def _safe_referer(request, fallback="/"):
    """Return the HTTP Referer only if it points to the same host, otherwise fallback."""
    ref = request.META.get("HTTP_REFERER", "")
    if ref:
        parsed = urlparse(ref)
        if parsed.netloc and parsed.netloc != request.get_host():
            return fallback
        return ref
    return fallback

from .models import Fee, FeeStructure, FeePayment, SubscriptionPayment, PaymentTransaction
from payments.services.ledger import PaymentTypes, record_payment_transaction
from finance.services.fee_payments import complete_fee_payment, net_amount_for_school_fee
from operations.services.portal_payments import (
    mark_bus_payment_completed,
    mark_canteen_payment_completed,
    mark_hostel_fee_completed,
    mark_textbook_sale_completed,
)
from .paystack_service import compute_paystack_gross_from_net, paystack_service
from accounts.models import User
from messaging.utils import send_sms
from schools.models import School
from schools.features import is_feature_enabled, is_feature_enabled_for_school, require_feature
from core.pagination import paginate
from core.utils import FEE_PAYSTACK_RETURN_SESSION_KEY, safe_internal_redirect_path
from audit.services import write_audit
import logging
logger = logging.getLogger(__name__)


def _check_payment_status_fee_payment_qs(user):
    """Tenant scope for payment reference lookup (non-superusers)."""
    qs = FeePayment.objects.select_related("fee", "fee__student", "fee__school")
    if not user or not getattr(user, "is_authenticated", False):
        return qs.none()
    if user.is_superuser:
        return qs
    parts = []
    school = getattr(user, "school", None)
    if school is not None:
        parts.append(models.Q(fee__school=school))
    if getattr(user, "role", None) == "parent":
        from students.utils import get_children_for_parent

        children = get_children_for_parent(user, active_only=False)
        if children.exists():
            parts.append(models.Q(fee__student__in=children))
    if not parts:
        return qs.none()
    combined = parts[0]
    for p in parts[1:]:
        combined |= p
    return qs.filter(combined)


def _check_payment_status_fee_qs(user):
    """Tenant scope for Fee rows when resolving a reference (non-superusers)."""
    qs = Fee.objects.select_related("student", "school")
    if not user or not getattr(user, "is_authenticated", False):
        return qs.none()
    if user.is_superuser:
        return qs
    parts = []
    school = getattr(user, "school", None)
    if school is not None:
        parts.append(models.Q(school=school))
    if getattr(user, "role", None) == "parent":
        from students.utils import get_children_for_parent

        children = get_children_for_parent(user, active_only=False)
        if children.exists():
            parts.append(models.Q(student__in=children))
    if not parts:
        return qs.none()
    combined = parts[0]
    for p in parts[1:]:
        combined |= p
    return qs.filter(combined)


def _store_fee_paystack_return(request, raw_next):
    nxt = safe_internal_redirect_path(raw_next)
    if nxt:
        request.session[FEE_PAYSTACK_RETURN_SESSION_KEY] = nxt


def _redirect_after_fee_paystack(request):
    raw = request.session.pop(FEE_PAYSTACK_RETURN_SESSION_KEY, None)
    nxt = safe_internal_redirect_path(raw) if raw else None
    if nxt:
        return redirect(nxt)
    return redirect("finance:parent_fee_list")


def _net_amount_for_school_fee(reference, fee_id, paystack_major_units):
    return net_amount_for_school_fee(reference=reference, fee_id=fee_id, paystack_major_units=paystack_major_units)


def _complete_fee_payment(fee_id, reference, paid_amount, paystack_id, channel):
    return complete_fee_payment(
        fee_id=fee_id,
        reference=reference,
        paid_amount=paid_amount,
        paystack_id=paystack_id,
        channel=channel,
    )


def is_paystack_configured():
    """Check if Paystack is properly configured."""
    return bool(settings.PAYSTACK_SECRET_KEY)


# How long a pending FeePayment is considered "live" before subsequent
# initiate clicks should mark it failed.  See Bug fix B4-A.
PENDING_FEE_PAYMENT_DEDUPE_MINUTES = 5


def _expire_stale_pending_fee_payments(fee_id: int) -> int:
    """Mark abandoned pending FeePayment rows on the given fee as failed.

    Called from the Paystack init views before they create a new pending
    row, so the ledger never accumulates more than one *recent* pending
    row per fee.  Returns the number of rows expired (for logging).

    Safe to call repeatedly; will never touch a completed/failed row.
    """
    cutoff = timezone.now() - timedelta(minutes=PENDING_FEE_PAYMENT_DEDUPE_MINUTES)
    expired = FeePayment.objects.filter(
        fee_id=fee_id,
        status="pending",
        created_at__lt=cutoff,
    ).update(status="failed")
    if expired:
        logger.info(
            "B4-A: expired %s stale pending FeePayment(s) for fee_id=%s",
            expired, fee_id,
        )
    return expired


def _reuse_recent_pending_fee_payment(
    fee_id: int, *, amount_net: Decimal, amount_gross: Decimal
) -> Optional[FeePayment]:
    """Return a pending FeePayment to re-use for Paystack init, or None.

    B4-A: repeated \"Pay\" clicks within ``PENDING_FEE_PAYMENT_DEDUPE_MINUTES``
    for the same net/gross amount should not mint a fresh pending row each
    time (abandoned attempts used to pile up).  After ``_expire_stale_pending_fee_payments``,
    any remaining pending row with matching amounts in the dedupe window is
    returned so the caller can call ``initialize`` again with the same
    Paystack reference.
    """
    cutoff = timezone.now() - timedelta(minutes=PENDING_FEE_PAYMENT_DEDUPE_MINUTES)
    qs = (
        FeePayment.objects.filter(
            fee_id=fee_id,
            status="pending",
            amount=amount_net,
            created_at__gte=cutoff,
        )
        .exclude(paystack_reference__isnull=True)
        .exclude(paystack_reference="")
        .order_by("-pk")
    )
    for fp in qs[:5]:
        fp_gross = fp.gross_amount if fp.gross_amount is not None else fp.amount
        if fp_gross == amount_gross:
            return fp
    return None


def _send_fee_payment_email_notice(fee, net_amount: float, reference: str) -> None:
    """Email parent/student when a school fee payment is recorded (best-effort)."""
    from django.core.mail import send_mail

    if not getattr(settings, "DEFAULT_FROM_EMAIL", None):
        return
    recipients = []
    if fee.student_id:
        if fee.student.parent_id and fee.student.parent.email:
            recipients.append(fee.student.parent.email.strip())
        su = fee.student.user
        if su and su.email and su.email.strip() not in recipients:
            recipients.append(su.email.strip())
    if not recipients:
        return
    school_name = fee.school.name if fee.school_id else "School"
    subject = f"Payment received — {school_name}"
    body = (
        f"A payment of GHS {net_amount:.2f} was applied to a fee for "
        f"{fee.student} (ref {reference}).\n"
        f"Remaining balance: GHS {fee.remaining_balance:.2f}\n"
        f"Thank you."
    )
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=True)
    except Exception:
        logger.exception("Fee payment confirmation email failed")


def _fee_for_payment_request(user, fee_id):
    """
    Load a fee for Paystack init / payment flows with school + ownership checks
    (prevents cross-tenant fee_id guessing).
    """
    qs = Fee.objects.select_related(
        "student", "student__user", "student__parent", "school"
    ).filter(pk=fee_id)
    user_school = getattr(user, "school", None)
    if not user.is_superuser and user_school:
        qs = qs.filter(school=user_school)
    fee = qs.first()
    if fee is None:
        raise Http404("Fee not found.")
    from students.utils import parent_is_guardian_of
    is_own = bool(
        fee.student_id
        and (
            fee.student.user_id == user.pk
            or parent_is_guardian_of(user, fee.student)
        )
    )
    is_staff = user.is_superuser or user_can_manage_school(user)
    if is_staff:
        if not user.is_superuser and user_school and fee.school_id != user_school.pk:
            raise Http404("Fee not found.")
    elif not is_own:
        raise Http404("Fee not found.")
    return fee


def _notify_fee_payer_after_payment(fee_id, reference: str, net_credited: float) -> None:
    """
    SMS + email once per Paystack reference (browser callback and webhook may both run).
    Uses a DB claim on FeePayment.payer_notified_at to dedupe.
    """
    if not reference:
        return
    fee = None
    try:
        with transaction.atomic():
            fp = (
                FeePayment.objects.select_for_update()
                .filter(paystack_reference=reference, status="completed")
                .order_by("-pk")
                .first()
            )
            if not fp or fp.payer_notified_at is not None:
                return
            claimed = FeePayment.objects.filter(
                pk=fp.pk, payer_notified_at__isnull=True
            ).update(payer_notified_at=timezone.now())
            if not claimed:
                return
            fee = Fee.objects.select_related(
                "student__parent", "student__user", "school"
            ).get(pk=fee_id)
    except Fee.DoesNotExist:
        logger.warning(
            "fee payment notify skipped: fee_id=%s paystack_reference=%s",
            fee_id,
            reference,
        )
        return

    try:
        from fees.services.admin_unpaid_notification import notify_parent_fee_paid

        if fee.student.parent and fee.student.parent.phone:
            notify_parent_fee_paid(fee.student, net_credited)
    except Exception:
        logger.exception("Fee payment SMS failed paystack_reference=%s", reference)

    try:
        fee.refresh_from_db()
        _send_fee_payment_email_notice(fee, float(net_credited), reference)
    except Exception:
        logger.exception("Fee payment email failed paystack_reference=%s", reference)


@login_required
def pay_with_paystack(request, fee_id):
    """
    Initialize Paystack payment for a fee.
    Supports partial payments - parent can pay any amount.
    Payment goes directly to school's subaccount if configured.
    Creates a pending payment record for tracking.
    """
    if not is_paystack_configured():
        messages.error(request, "Online payments are currently unavailable. Please contact the school for payment options.")
        return redirect(_safe_referer(request))

    user = request.user
    try:
        fee = _fee_for_payment_request(user, fee_id)
    except Http404:
        messages.error(request, "You do not have permission to pay this fee.")
        return redirect("/")

    if fee.school and not fee.school.is_payout_setup_active:
        messages.error(request, "Online fee payments are not yet available for this school. The school must complete payout setup first.")
        return redirect(_safe_referer(request))
    
    remaining = fee.remaining_balance
    if remaining <= 0:
        messages.error(request, "This fee has already been fully paid.")
        return redirect(_safe_referer(request))

    remaining_dec = remaining if isinstance(remaining, Decimal) else Decimal(str(remaining))
    
    amount = request.GET.get("amount")
    if amount:
        try:
            amount_dec = Decimal(str(amount))
            if amount_dec <= Decimal("0"):
                amount_dec = remaining_dec
            elif amount_dec > remaining_dec:
                amount_dec = remaining_dec
        except (ValueError, TypeError):
            amount_dec = remaining_dec
    else:
        amount_dec = remaining_dec

    amount_net, amount_gross = compute_paystack_gross_from_net(amount_dec)
    charge_amount = float(amount_gross)
    
    student_user = fee.student.user if fee.student else None
    parent_user = fee.student.parent if fee.student else None
    email = (
        (student_user.email if student_user and student_user.email else None)
        or (parent_user.email if parent_user and parent_user.email else None)
        or f"noreply+{fee.id}@mastex.app"
    )

    callback_url = request.build_absolute_uri(
        reverse("finance:paystack_callback", kwargs={"fee_id": fee_id})
    )
    
    reference = f"SCHOOL_FEE_{fee_id}_{uuid.uuid4().hex[:8].upper()}"
    
    school_subaccount = None
    if fee.school and fee.school.is_payout_setup_active:
        school_subaccount = fee.school.paystack_subaccount_code

    # B4-A: expire stale pendings, then reuse a recent matching pending row
    # (same net/gross within the window) instead of creating duplicates.
    _expire_stale_pending_fee_payments(fee.pk)
    reuse = _reuse_recent_pending_fee_payment(
        fee.pk, amount_net=amount_net, amount_gross=amount_gross
    )
    if reuse:
        pending_payment = reuse
        reference = pending_payment.paystack_reference or reference
        logger.info(
            "B4-A: reusing pending FeePayment id=%s reference=%s net=%s gross=%s",
            pending_payment.id, reference, amount_net, amount_gross,
        )
    else:
        pending_payment = FeePayment.objects.create(
            fee=fee,
            amount=amount_net,
            gross_amount=amount_gross,
            paystack_reference=reference,
            status="pending",
        )
        logger.info(
            "Created pending payment record: payment_id=%s, reference=%s, net=%s, gross=%s",
            pending_payment.id, reference, amount_net, amount_gross,
        )
    
    response = paystack_service.initialize_payment(
        email=email,
        amount=charge_amount,
        callback_url=callback_url,
        reference=reference,
        metadata={
            "fee_id": fee_id,
            "payment_id": pending_payment.id,
            "payment_type": "school_fee",
            "student_name": str(fee.student),
            "school_name": fee.school.name if fee.school else "",
            "school_id": fee.school.id if fee.school else None,
            "amount_net": float(amount_net),
            "amount_gross": float(amount_gross),
        },
        subaccount=school_subaccount
    )
    
    if response.get("status") and response.get("data", {}).get("authorization_url"):
        _store_fee_paystack_return(request, request.GET.get("next"))
        request.session[f"paystack_ref_{fee_id}"] = reference
        request.session[f"paystack_payment_id_{fee_id}"] = pending_payment.id
        return redirect(response["data"]["authorization_url"])
    else:
        pending_payment.status = 'failed'
        pending_payment.save()
        error_msg = response.get("message", "Could not initialize payment. Please try again.")
        messages.error(request, error_msg)
        return redirect(_safe_referer(request))


@login_required
def pay_with_paystack_custom_amount(request, fee_id):
    """
    Allow parent to specify custom payment amount.
    Payment goes directly to school's subaccount if configured.
    """
    if not is_paystack_configured():
        messages.error(request, "Online payments are currently unavailable. Please contact the school for payment options.")
        return redirect(_safe_referer(request))

    user = request.user
    try:
        fee = _fee_for_payment_request(user, fee_id)
    except Http404:
        messages.error(request, "You do not have permission to pay this fee.")
        return redirect("/")

    if fee.school and not fee.school.is_payout_setup_active:
        messages.error(request, "Online fee payments are not yet available for this school. The school must complete payout setup first.")
        return redirect(_safe_referer(request))

    if request.method == "POST":
        amount_str = request.POST.get("amount", "")
        try:
            amount_dec = Decimal(str(amount_str))
            if amount_dec <= Decimal("0"):
                messages.error(request, "Amount must be greater than 0.")
                return redirect(_safe_referer(request))
            
            remaining = fee.remaining_balance
            remaining_dec = remaining if isinstance(remaining, Decimal) else Decimal(str(remaining))
            if amount_dec > remaining_dec:
                messages.warning(request, f"Amount exceeds remaining balance of GHS {remaining}. Paying GHS {remaining} instead.")
                amount_dec = remaining_dec

            amount_net, amount_gross = compute_paystack_gross_from_net(amount_dec)
            charge_amount = float(amount_gross)
            
            student_user = fee.student.user if fee.student else None
            parent_user = fee.student.parent if fee.student else None
            email = (
                (student_user.email if student_user and student_user.email else None)
                or (parent_user.email if parent_user and parent_user.email else None)
                or f"noreply+{fee.id}@mastex.app"
            )
            
            # Build callback URL
            callback_url = request.build_absolute_uri(
                reverse("finance:paystack_callback", kwargs={"fee_id": fee_id})
            )

            reference = f"SCHOOL_FEE_{fee_id}_{uuid.uuid4().hex[:8].upper()}"

            # Get school's subaccount if configured
            school_subaccount = None
            if fee.school and fee.school.is_payout_setup_active:
                school_subaccount = fee.school.paystack_subaccount_code

            from .models import FeePayment

            _expire_stale_pending_fee_payments(fee.pk)
            reuse = _reuse_recent_pending_fee_payment(
                fee.pk, amount_net=amount_net, amount_gross=amount_gross
            )
            if reuse:
                pending_payment = reuse
                reference = pending_payment.paystack_reference or reference
                logger.info(
                    "B4-A: reusing pending FeePayment (custom) id=%s reference=%s net=%s gross=%s",
                    pending_payment.id, reference, amount_net, amount_gross,
                )
            else:
                pending_payment = FeePayment.objects.create(
                    fee=fee,
                    amount=amount_net,
                    gross_amount=amount_gross,
                    paystack_reference=reference,
                    status="pending",
                )
                logger.info(
                    "Created pending payment (custom): payment_id=%s, reference=%s, net=%s, gross=%s",
                    pending_payment.id, reference, amount_net, amount_gross,
                )
            
            # Initialize payment
            response = paystack_service.initialize_payment(
                email=email,
                amount=charge_amount,
                callback_url=callback_url,
                reference=reference,
                metadata={
                    "fee_id": fee_id,
                    "payment_id": pending_payment.id,
                    "payment_type": "school_fee",
                    "student_name": str(fee.student),
                    "school_name": fee.school.name if fee.school else "",
                    "school_id": fee.school.id if fee.school else None,
                    "amount_net": float(amount_net),
                    "amount_gross": float(amount_gross),
                },
                subaccount=school_subaccount
            )
            
            if response.get("status") and response.get("data", {}).get("authorization_url"):
                _store_fee_paystack_return(request, request.POST.get("next"))
                request.session[f"paystack_ref_{fee_id}"] = reference
                request.session[f"paystack_payment_id_{fee_id}"] = pending_payment.id
                return redirect(response["data"]["authorization_url"])
            else:
                # Mark payment as failed if initialization failed
                pending_payment.status = 'failed'
                pending_payment.save()
                error_msg = response.get("message", "Could not initialize payment.")
                messages.error(request, error_msg)
                return redirect(_safe_referer(request))
            
        except (ValueError, TypeError):
            messages.error(request, "Invalid amount entered.")
    
    return redirect(_safe_referer(request))


@login_required
def paystack_callback(request, fee_id):
    """
    Handle Paystack payment callback.
    Verify payment and update fee accordingly.
    Uses the pending FeePayment record created during initialization
    to prevent duplicate processing.
    """
    reference = request.GET.get("reference")
    
    if not reference:
        messages.error(request, "Payment reference not found.")
        return redirect("home")
    
    # Enforce fee ownership / tenant binding before applying payment
    try:
        fee = _fee_for_payment_request(request.user, fee_id)
    except Http404:
        messages.error(request, "Fee record not found.")
        return _redirect_after_fee_paystack(request)

    # Verify payment with Paystack
    response = paystack_service.verify_payment(reference)
    
    if response.get("status") and response.get("data", {}).get("status") == "success":
        data = response["data"]
        md = data.get("metadata") or {}
        md_fee_id = md.get("fee_id")
        md_payment_type = md.get("payment_type")
        md_school_id = md.get("school_id")

        if md_fee_id is None or md_school_id is None:
            messages.error(request, "Payment verification failed.")
            return _redirect_after_fee_paystack(request)
        try:
            if int(md_fee_id) != int(fee_id):
                messages.error(request, "Payment verification failed.")
                return _redirect_after_fee_paystack(request)
            if int(md_school_id) != int(fee.school_id):
                messages.error(request, "Payment verification failed.")
                return _redirect_after_fee_paystack(request)
        except (TypeError, ValueError):
            messages.error(request, "Payment verification failed.")
            return _redirect_after_fee_paystack(request)
        if md_payment_type and md_payment_type not in ("school_fee", "fee"):
            messages.error(request, "Payment verification failed.")
            return _redirect_after_fee_paystack(request)

        try:
            paystack_charged = Decimal(str(data.get("amount", 0))) / Decimal("100")
        except Exception:
            paystack_charged = Decimal("0")
        net_credited = _net_amount_for_school_fee(reference, fee_id, paystack_charged)
        channel = data.get("authorization", {}).get("channel", "card")
        paystack_id = data.get("id")
        
        try:
            with transaction.atomic():
                pending = (
                    FeePayment.objects.select_for_update()
                    .filter(fee_id=fee_id, paystack_reference=reference)
                    .order_by("-pk")
                    .first()
                )
                if not pending:
                    messages.error(request, "Payment verification failed.")
                    return _redirect_after_fee_paystack(request)
                if pending.status == "completed":
                    messages.info(request, "This payment has already been recorded.")
                    return _redirect_after_fee_paystack(request)
                if pending.status != "pending":
                    messages.error(request, "Payment verification failed.")
                    return _redirect_after_fee_paystack(request)

                was_new = _complete_fee_payment(fee_id, reference, net_credited, paystack_id, channel)

            if was_new:
                _notify_fee_payer_after_payment(fee_id, reference, float(net_credited))
                extra = ""
                try:
                    if paystack_charged > net_credited + Decimal("0.001"):
                        extra = f" (GHS {paystack_charged:.2f} charged including processing uplift)"
                except Exception:
                    pass
                messages.success(
                    request,
                    f"GHS {net_credited:.2f} applied to the fee successfully.{extra}",
                )
            else:
                # Bug fix B4-C: a `was_new=False` here means the webhook (or
                # a previous tab) raced us to completion — it is NOT a
                # genuine failure. The fee balance is already correct; the
                # earlier "failed" ledger row was misleading and would
                # poison reconciliation reports. Log as completed-duplicate
                # for observability and show a user-friendly info message.
                logger.info(
                    "paystack_callback duplicate completion (webhook race) reference=%s fee_id=%s",
                    reference, fee_id,
                )
                messages.info(request, "This payment has already been recorded.")

            return _redirect_after_fee_paystack(request)

        except Fee.DoesNotExist:
            messages.error(request, "Fee record not found.")

    else:
        FeePayment.objects.filter(
            paystack_reference=reference, status="pending"
        ).update(status="failed")
        record_payment_transaction(
            reference=reference,
            school_id=fee.school_id,
            amount=Decimal("0"),
            status="failed",
            payment_type="school_fee",
            object_id=str(fee_id),
            metadata={"fee_id": fee_id},
        )
        error_msg = response.get("message", "Payment verification failed.")
        messages.error(request, f"Payment was not successful: {error_msg}")

    return _redirect_after_fee_paystack(request)


def _paystack_webhook_fee_refund(payload: dict, event: str) -> None:
    """Close the two-phase refund cycle started by ``payment_history_void``.

    Paystack fires ``refund.processed`` once the refund actually moves
    money, or ``refund.failed`` if the refund could not be completed.
    The payload's ``data.transaction.reference`` (or ``data.transaction_reference``,
    depending on the event shape) points back to the original transaction
    reference we used at charge time, which is what we stored on
    ``FeePayment.paystack_reference``.
    """
    data = payload.get("data") or {}
    tx = data.get("transaction") or {}
    ref = (
        (tx.get("reference") if isinstance(tx, dict) else None)
        or data.get("transaction_reference")
        or data.get("reference")
        or ""
    )
    ref = str(ref).strip()
    if not ref:
        logger.warning("paystack refund webhook ignored: no transaction reference event=%s", event)
        return

    dedupe_key = f"paystack_refund_lock:{ref}:{event}"
    if cache.get(dedupe_key):
        logger.info("paystack refund webhook duplicate burst skipped reference=%s event=%s", ref, event)
        return
    cache.set(dedupe_key, 1, 120)

    try:
        with transaction.atomic():
            payment = (
                FeePayment.objects.select_for_update()
                .select_related("fee")
                .filter(paystack_reference=ref)
                .order_by("-pk")
                .first()
            )
            if not payment:
                logger.warning("paystack refund webhook ignored: no FeePayment reference=%s", ref)
                return

            if payment.refund_status == FeePayment.REFUND_STATUS_PROCESSED:
                logger.info("paystack refund webhook duplicate/already processed reference=%s", ref)
                return

            if event == "refund.processed":
                fee = payment.fee
                current_paid = fee.amount_paid or Decimal("0")
                reversal = payment.amount or Decimal("0")
                Fee.objects.filter(pk=fee.pk).update(
                    amount_paid=models.F("amount_paid") - reversal
                )
                fee.refresh_from_db(fields=["amount_paid"])
                # Clamp at zero in case multiple reversals overshoot.
                if fee.amount_paid < Decimal("0"):
                    Fee.objects.filter(pk=fee.pk).update(amount_paid=Decimal("0"))
                    fee.refresh_from_db(fields=["amount_paid"])
                fee.save()

                payment.status = "failed"
                payment.refund_status = FeePayment.REFUND_STATUS_PROCESSED
                payment.refund_processed_at = timezone.now()
                payment.voided_at = payment.refund_processed_at
                payment.save(update_fields=[
                    "status", "refund_status", "refund_processed_at", "voided_at",
                ])
                logger.info(
                    "paystack refund processed: reference=%s fee_id=%s reversed=%s",
                    ref, fee.pk, reversal,
                )
                try:
                    write_audit(
                        user=payment.voided_by,
                        action="refund_processed",
                        model_name="finance.FeePayment",
                        object_id=str(payment.pk),
                        school=getattr(fee, "school", None),
                        changes={
                            "fee_id": fee.pk,
                            "student_id": fee.student_id,
                            "amount": str(reversal),
                            "paystack_reference": ref,
                        },
                    )
                except Exception:
                    logger.exception("paystack refund processed: audit log failed reference=%s", ref)
                return

            # refund.failed — keep the original payment intact and surface
            # the failure reason for finance staff to retry.
            failure_reason = ""
            failures = data.get("failures") or data.get("reason") or data.get("status")
            if isinstance(failures, list) and failures:
                first = failures[0] if isinstance(failures[0], (dict, str)) else ""
                if isinstance(first, dict):
                    failure_reason = first.get("reason") or first.get("message") or ""
                else:
                    failure_reason = str(first)
            elif isinstance(failures, str):
                failure_reason = failures
            failure_reason = (failure_reason or data.get("message") or "Refund failed at Paystack.")[:2000]

            payment.refund_status = FeePayment.REFUND_STATUS_FAILED
            payment.refund_failure_reason = failure_reason
            payment.save(update_fields=["refund_status", "refund_failure_reason"])
            logger.warning(
                "paystack refund failed: reference=%s payment_id=%s reason=%s",
                ref, payment.pk, failure_reason,
            )
            try:
                write_audit(
                    user=payment.voided_by,
                    action="refund_failed",
                    model_name="finance.FeePayment",
                    object_id=str(payment.pk),
                    school=getattr(payment.fee, "school", None) if payment.fee_id else None,
                    changes={
                        "paystack_reference": ref,
                        "reason": failure_reason,
                    },
                )
            except Exception:
                logger.exception("paystack refund failed: audit log failed reference=%s", ref)
    except Exception:
        logger.exception("paystack refund webhook processing crashed reference=%s event=%s", ref, event)


def _paystack_webhook_staff_transfer(payload: dict, event: str) -> None:
    """Update StaffPayrollPayment rows for Paystack Transfer webhooks."""
    from accounts.hr_models import StaffPayrollPayment

    data = payload.get("data") or {}
    ref = (data.get("reference") or "").strip()
    if not ref:
        return
    pay = StaffPayrollPayment.objects.filter(reference=ref).first()
    if not pay:
        return
    if event == "transfer.success":
        pay.paystack_status = "success"
        tc = data.get("transfer_code") or pay.paystack_transfer_code
        if tc:
            pay.paystack_transfer_code = str(tc)[:64]
        pay.paystack_failure_reason = ""
        pay.save(update_fields=["paystack_status", "paystack_transfer_code", "paystack_failure_reason"])
        logger.info("Staff payroll transfer success: ref=%s payment_id=%s", ref, pay.pk)
    elif event == "transfer.failed":
        pay.paystack_status = "failed"
        failures = data.get("failures")
        reason = ""
        if isinstance(failures, list) and failures:
            first = failures[0]
            if isinstance(first, dict):
                reason = first.get("reason") or first.get("message") or ""
        if not reason:
            reason = data.get("message") or str(data)
        pay.paystack_failure_reason = str(reason)[:2000]
        pay.save(update_fields=["paystack_status", "paystack_failure_reason"])
        logger.warning("Staff payroll transfer failed: ref=%s payment_id=%s", ref, pay.pk)
        # Release reserved funds if this was from a payout request
        _release_funds_for_failed_transfer(ref, "failed")
    elif event == "transfer.reversed":
        pay.paystack_status = "failed"
        pay.paystack_failure_reason = "Transfer reversed."
        pay.save(update_fields=["paystack_status", "paystack_failure_reason"])
        logger.warning("Staff payroll transfer reversed: ref=%s payment_id=%s", ref, pay.pk)
        # Release reserved funds if this was from a payout request
        _release_funds_for_failed_transfer(ref, "reversed")


def _release_funds_for_failed_transfer(reference: str, event: str) -> None:
    """Release reserved funds for a payout request when transfer fails/reverses."""
    from finance.models import StaffPayoutRequest
    from finance.services.school_funds import release_reserved_funds

    req = StaffPayoutRequest.objects.filter(reference=reference).first()
    if not req:
        return
    if req.status not in ("funds_reserved", "executing"):
        return
    
    try:
        release_reserved_funds(
            school_id=req.school_id,
            amount=req.amount,
            reference=f"AUTO-RELEASE-{reference}-{event.upper()}",
            description=f"Auto-release after {event} for payout {reference}",
            currency=req.currency,
            metadata={
                "payout_request_id": req.pk,
                "payout_reference": req.reference,
                "original_ledger_ref": req.ledger_reference,
                "trigger_event": event,
            },
        )
        req.status = "failed"
        req.failed_at = timezone.now()
        req.failure_reason = f"Transfer {event}. Reserved funds released."
        req.save(update_fields=["status", "failed_at", "failure_reason"])
        logger.info(
            "Released reserved funds for failed payout: ref=%s req_id=%s event=%s",
            reference, req.pk, event
        )
    except Exception as e:
        logger.exception(
            "Failed to release reserved funds for payout: ref=%s req_id=%s event=%s error=%s",
            reference, getattr(req, "pk", None), event, e
        )


@csrf_exempt
def paystack_webhook(request):
    """
    Handle Paystack webhook for payment notifications.
    This ensures payments are recorded even if the user closes the browser
    before being redirected back to the site.
    """
    if request.method != "POST":
        r = HttpResponse(status=405)
        r["Cache-Control"] = "no-store"
        return r
    
    # HMAC-SHA512 of raw body; Paystack uses your API secret key (settings.PAYSTACK_WEBHOOK_SIGNING_SECRET).
    webhook_secret = settings.PAYSTACK_WEBHOOK_SIGNING_SECRET
    if not webhook_secret:
        logger.error(
            "Paystack webhook signing key missing: set PAYSTACK_SECRET_KEY (and optionally PAYSTACK_WEBHOOK_SECRET)"
        )
        r = HttpResponse("Paystack secret key not configured", status=500)
        r["Cache-Control"] = "no-store"
        return r
    
    signature = request.headers.get("x-paystack-signature")
    if not signature:
        logger.warning("Paystack webhook received without signature header")
        r = HttpResponse("Missing signature", status=403)
        r["Cache-Control"] = "no-store"
        return r
    
    body = request.body
    if not paystack_service.verify_webhook_signature(body, signature, webhook_secret):
        logger.warning("Invalid Paystack webhook signature")
        r = HttpResponse("Invalid signature", status=403)
        r["Cache-Control"] = "no-store"
        return r
    
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in webhook payload")
        r = HttpResponse(status=400)
        r["Cache-Control"] = "no-store"
        return r
    
    event = payload.get("event")
    logger.info(f"Paystack webhook received: event={event}")

    if event in ("transfer.success", "transfer.failed", "transfer.reversed"):
        _paystack_webhook_staff_transfer(payload, event)
        r = HttpResponse(status=200)
        r["Cache-Control"] = "no-store"
        return r

    # Bug fix B4-B: refund.processed / refund.failed close the two-phase
    # void on FeePayments.  See ``payment_history_void`` for phase 1.
    if event in ("refund.processed", "refund.failed"):
        _paystack_webhook_fee_refund(payload, event)
        r = HttpResponse(status=200)
        r["Cache-Control"] = "no-store"
        return r

    if event == "charge.success":
        data = payload.get("data", {})
        reference = data.get("reference")

        if reference:
            dedupe_key = f"paystack_webhook_lock:{reference}"
            if cache.get(dedupe_key):
                logger.info("paystack_webhook duplicate burst skipped reference=%s", reference)
                return HttpResponse(status=200)
            cache.set(dedupe_key, 1, 120)

            metadata = data.get("metadata", {})
            payment_type = metadata.get("payment_type")
            
            logger.info(f"Processing payment: type={payment_type}, reference={reference}")
            
            # Handle School Fee Payments
            if payment_type == "school_fee" or payment_type == "fee":
                fee_id = metadata.get("fee_id")
                school_id = metadata.get("school_id")
                if not fee_id or school_id is None:
                    logger.warning(
                        "paystack_webhook school_fee ignored: missing required metadata reference=%s fee_id=%s school_id=%s",
                        reference,
                        fee_id,
                        school_id,
                    )
                    return HttpResponse(status=200)
                if fee_id:
                    try:
                        with transaction.atomic():
                            pending = (
                                FeePayment.objects.select_for_update()
                                .select_related("fee")
                                .filter(paystack_reference=reference, status="pending")
                                .order_by("-pk")
                                .first()
                            )
                            if not pending:
                                logger.warning(
                                    "paystack_webhook school_fee ignored: no pending FeePayment reference=%s meta_fee_id=%s meta_school_id=%s",
                                    reference,
                                    fee_id,
                                    school_id,
                                )
                                return HttpResponse(status=200)

                            if not is_feature_enabled_for_school(pending.fee.school_id, "online_payments"):
                                logger.warning(
                                    "paystack_webhook school_fee ignored: online_payments disabled school_id=%s reference=%s",
                                    pending.fee.school_id,
                                    reference,
                                )
                                return HttpResponse(status=200)

                            if pending.fee_id != int(fee_id):
                                logger.warning(
                                    "paystack_webhook school_fee ignored: reference=%s fee_id mismatch meta=%s db=%s meta_school_id=%s db_school_id=%s",
                                    reference,
                                    fee_id,
                                    pending.fee_id,
                                    school_id,
                                    pending.fee.school_id,
                                )
                                return HttpResponse(status=200)

                            try:
                                if int(pending.fee.school_id) != int(school_id):
                                    logger.warning(
                                        "paystack_webhook school_fee ignored: reference=%s school_id mismatch meta=%s db=%s meta_fee_id=%s db_fee_id=%s",
                                        reference,
                                        school_id,
                                        pending.fee.school_id,
                                        fee_id,
                                        pending.fee_id,
                                    )
                                    return HttpResponse(status=200)
                            except (TypeError, ValueError):
                                logger.warning(
                                    "paystack_webhook school_fee ignored: reference=%s invalid school_id=%s meta_fee_id=%s",
                                    reference,
                                    school_id,
                                    fee_id,
                                )
                                return HttpResponse(status=200)

                            try:
                                paystack_charged = Decimal(str(data.get("amount", 0))) / Decimal("100")
                            except Exception:
                                paystack_charged = Decimal("0")

                            net_credited = _net_amount_for_school_fee(
                                reference, pending.fee_id, paystack_charged
                            )
                            channel = data.get("authorization", {}).get("channel", "card")
                            paystack_id = data.get("id")
                            was_new = _complete_fee_payment(
                                pending.fee_id, reference, net_credited, paystack_id, channel
                            )

                        if was_new:
                            logger.info(
                                "paystack_webhook school_fee recorded fee_id=%s "
                                "paystack_reference=%s net=%s gross=%s",
                                pending.fee_id,
                                reference,
                                net_credited,
                                paystack_charged,
                            )
                            _notify_fee_payer_after_payment(
                                pending.fee_id, reference, float(net_credited)
                            )
                        else:
                            logger.info(
                                "paystack_webhook school_fee duplicate/ignored paystack_reference=%s fee_id=%s",
                                reference,
                                pending.fee_id,
                            )
                    except Fee.DoesNotExist:
                        logger.error(f"Fee not found: fee_id={fee_id}")
            
            # Handle Canteen Payments
            elif payment_type == "canteen":
                payment_id = metadata.get("payment_id")
                if payment_id:
                    try:
                        from operations.models import CanteenPayment
                        # Bug fix: previously imported ``timezone`` locally here
                        # (and again in the bus/hostel branches below), which made
                        # ``timezone`` a function-local name everywhere in
                        # ``paystack_webhook``. The new subscription branch at
                        # the top of the function calls ``timezone.now()``
                        # before any of these branches run, triggering an
                        # ``UnboundLocalError``. The module-level
                        # ``from django.utils import timezone`` already covers us.
                        with transaction.atomic():
                            payment = CanteenPayment.objects.select_for_update().get(id=payment_id)
                            if not is_feature_enabled_for_school(payment.school_id, "canteen"):
                                logger.info(
                                    "paystack_webhook canteen ignored: feature disabled school_id=%s payment_id=%s",
                                    payment.school_id,
                                    payment_id,
                                )
                            elif payment.payment_status != 'completed':
                                mark_canteen_payment_completed(payment=payment, reference=reference)
                                logger.info(f"Canteen payment completed: payment_id={payment_id}")
                            else:
                                logger.info(f"Canteen payment already completed: payment_id={payment_id}")
                    except CanteenPayment.DoesNotExist:
                        logger.error(f"Canteen payment not found: payment_id={payment_id}")
            
            # Handle Bus/Transport Payments
            elif payment_type == "bus":
                payment_id = metadata.get("payment_id")
                if payment_id:
                    try:
                        from operations.models import BusPayment

                        with transaction.atomic():
                            payment = BusPayment.objects.select_for_update().get(id=payment_id)
                            if not is_feature_enabled_for_school(payment.school_id, "bus_transport"):
                                logger.info(
                                    "paystack_webhook bus ignored: feature disabled school_id=%s payment_id=%s",
                                    payment.school_id,
                                    payment_id,
                                )
                            elif payment.payment_status != 'completed':
                                mark_bus_payment_completed(payment=payment, reference=reference)
                                logger.info(f"Bus payment completed: payment_id={payment_id}")
                            else:
                                logger.info(f"Bus payment already completed: payment_id={payment_id}")
                    except BusPayment.DoesNotExist:
                        logger.error(f"Bus payment not found: payment_id={payment_id}")
            
            # Handle Textbook Payments
            elif payment_type == "textbook":
                payment_id = metadata.get("payment_id")
                if payment_id:
                    try:
                        from operations.models import TextbookSale, Textbook
                        with transaction.atomic():
                            sale = TextbookSale.objects.select_for_update().get(id=payment_id)
                            if not is_feature_enabled_for_school(sale.school_id, "textbooks"):
                                logger.info(
                                    "paystack_webhook textbook ignored: feature disabled school_id=%s sale_id=%s",
                                    sale.school_id,
                                    payment_id,
                                )
                            elif sale.payment_status != 'completed':
                                mark_textbook_sale_completed(sale=sale, reference=reference)
                                if sale.textbook:
                                    updated = Textbook.objects.filter(
                                        id=sale.textbook_id, stock__gte=sale.quantity
                                    ).update(stock=models.F('stock') - sale.quantity)
                                    if not updated:
                                        logger.warning(f"Textbook stock insufficient: textbook_id={sale.textbook_id}, requested={sale.quantity}")
                                    else:
                                        logger.info(f"Textbook stock reduced: textbook_id={sale.textbook_id}, quantity={sale.quantity}")
                                logger.info(f"Textbook sale completed: sale_id={payment_id}")
                            else:
                                logger.info(f"Textbook sale already completed: sale_id={payment_id}")
                    except TextbookSale.DoesNotExist:
                        logger.error(f"Textbook sale not found: sale_id={payment_id}")
            
            # Handle Subscription Renewals
            # Bug fix F4-13: previously `pay_subscription` set metadata `type`
            # instead of `payment_type`, so this branch never fired and a
            # subscription paid for via Paystack with a dropped browser was
            # never activated until the user re-hit the callback URL.
            elif payment_type == "subscription":
                try:
                    with transaction.atomic():
                        sp = (
                            SubscriptionPayment.objects.select_for_update()
                            .select_related("school")
                            .filter(paystack_reference=reference)
                            .order_by("-pk")
                            .first()
                        )
                        if not sp:
                            logger.warning(
                                "paystack_webhook subscription ignored: no SubscriptionPayment reference=%s",
                                reference,
                            )
                            return HttpResponse(status=200)
                        if sp.status == "completed":
                            logger.info(
                                "paystack_webhook subscription duplicate/ignored reference=%s",
                                reference,
                            )
                            return HttpResponse(status=200)

                        school = sp.school
                        if not school:
                            logger.warning(
                                "paystack_webhook subscription ignored: SubscriptionPayment %s has no school",
                                sp.pk,
                            )
                            return HttpResponse(status=200)

                        meta_school_id = metadata.get("school_id")
                        try:
                            if meta_school_id is not None and int(meta_school_id) != int(school.pk):
                                logger.warning(
                                    "paystack_webhook subscription ignored: reference=%s school_id mismatch meta=%s db=%s",
                                    reference, meta_school_id, school.pk,
                                )
                                return HttpResponse(status=200)
                        except (TypeError, ValueError):
                            logger.warning(
                                "paystack_webhook subscription ignored: invalid school_id meta=%s reference=%s",
                                meta_school_id, reference,
                            )
                            return HttpResponse(status=200)

                        now = timezone.now()
                        renewal_days = 30
                        if school.subscription_end_date and school.subscription_end_date > now:
                            new_end = school.subscription_end_date + timezone.timedelta(days=renewal_days)
                        else:
                            school.subscription_start_date = now
                            new_end = now + timezone.timedelta(days=renewal_days)
                        school.subscription_end_date = new_end
                        school.subscription_status = "active"
                        school.save(update_fields=[
                            "subscription_start_date",
                            "subscription_end_date",
                            "subscription_status",
                        ])

                        sp.status = "completed"
                        sp.paystack_payment_id = data.get("id")
                        sp.payment_method = data.get("authorization", {}).get("channel", "")
                        sp.save(update_fields=[
                            "status", "paystack_payment_id", "payment_method", "updated_at",
                        ])
                        logger.info(
                            "paystack_webhook subscription renewed reference=%s school_id=%s new_end=%s",
                            reference, school.pk, new_end,
                        )
                except Exception:
                    logger.exception(
                        "paystack_webhook subscription processing failed reference=%s",
                        reference,
                    )

            # Handle Hostel Payments
            elif payment_type == "hostel":
                payment_id = metadata.get("payment_id")
                if payment_id:
                    try:
                        from operations.models import HostelFee

                        with transaction.atomic():
                            fee = HostelFee.objects.select_for_update().get(id=payment_id)
                            if not is_feature_enabled_for_school(fee.school_id, "hostel"):
                                logger.info(
                                    "paystack_webhook hostel ignored: feature disabled school_id=%s fee_id=%s",
                                    fee.school_id,
                                    payment_id,
                                )
                            elif fee.payment_status != 'completed' and not fee.paid:
                                try:
                                    paid_amount = Decimal(str(data.get("amount", 0))) / Decimal("100")
                                except Exception:
                                    paid_amount = None
                                mark_hostel_fee_completed(
                                    fee=fee,
                                    reference=reference,
                                    paid_amount=paid_amount,
                                )
                                logger.info(f"Hostel payment completed: fee_id={payment_id}")
                            else:
                                logger.info(f"Hostel payment already completed: fee_id={payment_id}")
                    except HostelFee.DoesNotExist:
                        logger.error(f"Hostel fee not found: fee_id={payment_id}")

            else:
                logger.info(
                    "paystack_webhook charge.success ignored: unknown payment_type=%s reference=%s",
                    payment_type,
                    reference,
                )

    r = HttpResponse(status=200)
    r["Cache-Control"] = "no-store"
    return r



@login_required
def fee_list(request):
    """
    Fee management view for school admins.
    Shows all fees with payment status including partial payments.
    """
    user = request.user
    school = getattr(user, "school", None)

    if not school and not user.is_superuser:
        messages.error(request, "You are not attached to any school.")
        return redirect("accounts:dashboard")

    if not (user.is_superuser or user_can_manage_school(user)):
        messages.error(request, "You do not have permission to manage fees.")
        return redirect("accounts:dashboard")

    if school and (redir := require_feature(request, "fee_management", "accounts:dashboard")):
        return redir

    # Handle actions
    if request.method == "POST":
        if not (user.is_superuser or can_manage_finance(user)):
            messages.error(request, "You do not have permission to perform this action.")
            return redirect("finance:fee_list")
        fee_id = request.POST.get("fee_id")
        action = request.POST.get("action")
        
        if fee_id and action:
            qs = Fee.objects.all()
            if not user.is_superuser and school:
                qs = qs.filter(school=school)
            
            fee = qs.filter(id=fee_id).first()
            if fee:
                from audit.services import write_audit

                if action == "mark_paid":
                    # Mark entire fee as paid
                    try:
                        before_paid = Decimal(str(fee.amount_paid or Decimal("0")))
                        total = Decimal(str(fee.amount or Decimal("0")))
                        delta = total - before_paid
                        if delta < Decimal("0"):
                            delta = Decimal("0")
                    except Exception:
                        delta = None
                    fee.amount_paid = fee.amount
                    fee.save()
                    if delta is not None and delta > Decimal("0"):
                        try:
                            import uuid

                            record_payment_transaction(
                                provider="manual",
                                reference=f"MANUAL_FEE_MARKPAID_{fee.pk}_{uuid.uuid4().hex[:10].upper()}",
                                school_id=getattr(fee, "school_id", None),
                                amount=delta,
                                status="completed",
                                payment_type=PaymentTypes.SCHOOL_FEE_MANUAL,
                                object_id=str(fee.pk),
                                metadata={"fee_id": fee.pk, "action": "mark_paid"},
                            )
                        except Exception:
                            pass
                    try:
                        write_audit(
                            user=request.user,
                            action="fee_manual_mark_paid",
                            model_name="finance.Fee",
                            object_id=fee.pk,
                            school=fee.school,
                            request=request,
                            changes={"delta": str(delta or Decimal("0"))},
                        )
                    except Exception:
                        logger.exception("fee_list: audit log failed for mark_paid fee=%s", fee.pk)
                    messages.success(request, "Fee marked as fully paid.")
                elif action == "mark_partially_paid":
                    partial_amount = request.POST.get("partial_amount")
                    if partial_amount:
                        try:
                            amount = Decimal(str(partial_amount)).quantize(Decimal("0.01"))
                            if amount <= 0:
                                raise ValueError
                            remaining = fee.remaining_balance
                            if amount > remaining:
                                messages.error(request, "Amount exceeds remaining balance.")
                                return redirect("finance:fee_list")
                            fee.amount_paid = (fee.amount_paid or Decimal("0")) + amount
                            fee.save()
                            if amount > Decimal("0"):
                                try:
                                    import uuid

                                    record_payment_transaction(
                                        provider="manual",
                                        reference=f"MANUAL_FEE_PARTIAL_{fee.pk}_{uuid.uuid4().hex[:10].upper()}",
                                        school_id=getattr(fee, "school_id", None),
                                        amount=amount,
                                        status="completed",
                                        payment_type=PaymentTypes.SCHOOL_FEE_MANUAL,
                                        object_id=str(fee.pk),
                                        metadata={"fee_id": fee.pk, "action": "mark_partially_paid"},
                                    )
                                except Exception:
                                    pass
                            try:
                                write_audit(
                                    user=request.user,
                                    action="fee_manual_partial",
                                    model_name="finance.Fee",
                                    object_id=fee.pk,
                                    school=fee.school,
                                    request=request,
                                    changes={
                                        "amount": str(amount),
                                        "remaining_after": str(fee.remaining_balance),
                                    },
                                )
                            except Exception:
                                logger.exception("fee_list: audit log failed for partial fee=%s", fee.pk)
                            messages.success(request, f"Added GHS {amount} to payment.")
                        except (ValueError, TypeError):
                            messages.error(request, "Invalid amount.")
                elif action == "record_offline":
                    offline_amount = request.POST.get("offline_amount", str(fee.remaining_balance))
                    manual_reason = (request.POST.get("manual_reason") or "").strip()
                    if not manual_reason:
                        messages.error(request, "Provide a reason for the manual offline payment.")
                        return redirect("finance:fee_list")
                    try:
                        amount = Decimal(str(offline_amount)).quantize(Decimal("0.01"))
                        if amount <= 0:
                            raise ValueError
                        remaining = fee.remaining_balance
                        if amount > remaining:
                            messages.error(request, "Amount exceeds remaining balance.")
                            return redirect("finance:fee_list")
                        # Atomic: FeePayment + Fee.amount_paid bump + ledger row must
                        # either all commit or all roll back, so we never end up
                        # with a completed payment row that doesn't credit the fee
                        # (Bug F3-5 — previously not atomic).
                        with transaction.atomic():
                            fp = FeePayment.objects.create(
                                fee=fee,
                                amount=amount,
                                payment_method="offline",
                                status="completed",
                            )
                            Fee.objects.filter(pk=fee.pk).update(
                                amount_paid=models.F("amount_paid") + amount
                            )
                            fee.refresh_from_db()
                            fee.save()
                        try:
                            record_payment_transaction(
                                provider="offline",
                                reference=f"OFFLINE_FEE_{fee.pk}_{fp.pk}",
                                school_id=getattr(fee, "school_id", None),
                                amount=amount,
                                status="completed",
                                payment_type=PaymentTypes.SCHOOL_FEE_OFFLINE,
                                object_id=str(fee.pk),
                                metadata={
                                    "fee_id": fee.pk,
                                    "fee_payment_id": fp.pk,
                                    "action": "record_offline",
                                    "reason": manual_reason,
                                },
                            )
                        except Exception:
                            logger.exception("fee_list: record_payment_transaction failed for offline fee=%s fp=%s", fee.pk, fp.pk)
                        try:
                            write_audit(
                                user=request.user,
                                action="fee_offline_payment",
                                model_name="finance.FeePayment",
                                object_id=fp.pk,
                                school=fee.school,
                                request=request,
                                changes={
                                    "fee_id": fee.pk,
                                    "amount": str(amount),
                                    "reason": manual_reason,
                                },
                            )
                        except Exception:
                            logger.exception("fee_list: audit log failed for offline fee=%s", fee.pk)
                        messages.success(request, f"Recorded offline payment of GHS {amount}.")
                    except (ValueError, TypeError):
                        messages.error(request, "Invalid amount.")
        
        return redirect("finance:fee_list")

    # List all fees (paid and unpaid) for this school
    fees_qs = Fee.objects.select_related("student", "student__user", "school")
    if not user.is_superuser and school:
        fees_qs = fees_qs.filter(school=school)
    
    # Filter options
    filter_status = request.GET.get("filter")
    if filter_status == "unpaid":
        fees_qs = fees_qs.filter(amount_paid__lt=models.F('amount'))
    elif filter_status == "partial":
        fees_qs = fees_qs.filter(amount_paid__gt=0).filter(amount_paid__lt=models.F('amount'))
    elif filter_status == "paid":
        fees_qs = fees_qs.filter(amount_paid__gte=models.F('amount'))
    
    fees_qs = fees_qs.prefetch_related(
        Prefetch("payments", queryset=FeePayment.objects.order_by("-created_at"))
    )

    fees = fees_qs.order_by("student__school__name", "student__class_name", "student__admission_number")
    page_obj = paginate(request, fees, per_page=30)

    ctx = {"fees": page_obj, "school": school, "page_obj": page_obj, "total_count": page_obj.paginator.count}
    if can_export_data(user):
        ed = timezone.localdate()
        ctx["acct_export_start"] = ed - timedelta(days=89)
        ctx["acct_export_end"] = ed
    return render(request, "finance/fee_list.html", ctx)


# ============ Fee Structure Views ============

@login_required
def fee_structure_list(request):
    school = getattr(request.user, "school", None)
    if not school and not request.user.is_superuser:
        return redirect("accounts:dashboard")
    if not school:
        structures = FeeStructure.objects.all().select_related("school")[:100]
        return render(request, "finance/fee_structure_list.html", {"structures": structures, "school": None})
    if (redir := require_feature(request, "fee_management", "accounts:dashboard")):
        return redir
    structures = FeeStructure.objects.filter(school=school).order_by("name", "class_name")
    return render(request, "finance/fee_structure_list.html", {"structures": structures, "school": school})


@login_required
def fee_structure_create(request):
    school = getattr(request.user, "school", None)
    if not school and not request.user.is_superuser:
        return redirect("accounts:dashboard")
    if not school:
        messages.error(request, "School admins only.")
        return redirect("accounts:dashboard")
    if not (request.user.is_superuser or is_school_leadership(request.user)):
        return redirect("accounts:school_dashboard")
    if (redir := require_feature(request, "fee_management", "accounts:dashboard")):
        return redir
    form = FeeStructureForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            structure = form.save(commit=False)
            structure.school = school
            structure.save()
            try:
                write_audit(
                    user=request.user,
                    action="create",
                    model_name="finance.FeeStructure",
                    object_id=structure.pk,
                    school=school,
                    request=request,
                    changes={
                        "name": structure.name,
                        "amount": str(structure.amount),
                        "class_name": structure.class_name,
                        "term": structure.term,
                        "is_active": structure.is_active,
                    },
                )
            except Exception:
                logger.exception("fee_structure_create: audit failed for structure=%s", structure.pk)
            messages.success(request, "Fee structure added.")
            return redirect("finance:fee_structure_list")
        messages.error(request, "Please fix the highlighted errors.")

    return render(
        request,
        "finance/fee_structure_form.html",
        {
            "school": school,
            "form": form,
            "structure": form.instance if getattr(form.instance, "pk", None) else None,
        },
    )


@login_required
def fee_structure_edit(request, pk):
    """Edit an existing fee structure."""
    school = getattr(request.user, "school", None)
    if not school and not request.user.is_superuser:
        return redirect("accounts:dashboard")
    if not school:
        messages.error(request, "School admins only.")
        return redirect("accounts:dashboard")
    if not (request.user.is_superuser or is_school_leadership(request.user)):
        return redirect("accounts:school_dashboard")
    if (redir := require_feature(request, "fee_management", "accounts:dashboard")):
        return redir

    structure = get_object_or_404(FeeStructure, pk=pk, school=school)

    form = FeeStructureForm(request.POST or None, instance=structure)

    if request.method == "POST":
        if form.is_valid():
            before = {
                "name": structure.name,
                "amount": str(structure.amount),
                "class_name": structure.class_name,
                "term": structure.term,
                "is_active": structure.is_active,
            }
            form.save()
            try:
                write_audit(
                    user=request.user,
                    action="update",
                    model_name="finance.FeeStructure",
                    object_id=structure.pk,
                    school=school,
                    request=request,
                    changes={
                        "before": before,
                        "after": {
                            "name": structure.name,
                            "amount": str(structure.amount),
                            "class_name": structure.class_name,
                            "term": structure.term,
                            "is_active": structure.is_active,
                        },
                    },
                )
            except Exception:
                logger.exception("fee_structure_edit: audit failed for structure=%s", structure.pk)
            messages.success(request, "Fee structure updated.")
            return redirect("finance:fee_structure_list")
        messages.error(request, "Please fix the highlighted errors.")

    return render(
        request,
        "finance/fee_structure_form.html",
        {"school": school, "structure": structure, "form": form},
    )


@login_required
def fee_structure_delete(request, pk):
    """Delete a fee structure."""
    school = getattr(request.user, "school", None)
    if not school and not request.user.is_superuser:
        return redirect("accounts:dashboard")
    if not school:
        messages.error(request, "School admins only.")
        return redirect("accounts:dashboard")
    if not (request.user.is_superuser or is_school_leadership(request.user)):
        return redirect("accounts:school_dashboard")
    if (redir := require_feature(request, "fee_management", "accounts:dashboard")):
        return redir

    structure = get_object_or_404(FeeStructure, pk=pk, school=school)

    if request.method == "POST":
        snapshot = {
            "name": structure.name,
            "amount": str(structure.amount),
            "class_name": structure.class_name,
            "term": structure.term,
            "is_active": structure.is_active,
        }
        structure.delete()
        try:
            write_audit(
                user=request.user,
                action="delete",
                model_name="finance.FeeStructure",
                object_id=structure.pk,
                school=school,
                request=request,
                changes=snapshot,
            )
        except Exception:
            logger.exception("fee_structure_delete: audit failed for structure=%s", structure.pk)
        messages.success(request, "Fee structure deleted.")
        return redirect("finance:fee_structure_list")
    
    return render(request, "finance/confirm_delete.html", {
        "object": structure,
        "type": "fee structure",
        "cancel_url": "finance:fee_structure_list"
    })


def _active_students_queryset_for_fee_structure(school, structure):
    """Active students matching this structure's class scope (same rules as bulk / generate)."""
    from students.models import Student

    qs = Student.objects.filter(school=school, status="active")
    if structure.school_class_id:
        return qs.filter(school_class_id=structure.school_class_id)
    if structure.class_name:
        return qs.filter(class_name=structure.class_name)
    return qs


def _apply_generate_fees_from_structure(request, school, structure):
    """
    Create Fee rows for in-scope students who do not yet have one for this fee structure.
    Returns (created_count, skipped_count).
    """
    students_qs = _active_students_queryset_for_fee_structure(school, structure)
    total_scope = students_qs.count()
    existing_student_ids = set(
        Fee.objects.filter(school=school, fee_structure=structure).values_list("student_id", flat=True)
    )
    new_fees = [
        Fee(
            school=school,
            student=student,
            fee_structure=structure,
            term=structure.term_fk,
            amount=structure.amount,
        )
        for student in students_qs.iterator()
        if student.id not in existing_student_ids
    ]

    if new_fees:
        created_fees = Fee.objects.bulk_create(new_fees, batch_size=500)
        for _fee in created_fees:
            try:
                from core.signals import notify_fee_assigned

                notify_fee_assigned(sender=Fee, instance=_fee, created=True)
            except Exception:
                logger.warning(
                    "generate_fees_from_structure: parent notify failed fee=%s", _fee.pk, exc_info=True
                )

    created_count = len(new_fees)
    skipped_count = total_scope - created_count
    try:
        write_audit(
            user=request.user,
            action="generate",
            model_name="finance.FeeStructure",
            object_id=structure.pk,
            school=school,
            request=request,
            changes={
                "generated_count": created_count,
                "skipped_count": skipped_count,
            },
        )
    except Exception:
        logger.exception("generate_fees_from_structure: audit failed structure=%s", structure.pk)
    return created_count, skipped_count


@login_required
def fee_structure_coverage(request, pk):
    """
    Show in-scope students vs those who already have a Fee for this structure, and backfill missing rows.
    """
    school = getattr(request.user, "school", None)
    if not school and not request.user.is_superuser:
        return redirect("accounts:dashboard")
    if not school:
        messages.error(request, "School admins only.")
        return redirect("accounts:dashboard")
    if not (request.user.is_superuser or is_school_leadership(request.user)):
        return redirect("accounts:school_dashboard")
    if (redir := require_feature(request, "fee_management", "accounts:dashboard")):
        return redir

    structure = get_object_or_404(
        FeeStructure.objects.select_related("school_class", "term_fk"),
        pk=pk,
        school=school,
    )

    if request.method == "POST":
        created_count, skipped_count = _apply_generate_fees_from_structure(request, school, structure)
        messages.success(
            request,
            f"Created {created_count} new fee record(s). {skipped_count} student(s) already had this fee (unchanged).",
        )
        return redirect("finance:fee_structure_coverage", pk=structure.pk)

    in_scope = _active_students_queryset_for_fee_structure(school, structure).select_related(
        "user", "school_class"
    )
    total_in_scope = in_scope.count()
    existing_ids = set(
        Fee.objects.filter(school=school, fee_structure=structure).values_list("student_id", flat=True)
    )
    charged_in_scope = in_scope.filter(pk__in=existing_ids).count()
    missing_qs = in_scope.exclude(pk__in=existing_ids).order_by(
        "user__last_name", "user__first_name", "admission_number"
    )
    missing_count = missing_qs.count()
    missing_preview = list(missing_qs[:150])
    missing_not_shown = max(0, missing_count - len(missing_preview))

    return render(
        request,
        "finance/fee_structure_coverage.html",
        {
            "school": school,
            "structure": structure,
            "total_in_scope": total_in_scope,
            "charged_in_scope": charged_in_scope,
            "missing_count": missing_count,
            "missing_preview": missing_preview,
            "missing_not_shown": missing_not_shown,
        },
    )


@login_required
def generate_fees_from_structure(request, pk):
    """Generate individual Fee records for all students in a class based on FeeStructure.

    GET kept for backward compatibility with existing confirm() links from the fee list.
    """
    school = getattr(request.user, "school", None)
    if not school and not request.user.is_superuser:
        return redirect("accounts:dashboard")
    if not school:
        messages.error(request, "School admins only.")
        return redirect("accounts:dashboard")
    if not (request.user.is_superuser or is_school_leadership(request.user)):
        return redirect("accounts:school_dashboard")
    if (redir := require_feature(request, "fee_management", "accounts:dashboard")):
        return redir

    structure = get_object_or_404(
        FeeStructure.objects.select_related("school_class", "term_fk"),
        pk=pk,
        school=school,
    )

    created_count, skipped_count = _apply_generate_fees_from_structure(request, school, structure)
    messages.success(
        request,
        f"Generated fees for {created_count} students. {skipped_count} skipped (already present).",
    )
    return redirect("finance:fee_structure_list")


# ============ Paystack Subscription Views (for schools paying YOU) ============

@login_required
def subscription_view(request):
    """
    View subscription status and manage subscription.
    """
    school = getattr(request.user, "school", None)
    if not school:
        messages.error(request, "You are not attached to any school.")
        return redirect("accounts:dashboard")
    
    # Check if Paystack is configured
    paystack_available = is_paystack_configured()
    
    context = {
        "school": school,
        "paystack_available": paystack_available,
    }
    
    return render(request, "finance/subscription.html", context)


@login_required
def pay_subscription(request):
    """
    Initialize Paystack payment for school subscription renewal.
    """
    school = getattr(request.user, "school", None)
    if not school:
        messages.error(request, "You are not attached to any school.")
        return redirect("accounts:dashboard")
    
    # Check if Paystack is configured
    if not is_paystack_configured():
        messages.error(request, "Online payments are currently unavailable. Please contact support.")
        return redirect("finance:subscription")
    
    # Subscription list price (net to platform); customer may pay gross if fee pass-through is on.
    amount_dec = (
        school.subscription_amount
        if isinstance(getattr(school, "subscription_amount", None), Decimal)
        else Decimal(str(school.subscription_amount))
    ) if school.subscription_amount else Decimal("1500")
    amount_net, amount_gross = compute_paystack_gross_from_net(amount_dec)
    charge_amount = float(amount_gross)
    
    # Get admin's email
    email = request.user.email or "admin@school.com"
    
    # Build callback URL
    callback_url = request.build_absolute_uri(
        reverse("finance:subscription_callback")
    )
    # Create a unique reference
    reference = f"SCHOOL_SUB_{school.id}_{uuid.uuid4().hex[:8].upper()}"

    SubscriptionPayment.objects.create(
        school=school,
        user=request.user,
        amount=amount_net,
        gross_amount=amount_gross,
        paystack_reference=reference,
        status="pending",
    )
    
    # Initialize payment with Paystack
    response = paystack_service.initialize_payment(
        email=email,
        amount=charge_amount,
        callback_url=callback_url,
        reference=reference,
        metadata={
            "school_id": school.id,
            "school_name": school.name,
            # Webhook handler reads `payment_type`, not `type`. The legacy
            # `type` key is kept for backward-compatibility with any external
            # tooling that already reads it, but `payment_type` is now what
            # routes the webhook into the subscription branch (Bug F4-13).
            "type": "subscription",
            "payment_type": "subscription",
            "amount_net": float(amount_net),
            "amount_gross": float(amount_gross),
        },
    )

    if response.get("status") and response.get("data", {}).get("authorization_url"):
        return redirect(response["data"]["authorization_url"])
    else:
        error_msg = response.get("message", "Could not initialize payment. Please try again.")
        messages.error(request, error_msg)
        return redirect("finance:subscription")


@login_required
def subscription_callback(request):
    """
    Handle Paystack subscription payment callback.
    School ID is resolved from SubscriptionPayment by Paystack reference.
    """
    reference = request.GET.get("reference")
    
    if not reference:
        messages.error(request, "Payment reference not found.")
        return redirect("finance:subscription")
    
    response = paystack_service.verify_payment(reference)
    
    if response.get("status") and response.get("data", {}).get("status") == "success":
        data = response["data"]
        
        sp = (
            SubscriptionPayment.objects.select_related("school")
            .filter(paystack_reference=reference)
            .order_by("-pk")
            .first()
        )
        if not sp:
            messages.error(request, "Payment verification failed.")
            return redirect("finance:subscription")

        if sp.status == "completed":
            return redirect("finance:subscription")

        school = sp.school
        if school:
            try:
                
                from django.utils import timezone
                now = timezone.now()
                renewal_days = 30
                
                if school.subscription_end_date and school.subscription_end_date > now:
                    new_end_date = school.subscription_end_date + timezone.timedelta(days=renewal_days)
                else:
                    school.subscription_start_date = now
                    new_end_date = now + timezone.timedelta(days=renewal_days)
                
                school.subscription_end_date = new_end_date
                school.subscription_status = "active"
                school.save()

                sp.status = "completed"
                sp.paystack_payment_id = data.get("id")
                sp.payment_method = data.get("authorization", {}).get("channel", "")
                sp.save(update_fields=["status", "paystack_payment_id", "payment_method", "updated_at"])
                
                messages.success(request, f"Subscription renewed successfully! Valid until {new_end_date.strftime('%Y-%m-%d')}")
                
            except School.DoesNotExist:
                messages.error(request, "School not found.")
    else:
        SubscriptionPayment.objects.filter(
            paystack_reference=reference, status="pending"
        ).update(status="failed")
        error_msg = response.get("message", "Payment verification failed.")
        messages.error(request, f"Payment was not successful: {error_msg}")
    
    return redirect("finance:subscription")


def retry_failed_payments():
    """
    Retry all unpaid fees that have a Paystack reference.
    """
    failed_fees = Fee.objects.filter(
        amount_paid__lt=models.F('amount'),
        paystack_reference__isnull=False
    )
    return len(failed_fees)


def notify_admin_unpaid_fees():
    """
    Notify all school_admin users of unpaid fees.
    """
    unpaid_fees = Fee.objects.filter(amount_paid__lt=models.F('amount'))
    unpaid_count = unpaid_fees.count()
    admins = User.objects.filter(role="school_admin")
    for admin in admins:
        message = f"There are {unpaid_count} unpaid/partial fees pending in the system."
        if admin.phone:
            send_sms(admin.phone, message)
    return unpaid_count


# ============ Parent Portal Views ============

@login_required
def parent_fee_list(request):
    """
    View for parents to see their children's fees and make payments.
    """
    from django.db.models import Prefetch

    user = request.user

    from students.utils import get_children_for_parent

    students = get_children_for_parent(user, active_only=False)

    if not students.exists():
        messages.info(request, "No students linked to your account.")
        return render(request, "finance/parent_fee_list.html", {"fees": [], "students": []})

    student_id = (request.GET.get("student") or "").strip()
    active_student = None
    if student_id:
        active_student = students.filter(pk=student_id).first()

    fee_students = students.filter(pk=active_student.pk) if active_student else students

    fees = (
        Fee.objects.filter(student__in=fee_students)
        .select_related("student", "student__user", "school")
        .prefetch_related(
            Prefetch(
                "payments",
                queryset=FeePayment.objects.filter(status="completed").order_by("-created_at"),
            )
        )
        .order_by("-created_at")
    )

    paystack_available = is_paystack_configured()
    if paystack_available:
        user_school = getattr(request.user, "school", None)
        if user_school:
            paystack_available = user_school.is_payout_setup_active

    return render(
        request,
        "finance/parent_fee_list.html",
        {
            "fees": fees,
            "students": students,
            "active_student": active_student,
            "paystack_available": paystack_available,
        },
    )


@login_required
def payment_success(request):
    """Show payment success page after Paystack redirect.

    Paystack appends ?reference=... to the callback URL.
    If the reference matches a completed PaymentTransaction,
    we enrich the page with payment details and receipt link.
    """
    reference = request.GET.get("reference") or request.GET.get("trxref")
    payment = None
    fee_payment = None

    denied = False
    if reference:
        try:
            from finance.models import PaymentTransaction, FeePayment
            tx = (
                PaymentTransaction.objects.filter(reference=reference)
                .select_related("school")
                .first()
            )
            if tx:
                fee_payment = (
                    FeePayment.objects.filter(paystack_reference=reference)
                    .select_related(
                        "fee", "fee__student", "fee__student__user",
                        "fee__student__school", "fee__school",
                    )
                    .first()
                )
                if fee_payment:
                    fee = fee_payment.fee
                    from students.utils import parent_is_guardian_of

                    is_parent_of = fee and fee.student and (
                        (fee.student.user and fee.student.user_id == request.user.id)
                        or parent_is_guardian_of(request.user, fee.student)
                    )
                    user_school = getattr(request.user, "school", None)
                    is_school_staff = (request.user.is_superuser or user_can_manage_school(request.user)) and (
                        request.user.is_superuser
                        or (user_school and fee and fee.school_id == user_school.id)
                    )
                    if not (is_school_staff or is_parent_of):
                        denied = True
                else:
                    denied = True
                payment = tx
        except Exception:
            pass

    if denied:
        messages.error(request, "You do not have permission to view this payment.")
        return redirect("home")

    if fee_payment and getattr(fee_payment, "fee", None):
        _fee = fee_payment.fee
        if not is_feature_enabled_for_school(_fee.school_id, "fee_management"):
            messages.error(request, "Fee management is disabled for this school.")
            return redirect("home")

    ctx = {
        "reference": reference,
        "payment": payment,
        "fee_payment": fee_payment,
    }
    return render(request, "finance/payment_success.html", ctx)


@login_required
def payment_receipt(request, pk):
    """Generate a downloadable PDF receipt for a payment."""
    payment = get_object_or_404(
        FeePayment.objects.select_related("fee", "fee__student", "fee__student__user", "fee__school"),
        pk=pk, status="completed",
    )
    fee = payment.fee
    school = fee.school if fee else None
    user = request.user

    from students.utils import parent_is_guardian_of
    is_parent_of = fee.student and (
        (fee.student.user and fee.student.user_id == user.id)
        or parent_is_guardian_of(user, fee.student)
    )
    user_school = getattr(user, "school", None)
    is_school_staff = (user.is_superuser or user_can_manage_school(user)) and (
        user.is_superuser or (user_school and school and school.pk == user_school.pk)
    )
    if not (is_school_staff or is_parent_of):
        messages.error(request, "You do not have permission to view this receipt.")
        return redirect("home")

    if not is_feature_enabled_for_school(fee.school_id, "fee_management"):
        messages.error(request, "Fee management is disabled for this school.")
        return redirect("home")

    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.units import mm

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=30*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()
    elements = []

    school_name = school.name if school else "Mastex SchoolOS"
    elements.append(Paragraph(f"<b>{school_name}</b>", styles["Title"]))
    elements.append(Paragraph("Payment Receipt", styles["Heading2"]))
    elements.append(Spacer(1, 10*mm))

    student_name = fee.student.user.get_full_name() if fee.student and fee.student.user else "N/A"
    admno = fee.student.admission_number if fee.student else "N/A"

    data = [
        ["Receipt No.", str(payment.id).zfill(6)],
        ["Date", payment.created_at.strftime("%B %d, %Y") if payment.created_at else ""],
        ["Student", student_name],
        ["Admission No.", admno],
        ["Fee Description", str(getattr(fee, "description", None) or getattr(fee, "fee_type", None) or "School Fee")],
        ["Amount Paid", f"GHS {payment.amount:,.2f}"],
        ["Payment Method", (payment.payment_method or "Paystack").title()],
        ["Reference", payment.paystack_reference or "---"],
        ["Status", "Completed"],
    ]
    t = Table(data, colWidths=[50*mm, 100*mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, -1), (-1, -1), 1, colors.black),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 15*mm))
    elements.append(Paragraph("This is a computer-generated receipt. No signature required.", styles["Italic"]))

    doc.build(elements)
    pdf = buf.getvalue()
    buf.close()

    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="receipt_{payment.id}.pdf"'
    return resp


@login_required
def payment_ledger_health(request):
    user = request.user
    school = getattr(user, "school", None)

    if not school and not user.is_superuser:
        messages.error(request, "You are not attached to any school.")
        return redirect("accounts:dashboard")

    if not (user.is_superuser or user_can_manage_school(user)):
        messages.error(request, "You do not have permission to view the payment ledger.")
        return redirect("accounts:dashboard")

    if school and (redir := require_feature(request, "fee_management", "accounts:dashboard")):
        return redir

    qs = PaymentTransaction.objects.all().select_related("school", "reviewed_by")
    if school and not user.is_superuser:
        qs = qs.filter(school=school)

    try:
        days = int(request.GET.get("days") or 30)
    except Exception:
        days = 30
    days = max(1, min(days, 365))

    from django.utils import timezone

    since = timezone.now() - timezone.timedelta(days=days)
    qs = qs.filter(created_at__gte=since)

    date_from = since.date().strftime("%Y-%m-%d")
    date_to = timezone.now().date().strftime("%Y-%m-%d")

    from django.db.models import Count, Sum

    by_type_provider = (
        qs.values("provider", "payment_type", "status")
        .annotate(count=Count("id"), amount=Sum("amount"))
        .order_by("provider", "payment_type", "status")
    )

    recent_failed = (
        qs.filter(status="failed")
        .order_by("-created_at")
        [:50]
    )

    return render(
        request,
        "finance/payment_ledger_health.html",
        {
            "school": school,
            "days": days,
            "filter_from": date_from,
            "filter_to": date_to,
            "by_type_provider": list(by_type_provider),
            "recent_failed": recent_failed,
        },
    )


@login_required
def check_payment_status(request):
    """
    Allow authenticated users to check payment status using their payment reference.
    This helps when user closes browser during payment and needs to verify
    if their payment was recorded via webhook.
    """
    payment = None
    error = None
    
    if request.method == "POST":
        reference = request.POST.get("reference", "").strip()
        
        if not reference:
            error = "Please enter a payment reference."
        else:
            payment = _check_payment_status_fee_payment_qs(request.user).filter(
                paystack_reference=reference
            ).first()

            if not payment:
                fee_with_ref = _check_payment_status_fee_qs(request.user).filter(
                    paystack_reference=reference
                ).first()
                
                if fee_with_ref is not None:
                    paid = getattr(fee_with_ref, "amount_paid", None) or Decimal("0")
                    if paid > 0:
                        # Create a virtual payment object for display
                        class VirtualPayment:
                            def __init__(self, fee):
                                self.amount = getattr(fee, "amount_paid", None) or Decimal("0")
                                self.paystack_reference = getattr(fee, "paystack_reference", None) or ""
                                self.status = "completed"
                                self.created_at = getattr(fee, "updated_at", None) or getattr(
                                    fee, "created_at", None
                                )
                                self.fee = fee

                        payment = VirtualPayment(fee_with_ref)
            
            if not payment:
                error = f"No payment found with reference '{reference}'. Please check and try again."
    
    return render(request, "finance/payment_status_check.html", {
        "payment": payment,
        "error": error,
        "reference": request.POST.get("reference", "") if request.method == "POST" else ""
    })


# ============ Payment History Management ============

@login_required
def payment_history_list(request):
    """
    View for school admins to see and manage payment history.
    Allows filtering, searching, and batch operations.
    """
    user = request.user
    school = getattr(user, "school", None)

    if not school and not user.is_superuser:
        messages.error(request, "You are not attached to any school.")
        return redirect("accounts:dashboard")

    if not (user.is_superuser or user_can_manage_school(user) or can_manage_finance(user)):
        messages.error(request, "You do not have permission to view payment history.")
        return redirect("accounts:dashboard")

    if school and (redir := require_feature(request, "fee_management", "accounts:dashboard")):
        return redir

    # Get all payments for this school
    payments_qs = FeePayment.objects.select_related(
        "fee", "fee__student", "fee__school"
    )
    
    if not user.is_superuser and school:
        payments_qs = payments_qs.filter(fee__school=school)
    
    # Filter by status
    filter_status = request.GET.get("status")
    if filter_status == "completed":
        payments_qs = payments_qs.filter(status="completed")
    elif filter_status == "pending":
        payments_qs = payments_qs.filter(status="pending")
    elif filter_status == "failed":
        payments_qs = payments_qs.filter(status="failed")
    
    # Search by student name (on the linked User) or payment reference.
    # Bug fix: previously filtered ``fee__student__first_name`` but Student
    # has no first_name/last_name fields (they live on User). The old query
    # raised ``FieldError`` whenever a user typed in the search box.
    search = (request.GET.get("search") or "").strip()
    if search:
        payments_qs = payments_qs.filter(
            models.Q(fee__student__user__first_name__icontains=search) |
            models.Q(fee__student__user__last_name__icontains=search) |
            models.Q(fee__student__user__username__icontains=search) |
            models.Q(fee__student__admission_number__icontains=search) |
            models.Q(paystack_reference__icontains=search) |
            models.Q(receipt_no__icontains=search)
        )
    
    payments_qs = payments_qs.order_by("-created_at")

    from django.db.models import Sum as _Sum
    totals = payments_qs.filter(status="completed").aggregate(total_amount=_Sum("amount"))
    total_amount = totals["total_amount"] or 0
    total_count = payments_qs.count()

    page_obj = paginate(request, payments_qs, per_page=30)

    return render(request, "finance/payment_history_list.html", {
        "payments": page_obj,
        "total_amount": total_amount,
        "total_count": total_count,
        "school": school,
        "filter_status": filter_status,
        "search": search,
        "page_obj": page_obj,
    })


@login_required
def payment_history_delete(request, pk):
    """
    Delete a single payment record.
    Only allows deleting pending or failed payments (not completed).
    """
    user = request.user
    school = getattr(user, "school", None)

    if not school and not user.is_superuser:
        messages.error(request, "You are not attached to any school.")
        return redirect("accounts:dashboard")

    if not (user.is_superuser or can_manage_finance(user)):
        messages.error(request, "You do not have permission to manage payment records.")
        return redirect("accounts:dashboard")

    if school and (redir := require_feature(request, "fee_management", "accounts:dashboard")):
        return redir

    pay_qs = FeePayment.objects.select_related("fee", "fee__school").filter(pk=pk)
    if school and not user.is_superuser:
        pay_qs = pay_qs.filter(fee__school=school)
    payment = pay_qs.first()
    if not payment:
        messages.error(request, "Payment not found or you do not have permission.")
        return redirect("finance:payment_history_list")

    fee_school_id = getattr(getattr(payment, "fee", None), "school_id", None)
    if fee_school_id and not is_feature_enabled_for_school(fee_school_id, "fee_management"):
        messages.error(request, "Fee management is disabled for the school that owns this payment.")
        return redirect("finance:payment_history_list")

    # Only allow deleting pending or failed payments
    if payment.status == "completed":
        messages.error(request, "Completed payments cannot be deleted. Use the void workflow.")
        return redirect("finance:payment_history_list")
    
    if request.method == "POST":
        # Snapshot before delete so we can write an audit row.
        snapshot = {
            "fee_id": payment.fee_id,
            "amount": str(payment.amount or Decimal("0")),
            "status": payment.status,
            "payment_method": payment.payment_method,
            "paystack_reference": payment.paystack_reference or "",
        }
        payment.delete()
        try:
            from audit.services import write_audit
            write_audit(
                user=user,
                action="delete",
                model_name="finance.FeePayment",
                object_id=str(pk),
                school=school or getattr(payment.fee, "school", None),
                request=request,
                changes=snapshot,
            )
        except Exception:
            logger.exception("payment_history_delete: audit log failed for payment=%s", pk)
        messages.success(request, "Payment record deleted successfully.")
        return redirect("finance:payment_history_list")
    
    return render(request, "finance/confirm_delete.html", {
        "object": payment,
        "type": "payment",
        "cancel_url": "finance:payment_history_list"
    })


@login_required
def payment_history_delete_multiple(request):
    """
    Delete multiple payment records at once.
    Only allows deleting pending or failed payments (not completed).
    """
    user = request.user
    school = getattr(user, "school", None)

    if not school and not user.is_superuser:
        messages.error(request, "You are not attached to any school.")
        return redirect("accounts:dashboard")

    if not (user.is_superuser or can_manage_finance(user)):
        messages.error(request, "You do not have permission to manage payment records.")
        return redirect("accounts:dashboard")

    if school and (redir := require_feature(request, "fee_management", "accounts:dashboard")):
        return redir

    if request.method == "POST":
        payment_ids = request.POST.getlist("payment_ids")
        
        if not payment_ids:
            messages.error(request, "No payments selected.")
            return redirect("finance:payment_history_list")
        
        # Filter payments to only include pending or failed
        payments_qs = FeePayment.objects.filter(pk__in=payment_ids)
        
        if not user.is_superuser and school:
            payments_qs = payments_qs.filter(fee__school=school)

        from schools.models import SchoolFeature

        payments_qs = payments_qs.exclude(
            fee__school_id__in=SchoolFeature.objects.filter(key="fee_management", enabled=False).values_list(
                "school_id", flat=True
            )
        )

        # Separate deletable from non-deletable
        deletable = payments_qs.filter(status__in=["pending", "failed"])
        non_deletable = payments_qs.filter(status="completed").count()
        
        if non_deletable > 0:
            messages.warning(request, f"Skipped {non_deletable} completed payments (use void workflow).")
        
        # Snapshot deletable rows so we can audit individual deletions.
        snapshots = list(deletable.values(
            "pk", "fee_id", "amount", "status", "payment_method", "paystack_reference",
        ))
        deleted_count = deletable.count()
        deletable.delete()
        try:
            from audit.services import write_audit
            for snap in snapshots:
                write_audit(
                    user=user,
                    action="delete",
                    model_name="finance.FeePayment",
                    object_id=str(snap["pk"]),
                    school=school,
                    request=request,
                    changes={k: (str(v) if k == "amount" else v) for k, v in snap.items() if k != "pk"},
                )
        except Exception:
            logger.exception("payment_history_delete_multiple: audit log failed (count=%s)", deleted_count)
        
        messages.success(request, f"Successfully deleted {deleted_count} payment record(s).")
    
    return redirect("finance:payment_history_list")


@login_required
def payment_history_void(request, pk):
    """
    Void a completed payment with audit trail and optional Paystack refund.
    Requires leadership-level finance permissions.
    """
    user = request.user
    school = getattr(user, "school", None)
    if not school and not user.is_superuser:
        messages.error(request, "You are not attached to any school.")
        return redirect("accounts:dashboard")
    if not (user.is_superuser or (can_manage_finance(user) and is_school_leadership(user))):
        messages.error(request, "You do not have permission to void completed payments.")
        return redirect("finance:payment_history_list")

    if school and (redir := require_feature(request, "fee_management", "accounts:dashboard")):
        return redir

    pay_qs = FeePayment.objects.select_related("fee", "fee__school", "fee__student").filter(pk=pk)
    if school and not user.is_superuser:
        pay_qs = pay_qs.filter(fee__school=school)
    payment = pay_qs.first()
    if not payment:
        messages.error(request, "Payment not found or not accessible.")
        return redirect("finance:payment_history_list")
    fee_school_id = getattr(getattr(payment, "fee", None), "school_id", None)
    if fee_school_id and not is_feature_enabled_for_school(fee_school_id, "fee_management"):
        messages.error(request, "Fee management is disabled for the school that owns this payment.")
        return redirect("finance:payment_history_list")
    if payment.status != "completed":
        messages.error(request, "Only completed payments can be voided.")
        return redirect("finance:payment_history_list")
    if payment.voided_at:
        messages.info(request, "Payment has already been voided.")
        return redirect("finance:payment_history_list")
    if payment.refund_status == FeePayment.REFUND_STATUS_REQUESTED:
        messages.info(
            request,
            "A refund is already in progress for this payment. The fee balance will adjust when Paystack confirms.",
        )
        return redirect("finance:payment_history_list")

    if request.method == "POST":
        reason = (request.POST.get("void_reason") or "").strip()
        if len(reason) < 8:
            messages.error(request, "Provide a clear reason (at least 8 characters).")
            return render(request, "finance/payment_void_confirm.html", {"payment": payment})

        with transaction.atomic():
            locked = (
                FeePayment.objects.select_for_update()
                .select_related("fee", "fee__student", "fee__school")
                .filter(pk=payment.pk)
                .first()
            )
            if not locked or locked.voided_at:
                messages.error(request, "Payment has already been processed.")
                return redirect("finance:payment_history_list")
            if locked.status != "completed":
                messages.error(request, "Only completed payments can be voided.")
                return redirect("finance:payment_history_list")
            if locked.refund_status == FeePayment.REFUND_STATUS_REQUESTED:
                messages.info(
                    request,
                    "A refund has already been requested for this payment. Waiting for Paystack confirmation.",
                )
                return redirect("finance:payment_history_list")

            # Bug fix B4-B: two-phase refund commit.
            #
            # Paystack refunds are *queued*, not synchronous — Paystack's
            # ``/refund`` endpoint returns ``status:true`` once it accepts
            # the request, but the actual money movement is confirmed
            # later via ``refund.processed`` / ``refund.failed`` webhooks.
            #
            # Previously we eagerly reversed ``fee.amount_paid`` and marked
            # the payment failed at request time.  If Paystack subsequently
            # rejected the refund (insufficient merchant balance, no card
            # on file, etc.) the ledger ended up under-counted forever.
            #
            # Now: we only mark the payment as "refund requested" and
            # record the audit trail.  The fee balance is reversed by the
            # webhook handler when Paystack confirms the refund.
            if locked.paystack_reference:
                refund_resp = paystack_service.initiate_refund(
                    transaction_reference=locked.paystack_reference,
                    amount_major=locked.amount,
                    currency=getattr(settings, "PAYSTACK_CURRENCY", "GHS"),
                )
                if not refund_resp.get("status"):
                    messages.error(
                        request,
                        f"Refund request failed; payment not voided. {refund_resp.get('message', 'Unknown error')}",
                    )
                    return render(request, "finance/payment_void_confirm.html", {"payment": locked})

                fee = locked.fee
                locked.refund_status = FeePayment.REFUND_STATUS_REQUESTED
                locked.refund_requested_at = timezone.now()
                locked.voided_by = user
                locked.void_reason = reason
                locked.save(update_fields=[
                    "refund_status", "refund_requested_at",
                    "voided_by", "void_reason",
                ])

                write_audit(
                    user=user,
                    action="refund_requested",
                    model_name="finance.FeePayment",
                    object_id=str(locked.pk),
                    school=getattr(fee, "school", None),
                    changes={
                        "fee_id": fee.pk,
                        "student_id": fee.student_id,
                        "amount": str(locked.amount or Decimal("0")),
                        "reason": reason,
                        "paystack_reference": locked.paystack_reference or "",
                    },
                )
                messages.success(
                    request,
                    "Refund requested. The fee balance will be reversed once "
                    "Paystack confirms the refund (typically within a few minutes).",
                )
                return redirect("finance:payment_history_list")

            # Offline / non-Paystack payment — no provider to wait on, so
            # this stays a synchronous void (legacy behaviour preserved).
            fee = locked.fee
            current_paid = fee.amount_paid or Decimal("0")
            reversal = locked.amount or Decimal("0")
            fee.amount_paid = max(Decimal("0"), current_paid - reversal)
            fee.save(update_fields=["amount_paid", "paid", "updated_at"])

            locked.status = "failed"
            locked.voided_at = timezone.now()
            locked.voided_by = user
            locked.void_reason = reason
            locked.save(update_fields=["status", "voided_at", "voided_by", "void_reason"])

            write_audit(
                user=user,
                action="void",
                model_name="finance.FeePayment",
                object_id=str(locked.pk),
                school=getattr(fee, "school", None),
                changes={
                    "fee_id": fee.pk,
                    "student_id": fee.student_id,
                    "amount": str(reversal),
                    "reason": reason,
                    "paystack_reference": locked.paystack_reference or "",
                },
            )

        messages.success(request, "Payment voided and fee balance restored.")
        return redirect("finance:payment_history_list")

    return render(request, "finance/payment_void_confirm.html", {"payment": payment})


@login_required
def payment_ledger_list(request):
    user = request.user
    school = getattr(user, "school", None)

    if not school and not user.is_superuser:
        messages.error(request, "You are not attached to any school.")
        return redirect("accounts:dashboard")

    if not (user.is_superuser or user_can_manage_school(user)):
        messages.error(request, "You do not have permission to view the payment ledger.")
        return redirect("accounts:dashboard")

    if school and (redir := require_feature(request, "fee_management", "accounts:dashboard")):
        return redir

    qs = PaymentTransaction.objects.all().select_related("school", "reviewed_by")
    if school and not user.is_superuser:
        qs = qs.filter(school=school)

    status_any = (request.GET.get("status_any") or "").strip()
    status = (request.GET.get("status") or "").strip()
    if status_any:
        parts = [p.strip() for p in status_any.split(",") if p.strip()]
        allowed = {"pending", "completed", "failed"}
        parts = [p for p in parts if p in allowed]
        if parts:
            qs = qs.filter(status__in=parts)
    elif status in ("pending", "completed", "failed"):
        qs = qs.filter(status=status)

    provider = (request.GET.get("provider") or "").strip()
    if provider:
        qs = qs.filter(provider__icontains=provider)

    reference = (request.GET.get("reference") or "").strip()
    if reference:
        qs = qs.filter(reference__icontains=reference)

    payment_type = (request.GET.get("payment_type") or "").strip()
    if payment_type:
        qs = qs.filter(payment_type__icontains=payment_type)

    review_status = (request.GET.get("review") or "").strip()
    if review_status in ("open", "reviewed"):
        qs = qs.filter(review_status=review_status)

    date_from = (request.GET.get("from") or "").strip()
    date_to = (request.GET.get("to") or "").strip()
    if date_from or date_to:
        try:
            from datetime import datetime, time

            from django.utils import timezone

            tz = timezone.get_current_timezone()
            if date_from:
                d0 = datetime.strptime(date_from, "%Y-%m-%d").date()
                start = timezone.make_aware(datetime.combine(d0, time.min), tz)
                qs = qs.filter(created_at__gte=start)
            if date_to:
                d1 = datetime.strptime(date_to, "%Y-%m-%d").date()
                end = timezone.make_aware(datetime.combine(d1, time.max), tz)
                qs = qs.filter(created_at__lte=end)
        except Exception:
            pass

    from django.db.models import Count as _Count
    from django.db.models import Sum as _Sum
    summary = {
        "total_count": qs.count(),
        "completed_count": qs.filter(status="completed").count(),
        "failed_count": qs.filter(status="failed").count(),
        "pending_count": qs.filter(status="pending").count(),
        "completed_amount": (qs.filter(status="completed").aggregate(v=_Sum("amount"))["v"] or Decimal("0")),
        "failed_amount": (qs.filter(status="failed").aggregate(v=_Sum("amount"))["v"] or Decimal("0")),
    }


    try:
        limit = int(request.GET.get("limit") or "")
    except Exception:
        limit = ""

    qs = qs.order_by("-created_at")
    page_obj = paginate(request, qs, per_page=50)

    return render(
        request,
        "finance/payment_ledger_list.html",
        {
            "is_queue": False,
            "page_obj": page_obj,
            "transactions": page_obj,
            "school": school,
            "filter_status": status,
            "filter_status_any": status_any,
            "filter_provider": provider,
            "filter_reference": reference,
            "filter_payment_type": payment_type,
            "filter_review": review_status,
            "filter_from": date_from,
            "filter_to": date_to,
            "filter_limit": limit,
            "summary": summary,
        },
    )


@login_required
def payment_ledger_queue(request):
    user = request.user
    school = getattr(user, "school", None)

    if not school and not user.is_superuser:
        messages.error(request, "You are not attached to any school.")
        return redirect("accounts:dashboard")

    if not (user.is_superuser or user_can_manage_school(user)):
        messages.error(request, "You do not have permission to view the payment ledger.")
        return redirect("accounts:dashboard")

    if school and (redir := require_feature(request, "fee_management", "accounts:dashboard")):
        return redir

    try:
        days = int(request.GET.get("days") or 30)
    except Exception:
        days = 30
    days = max(1, min(days, 365))

    since = timezone.now() - timezone.timedelta(days=days)
    date_from = since.date().strftime("%Y-%m-%d")
    date_to = timezone.now().date().strftime("%Y-%m-%d")

    from urllib.parse import urlencode

    qs = {
        "review": "open",
        "from": date_from,
        "to": date_to,
    }
    queue = (request.GET.get("queue") or "").strip().lower()
    if queue == "pending":
        qs["status"] = "pending"
    elif queue == "failed":
        qs["status"] = "failed"
    else:
        qs["status_any"] = "pending,failed"

    url = reverse("finance:payment_ledger_list") + "?" + urlencode(qs)
    return redirect(url)


@login_required
def payment_ledger_queue_page(request):
    user = request.user
    school = getattr(user, "school", None)

    if not school and not user.is_superuser:
        messages.error(request, "You are not attached to any school.")
        return redirect("accounts:dashboard")

    if not (user.is_superuser or user_can_manage_school(user)):
        messages.error(request, "You do not have permission to view the payment ledger.")
        return redirect("accounts:dashboard")

    if school and (redir := require_feature(request, "fee_management", "accounts:dashboard")):
        return redir

    try:
        days = int(request.GET.get("days") or 30)
    except Exception:
        days = 30
    days = max(1, min(days, 365))

    since = timezone.now() - timezone.timedelta(days=days)
    default_from = since.date().strftime("%Y-%m-%d")
    default_to = timezone.now().date().strftime("%Y-%m-%d")

    qs = PaymentTransaction.objects.all().select_related("school", "reviewed_by")
    if school and not user.is_superuser:
        qs = qs.filter(school=school)

    status_any = (request.GET.get("status_any") or "").strip() or "pending,failed"
    status = (request.GET.get("status") or "").strip()
    if status:
        if status in ("pending", "completed", "failed"):
            qs = qs.filter(status=status)
    else:
        parts = [p.strip() for p in status_any.split(",") if p.strip()]
        allowed = {"pending", "completed", "failed"}
        parts = [p for p in parts if p in allowed]
        if parts:
            qs = qs.filter(status__in=parts)

    review_status = (request.GET.get("review") or "").strip() or "open"
    if review_status in ("open", "reviewed"):
        qs = qs.filter(review_status=review_status)

    provider = (request.GET.get("provider") or "").strip()
    if provider:
        qs = qs.filter(provider__icontains=provider)

    reference = (request.GET.get("reference") or "").strip()
    if reference:
        qs = qs.filter(reference__icontains=reference)

    payment_type = (request.GET.get("payment_type") or "").strip()
    if payment_type:
        qs = qs.filter(payment_type__icontains=payment_type)

    date_from = (request.GET.get("from") or "").strip() or default_from
    date_to = (request.GET.get("to") or "").strip() or default_to
    if date_from or date_to:
        try:
            from datetime import datetime, time

            tz = timezone.get_current_timezone()
            if date_from:
                d0 = datetime.strptime(date_from, "%Y-%m-%d").date()
                start = timezone.make_aware(datetime.combine(d0, time.min), tz)
                qs = qs.filter(created_at__gte=start)
            if date_to:
                d1 = datetime.strptime(date_to, "%Y-%m-%d").date()
                end = timezone.make_aware(datetime.combine(d1, time.max), tz)
                qs = qs.filter(created_at__lte=end)
        except Exception:
            pass

    from django.db.models import Sum as _Sum
    summary = {
        "total_count": qs.count(),
        "completed_count": qs.filter(status="completed").count(),
        "failed_count": qs.filter(status="failed").count(),
        "pending_count": qs.filter(status="pending").count(),
        "completed_amount": (qs.filter(status="completed").aggregate(v=_Sum("amount"))["v"] or Decimal("0")),
        "failed_amount": (qs.filter(status="failed").aggregate(v=_Sum("amount"))["v"] or Decimal("0")),
    }

    try:
        limit = int(request.GET.get("limit") or "")
    except Exception:
        limit = ""

    qs = qs.order_by("-created_at")
    page_obj = paginate(request, qs, per_page=50)

    from django.db.models import Count as _Count

    queue_days = days
    queue_since = timezone.now() - timezone.timedelta(days=queue_days)
    queue_qs = PaymentTransaction.objects.all().select_related("school")
    if school and not user.is_superuser:
        queue_qs = queue_qs.filter(school=school)
    queue_qs = queue_qs.filter(review_status="open", status__in=["pending", "failed"], created_at__gte=queue_since)

    queue_summary = {
        "open_pending_count": queue_qs.filter(status="pending").count(),
        "open_pending_amount": (queue_qs.filter(status="pending").aggregate(v=_Sum("amount"))["v"] or Decimal("0")),
        "open_failed_count": queue_qs.filter(status="failed").count(),
        "open_failed_amount": (queue_qs.filter(status="failed").aggregate(v=_Sum("amount"))["v"] or Decimal("0")),
    }

    queue_by_provider = (
        queue_qs.values("provider", "status")
        .annotate(count=_Count("id"), amount=_Sum("amount"))
        .order_by("provider", "status")
    )

    return render(
        request,
        "finance/payment_ledger_list.html",
        {
            "is_queue": True,
            "queue_days": queue_days,
            "queue_summary": queue_summary,
            "queue_by_provider": queue_by_provider,
            "page_obj": page_obj,
            "transactions": page_obj,
            "school": school,
            "filter_status": status,
            "filter_status_any": status_any,
            "filter_provider": provider,
            "filter_reference": reference,
            "filter_payment_type": payment_type,
            "filter_review": review_status,
            "filter_from": date_from,
            "filter_to": date_to,
            "filter_limit": limit,
            "summary": summary,
        },
    )


@login_required
def payment_ledger_detail(request, pk):
    user = request.user
    school = getattr(user, "school", None)

    if not school and not user.is_superuser:
        messages.error(request, "You are not attached to any school.")
        return redirect("accounts:dashboard")

    if not (user.is_superuser or user_can_manage_school(user)):
        messages.error(request, "You do not have permission to view the payment ledger.")
        return redirect("accounts:dashboard")

    if school and (redir := require_feature(request, "fee_management", "accounts:dashboard")):
        return redir

    qs = PaymentTransaction.objects.select_related("school", "reviewed_by").filter(pk=pk)
    if school and not user.is_superuser:
        qs = qs.filter(school=school)
    tx = qs.first()
    if not tx:
        messages.error(request, "Ledger entry not found or you do not have permission.")
        nxt = safe_internal_redirect_path((request.POST.get("next") or "").strip())
        if nxt:
            return redirect(nxt)
        return redirect(_safe_referer(request, fallback=reverse("finance:payment_ledger_list")))

    return render(
        request,
        "finance/payment_ledger_detail.html",
        {"tx": tx, "school": school},
    )


@login_required
def payment_ledger_toggle_review(request, pk):
    if request.method != "POST":
        return redirect("finance:payment_ledger_detail", pk=pk)

    user = request.user
    school = getattr(user, "school", None)

    if not school and not user.is_superuser:
        messages.error(request, "You are not attached to any school.")
        return redirect("accounts:dashboard")

    if not (user.is_superuser or user_can_manage_school(user)):
        messages.error(request, "You do not have permission to update ledger review status.")
        return redirect("accounts:dashboard")

    if school and (redir := require_feature(request, "fee_management", "accounts:dashboard")):
        return redir

    qs = PaymentTransaction.objects.select_related("school").filter(pk=pk)
    if school and not user.is_superuser:
        qs = qs.filter(school=school)
    tx = qs.first()
    if not tx:
        messages.error(request, "Ledger entry not found or you do not have permission.")
        return redirect("finance:payment_ledger_list")

    from django.utils import timezone

    desired = (request.POST.get("review") or "").strip().lower()
    old = tx.review_status
    if desired == "reviewed":
        tx.review_status = "reviewed"
        tx.reviewed_at = timezone.now()
        tx.reviewed_by = user
        tx.save(update_fields=["review_status", "reviewed_at", "reviewed_by"])
        messages.success(request, "Ledger entry marked as reviewed.")
    elif desired == "open":
        tx.review_status = "open"
        tx.reviewed_at = None
        tx.reviewed_by = None
        tx.save(update_fields=["review_status", "reviewed_at", "reviewed_by"])
        messages.success(request, "Ledger entry marked as open.")
    else:
        messages.error(request, "Invalid review status.")

    if desired in ("reviewed", "open") and old != tx.review_status:
        write_audit(
            user=user,
            action="update",
            model_name="finance.PaymentTransaction",
            object_id=tx.pk,
            object_repr=f"PaymentTransaction {tx.reference}"[:255],
            changes={"review_status": {"old": old, "new": tx.review_status}},
            request=request,
            school=getattr(tx, "school", None),
        )

    return redirect("finance:payment_ledger_detail", pk=pk)


@login_required
def payment_ledger_bulk_review(request):
    if request.method != "POST":
        return redirect("finance:payment_ledger_list")

    user = request.user
    school = getattr(user, "school", None)

    post_next = safe_internal_redirect_path((request.POST.get("next") or "").strip())

    if not school and not user.is_superuser:
        messages.error(request, "You are not attached to any school.")
        return redirect("accounts:dashboard")

    if not (user.is_superuser or user_can_manage_school(user)):
        messages.error(request, "You do not have permission to update ledger review status.")
        return redirect("accounts:dashboard")

    if school and (redir := require_feature(request, "fee_management", "accounts:dashboard")):
        return redir

    desired = (request.POST.get("review") or "").strip().lower()
    scope = (request.POST.get("scope") or "selected").strip().lower()
    if desired not in ("reviewed", "open"):
        messages.error(request, "Invalid review status.")
        return redirect("finance:payment_ledger_list")

    if scope == "all" and (request.POST.get("confirm_all") or "") != "1":
        messages.error(request, "Confirmation required for bulk action on all filtered results.")
        if post_next:
            return redirect(post_next)
        else:
            return redirect(_safe_referer(request, fallback=reverse("finance:payment_ledger_list")))

    enforce_queue = (request.POST.get("enforce_queue") or "") == "1"

    MAX_BULK_ALL = 5000

    qs = PaymentTransaction.objects.all()
    if school and not user.is_superuser:
        qs = qs.filter(school=school)

    status_any = (request.GET.get("status_any") or "").strip()
    status = (request.GET.get("status") or "").strip()
    if status_any:
        parts = [p.strip() for p in status_any.split(",") if p.strip()]
        allowed = {"pending", "completed", "failed"}
        parts = [p for p in parts if p in allowed]
        if parts:
            qs = qs.filter(status__in=parts)
    elif status in ("pending", "completed", "failed"):
        qs = qs.filter(status=status)

    provider = (request.GET.get("provider") or "").strip()
    if provider:
        qs = qs.filter(provider__icontains=provider)

    reference = (request.GET.get("reference") or "").strip()
    if reference:
        qs = qs.filter(reference__icontains=reference)

    payment_type = (request.GET.get("payment_type") or "").strip()
    if payment_type:
        qs = qs.filter(payment_type__icontains=payment_type)

    review_status = (request.GET.get("review") or "").strip()
    if review_status in ("open", "reviewed"):
        qs = qs.filter(review_status=review_status)

    date_from = (request.GET.get("from") or "").strip()
    date_to = (request.GET.get("to") or "").strip()
    if date_from or date_to:
        try:
            from datetime import datetime, time

            from django.utils import timezone

            tz = timezone.get_current_timezone()
            if date_from:
                d0 = datetime.strptime(date_from, "%Y-%m-%d").date()
                start = timezone.make_aware(datetime.combine(d0, time.min), tz)
                qs = qs.filter(created_at__gte=start)
            if date_to:
                d1 = datetime.strptime(date_to, "%Y-%m-%d").date()
                end = timezone.make_aware(datetime.combine(d1, time.max), tz)
                qs = qs.filter(created_at__lte=end)
        except Exception:
            pass

    if scope == "all":
        target_qs = qs
    else:
        raw_ids = request.POST.getlist("ids")
        try:
            ids = [int(x) for x in raw_ids if str(x).strip()]
        except Exception:
            ids = []
        target_qs = qs.filter(id__in=ids)

    from django.utils import timezone

    if desired == "reviewed":
        updated = target_qs.update(review_status="reviewed", reviewed_at=timezone.now(), reviewed_by_id=user.id)
        messages.success(request, f"Marked {updated} ledger entries as reviewed.")
    else:
        updated = target_qs.update(review_status="open", reviewed_at=None, reviewed_by=None)
        messages.success(request, f"Marked {updated} ledger entries as open.")

    write_audit(
        user=user,
        action="update",
        model_name="finance.PaymentTransaction",
        object_id=None,
        object_repr="Bulk ledger review update",
        changes={
            "desired": desired,
            "scope": scope,
            "enforce_queue": enforce_queue,
            "updated": updated,
            "filters": {
                "status": status,
                "status_any": status_any,
                "provider": provider,
                "reference": reference,
                "payment_type": payment_type,
                "review": review_status,
                "from": date_from,
                "to": date_to,
            },
        },
        request=request,
        school=school,
    )

    if post_next:
        return redirect(post_next)
    return redirect(_safe_referer(request, fallback=reverse("finance:payment_ledger_list")))


@login_required
def payment_ledger_export_csv(request):
    user = request.user
    school = getattr(user, "school", None)

    if not school and not user.is_superuser:
        messages.error(request, "You are not attached to any school.")
        return redirect("accounts:dashboard")

    if not (user.is_superuser or user_can_manage_school(user)):
        messages.error(request, "You do not have permission to export the payment ledger.")
        return redirect("accounts:dashboard")

    if school and (redir := require_feature(request, "fee_management", "accounts:dashboard")):
        return redir

    qs = PaymentTransaction.objects.all().select_related("school", "reviewed_by")
    if school and not user.is_superuser:
        qs = qs.filter(school=school)

    status_any = (request.GET.get("status_any") or "").strip()
    status = (request.GET.get("status") or "").strip()
    if status_any:
        parts = [p.strip() for p in status_any.split(",") if p.strip()]
        allowed = {"pending", "completed", "failed"}
        parts = [p for p in parts if p in allowed]
        if parts:
            qs = qs.filter(status__in=parts)
    elif status in ("pending", "completed", "failed"):
        qs = qs.filter(status=status)

    provider = (request.GET.get("provider") or "").strip()
    if provider:
        qs = qs.filter(provider__icontains=provider)

    reference = (request.GET.get("reference") or "").strip()
    if reference:
        qs = qs.filter(reference__icontains=reference)

    payment_type = (request.GET.get("payment_type") or "").strip()
    if payment_type:
        qs = qs.filter(payment_type__icontains=payment_type)

    review_status = (request.GET.get("review") or "").strip()
    if review_status in ("open", "reviewed"):
        qs = qs.filter(review_status=review_status)

    date_from = (request.GET.get("from") or "").strip()
    date_to = (request.GET.get("to") or "").strip()
    if date_from or date_to:
        try:
            from datetime import datetime, time

            from django.utils import timezone

            tz = timezone.get_current_timezone()
            if date_from:
                d0 = datetime.strptime(date_from, "%Y-%m-%d").date()
                start = timezone.make_aware(datetime.combine(d0, time.min), tz)
                qs = qs.filter(created_at__gte=start)
            if date_to:
                d1 = datetime.strptime(date_to, "%Y-%m-%d").date()
                end = timezone.make_aware(datetime.combine(d1, time.max), tz)
                qs = qs.filter(created_at__lte=end)
        except Exception:
            pass

    # Hard cap to prevent expensive exports.
    try:
        limit = int(request.GET.get("limit") or 5000)
    except Exception:
        limit = 5000
    limit = max(1, min(limit, 20000))

    write_audit(
        user=user,
        action="export",
        model_name="finance.PaymentTransaction",
        object_id=None,
        object_repr="Payment ledger export",
        changes={
            "limit": limit,
            "filters": {
                "status": status,
                "status_any": status_any,
                "provider": provider,
                "reference": reference,
                "payment_type": payment_type,
                "review": review_status,
                "from": date_from,
                "to": date_to,
            },
        },
        request=request,
        school=school,
    )

    qs = qs.order_by("-created_at")[:limit]

    import csv

    from django.http import HttpResponse

    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Cache-Control"] = "no-store"
    resp["Content-Disposition"] = 'attachment; filename="payment_ledger.csv"'
    w = csv.writer(resp)
    w.writerow([
        "created_at",
        "updated_at",
        "school_id",
        "school_name",
        "provider",
        "status",
        "review_status",
        "reviewed_at",
        "reviewed_by",
        "payment_type",
        "amount",
        "currency",
        "reference",
        "object_id",
    ])
    for tx in qs:
        w.writerow([
            tx.created_at.isoformat() if tx.created_at else "",
            tx.updated_at.isoformat() if tx.updated_at else "",
            tx.school_id or "",
            getattr(tx.school, "name", "") if getattr(tx, "school_id", None) else "",
            tx.provider,
            tx.status,
            getattr(tx, "review_status", ""),
            tx.reviewed_at.isoformat() if getattr(tx, "reviewed_at", None) else "",
            getattr(getattr(tx, "reviewed_by", None), "username", "") if getattr(tx, "reviewed_by_id", None) else "",
            tx.payment_type,
            str(tx.amount),
            tx.currency,
            tx.reference,
            tx.object_id,
        ])
    return resp


@login_required
def payment_ledger_queue_export_csv(request):
    user = request.user
    school = getattr(user, "school", None)

    if not school and not user.is_superuser:
        messages.error(request, "You are not attached to any school.")
        return redirect("accounts:dashboard")

    if not (user.is_superuser or user_can_manage_school(user)):
        messages.error(request, "You do not have permission to export the payment ledger.")
        return redirect("accounts:dashboard")

    if school and (redir := require_feature(request, "fee_management", "accounts:dashboard")):
        return redir

    qs = PaymentTransaction.objects.all().select_related("school", "reviewed_by")
    if school and not user.is_superuser:
        qs = qs.filter(school=school)

    try:
        days = int(request.GET.get("days") or 30)
    except Exception:
        days = 30
    days = max(1, min(days, 365))

    since = timezone.now() - timezone.timedelta(days=days)
    default_from = since.date().strftime("%Y-%m-%d")
    default_to = timezone.now().date().strftime("%Y-%m-%d")

    provider = (request.GET.get("provider") or "").strip()
    if provider:
        qs = qs.filter(provider__icontains=provider)

    reference = (request.GET.get("reference") or "").strip()
    if reference:
        qs = qs.filter(reference__icontains=reference)

    payment_type = (request.GET.get("payment_type") or "").strip()
    if payment_type:
        qs = qs.filter(payment_type__icontains=payment_type)

    qs = qs.filter(review_status="open").filter(status__in=["pending", "failed"])

    date_from = (request.GET.get("from") or "").strip() or default_from
    date_to = (request.GET.get("to") or "").strip() or default_to
    if date_from or date_to:
        try:
            from datetime import datetime, time

            tz = timezone.get_current_timezone()
            if date_from:
                d0 = datetime.strptime(date_from, "%Y-%m-%d").date()
                start = timezone.make_aware(datetime.combine(d0, time.min), tz)
                qs = qs.filter(created_at__gte=start)
            if date_to:
                d1 = datetime.strptime(date_to, "%Y-%m-%d").date()
                end = timezone.make_aware(datetime.combine(d1, time.max), tz)
                qs = qs.filter(created_at__lte=end)
        except Exception:
            pass

    try:
        limit = int(request.GET.get("limit") or 5000)
    except Exception:
        limit = 5000
    limit = max(1, min(limit, 20000))

    write_audit(
        user=user,
        action="export",
        model_name="finance.PaymentTransaction",
        object_id=None,
        object_repr="Reconciliation queue export",
        changes={
            "limit": limit,
            "filters": {
                "provider": provider,
                "reference": reference,
                "payment_type": payment_type,
                "review": "open",
                "status_any": "pending,failed",
                "from": date_from,
                "to": date_to,
                "days": days,
            },
        },
        request=request,
        school=school,
    )

    qs = qs.order_by("-created_at")[:limit]

    import csv

    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Cache-Control"] = "no-store"
    resp["Content-Disposition"] = 'attachment; filename="reconciliation_queue.csv"'
    w = csv.writer(resp)
    w.writerow([
        "created_at",
        "school_id",
        "school_name",
        "provider",
        "status",
        "review_status",
        "payment_type",
        "amount",
        "currency",
        "reference",
        "reviewed_at",
        "reviewed_by",
    ])
    for tx in qs:
        w.writerow([
            tx.created_at.isoformat() if tx.created_at else "",
            tx.school_id or "",
            getattr(tx.school, "name", "") if getattr(tx, "school_id", None) else "",
            tx.provider,
            tx.status,
            getattr(tx, "review_status", ""),
            tx.payment_type,
            str(tx.amount),
            tx.currency,
            tx.reference,
            tx.reviewed_at.isoformat() if getattr(tx, "reviewed_at", None) else "",
            getattr(getattr(tx, "reviewed_by", None), "username", "") if getattr(tx, "reviewed_by_id", None) else "",
        ])
    return resp


@login_required
def payment_ledger_bulk_review_preview(request):
    user = request.user
    school = getattr(user, "school", None)

    if not school and not user.is_superuser:
        return JsonResponse({"ok": False, "error": "no_school"}, status=403)

    if not (user.is_superuser or user_can_manage_school(user)):
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)

    if school and not is_feature_enabled(request, "fee_management"):
        return JsonResponse({"ok": False, "error": "feature_disabled"}, status=403)

    qs = PaymentTransaction.objects.all()
    if school and not user.is_superuser:
        qs = qs.filter(school=school)

    status_any = (request.GET.get("status_any") or "").strip()
    status = (request.GET.get("status") or "").strip()
    if status_any:
        parts = [p.strip() for p in status_any.split(",") if p.strip()]
        allowed = {"pending", "completed", "failed"}
        parts = [p for p in parts if p in allowed]
        if parts:
            qs = qs.filter(status__in=parts)
    elif status in ("pending", "completed", "failed"):
        qs = qs.filter(status=status)

    provider = (request.GET.get("provider") or "").strip()
    if provider:
        qs = qs.filter(provider__icontains=provider)

    reference = (request.GET.get("reference") or "").strip()
    if reference:
        qs = qs.filter(reference__icontains=reference)

    payment_type = (request.GET.get("payment_type") or "").strip()
    if payment_type:
        qs = qs.filter(payment_type__icontains=payment_type)

    review_status = (request.GET.get("review") or "").strip()
    if review_status in ("open", "reviewed"):
        qs = qs.filter(review_status=review_status)

    enforce_queue = (request.GET.get("enforce_queue") or "") == "1"
    if enforce_queue:
        qs = qs.filter(review_status="open").filter(status__in=["pending", "failed"])

    date_from = (request.GET.get("from") or "").strip()
    date_to = (request.GET.get("to") or "").strip()
    if date_from or date_to:
        try:
            from datetime import datetime, time

            tz = timezone.get_current_timezone()
            if date_from:
                d0 = datetime.strptime(date_from, "%Y-%m-%d").date()
                start = timezone.make_aware(datetime.combine(d0, time.min), tz)
                qs = qs.filter(created_at__gte=start)
            if date_to:
                d1 = datetime.strptime(date_to, "%Y-%m-%d").date()
                end = timezone.make_aware(datetime.combine(d1, time.max), tz)
                qs = qs.filter(created_at__lte=end)
        except Exception:
            pass

    from django.db.models import Sum as _Sum

    total_count = qs.count()
    total_amount = qs.aggregate(v=_Sum("amount"))["v"] or Decimal("0")
    return JsonResponse({"ok": True, "count": total_count, "amount": str(total_amount)})


# ============ Subscription Cron Endpoint (for Railway/external cron services) ============

@require_POST
def run_subscription_check(request):
    """
    Endpoint for external cron services (like cron-job.org) to trigger subscription checks.
    Requires a secret key for security.
    
    Usage: POST /finance/run-subscription-check/  Header: X-Cron-Key: YOUR_SECRET_KEY
    """
    import os
    from django.conf import settings
    
    import hmac as _hmac
    
    provided_key = request.headers.get("X-Cron-Key", "") or request.POST.get("key", "")
    expected_key = getattr(settings, 'CRON_SECRET_KEY', os.environ.get('CRON_SECRET_KEY', ''))
    
    if not expected_key:
        return JsonResponse({"error": "CRON_SECRET_KEY not configured"}, status=500)
    if not provided_key or not _hmac.compare_digest(provided_key, expected_key):
        return JsonResponse({"error": "Unauthorized"}, status=401)
    
    try:
        # Import and run the subscription check
        from fees.services.subscription_reminder import run_subscription_checks
        result = run_subscription_checks()
        
        return JsonResponse({
            "status": "success",
            "message": "Subscription checks completed",
            "expired_count": result['expired'],
            "reminders_sent": len(result['reminders'])
        })
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)


# ---------------------------------------------------------------------------
#  Staff Payout Requests — maker-checker workflow views
# ---------------------------------------------------------------------------

@login_required
def payout_request_list(request):
    """List payout requests for the current school. Finance managers + leadership."""
    from accounts.permissions import can_manage_finance
    from finance.models import StaffPayoutRequest
    from finance.services.school_funds import get_balance
    from core.pagination import paginate

    if not can_manage_finance(request.user):
        messages.error(request, "You do not have permission to view payout requests.")
        return redirect("accounts:school_dashboard")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("accounts:dashboard")

    status_filter = request.GET.get("status", "").strip()
    qs = StaffPayoutRequest.objects.filter(school=school).select_related(
        "staff_user", "requested_by", "approved_by",
    )
    if status_filter:
        qs = qs.filter(status=status_filter)

    balance = get_balance(school.pk)
    page_obj = paginate(request, qs, per_page=50)
    return render(request, "finance/payout_request_list.html", {
        "requests": page_obj,
        "balance": balance,
        "status_filter": status_filter,
        "status_choices": StaffPayoutRequest.STATUS_CHOICES,
    })


@login_required
def payout_request_detail(request, pk):
    """View full details of a single payout request. Finance managers + leadership."""
    from accounts.permissions import can_manage_finance
    from finance.models import StaffPayoutRequest, SchoolFundsLedgerEntry

    if not can_manage_finance(request.user):
        messages.error(request, "You do not have permission to view payout requests.")
        return redirect("accounts:school_dashboard")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("accounts:dashboard")

    req = StaffPayoutRequest.objects.filter(pk=pk, school=school).select_related(
        "staff_user", "requested_by", "approved_by", "rejected_by", "cancelled_by",
    ).first()
    if not req:
        messages.error(request, "Payout request not found.")
        return redirect("finance:payout_request_list")

    ledger_entries = []
    if req.ledger_reference:
        ledger_entries = SchoolFundsLedgerEntry.objects.filter(
            school=school, reference=req.ledger_reference,
        ).order_by("created_at")

    return render(request, "finance/payout_request_detail.html", {
        "req": req,
        "ledger_entries": ledger_entries,
    })


@login_required
def payout_request_create(request):
    """Create a new payout request (maker). Finance managers only."""
    from accounts.permissions import can_manage_finance
    from finance.services.payout_requests import create_payout_request, PayoutError
    from finance.staff_payroll_paystack import recipient_snapshot_for_route

    if not can_manage_finance(request.user):
        messages.error(request, "You do not have permission to create payout requests.")
        return redirect("accounts:school_dashboard")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("accounts:dashboard")

    if request.method == "GET":
        from accounts.models import User
        from finance.services.school_funds import get_balance

        query = (request.GET.get("q") or "").strip()
        staff_qs = []
        staff_total = 0
        staff_page = None
        if query:
            base_qs = (
                User.objects.filter(school=school, role__in=[
                    "teacher", "accountant", "librarian", "admin_assistant",
                    "school_nurse", "admission_officer", "hod", "deputy_head",
                    "school_admin", "staff",
                ])
                .filter(
                    models.Q(first_name__icontains=query)
                    | models.Q(last_name__icontains=query)
                    | models.Q(username__icontains=query)
                    | models.Q(payroll_momo_number__icontains=query)
                    | models.Q(payroll_bank_account_number__icontains=query)
                )
                .order_by("first_name", "last_name")
            )
            staff_page = paginate(request, base_qs, per_page=25)
            staff_qs = list(staff_page.object_list)
            staff_total = staff_page.paginator.count
        balance = get_balance(school.pk)
        return render(request, "finance/payout_request_create.html", {
            "staff_list": staff_qs,
            "balance": balance,
            "query": query,
            "staff_total": staff_total,
            "staff_page": staff_page,
        })

    # POST
    from decimal import InvalidOperation
    staff_id_raw = request.POST.get("staff_user_id", "").strip()
    amount_raw = request.POST.get("amount", "").strip().replace(",", "")
    period_label = request.POST.get("period_label", "").strip()
    route = request.POST.get("route", "").strip()
    reason = request.POST.get("reason", "").strip()

    try:
        staff_id = int(staff_id_raw)
    except (ValueError, TypeError):
        messages.error(request, "Select a staff member.")
        return redirect("finance:payout_request_create")
    try:
        amount = Decimal(amount_raw).quantize(Decimal("0.01"))
        if amount <= 0:
            raise InvalidOperation
    except (InvalidOperation, TypeError):
        messages.error(request, "Enter a valid amount.")
        return redirect("finance:payout_request_create")

    from accounts.models import User
    staff = User.objects.filter(pk=staff_id, school=school).first()
    if not staff:
        messages.error(request, "Staff member not found for this school.")
        return redirect("finance:payout_request_create")
    snap = recipient_snapshot_for_route(staff, route)

    try:
        req = create_payout_request(
            school_id=school.pk,
            staff_user_id=staff_id,
            amount=amount,
            period_label=period_label,
            route=route,
            requested_by_id=request.user.pk,
            reason=reason,
            recipient_snapshot=snap,
        )
        messages.success(request, f"Payout request {req.reference} created — awaiting approval.")
    except PayoutError as e:
        messages.error(request, str(e))
        return redirect("finance:payout_request_create")

    return redirect("finance:payout_request_list")


@login_required
def payout_request_approve(request, pk):
    """Approve a payout request (checker). Leadership only. POST only."""
    if request.method != "POST":
        return redirect("finance:payout_request_list")
    if not (request.user.is_superuser or is_school_leadership(request.user)):
        messages.error(request, "Only school leadership can approve payout requests.")
        return redirect("finance:payout_request_list")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("accounts:dashboard")

    from finance.models import StaffPayoutRequest
    from finance.services.payout_requests import approve_payout_request, PayoutError

    req = StaffPayoutRequest.objects.filter(pk=pk, school=school).first()
    if not req:
        messages.error(request, "Payout request not found.")
        return redirect("finance:payout_request_list")

    try:
        approve_payout_request(request_id=req.pk, approved_by_id=request.user.pk)
        messages.success(request, f"Payout {req.reference} approved. Funds can now be reserved.")
    except PayoutError as e:
        messages.error(request, str(e))

    return redirect("finance:payout_request_list")


@login_required
def payout_request_reserve(request, pk):
    """Reserve funds for an approved payout request. Leadership only. POST only."""
    if request.method != "POST":
        return redirect("finance:payout_request_list")
    if not (request.user.is_superuser or is_school_leadership(request.user)):
        messages.error(request, "Only school leadership can reserve payout funds.")
        return redirect("finance:payout_request_list")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("accounts:dashboard")

    from finance.models import StaffPayoutRequest
    from finance.services.payout_requests import reserve_funds_for_payout, PayoutError

    req = StaffPayoutRequest.objects.filter(pk=pk, school=school).first()
    if not req:
        messages.error(request, "Payout request not found.")
        return redirect("finance:payout_request_list")

    try:
        reserve_funds_for_payout(request_id=req.pk)
        messages.success(request, f"Funds reserved for payout {req.reference}.")
    except PayoutError as e:
        messages.error(request, str(e))

    return redirect("finance:payout_request_list")


@login_required
def payout_request_reject(request, pk):
    """Reject a pending payout request. Leadership only. POST only."""
    if request.method != "POST":
        return redirect("finance:payout_request_list")
    if not (request.user.is_superuser or is_school_leadership(request.user)):
        messages.error(request, "Only school leadership can reject payout requests.")
        return redirect("finance:payout_request_list")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("accounts:dashboard")

    from finance.models import StaffPayoutRequest
    from finance.services.payout_requests import reject_payout_request, PayoutError

    reason = request.POST.get("reason", "").strip()
    req = StaffPayoutRequest.objects.filter(pk=pk, school=school).first()
    if not req:
        messages.error(request, "Payout request not found.")
        return redirect("finance:payout_request_list")

    try:
        reject_payout_request(request_id=req.pk, rejected_by_id=request.user.pk, reason=reason)
        messages.success(request, f"Payout {req.reference} rejected.")
    except PayoutError as e:
        messages.error(request, str(e))

    return redirect("finance:payout_request_list")


@login_required
def payout_request_cancel(request, pk):
    """Cancel a payout request and release reserved funds. Finance managers. POST only."""
    if request.method != "POST":
        return redirect("finance:payout_request_list")
    from accounts.permissions import can_manage_finance
    if not can_manage_finance(request.user):
        messages.error(request, "You do not have permission to cancel payout requests.")
        return redirect("finance:payout_request_list")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("accounts:dashboard")

    from finance.models import StaffPayoutRequest
    from finance.services.payout_requests import cancel_payout_request, PayoutError

    reason = request.POST.get("reason", "").strip()
    req = StaffPayoutRequest.objects.filter(pk=pk, school=school).first()
    if not req:
        messages.error(request, "Payout request not found.")
        return redirect("finance:payout_request_list")

    try:
        cancel_payout_request(request_id=req.pk, cancelled_by_id=request.user.pk, reason=reason)
        messages.success(request, f"Payout {req.reference} cancelled.")
    except PayoutError as e:
        messages.error(request, str(e))

    return redirect("finance:payout_request_list")


# ============================================================
# UX-1 — Fixed Asset Register
# ============================================================

@login_required
def fixed_asset_list(request):
    school = getattr(request.user, "school", None)
    if not school and not request.user.is_superuser:
        return redirect("accounts:dashboard")
    if not can_manage_finance(request.user):
        messages.error(request, "Finance access required.")
        return redirect("accounts:dashboard")
    if school:
        redir = require_feature(request, "finance_admin", "accounts:dashboard")
        if redir:
            return redir
    from finance.models import FixedAsset
    assets = FixedAsset.objects.filter(school=school).order_by("category", "name")
    category_filter = request.GET.get("category", "")
    active_filter = request.GET.get("active", "1")
    if category_filter:
        assets = assets.filter(category=category_filter)
    if active_filter == "1":
        assets = assets.filter(is_active=True)
    elif active_filter == "0":
        assets = assets.filter(is_active=False)
    categories = FixedAsset.ASSET_CATEGORIES
    return render(request, "finance/fixed_asset_list.html", {
        "assets": assets,
        "school": school,
        "categories": categories,
        "category_filter": category_filter,
        "active_filter": active_filter,
    })


@login_required
def fixed_asset_create(request):
    school = getattr(request.user, "school", None)
    if not school or not can_manage_finance(request.user):
        return redirect("accounts:dashboard")
    redir = require_feature(request, "finance_admin", "accounts:dashboard")
    if redir:
        return redir
    from finance.models import FixedAsset, PurchaseOrder
    error = None
    if request.method == "POST":
        try:
            po_id = request.POST.get("linked_purchase_order") or None
            po = PurchaseOrder.objects.filter(pk=po_id, school=school).first() if po_id else None
            asset = FixedAsset(
                school=school,
                name=request.POST["name"],
                category=request.POST.get("category", "other"),
                description=request.POST.get("description", ""),
                purchase_date=request.POST["purchase_date"],
                purchase_cost=Decimal(request.POST["purchase_cost"]),
                useful_life_years=int(request.POST.get("useful_life_years", 5)),
                salvage_value=Decimal(request.POST.get("salvage_value", "0")),
                condition=request.POST.get("condition", "good"),
                location=request.POST.get("location", ""),
                serial_number=request.POST.get("serial_number", ""),
                supplier=request.POST.get("supplier", ""),
                currency=request.POST.get("currency", school.currency if hasattr(school, "currency") else "GHS"),
                linked_purchase_order=po,
            )
            asset.full_clean()
            asset.save()
            messages.success(request, f"Asset '{asset.name}' [{asset.asset_tag}] created.")
            return redirect("finance:fixed_asset_list")
        except Exception as e:
            error = str(e)
    return render(request, "finance/fixed_asset_form.html", {
        "school": school,
        "action": "Create",
        "error": error,
        "categories": FixedAsset.ASSET_CATEGORIES,
        "conditions": FixedAsset.CONDITION_CHOICES,
    })


@login_required
def fixed_asset_detail(request, pk):
    school = getattr(request.user, "school", None)
    if not school or not can_manage_finance(request.user):
        return redirect("accounts:dashboard")
    redir = require_feature(request, "finance_admin", "accounts:dashboard")
    if redir:
        return redir
    from finance.models import FixedAsset
    asset = get_object_or_404(FixedAsset, pk=pk, school=school)
    return render(request, "finance/fixed_asset_detail.html", {"asset": asset, "school": school})


@login_required
def fixed_asset_edit(request, pk):
    school = getattr(request.user, "school", None)
    if not school or not can_manage_finance(request.user):
        return redirect("accounts:dashboard")
    redir = require_feature(request, "finance_admin", "accounts:dashboard")
    if redir:
        return redir
    from finance.models import FixedAsset
    asset = get_object_or_404(FixedAsset, pk=pk, school=school)
    error = None
    if request.method == "POST":
        try:
            asset.name = request.POST.get("name", asset.name)
            asset.category = request.POST.get("category", asset.category)
            asset.description = request.POST.get("description", asset.description)
            asset.location = request.POST.get("location", asset.location)
            asset.serial_number = request.POST.get("serial_number", asset.serial_number)
            asset.supplier = request.POST.get("supplier", asset.supplier)
            asset.condition = request.POST.get("condition", asset.condition)
            asset.currency = request.POST.get("currency", asset.currency)
            asset.full_clean()
            asset.save()
            messages.success(request, f"Asset '{asset.name}' updated.")
            return redirect("finance:fixed_asset_detail", pk=asset.pk)
        except Exception as e:
            error = str(e)
    return render(request, "finance/fixed_asset_form.html", {
        "school": school,
        "asset": asset,
        "action": "Edit",
        "error": error,
        "categories": FixedAsset.ASSET_CATEGORIES,
        "conditions": FixedAsset.CONDITION_CHOICES,
    })


@login_required
def fixed_asset_dispose(request, pk):
    school = getattr(request.user, "school", None)
    if not school or not can_manage_finance(request.user):
        return redirect("accounts:dashboard")
    redir = require_feature(request, "finance_admin", "accounts:dashboard")
    if redir:
        return redir
    from finance.models import FixedAsset
    asset = get_object_or_404(FixedAsset, pk=pk, school=school)
    if request.method == "POST":
        asset.is_active = False
        asset.disposal_date = timezone.now().date()
        asset.disposal_notes = request.POST.get("notes", "")
        asset.condition = "written_off"
        asset.save(update_fields=["is_active", "disposal_date", "disposal_notes", "condition", "updated_at"])
        messages.success(request, f"Asset '{asset.name}' disposed.")
        return redirect("finance:fixed_asset_list")
    return render(request, "finance/fixed_asset_dispose.html", {"asset": asset, "school": school})


# ============================================================
# UX-2 — Approval Workflow Inbox
# ============================================================

@login_required
def approval_inbox(request):
    """Show pending WorkflowInstance rows where current step role matches the user's role."""
    school = getattr(request.user, "school", None)
    if not school and not request.user.is_superuser:
        return redirect("accounts:dashboard")
    from finance.models import WorkflowInstance
    user_role = getattr(request.user, "role", None)
    qs = WorkflowInstance.objects.filter(school=school, status__in=["pending", "in_progress"]).select_related("workflow")
    pending_for_me = []
    for inst in qs:
        steps = inst.workflow.steps or []
        step_def = next((s for s in steps if s.get("step") == inst.current_step), None)
        if step_def and (step_def.get("role") == user_role or request.user.is_superuser):
            pending_for_me.append(inst)
    return render(request, "finance/approval_inbox.html", {
        "instances": pending_for_me,
        "school": school,
    })


@login_required
def approval_advance(request, pk):
    """Approve or reject a WorkflowInstance step."""
    school = getattr(request.user, "school", None)
    if not school and not request.user.is_superuser:
        return redirect("accounts:dashboard")
    from finance.models import WorkflowInstance
    inst = get_object_or_404(WorkflowInstance, pk=pk, school=school)
    if request.method == "POST":
        action = request.POST.get("action")
        note = request.POST.get("note", "").strip()
        if action not in ("approved", "rejected"):
            messages.error(request, "Invalid action.")
            return redirect("finance:approval_inbox")
        try:
            approved = inst.advance(actor=request.user, action=action, note=note)
            if approved:
                messages.success(request, f"Workflow #{inst.pk} fully approved.")
            elif action == "rejected":
                messages.warning(request, f"Workflow #{inst.pk} rejected at step {inst.current_step}.")
            else:
                messages.info(request, f"Step advanced. Workflow #{inst.pk} now at step {inst.current_step}.")
        except PermissionError as e:
            messages.error(request, str(e))
    return redirect("finance:approval_inbox")
