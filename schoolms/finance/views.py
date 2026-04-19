import uuid
import json
import requests
from datetime import timedelta
from decimal import Decimal
from django.conf import settings
from django.db import models, transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.utils import timezone

from urllib.parse import urlparse
from django.contrib.auth.decorators import login_required
from accounts.permissions import can_export_data, is_school_leadership, user_can_manage_school


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
from core.pagination import paginate
from core.utils import FEE_PAYSTACK_RETURN_SESSION_KEY, safe_internal_redirect_path
from audit.services import write_audit
import logging
logger = logging.getLogger(__name__)


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
    is_own = bool(
        fee.student_id
        and (
            fee.student.parent_id == user.pk
            or fee.student.user_id == user.pk
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
    if fee.school and fee.school.paystack_subaccount_code:
        school_subaccount = fee.school.paystack_subaccount_code
    
    pending_payment = FeePayment.objects.create(
        fee=fee,
        amount=amount_net,
        gross_amount=amount_gross,
        paystack_reference=reference,
        status='pending'
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
            
            # Create a unique reference
            reference = f"SCHOOL_FEE_{fee_id}_{uuid.uuid4().hex[:8].upper()}"
            
            # Get school's subaccount if configured
            school_subaccount = None
            if fee.school and fee.school.paystack_subaccount_code:
                school_subaccount = fee.school.paystack_subaccount_code
            
            # Create pending payment record for tracking
            from .models import FeePayment
            pending_payment = FeePayment.objects.create(
                fee=fee,
                amount=amount_net,
                gross_amount=amount_gross,
                paystack_reference=reference,
                status='pending'
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
                record_payment_transaction(
                    reference=reference,
                    school_id=fee.school_id,
                    amount=net_credited,
                    status="failed",
                    payment_type="school_fee",
                    object_id=str(fee_id),
                    metadata={"fee_id": fee_id},
                )
                messages.error(request, "Payment verification failed.")

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
        fail = data.get("failures")
        reason = ""
        if isinstance(fail, list) and fail:
            first = fail[0]
            if isinstance(first, dict):
                reason = first.get("reason") or first.get("message") or ""
        if not reason:
            reason = data.get("message") or str(data)
        pay.paystack_failure_reason = str(reason)[:2000]
        pay.save(update_fields=["paystack_status", "paystack_failure_reason"])
        logger.warning("Staff payroll transfer failed: ref=%s payment_id=%s", ref, pay.pk)
    elif event == "transfer.reversed":
        pay.paystack_status = "failed"
        pay.paystack_failure_reason = "Transfer reversed."
        pay.save(update_fields=["paystack_status", "paystack_failure_reason"])
        logger.warning("Staff payroll transfer reversed: ref=%s payment_id=%s", ref, pay.pk)


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
    
    if event == "charge.success":
        data = payload.get("data", {})
        reference = data.get("reference")
        
        if reference:
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
                        from django.utils import timezone
                        with transaction.atomic():
                            payment = CanteenPayment.objects.select_for_update().get(id=payment_id)
                            if payment.payment_status != 'completed':
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
                        from django.utils import timezone

                        with transaction.atomic():
                            payment = BusPayment.objects.select_for_update().get(id=payment_id)
                            if payment.payment_status != 'completed':
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
                            if sale.payment_status != 'completed':
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
            
            # Handle Hostel Payments
            elif payment_type == "hostel":
                payment_id = metadata.get("payment_id")
                if payment_id:
                    try:
                        from operations.models import HostelFee
                        from django.utils import timezone

                        with transaction.atomic():
                            fee = HostelFee.objects.select_for_update().get(id=payment_id)
                            if fee.payment_status != 'completed' and not fee.paid:
                                mark_hostel_fee_completed(fee=fee, reference=reference)
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

    # Handle actions
    if request.method == "POST":
        fee_id = request.POST.get("fee_id")
        action = request.POST.get("action")
        
        if fee_id and action:
            qs = Fee.objects.all()
            if not user.is_superuser and school:
                qs = qs.filter(school=school)
            
            fee = qs.filter(id=fee_id).first()
            if fee:
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
                    messages.success(request, "Fee marked as fully paid.")
                elif action == "mark_partially_paid":
                    partial_amount = request.POST.get("partial_amount")
                    if partial_amount:
                        try:
                            amount = Decimal(str(partial_amount))
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
                            messages.success(request, f"Added GHS {amount} to payment.")
                        except (ValueError, TypeError):
                            messages.error(request, "Invalid amount.")
                elif action == "record_offline":
                    offline_amount = request.POST.get("offline_amount", str(fee.remaining_balance))
                    try:
                        amount = Decimal(str(offline_amount))
                        # Payment row first, then F() update so Fee post_save does not double-notify.
                        fp = FeePayment.objects.create(
                            fee=fee,
                            amount=amount,
                            payment_method="offline",
                            status="completed",
                        )
                        try:
                            record_payment_transaction(
                                provider="offline",
                                reference=f"OFFLINE_FEE_{fee.pk}_{fp.pk}",
                                school_id=getattr(fee, "school_id", None),
                                amount=amount,
                                status="completed",
                                payment_type=PaymentTypes.SCHOOL_FEE_OFFLINE,
                                object_id=str(fee.pk),
                                metadata={"fee_id": fee.pk, "fee_payment_id": fp.pk},
                            )
                        except Exception:
                            pass
                        Fee.objects.filter(pk=fee.pk).update(
                            amount_paid=models.F("amount_paid") + amount
                        )
                        fee.refresh_from_db()
                        fee.save()
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
    
    fees = fees_qs.order_by("student__school__name", "student__class_name", "student__admission_number")
    page_obj = paginate(request, fees, per_page=30)

    ctx = {"fees": page_obj, "school": school, "page_obj": page_obj}
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
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        try:
            amount = Decimal(str(request.POST.get("amount", 0)))
            class_name = request.POST.get("class_name", "").strip()
            term = request.POST.get("term", "").strip()
            if name and amount >= 0:
                FeeStructure.objects.create(
                    school=school, name=name, amount=amount,
                    class_name=class_name, term=term
                )
                messages.success(request, "Fee structure added.")
                return redirect("finance:fee_structure_list")
        except (ValueError, TypeError):
            pass
    return render(request, "finance/fee_structure_form.html", {"school": school})


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
    
    structure = get_object_or_404(FeeStructure, pk=pk, school=school)
    
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        try:
            amount = Decimal(str(request.POST.get("amount", 0)))
            class_name = request.POST.get("class_name", "").strip()
            term = request.POST.get("term", "").strip()
            is_active = request.POST.get("is_active") == "on"
            
            if name and amount >= 0:
                structure.name = name
                structure.amount = amount
                structure.class_name = class_name
                structure.term = term
                structure.is_active = is_active
                structure.save()
                messages.success(request, "Fee structure updated.")
                return redirect("finance:fee_structure_list")
        except (ValueError, TypeError):
            messages.error(request, "Invalid amount.")
    
    return render(request, "finance/fee_structure_form.html", {"school": school, "structure": structure})


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
    
    structure = get_object_or_404(FeeStructure, pk=pk, school=school)
    
    if request.method == "POST":
        structure.delete()
        messages.success(request, "Fee structure deleted.")
        return redirect("finance:fee_structure_list")
    
    return render(request, "finance/confirm_delete.html", {
        "object": structure,
        "type": "fee structure",
        "cancel_url": "finance:fee_structure_list"
    })


@login_required
def generate_fees_from_structure(request, pk):
    """Generate individual Fee records for all students in a class based on FeeStructure."""
    school = getattr(request.user, "school", None)
    if not school and not request.user.is_superuser:
        return redirect("accounts:dashboard")
    if not school:
        messages.error(request, "School admins only.")
        return redirect("accounts:dashboard")
    if not (request.user.is_superuser or is_school_leadership(request.user)):
        return redirect("accounts:school_dashboard")
    
    from students.models import Student
    
    structure = get_object_or_404(FeeStructure, pk=pk, school=school)
    
    # Get students for this class (or all if no class specified)
    if structure.class_name:
        students = Student.objects.filter(school=school, class_name=structure.class_name, status="active")
    else:
        students = Student.objects.filter(school=school, status="active")
    
    created_count = 0
    skipped_count = 0
    
    for student in students:
        existing = Fee.objects.filter(
            school=school, student=student, amount=structure.amount
        ).exists()
        
        if not existing:
            Fee.objects.create(
                school=school,
                student=student,
                amount=structure.amount
            )
            created_count += 1
        else:
            skipped_count += 1
    
    messages.success(request, f"Generated fees for {created_count} students. {skipped_count} skipped (already have matching fees).")
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
            "type": "subscription",
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

    from students.models import Student

    students = Student.objects.filter(parent=user).order_by("class_name", "admission_number")

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


def payment_success(request):
    """Show payment success page after successful payment."""
    return render(request, "finance/payment_success.html")


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

    is_parent_of = fee.student and (
        fee.student.parent_id == user.id or (fee.student.user and fee.student.user_id == user.id)
    )
    user_school = getattr(user, "school", None)
    is_school_staff = (user.is_superuser or user_can_manage_school(user)) and (
        user.is_superuser or (user_school and school and school.pk == user_school.pk)
    )
    if not (is_school_staff or is_parent_of):
        messages.error(request, "You do not have permission to view this receipt.")
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
            # Search in FeePayment by paystack_reference
            payment = FeePayment.objects.filter(
                paystack_reference=reference
            ).select_related("fee", "fee__student", "fee__school").first()
            
            if not payment:
                # Also check Fee model directly for the reference
                from .models import Fee
                fee_with_ref = Fee.objects.filter(
                    paystack_reference=reference
                ).select_related("student", "school").first()
                
                if fee_with_ref and fee_with_ref.amount_paid > 0:
                    # Create a virtual payment object for display
                    class VirtualPayment:
                        def __init__(self, fee):
                            self.amount = fee.amount_paid
                            self.paystack_reference = fee.paystack_reference
                            self.status = "completed"
                            self.created_at = fee.updated_at
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
    
    # Search by student name or payment reference
    search = request.GET.get("search")
    if search:
        payments_qs = payments_qs.filter(
            models.Q(fee__student__first_name__icontains=search) |
            models.Q(fee__student__last_name__icontains=search) |
            models.Q(fee__student__admission_number__icontains=search) |
            models.Q(paystack_reference__icontains=search)
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

    pay_qs = FeePayment.objects.select_related("fee", "fee__school").filter(pk=pk)
    if school and not user.is_superuser:
        pay_qs = pay_qs.filter(fee__school=school)
    payment = pay_qs.first()
    if not payment:
        messages.error(request, "Payment not found or you do not have permission.")
        return redirect("finance:payment_history_list")

    # Only allow deleting pending or failed payments
    if payment.status == "completed":
        messages.error(request, "Cannot delete completed payments. Contact system administrator.")
        return redirect("finance:payment_history_list")
    
    if request.method == "POST":
        payment.delete()
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

    if request.method == "POST":
        payment_ids = request.POST.getlist("payment_ids")
        
        if not payment_ids:
            messages.error(request, "No payments selected.")
            return redirect("finance:payment_history_list")
        
        # Filter payments to only include pending or failed
        payments_qs = FeePayment.objects.filter(pk__in=payment_ids)
        
        if not user.is_superuser and school:
            payments_qs = payments_qs.filter(fee__school=school)
        
        # Separate deletable from non-deletable
        deletable = payments_qs.filter(status__in=["pending", "failed"])
        non_deletable = payments_qs.filter(status="completed").count()
        
        if non_deletable > 0:
            messages.warning(request, f"Skipped {non_deletable} completed payments (cannot be deleted).")
        
        deleted_count = deletable.count()
        deletable.delete()
        
        messages.success(request, f"Successfully deleted {deleted_count} payment record(s).")
    
    return redirect("finance:payment_history_list")


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

def run_subscription_check(request):
    """
    Endpoint for external cron services (like cron-job.org) to trigger subscription checks.
    Requires a secret key for security.
    
    Usage: GET /finance/run-subscription-check/?key=YOUR_SECRET_KEY
    """
    import os
    from django.conf import settings
    
    import hmac as _hmac
    
    provided_key = request.GET.get("key", "") or request.headers.get("X-Cron-Key", "")
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
