"""
Payment Views for Canteen, Bus, Textbooks, and Hostel with Paystack Integration
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from django.db.models import F
from django.contrib import messages
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from datetime import date, datetime, time, timedelta

from django.utils import timezone
from django.utils.dateparse import parse_date
from django.conf import settings
import uuid
from decimal import Decimal, InvalidOperation

from accounts.decorators import login_required, parent_required, student_required
from accounts.permissions import (
    can_manage_finance,
    is_school_leadership,
    is_super_admin,
    user_can_manage_school,
)
from core.pagination import paginate
from core.academic_context import get_current_term_for_school
from schools.features import is_feature_enabled_for_school, require_feature

from students.models import Student
from students.utils import parent_is_guardian_of
from schools.models import School
from schools.features import is_feature_enabled_for_school
from .models import CanteenItem, CanteenPayment, BusRoute, BusPayment, Textbook, TextbookSale, HostelFee
from finance.paystack_service import paystack_service
from finance.models import Fee, FeePayment
from core.utils import FEE_PAYSTACK_RETURN_SESSION_KEY, safe_internal_redirect_path
from operations.services.portal_payments import (
    mark_bus_payment_completed,
    mark_bus_payment_failed,
    mark_canteen_payment_completed,
    mark_canteen_payment_failed,
    mark_hostel_fee_completed,
    mark_hostel_fee_failed,
    mark_textbook_sale_completed,
    mark_textbook_sale_failed,
)
from payments.services.ledger import record_payment_transaction, PaymentTypes


def _payment_history_sort_dt(val):
    """Coerce mixed date/datetime fields to an aware datetime for stable sorting."""
    if val is None:
        return timezone.now()
    if isinstance(val, datetime):
        return val if timezone.is_aware(val) else timezone.make_aware(val)
    if isinstance(val, date):
        return timezone.make_aware(datetime.combine(val, time.min))
    return timezone.now()

import logging
logger = logging.getLogger(__name__)


def _payment_datetime(value):
    """Coerce date/dateTime values to timezone-aware datetimes for sorting."""
    if value is None:
        return timezone.now()
    if isinstance(value, datetime):
        return value if timezone.is_aware(value) else timezone.make_aware(value, timezone.get_current_timezone())
    if isinstance(value, date):
        naive_dt = datetime.combine(value, time.min)
        return timezone.make_aware(naive_dt, timezone.get_current_timezone())
    return timezone.now()


def _get_paystack_public_key(request):
    """Get Paystack public key from settings."""
    return getattr(settings, 'PAYSTACK_PUBLIC_KEY', '')


def _get_user_student(request):
    """Get the student object for the current user."""
    if request.user.role == 'student':
        return request.user.student
    elif request.user.role == 'parent':
        # For parents, get the first child
        children = request.user.children.all()
        return children.first() if children.exists() else None
    return None


def _get_school(request):
    """Get the school for the current user, falling back to student's school."""
    from core.utils import get_school
    school = get_school(request)
    if school:
        return school
    student = _get_user_student(request)
    return student.school if student else None


def _get_parent_email(student, request):
    """Get parent's email for a student."""
    if student.parent and student.parent.email:
        return student.parent.email
    return None


def _portal_children(user):
    """Students linked to a parent user via legacy FK or StudentGuardian (stable ordering)."""
    from students.utils import get_children_for_parent
    return list(get_children_for_parent(user))


def student_for_portal(request):
    """
    Active student on canteen/bus/textbook/my_payments portals.
    Parent may choose via ?student=<pk>; invalid id falls back to first child.
    """
    role = getattr(request.user, "role", None)
    if role == "student":
        return getattr(request.user, "student", None)
    if role == "parent":
        children = _portal_children(request.user)
        if not children:
            return None
        raw = request.GET.get("student")
        if raw:
            try:
                sid = int(raw)
            except (TypeError, ValueError):
                sid = None
            if sid is not None:
                for c in children:
                    if c.id == sid:
                        return c
        return children[0]
    return None


def authorized_student_for_payment_post(request):
    """
    Student record for POST initiate endpoints (canteen, bus, textbook).
    Parent may pass student_id for the child; student role ignores mismatching student_id.
    Returns (student, None) or (None, JsonResponse).
    """
    role = getattr(request.user, "role", None)
    raw_sid = request.POST.get("student_id")
    want_id = None
    if raw_sid not in (None, ""):
        try:
            want_id = int(raw_sid)
        except (TypeError, ValueError):
            return None, JsonResponse({"success": False, "error": "Invalid student_id"}, status=400)

    if role == "student":
        st = getattr(request.user, "student", None)
        if not st:
            return None, JsonResponse({"success": False, "error": "Student not found"}, status=400)
        if want_id is not None and want_id != st.id:
            return None, JsonResponse({"success": False, "error": "Forbidden"}, status=403)
        return st, None

    if role == "parent":
        qs = request.user.children.select_related("user", "school")
        if want_id is not None:
            st = qs.filter(id=want_id).first()
        else:
            st = qs.first()
        if not st:
            return None, JsonResponse({"success": False, "error": "Student not found"}, status=400)
        return st, None

    return None, JsonResponse({"success": False, "error": "Forbidden"}, status=403)


def user_can_access_student_payment(user, student):
    """Student, parent of student, or school staff for the student's school."""
    if user.is_superuser:
        return True
    if student is None:
        return False
    role = getattr(user, "role", None)
    if role == "student" and student.user_id == user.id:
        return True
    if role == "parent" and parent_is_guardian_of(user, student):
        return True
    school = getattr(user, "school", None)
    if school and student.school_id == school.id:
        if user_can_manage_school(user):
            return True
    return False


def _deny_unowned_payment_verify(request):
    messages.error(request, "You do not have permission to verify this payment.")
    return redirect("home")


def _reference_matches_payment(reference, payment) -> bool:
    """
    Bug fix F4-14: prevent reference-forgery attacks against verify endpoints.

    The initiate views store ``payment.payment_reference`` at the moment we
    talk to Paystack. The verify endpoints then accept a ``reference`` query
    param so the browser-return URL can be linked back to the row. Without
    binding, an attacker can pass *any* successful Paystack reference (e.g.
    from a different student's transaction) and have it credited to a row
    they own.

    This helper enforces that the URL-supplied reference must equal the
    canonical reference we stored on the row.  Empty/blank values are
    treated as "no reference supplied" and the caller is expected to fall
    back to the stored reference.
    """
    if payment is None:
        return False
    stored = (getattr(payment, "payment_reference", None) or "").strip()
    incoming = (reference or "").strip()
    if not incoming:
        # caller will fall back to stored reference; nothing to validate yet
        return True
    if not stored:
        # row was never initiated against Paystack; refuse marking completed
        return False
    return incoming == stored


# ==================== CANTEEN PAYMENTS ====================

@student_required
def canteen_my(request):
    """Student view to browse and purchase canteen items."""
    student = student_for_portal(request)
    if not student:
        messages.error(request, "No student profile is linked to this account.")
        return redirect("home")

    school = student.school
    if not is_feature_enabled_for_school(school.pk, "canteen"):
        messages.info(request, "Canteen is not enabled for your school.")
        return redirect("accounts:dashboard")

    # Get available canteen items
    items = CanteenItem.objects.filter(school=school, is_available=True)

    # Get student's payment history (only completed payments)
    my_payments_qs = CanteenPayment.objects.filter(
        student=student,
        payment_status='completed'
    ).order_by('-payment_date', '-id')
    my_payments = paginate(request, my_payments_qs, per_page=25, page_param="canteen_hist")

    # Get pending payments
    pending_qs = CanteenPayment.objects.filter(
        student=student,
        payment_status='pending'
    ).order_by('-payment_date', '-id')
    pending_payments = paginate(request, pending_qs, per_page=25, page_param="canteen_pending")

    from django.conf import settings
    portal_children = _portal_children(request.user)
    context = {
        'items': items,
        'my_payments': my_payments,
        'pending_payments': pending_payments,
        'page_obj': my_payments,
        'page_title': 'Canteen',
        'paystack_public_key': getattr(settings, 'PAYSTACK_PUBLIC_KEY', ''),
        'portal_children': portal_children,
        'portal_student': student,
    }
    return render(request, 'operations/canteen_my.html', context)


@login_required
@require_POST
def canteen_initiate_payment(request):
    """Initiate Paystack payment for canteen items."""
    student, err = authorized_student_for_payment_post(request)
    if err:
        return err

    if not is_feature_enabled_for_school(student.school_id, "canteen"):
        return JsonResponse({"success": False, "error": "Canteen is not enabled for your school."}, status=403)

    item_id = request.POST.get('item_id')
    try:
        quantity = int(request.POST.get('quantity', 1))
    except (TypeError, ValueError):
        quantity = 1
    if quantity <= 0:
        quantity = 1
    payment_method = request.POST.get('payment_method', 'card')
    
    try:
        item = CanteenItem.objects.get(id=item_id, school=student.school, is_available=True)
    except CanteenItem.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Item not found'}, status=404)
    
    total_amount = (Decimal(str(item.price)) * Decimal(quantity)).quantize(Decimal("0.01"))

    # Generate unique reference
    reference = f"CANTEEN_{uuid.uuid4().hex[:12].upper()}"

    # Create pending payment record (atomic so reference can't be lost under concurrency)
    with transaction.atomic():
        payment = CanteenPayment.objects.create(
            school=student.school,
            student=student,
            amount=total_amount,
            description=f"{item.name} x{quantity}",
            payment_reference=reference,
            payment_status='pending'
        )
    
    # Get parent email for payment using helper function
    parent_email = _get_parent_email(student, request)
    
    if not parent_email and request.user.email:
        parent_email = request.user.email
    
    # Build callback URL with payment_id for reliable lookup
    callback_url = request.build_absolute_uri(
        reverse('operations:canteen_payment_verify') + f"?payment_id={payment.id}"
    )
    
    # Initialize Paystack payment
    metadata = {
        'payment_type': 'canteen',
        'payment_id': str(payment.id),
        'item_name': item.name,
        'quantity': quantity,
        'student_name': student.user.get_full_name()
    }
    
    # Get school's subaccount if configured
    school = student.school
    school_subaccount = None
    if school and getattr(school, 'is_payout_setup_active', False):
        school_subaccount = school.paystack_subaccount_code
    
    # Get currency from settings
    from django.conf import settings
    currency = getattr(settings, 'PAYSTACK_CURRENCY', 'GHS')
    
    result = paystack_service.initialize_payment(
        email=parent_email or student.user.email,
        amount=float(total_amount),
        callback_url=callback_url,
        reference=reference,
        metadata=metadata,
        subaccount=school_subaccount,
        currency=currency
    )
    
    if result.get('status'):
        return JsonResponse({
            'success': True,
            'authorization_url': result['data']['authorization_url'],
            'reference': reference,
            'payment_id': payment.id,  # Return payment_id for reliable lookup
            'email': parent_email or student.user.email
        })
    else:
        with transaction.atomic():
            p = CanteenPayment.objects.select_for_update().filter(pk=payment.pk).first()
            if p and p.payment_status != "completed":
                p.payment_status = 'failed'
                p.save(update_fields=["payment_status"])
        return JsonResponse({
            'success': False,
            'error': result.get('message', 'Payment initialization failed')
        })


@login_required
def canteen_payment_verify(request):
    """Verify Paystack payment for canteen."""
    # First try to find by payment_id from query parameter (most reliable)
    payment_id = request.GET.get('payment_id')
    
    if payment_id:
        try:
            payment = CanteenPayment.objects.get(id=payment_id)
            if not user_can_access_student_payment(request.user, payment.student):
                return _deny_unowned_payment_verify(request)
            if not is_feature_enabled_for_school(payment.school_id, "canteen"):
                messages.info(request, "Canteen is not enabled for your school.")
                return redirect('operations:canteen_my')
            if payment.payment_status == 'completed':
                messages.info(request, "Payment already confirmed.")
                return redirect('operations:canteen_my')
        except CanteenPayment.DoesNotExist:
            pass
    
    reference = request.GET.get('reference')
    result = paystack_service.verify_payment(reference) if reference else None
    if not result and payment_id:
        # Fall back to stored reference if query param missing
        stored_ref = CanteenPayment.objects.filter(pk=payment_id).values_list('payment_reference', flat=True).first()
        if stored_ref:
            reference = stored_ref
            result = paystack_service.verify_payment(reference)
    
    payment = None
    try:
        with transaction.atomic():
            if payment_id:
                payment = CanteenPayment.objects.select_for_update().filter(id=payment_id).first()
            if not payment and reference:
                payment = CanteenPayment.objects.select_for_update().filter(payment_reference=reference).first()

            if payment:
                if not user_can_access_student_payment(request.user, payment.student):
                    return _deny_unowned_payment_verify(request)
                if not is_feature_enabled_for_school(payment.school_id, "canteen"):
                    messages.info(request, "Canteen is not enabled for your school.")
                    return redirect('operations:canteen_my')
                if payment.payment_status == 'completed':
                    messages.info(request, "Payment already confirmed.")
                    return redirect('operations:canteen_my')

                # Bug fix F4-14: reject reference-forgery attempts before
                # marking completed. ``reference`` either matches the row's
                # stored reference or is empty (in which case use stored).
                if not _reference_matches_payment(reference, payment):
                    logger.warning(
                        "canteen_payment_verify reference mismatch payment_id=%s url_ref=%s stored_ref=%s",
                        payment.id, reference, payment.payment_reference,
                    )
                    messages.error(request, "Payment verification failed: reference mismatch.")
                    return redirect('operations:canteen_my')
                if not reference and payment.payment_reference:
                    reference = payment.payment_reference
                    if not result:
                        result = paystack_service.verify_payment(reference)

                if result and result.get('status') and result['data']['status'] == 'success':
                    mark_canteen_payment_completed(payment=payment, reference=reference)
                    messages.success(request, "Payment successful! Your order has been placed.")
                else:
                    # Do not overwrite a completion that might have happened via webhook in parallel.
                    mark_canteen_payment_failed(payment=payment, reference=reference)
                    messages.error(request, "Payment failed. Please try again.")
            else:
                messages.error(request, "Payment record not found")
    except Exception:
        messages.error(request, "Payment verification failed. Please try again.")
    
    return redirect('operations:canteen_my')


# ==================== BUS/TRANSPORT PAYMENTS ====================

@student_required
def bus_my(request):
    """Student view to see bus routes and make payments."""
    student = student_for_portal(request)
    if not student:
        messages.error(request, "No student profile is linked to this account.")
        return redirect("home")

    school = student.school
    if not is_feature_enabled_for_school(school.pk, "bus_transport"):
        messages.info(request, "Bus transport is not enabled for your school.")
        return redirect("accounts:dashboard")
    current_term = request.GET.get("term") or f"Term {timezone.now().year}"

    # Get all bus routes with fees
    routes = BusRoute.objects.filter(school=school)

    # Get student's payment records
    my_payments_qs = BusPayment.objects.filter(
        student=student,
        payment_status='completed'
    ).select_related('route').order_by('-payment_date', '-id')

    my_payments = paginate(request, my_payments_qs, per_page=25, page_param="hist_page")

    # Get pending payments
    pending_qs = BusPayment.objects.filter(
        student=student,
        payment_status='pending'
    ).order_by('-payment_date', '-id')
    pending_page = paginate(request, pending_qs, per_page=25, page_param="pending_page")

    from django.conf import settings
    portal_children = _portal_children(request.user)
    context = {
        'routes': routes,
        'my_payments': my_payments,
        'pending_payments': pending_page,
        'pending_page': pending_page,
        'page_title': 'Transport',
        'paystack_public_key': getattr(settings, 'PAYSTACK_PUBLIC_KEY', ''),
        'portal_children': portal_children,
        'portal_student': student,
        'mode': 'parent' if getattr(request.user, 'role', None) == 'parent' else 'student',
        'children': portal_children,
        'current_term': current_term,
    }
    return render(request, 'operations/bus_my.html', context)


@login_required
@require_POST
def bus_initiate_payment(request):
    """Initiate Paystack payment for bus/transport."""
    student, err = authorized_student_for_payment_post(request)
    if err:
        return err

    if not is_feature_enabled_for_school(student.school_id, "bus_transport"):
        return JsonResponse({"success": False, "error": "Bus transport is not enabled for your school."}, status=403)

    route_id = request.POST.get('route_id')
    term = request.POST.get('term', f'Term {timezone.now().year}')
    payment_method = request.POST.get('payment_method', 'card')
    try:
        daily_units = int(request.POST.get('daily_units', "0"))
    except (TypeError, ValueError):
        daily_units = 0
    
    try:
        route = BusRoute.objects.get(id=route_id, school=student.school)
    except BusRoute.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Route not found'}, status=404)
    
    # Check if already paid for this term (term frequency only)
    if route.payment_frequency == 'term':
        existing = BusPayment.objects.filter(
            student=student,
            route=route,
            term_period=term,
            payment_status='completed'
        ).exists()
        if existing:
            return JsonResponse({'success': False, 'error': 'Already paid for this term'}, status=400)
    
    # Calculate amount based on payment frequency
    base_amount = Decimal(str(route.fee_per_term or 0)).quantize(Decimal("0.01"))
    if route.payment_frequency == 'daily':
        if daily_units <= 0:
            return JsonResponse({'success': False, 'error': 'Enter how many days you are paying for.'}, status=400)
        amount = (base_amount * daily_units).quantize(Decimal("0.01"))
    else:
        amount = base_amount
        daily_units = 0

    # Generate unique reference
    reference = f"BUS_{uuid.uuid4().hex[:12].upper()}"

    # Create pending payment record (atomic so reference can't be lost under concurrency)
    with transaction.atomic():
        payment = BusPayment.objects.create(
            school=student.school,
            student=student,
            route=route,
            amount=amount,
            term_period=term,
            daily_units=daily_units,
            payment_reference=reference,
            payment_status='pending'
        )
    
    # Get parent email using helper function
    parent_email = _get_parent_email(student, request)
    
    if not parent_email and request.user.email:
        parent_email = request.user.email
    
    metadata = {
        'payment_type': 'bus',
        'payment_id': str(payment.id),
        'route_name': route.name,
        'term': term,
        'student_name': student.user.get_full_name(),
        'daily_units': daily_units,
    }
    
    # Get school's subaccount if configured
    school = student.school
    school_subaccount = None
    if school and getattr(school, 'is_payout_setup_active', False):
        school_subaccount = school.paystack_subaccount_code
    
    from django.conf import settings
    currency = getattr(settings, 'PAYSTACK_CURRENCY', 'GHS')
    
    # Callback URL with payment_id as query parameter for reliable lookup on return.
    callback_url = request.build_absolute_uri(
        reverse('operations:bus_payment_verify') + f"?payment_id={payment.id}"
    )
    
    result = paystack_service.initialize_payment(
        email=parent_email or student.user.email,
        amount=float(amount),
        callback_url=callback_url,
        reference=reference,
        metadata=metadata,
        subaccount=school_subaccount,
        currency=currency
    )
    
    if result.get('status'):
        pe = parent_email or student.user.email
        return JsonResponse({
            'success': True,
            'authorization_url': result['data']['authorization_url'],
            'reference': reference,
            'payment_id': payment.id,  # Return payment_id for reliable lookup
            'email': pe,
            'charge_amount': str(amount),
        })
    else:
        with transaction.atomic():
            p = BusPayment.objects.select_for_update().filter(pk=payment.pk).first()
            if p and p.payment_status != "completed":
                p.payment_status = 'failed'
                p.save(update_fields=["payment_status"])
        return JsonResponse({
            'success': False,
            'error': result.get('message', 'Payment initialization failed')
        })


@login_required
def bus_payment_verify(request):
    """Verify Paystack payment for bus."""
    # First try to find by payment_id from query parameter (most reliable)
    payment_id = request.GET.get('payment_id')
    
    if payment_id:
        try:
            payment = BusPayment.objects.get(id=payment_id)
            if not user_can_access_student_payment(request.user, payment.student):
                return _deny_unowned_payment_verify(request)
            if not is_feature_enabled_for_school(payment.school_id, "bus_transport"):
                messages.info(request, "Bus transport is not enabled for your school.")
                return redirect('operations:bus_my')
            if payment.payment_status == 'completed':
                messages.info(request, "Payment already confirmed.")
                return redirect('operations:bus_my')
        except BusPayment.DoesNotExist:
            pass
    
    reference = request.GET.get('reference')
    result = paystack_service.verify_payment(reference) if reference else None
    
    payment = None
    try:
        with transaction.atomic():
            if payment_id:
                payment = BusPayment.objects.select_for_update().filter(id=payment_id).first()
            if not payment and reference:
                payment = BusPayment.objects.select_for_update().filter(payment_reference=reference).first()

            if payment:
                if not user_can_access_student_payment(request.user, payment.student):
                    return _deny_unowned_payment_verify(request)
                if not is_feature_enabled_for_school(payment.school_id, "bus_transport"):
                    messages.info(request, "Bus transport is not enabled for your school.")
                    return redirect('operations:bus_my')
                if payment.payment_status == 'completed':
                    messages.info(request, "Payment already confirmed.")
                    return redirect('operations:bus_my')

                # Bug fix F4-14: reject reference-forgery attempts.
                if not _reference_matches_payment(reference, payment):
                    logger.warning(
                        "bus_payment_verify reference mismatch payment_id=%s url_ref=%s stored_ref=%s",
                        payment.id, reference, payment.payment_reference,
                    )
                    messages.error(request, "Payment verification failed: reference mismatch.")
                    return redirect('operations:bus_my')
                if not reference and payment.payment_reference:
                    reference = payment.payment_reference
                    if not result:
                        result = paystack_service.verify_payment(reference)

                if result and result.get('status') and result['data']['status'] == 'success':
                    mark_bus_payment_completed(payment=payment, reference=reference)
                    messages.success(request, "Payment successful! Your bus pass is now active.")
                else:
                    mark_bus_payment_failed(payment=payment, reference=reference)
                    messages.error(request, "Payment failed. Please try again.")
            else:
                messages.error(request, "Payment record not found")
    except Exception:
        messages.error(request, "Payment verification failed. Please try again.")
    
    return redirect('operations:bus_my')


# ==================== TEXTBOOK PAYMENTS ====================

@student_required
def textbook_my(request):
    """Student view to browse and purchase textbooks."""
    student = student_for_portal(request)
    if not student:
        messages.error(request, "No student profile is linked to this account.")
        return redirect("home")

    school = student.school
    if not is_feature_enabled_for_school(school.pk, "textbooks"):
        messages.info(request, "Textbooks are not enabled for your school.")
        return redirect("accounts:dashboard")

    # Get available textbooks
    textbooks = Textbook.objects.filter(school=school, stock__gt=0)

    # Get student's purchase history
    my_purchases_page = paginate(
        request,
        TextbookSale.objects.filter(
            student=student,
            payment_status='completed'
        ).select_related('textbook').order_by('-id'),
        per_page=25,
        page_param="textbook_hist",
    )

    # Get pending purchases
    pending_page = paginate(
        request,
        TextbookSale.objects.filter(
            student=student,
            payment_status='pending'
        ).select_related('textbook').order_by('-id'),
        per_page=25,
        page_param="textbook_pending",
    )

    from django.conf import settings
    portal_children = _portal_children(request.user)
    context = {
        'textbooks': textbooks,
        'my_purchases': my_purchases_page,
        'pending_purchases': pending_page,
        'pending_page': pending_page,
        'page_obj': my_purchases_page,
        'page_title': 'Textbooks',
        'paystack_public_key': getattr(settings, 'PAYSTACK_PUBLIC_KEY', ''),
        'portal_children': portal_children,
        'portal_student': student,
    }
    return render(request, 'operations/textbook_my.html', context)


@login_required
@require_POST
def textbook_initiate_payment(request):
    """Initiate Paystack payment for textbooks."""
    student, err = authorized_student_for_payment_post(request)
    if err:
        return err

    if not is_feature_enabled_for_school(student.school_id, "textbooks"):
        return JsonResponse({"success": False, "error": "Textbooks are not enabled for your school."}, status=403)

    textbook_id = request.POST.get('textbook_id')
    quantity = int(request.POST.get('quantity', 1))

    # Generate unique reference before the atomic block
    reference = f"TEXTBOOK_{uuid.uuid4().hex[:12].upper()}"

    # Lock the textbook row to prevent concurrent overselling
    with transaction.atomic():
        try:
            textbook = Textbook.objects.select_for_update().get(
                id=textbook_id, school=student.school, stock__gte=quantity
            )
        except Textbook.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Textbook not found or insufficient stock'}, status=404)

        total_amount = (Decimal(str(textbook.price)) * Decimal(quantity)).quantize(Decimal("0.01"))

        sale = TextbookSale.objects.create(
            school=student.school,
            student=student,
            textbook=textbook,
            quantity=quantity,
            amount=total_amount,
            payment_reference=reference,
            payment_status='pending'
        )
    
    # Get parent email using helper function
    parent_email = _get_parent_email(student, request)
    
    if not parent_email and request.user.email:
        parent_email = request.user.email
    
    # Build callback URL with payment_id for reliable lookup
    callback_url = request.build_absolute_uri(
        reverse('operations:textbook_payment_verify') + f"?payment_id={sale.id}"
    )
    
    metadata = {
        'payment_type': 'textbook',
        'payment_id': str(sale.id),
        'textbook_title': textbook.title,
        'quantity': quantity,
        'student_name': student.user.get_full_name()
    }
    
    # Get school's subaccount if configured
    school = student.school
    school_subaccount = None
    if school and getattr(school, 'is_payout_setup_active', False):
        school_subaccount = school.paystack_subaccount_code
    
    # Get currency from settings
    from django.conf import settings
    currency = getattr(settings, 'PAYSTACK_CURRENCY', 'GHS')
    
    result = paystack_service.initialize_payment(
        email=parent_email or student.user.email,
        amount=float(total_amount),
        callback_url=callback_url,
        reference=reference,
        metadata=metadata,
        subaccount=school_subaccount,
        currency=currency
    )
    
    if result.get('status'):
        pe = parent_email or student.user.email
        return JsonResponse({
            'success': True,
            'authorization_url': result['data']['authorization_url'],
            'reference': reference,
            'payment_id': sale.id,  # Return payment_id for reliable lookup
            'email': pe,
        })
    else:
        with transaction.atomic():
            s = TextbookSale.objects.select_for_update().filter(pk=sale.pk).first()
            if s and s.payment_status != "completed":
                s.payment_status = 'failed'
                s.save(update_fields=["payment_status"])
        return JsonResponse({
            'success': False,
            'error': result.get('message', 'Payment initialization failed')
        })


@login_required
def textbook_payment_verify(request):
    """Verify Paystack payment for textbooks."""
    # First try to find by payment_id from query parameter (most reliable)
    payment_id = request.GET.get('payment_id')
    
    if payment_id:
        try:
            sale = TextbookSale.objects.get(id=payment_id)
            if not user_can_access_student_payment(request.user, sale.student):
                return _deny_unowned_payment_verify(request)
            if not is_feature_enabled_for_school(sale.school_id, "textbooks"):
                messages.info(request, "Textbooks are not enabled for your school.")
                return redirect('operations:textbook_my')
            if sale.payment_status == 'completed':
                messages.info(request, "Payment already confirmed.")
                return redirect('operations:textbook_my')
        except TextbookSale.DoesNotExist:
            pass
    
    reference = request.GET.get('reference')
    result = paystack_service.verify_payment(reference) if reference else None
    
    sale = None
    try:
        with transaction.atomic():
            if payment_id:
                sale = TextbookSale.objects.select_for_update().select_related("textbook").filter(id=payment_id).first()
            if not sale and reference:
                sale = TextbookSale.objects.select_for_update().select_related("textbook").filter(payment_reference=reference).first()

            if sale:
                if not user_can_access_student_payment(request.user, sale.student):
                    return _deny_unowned_payment_verify(request)
                if not is_feature_enabled_for_school(sale.school_id, "textbooks"):
                    messages.info(request, "Textbooks are not enabled for your school.")
                    return redirect('operations:textbook_my')
                if sale.payment_status == 'completed':
                    messages.info(request, "Payment already confirmed.")
                    return redirect('operations:textbook_my')

                # Bug fix F4-14: reject reference-forgery attempts.
                if not _reference_matches_payment(reference, sale):
                    logger.warning(
                        "textbook_payment_verify reference mismatch sale_id=%s url_ref=%s stored_ref=%s",
                        sale.id, reference, sale.payment_reference,
                    )
                    messages.error(request, "Payment verification failed: reference mismatch.")
                    return redirect('operations:textbook_my')
                if not reference and sale.payment_reference:
                    reference = sale.payment_reference
                    if not result:
                        result = paystack_service.verify_payment(reference)

                if result and result.get('status') and result['data']['status'] == 'success':
                    mark_textbook_sale_completed(sale=sale, reference=reference)

                    if sale.textbook_id:
                        updated = Textbook.objects.filter(
                            pk=sale.textbook_id, stock__gte=sale.quantity
                        ).update(stock=F('stock') - sale.quantity)
                        if not updated:
                            messages.warning(request, "Payment confirmed, but textbook stock was insufficient. Please contact the school.")
                    messages.success(request, "Payment successful! Your textbook(s) have been reserved.")
                else:
                    mark_textbook_sale_failed(sale=sale, reference=reference)
                    messages.error(request, "Payment failed. Please try again.")
            else:
                messages.error(request, "Payment record not found")
    except Exception:
        messages.error(request, "Payment verification failed. Please try again.")
    
    return redirect('operations:textbook_my')


# ==================== HOSTEL FEE PAYMENTS ====================

@login_required
@require_POST
def hostel_initiate_payment(request):
    """Initiate Paystack payment for hostel fees."""
    fee_id = request.POST.get('fee_id')
    if not fee_id:
        return JsonResponse({'success': False, 'error': 'Missing fee_id'}, status=400)

    try:
        fee = HostelFee.objects.select_related('student', 'student__user', 'hostel', 'school').get(id=fee_id)
    except HostelFee.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Fee not found'}, status=404)

    student = fee.student
    role = getattr(request.user, 'role', None)
    if role == 'student':
        if student.user_id != request.user.id:
            return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)
    elif role == 'parent':
        if student.parent_id != request.user.id:
            return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)
    else:
        return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)

    if not is_feature_enabled_for_school(fee.school_id, "hostel"):
        return JsonResponse({"success": False, "error": "Hostel is not enabled for your school."}, status=403)

    if fee.payment_status == 'completed' or fee.paid:
        return JsonResponse({'success': False, 'error': 'Already paid'}, status=400)

    try:
        amount_raw = request.POST.get('amount')
        if amount_raw:
            amount = Decimal(str(amount_raw))
        else:
            amount = Decimal(str(fee.balance if hasattr(fee, "balance") else fee.amount))
    except (TypeError, ValueError, InvalidOperation):
        return JsonResponse({'success': False, 'error': 'Enter a valid amount.'}, status=400)
    amount = amount.quantize(Decimal("0.01"))
    balance = Decimal(str(fee.balance if hasattr(fee, "balance") else fee.amount)).quantize(Decimal("0.01"))
    if amount <= 0:
        return JsonResponse({'success': False, 'error': 'Amount must be greater than zero.'}, status=400)
    if amount > balance:
        return JsonResponse({'success': False, 'error': 'Amount exceeds remaining balance.'}, status=400)

    # Generate unique reference
    reference = f"HOSTEL_{uuid.uuid4().hex[:12].upper()}"
    with transaction.atomic():
        fee = HostelFee.objects.select_for_update().select_related('student', 'student__user', 'hostel', 'school').get(id=fee_id)
        if fee.payment_status == 'completed' or fee.paid:
            return JsonResponse({'success': False, 'error': 'Already paid'}, status=400)
        fee.payment_reference = reference
        fee.payment_status = 'pending'
        fee.save(update_fields=["payment_reference", "payment_status"])

    # Get parent email using helper function
    parent_email = _get_parent_email(student, request)

    if not parent_email and request.user.email:
        parent_email = request.user.email

    # Build callback URL with payment_id for reliable lookup
    callback_url = request.build_absolute_uri(
        reverse('operations:hostel_payment_verify') + f"?payment_id={fee.id}"
    )

    metadata = {
        'payment_type': 'hostel',
        'payment_id': str(fee.id),
        'hostel_name': fee.hostel.name,
        'term': fee.term,
        'student_name': student.user.get_full_name(),
        'requested_amount': str(amount),
    }

    # Get school's subaccount if configured
    school = student.school
    school_subaccount = None
    if school and getattr(school, 'is_payout_setup_active', False):
        school_subaccount = school.paystack_subaccount_code
    
    # Get currency from settings
    from django.conf import settings
    currency = getattr(settings, 'PAYSTACK_CURRENCY', 'GHS')
    
    result = paystack_service.initialize_payment(
        email=parent_email or student.user.email,
        amount=float(amount),
        callback_url=callback_url,
        reference=reference,
        metadata=metadata,
        subaccount=school_subaccount,
        currency=currency
    )
    
    if result.get('status'):
        return JsonResponse({
            'success': True,
            'authorization_url': result['data']['authorization_url'],
            'reference': reference,
            'payment_id': fee.id,  # Return payment_id for reliable lookup
            'charge_amount': str(amount),
        })
    else:
        with transaction.atomic():
            f = HostelFee.objects.select_for_update().filter(pk=fee.pk).first()
            if f and f.payment_status != "completed" and not f.paid:
                f.payment_status = 'failed'
                f.save(update_fields=["payment_status"])
        return JsonResponse({
            'success': False,
            'error': result.get('message', 'Payment initialization failed')
        })


@login_required
def hostel_payment_verify(request):
    """Verify Paystack payment for hostel fees."""
    # First try to find by payment_id from query parameter (most reliable)
    payment_id = request.GET.get('payment_id')
    
    if payment_id:
        try:
            fee = HostelFee.objects.get(id=payment_id)
            if not user_can_access_student_payment(request.user, fee.student):
                return _deny_unowned_payment_verify(request)
            if not is_feature_enabled_for_school(fee.school_id, "hostel"):
                messages.info(request, "Hostel is not enabled for your school.")
                return redirect('operations:hostel_my')
            if fee.payment_status == 'completed':
                messages.info(request, "Payment already confirmed.")
                return redirect('operations:hostel_my')
        except HostelFee.DoesNotExist:
            pass
    
    reference = request.GET.get('reference')
    result = paystack_service.verify_payment(reference) if reference else None
    
    fee = None
    try:
        with transaction.atomic():
            if payment_id:
                fee = HostelFee.objects.select_for_update().filter(id=payment_id).first()
            if not fee and reference:
                fee = HostelFee.objects.select_for_update().filter(payment_reference=reference).first()
            if not reference and fee and fee.payment_reference:
                reference = fee.payment_reference
                result = paystack_service.verify_payment(reference)

            if fee:
                if not user_can_access_student_payment(request.user, fee.student):
                    return _deny_unowned_payment_verify(request)
                if not is_feature_enabled_for_school(fee.school_id, "hostel"):
                    messages.info(request, "Hostel is not enabled for your school.")
                    return redirect('operations:hostel_my')
                if fee.payment_status == 'completed' or fee.paid:
                    messages.info(request, "Payment already confirmed.")
                    return redirect('operations:hostel_my')

                # Bug fix F4-14: reject reference-forgery attempts.
                if not _reference_matches_payment(reference, fee):
                    logger.warning(
                        "hostel_payment_verify reference mismatch fee_id=%s url_ref=%s stored_ref=%s",
                        fee.id, reference, fee.payment_reference,
                    )
                    messages.error(request, "Payment verification failed: reference mismatch.")
                    return redirect('operations:hostel_my')

                if result and result.get('status') and result['data']['status'] == 'success':
                    paid_amount = Decimal(str(result['data'].get('amount', 0))) / Decimal('100')
                    applied_amount = mark_hostel_fee_completed(
                        fee=fee,
                        paid_amount=paid_amount,
                        reference=reference,
                    )
                    fee.refresh_from_db(fields=[
                        "amount",
                        "amount_paid",
                        "payment_status",
                        "paid",
                    ])
                    if applied_amount == Decimal("0"):
                        messages.info(request, "Payment already recorded for this reference.")
                    elif fee.paid:
                        messages.success(request, "Payment successful! Your hostel fee is now cleared.")
                    else:
                        remaining = (fee.amount or Decimal("0")) - (fee.amount_paid or Decimal("0"))
                        if remaining < Decimal("0"):
                            remaining = Decimal("0")
                        messages.success(
                            request,
                            f"Payment received! Remaining balance: GHS {remaining.quantize(Decimal('0.01'))}",
                        )
                else:
                    mark_hostel_fee_failed(fee=fee, reference=reference)
                    messages.error(request, "Payment failed. Please try again.")
            else:
                messages.error(request, "Payment record not found")
    except Exception:
        messages.error(request, "Payment verification failed. Please try again.")
    
    return redirect('operations:hostel_my')


# ==================== GENERAL PAYMENT DASHBOARD ====================

@login_required
def payment_dashboard(request):
    """Admin dashboard showing all payments across the system."""
    school = getattr(request.user, 'school', None)
    if not school:
        messages.error(request, "School not found")
        return redirect('accounts:dashboard')
    if not (request.user.is_superuser or can_manage_finance(request.user)):
        messages.error(request, "You do not have permission to view finance dashboard.")
        return redirect("accounts:dashboard")
    
    # Get filter parameters
    date_filter = request.GET.get('date_filter', 'all')
    payment_type = request.GET.get('payment_type', 'all')
    start_date_input = request.GET.get('start_date')
    end_date_input = request.GET.get('end_date')
    start_date = parse_date(start_date_input) if start_date_input else None
    end_date = parse_date(end_date_input) if end_date_input else None

    range_start = None
    range_end = None
    today = timezone.now().date()

    if date_filter == 'today':
        range_start = today
        range_end = today
    elif date_filter == 'week':
        range_start = today - timedelta(days=7)
        range_end = today
    elif date_filter == 'month':
        range_start = today - timedelta(days=30)
        range_end = today
    elif date_filter == 'term':
        current_term = get_current_term_for_school(school)
        if current_term and current_term.start_date:
            range_start = current_term.start_date
            range_end = current_term.end_date or today

    if start_date:
        range_start = start_date
    if end_date:
        range_end = end_date

    # expose resolved dates back to template
    start_date = range_start
    end_date = range_end
    
    # Base queryset for fees
    from finance.models import Fee
    fees = Fee.objects.filter(school=school).select_related('student')
    
    if start_date:
        fees = fees.filter(created_at__date__gte=start_date)
    if end_date:
        fees = fees.filter(created_at__date__lte=end_date)
    
    # Get payment counts
    total_fees = fees.count()
    paid_fees = fees.filter(paid=True).count()
    pending_fees = total_fees - paid_fees
    
    # Get amounts
    total_amount = sum((f.amount or Decimal("0")) for f in fees)
    total_collected = sum((f.amount_paid or Decimal("0")) for f in fees)
    
    # Get other payments (canteen, bus, textbook) with date filtering
    canteen_payments = CanteenPayment.objects.filter(school=school).select_related('student', 'student__user', 'recorded_by')
    bus_payments = BusPayment.objects.filter(school=school).select_related('student', 'student__user', 'route')
    textbook_sales = TextbookSale.objects.filter(school=school).select_related('student', 'student__user', 'textbook')
    hostel_fees = HostelFee.objects.filter(school=school).select_related('student', 'student__user')
    
    if start_date:
        canteen_payments = canteen_payments.filter(payment_date__gte=start_date)
        bus_payments = bus_payments.filter(payment_date__gte=start_date)
        textbook_sales = textbook_sales.filter(sale_date__gte=start_date)
        hostel_fees = hostel_fees.filter(payment_date__gte=start_date)
    if end_date:
        canteen_payments = canteen_payments.filter(payment_date__lte=end_date)
        bus_payments = bus_payments.filter(payment_date__lte=end_date)
        textbook_sales = textbook_sales.filter(sale_date__lte=end_date)
        hostel_fees = hostel_fees.filter(payment_date__lte=end_date)
    
    # Filter by payment type if not 'all'
    canteen_filtered = canteen_payments.filter(payment_status='completed')
    bus_filtered = bus_payments.filter(paid=True)
    textbook_filtered = textbook_sales.filter(payment_status='completed')
    hostel_filtered = hostel_fees.filter(paid=True)
    school_fees_filtered = fees.filter(paid=True)
    
    # Calculate totals by type (show all totals regardless of filter for the summary cards)
    canteen_total_all = sum((p.amount or Decimal("0")) for p in canteen_payments.filter(payment_status='completed'))
    bus_total_all = sum((p.amount or Decimal("0")) for p in bus_payments.filter(paid=True))
    textbook_total_all = sum((s.amount or Decimal("0")) for s in textbook_sales.filter(payment_status='completed'))
    hostel_total_all = sum((f.amount or Decimal("0")) for f in hostel_fees.filter(paid=True))
    school_fees_total_all = total_collected
    
    # Use totals based on filter
    canteen_total = canteen_total_all
    bus_total = bus_total_all
    textbook_total = textbook_total_all
    hostel_total = hostel_total_all
    school_fees_total = school_fees_total_all
    
    # Build recent payments list combining all types
    recent_payments = []
    
    if payment_type in ['all', 'school_fees']:
        for f in school_fees_filtered[:20]:
            recent_payments.append({
                'student': f.student,
                'date': _payment_datetime(f.created_at),
                'type': 'School Fee',
                'amount': f.amount_paid,
                'description': f.term or 'School Fee',
            })
    
    if payment_type in ['all', 'canteen']:
        for p in canteen_filtered:
            recent_payments.append({
                'student': p.student,
                'date': _payment_datetime(p.payment_date),
                'type': 'Canteen',
                'amount': p.amount,
                'description': p.description,
                'id': p.id,
            })
    
    if payment_type in ['all', 'bus']:
        for p in bus_filtered:
            recent_payments.append({
                'student': p.student,
                'date': _payment_datetime(p.payment_date),
                'type': 'Bus',
                'amount': p.amount,
                'description': p.route.name if p.route else 'Bus Fee',
                'id': p.id,
            })
    
    if payment_type in ['all', 'textbook']:
        for s in textbook_filtered:
            recent_payments.append({
                'student': s.student,
                'date': _payment_datetime(s.sale_date),
                'type': 'Textbook',
                'amount': s.amount,
                'description': s.textbook.title if s.textbook else 'Textbook',
                'id': s.id,
            })
    
    if payment_type in ['all', 'hostel']:
        for h in hostel_filtered:
            recent_payments.append({
                'student': h.student,
                'date': _payment_datetime(h.payment_date),
                'type': 'Hostel',
                'amount': h.amount,
                'description': f"Hostel Fee - {h.term}" if h.term else 'Hostel Fee',
                'id': h.id,
            })
    
    # Sort by date descending
    recent_payments.sort(key=lambda x: x['date'], reverse=True)
    recent_payments = recent_payments[:50]  # Limit to 50 most recent
    
    # Count variables for template
    canteen_count = canteen_filtered.count()
    bus_count = bus_filtered.count()
    bus_paid = bus_filtered.count()
    bus_unpaid = bus_payments.filter(paid=False).count()
    textbook_count = textbook_filtered.count()
    
    # Paginate bus and canteen payments
    from django.core.paginator import Paginator
    bus_payments_paginator = Paginator(bus_payments, 50)
    canteen_payments_paginator = Paginator(canteen_payments, 50)
    
    bus_payments_page_number = request.GET.get('bus_payments_page')
    canteen_payments_page_number = request.GET.get('canteen_payments_page')
    
    bus_payments_page_obj = bus_payments_paginator.get_page(bus_payments_page_number)
    canteen_payments_page_obj = canteen_payments_paginator.get_page(canteen_payments_page_number)
    
    outstanding_students = (
        Student.objects.filter(school=school, fee__paid=False)
        .distinct()
        .select_related('user')
        .order_by('user__last_name', 'user__first_name')[:10]
    )

    # Daily collections — use PaymentTransaction as the unified ledger
    from django.db.models.functions import TruncDate
    from django.db.models import Sum as _Sum
    from finance.models import PaymentTransaction
    daily_qs = PaymentTransaction.objects.filter(school=school, status='completed')
    if range_start:
        daily_qs = daily_qs.filter(created_at__date__gte=range_start)
    if range_end:
        daily_qs = daily_qs.filter(created_at__date__lte=range_end)
    daily_collections = list(
        daily_qs
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(total=_Sum('amount'))
        .order_by('-day')[:30]
    )
    grand_total = sum((r['total'] or Decimal('0')) for r in daily_collections)

    context = {
        'fees': school_fees_filtered[:20],
        'school_fees': school_fees_filtered[:20],
        'canteen_payments': canteen_payments_page_obj,
        'bus_payments': bus_payments_page_obj,
        'textbook_sales': textbook_filtered,
        'hostel_payments': hostel_filtered,
        'recent_payments': recent_payments,
        'total_fees': total_fees,
        'paid_fees': paid_fees,
        'pending_fees': pending_fees,
        'total_amount': total_amount,
        'total_collected': total_collected,
        'canteen_total': canteen_total,
        'bus_total': bus_total,
        'textbook_total': textbook_total,
        'hostel_total': hostel_total,
        'school_fees_total': school_fees_total,
        'canteen_count': canteen_count,
        'bus_count': bus_count,
        'bus_paid': bus_paid,
        'bus_unpaid': bus_unpaid,
        'textbook_count': textbook_count,
        'date_filter': date_filter,
        'payment_type': payment_type,
        'start_date': start_date,
        'end_date': end_date,
        'page_title': 'Payment Dashboard',
        'outstanding_students': outstanding_students,
        'bus_payments_page_obj': bus_payments_page_obj,
        'canteen_payments_page_obj': canteen_payments_page_obj,
        'daily_collections': daily_collections,
        'grand_total': grand_total,
    }
    return render(request, 'operations/payment_dashboard.html', context)


@login_required
def student_payment_history(request, student_id):
    """View payment history for a specific student."""
    from finance.models import Fee, FeePayment

    school = getattr(request.user, "school", None)
    role = getattr(request.user, "role", None)

    if is_super_admin(request.user) or getattr(request.user, "is_superuser", False):
        student = get_object_or_404(Student, pk=student_id)
    elif role == "student" and school:
        student = get_object_or_404(Student, user=request.user, school=school)
        if student.pk != int(student_id):
            messages.error(request, "You can only view your own payment history.")
            return redirect("portal")
    elif role == "parent" and school:
        student = get_object_or_404(Student, pk=student_id, school=school)
        if not parent_is_guardian_of(request.user, student):
            messages.error(request, "You do not have access to this student's payment history.")
            return redirect("portal")
    elif (
        school
        and (
            can_manage_finance(request.user)
            or is_school_leadership(request.user)
            or user_can_manage_school(request.user)
        )
    ):
        student = get_object_or_404(Student, pk=student_id, school=school)
    else:
        messages.error(request, "You do not have permission to view this payment history.")
        return redirect("home")

    # Get all fees for student (active billing rows only)
    fees = Fee.objects.filter(student=student, deleted_at__isnull=True).order_by("-created_at")
    
    # Get all related payments
    all_payments = []
    for fee in fees:
        fee_payments = FeePayment.objects.filter(fee=fee).order_by('-created_at')
        for payment in fee_payments:
            all_payments.append({
                'type': 'school_fee',
                'fee': fee,
                'payment': payment,
                'amount': float(payment.amount),
                'status': payment.status,
                'date': payment.created_at,
            })
    
    # Get canteen payments
    canteen_payments = CanteenPayment.objects.filter(student=student).order_by('-payment_date')
    for payment in canteen_payments:
        all_payments.append({
            'type': 'canteen',
            'payment': payment,
            'amount': float(payment.amount),
            'status': payment.payment_status,
            'date': payment.payment_date,
        })
    
    # Get bus payments
    bus_payments = BusPayment.objects.filter(student=student).order_by('-id')
    for payment in bus_payments:
        all_payments.append({
            'type': 'bus',
            'payment': payment,
            'amount': float(payment.amount),
            'status': payment.payment_status,
            'date': payment.payment_date,
        })
    
    # Get textbook sales - use sale_date instead of created_at
    textbook_sales = TextbookSale.objects.filter(student=student).order_by('-id')
    for sale in textbook_sales:
        all_payments.append({
            'type': 'textbook',
            'payment': sale,
            'amount': float(sale.amount),
            'status': sale.payment_status,
            'date': sale.sale_date,
        })
    
    # Sort by date (FeePayment uses datetime; canteen/bus/textbook often use date only)
    all_payments.sort(key=lambda x: _payment_history_sort_dt(x["date"]), reverse=True)
    
    # Calculate totals
    total_paid = sum(p['amount'] for p in all_payments if p['status'] == 'completed')
    total_pending = sum(p['amount'] for p in all_payments if p['status'] == 'pending')

    # Per-type totals for template summary cards
    school_fees_total = sum((f.amount or Decimal('0')) for f in fees)
    school_fees_paid = sum((f.amount_paid or Decimal('0')) for f in fees)
    school_fees_outstanding = school_fees_total - school_fees_paid
    canteen_total = sum((p.amount or Decimal('0')) for p in canteen_payments)
    bus_total = sum((p.amount or Decimal('0')) for p in bus_payments if p.paid)
    textbook_total = sum((s.amount or Decimal('0')) for s in textbook_sales)
    overall_total = school_fees_paid + canteen_total + bus_total + textbook_total

    context = {
        'student': student,
        'payments': all_payments,
        'fees': fees,
        'school_fees': fees,
        'canteen': canteen_payments,
        'bus': bus_payments,
        'textbooks': textbook_sales,
        'total_paid': total_paid,
        'total_pending': total_pending,
        'school_fees_total': school_fees_total,
        'school_fees_paid': school_fees_paid,
        'school_fees_outstanding': school_fees_outstanding,
        'canteen_total': canteen_total,
        'bus_total': bus_total,
        'textbook_total': textbook_total,
        'overall_total': overall_total,
        'page_title': f'Payment History - {student.user.get_full_name()}',
    }
    return render(request, 'operations/student_payment_history.html', context)


@login_required
def record_payment(request):
    """Manually record a cash/offline payment for a student."""
    from finance.models import Fee, FeePayment

    if request.method == 'POST':
        logger.debug("record_payment POST keys=%s", list(request.POST.keys()))

    school = getattr(request.user, 'school', None)
    if not school:
        messages.error(request, "School not found")
        return redirect('accounts:dashboard')
    if not (request.user.is_superuser or can_manage_finance(request.user)):
        messages.error(request, "You do not have permission to record payments.")
        return redirect("accounts:dashboard")

    if not any(
        is_feature_enabled_for_school(school.pk, k)
        for k in ("fee_management", "canteen", "bus_transport", "textbooks", "hostel")
    ):
        messages.error(
            request,
            "No payment recording modules are enabled for your school (fees, canteen, transport, textbooks, or hostel).",
        )
        return redirect("accounts:dashboard")

    if request.method == 'POST':
        payment_type = request.POST.get('payment_type', '')
        payment_method = request.POST.get('payment_method', 'cash')

        if payment_type in ('canteen', 'bus', 'textbook', 'hostel'):
            feat_key = {
                "canteen": "canteen",
                "bus": "bus_transport",
                "textbook": "textbooks",
                "hostel": "hostel",
            }[payment_type]
            if (redir := require_feature(request, feat_key, "accounts:dashboard", school=school)):
                return redir
            # ── Services cash recording path ─────────────────────────────────
            student_id = request.POST.get('student')
            if payment_type == 'canteen':
                amount_str = request.POST.get('canteen_amount', '0')
                payment_frequency = request.POST.get('payment_frequency', 'single')
                daily_units = int(request.POST.get('daily_units', '0')) if payment_frequency == 'daily' else 0
                
                if payment_frequency == 'daily' and daily_units <= 0:
                    messages.error(request, 'Enter number of days for daily payment.')
                    return redirect('operations:record_payment')
            elif payment_type == 'textbook':
                amount_str = request.POST.get('textbook_amount', '0')
            elif payment_type == 'hostel':
                amount_str = request.POST.get('hostel_amount', '0')
            else:
                amount_str = request.POST.get('amount', '0')
            try:
                student = Student.objects.get(id=student_id, school=school)
                amount_decimal = Decimal(str(amount_str)).quantize(Decimal('0.01'))
                if amount_decimal <= 0:
                    raise ValueError("Amount must be positive.")
            except Student.DoesNotExist:
                messages.error(request, "Student not found.")
                return redirect('operations:record_payment')
            except (ValueError, InvalidOperation) as exc:
                messages.error(request, f"Invalid amount: {exc}")
                return redirect('operations:record_payment')

            reference = f"CASH_{payment_type.upper()}_{uuid.uuid4().hex[:10].upper()}"
            success_amount = amount_decimal
            try:
                if payment_type == 'canteen':
                    description = request.POST.get('description', '').strip()
                    today = timezone.localdate()
                    hist = [
                        {
                            "amount": str(amount_decimal),
                            "date": str(today),
                            "reference": reference,
                        }
                    ]
                    obj = CanteenPayment.objects.create(
                        school=school,
                        student=student,
                        amount=amount_decimal,
                        amount_paid=amount_decimal,
                        description=description,
                        payment_reference=reference,
                        payment_status='completed',
                        recorded_by=request.user,
                        payment_frequency=payment_frequency,
                        daily_units=daily_units,
                        payment_history=hist,
                    )
                    record_payment_transaction(
                        provider='manual',
                        reference=reference,
                        school_id=school.pk,
                        amount=amount_decimal,
                        status='completed',
                        payment_type=PaymentTypes.CANTEEN,
                        object_id=str(obj.pk),
                        metadata={'payment_method': payment_method, 'description': description},
                    )

                elif payment_type == 'bus':
                    term = request.POST.get('term', '').strip()
                    route_id = (request.POST.get('bus_route_id') or '').strip()
                    if not route_id:
                        messages.error(request, "Select a bus route for this payment.")
                        return redirect('operations:record_payment')
                    route = BusRoute.objects.filter(pk=route_id, school=school).first()
                    if not route:
                        messages.error(request, "Bus route not found.")
                        return redirect('operations:record_payment')
                    try:
                        bus_daily_units = int(request.POST.get('bus_daily_units', '0'))
                    except (TypeError, ValueError):
                        bus_daily_units = 0
                    if route.payment_frequency == 'daily':
                        if bus_daily_units <= 0:
                            messages.error(request, "Enter how many days this daily bus payment covers.")
                            return redirect('operations:record_payment')
                        expected = (
                            Decimal(str(route.fee_per_term or 0)) * bus_daily_units
                        ).quantize(Decimal('0.01'))
                        if amount_decimal != expected:
                            messages.error(
                                request,
                                f"For this daily route, amount must be GHS {expected} "
                                f"(GHS {route.fee_per_term} × {bus_daily_units} days).",
                            )
                            return redirect('operations:record_payment')
                    else:
                        bus_daily_units = 0
                        expected_period = Decimal(str(route.fee_per_term or 0)).quantize(Decimal('0.01'))
                        if amount_decimal != expected_period:
                            freq_label = str(route.get_payment_frequency_display())
                            messages.error(
                                request,
                                f"For this {freq_label.lower()} route, the amount must be GHS {expected_period}.",
                            )
                            return redirect('operations:record_payment')

                    with transaction.atomic():
                        obj = BusPayment.objects.create(
                            school=school,
                            student=student,
                            route=route,
                            amount=amount_decimal,
                            amount_paid=Decimal('0'),
                            term_period=term,
                            daily_units=bus_daily_units,
                            payment_date=timezone.localdate(),
                            payment_reference=reference,
                            payment_status='pending',
                            paid=False,
                        )
                        if not obj.add_payment(
                            amount_decimal,
                            payment_reference=reference,
                            recorded_by=request.user,
                        ):
                            raise ValueError("Could not apply bus payment.")
                    record_payment_transaction(
                        provider='manual',
                        reference=reference,
                        school_id=school.pk,
                        amount=amount_decimal,
                        status='completed',
                        payment_type=PaymentTypes.BUS,
                        object_id=str(obj.pk),
                        metadata={
                            'payment_method': payment_method,
                            'term': term,
                            'route_id': route.pk,
                            'daily_units': bus_daily_units,
                        },
                    )

                elif payment_type == 'textbook':
                    textbook_id = request.POST.get('textbook')
                    try:
                        qty = max(1, int(request.POST.get('quantity', 1)))
                    except (TypeError, ValueError):
                        qty = 1
                    # Atomic stock check + decrement + sale creation: prevents
                    # overselling when two cashiers ring up the last copy at
                    # once. Mirrors the Paystack textbook verify flow above.
                    with transaction.atomic():
                        textbook = Textbook.objects.select_for_update().get(id=textbook_id, school=school)
                        if textbook.stock < qty:
                            raise ValueError(
                                f"Only {textbook.stock} copies of '{textbook.title}' remain in stock."
                            )
                        sale_amount = (Decimal(str(textbook.price)) * qty).quantize(Decimal('0.01'))
                        obj = TextbookSale.objects.create(
                            school=school,
                            student=student,
                            textbook=textbook,
                            quantity=qty,
                            amount=sale_amount,
                            payment_reference=reference,
                            payment_status='completed',
                            recorded_by=request.user,
                        )
                        # Conditional decrement guards against race conditions
                        # outside the select_for_update window (e.g. webhook).
                        updated = Textbook.objects.filter(
                            pk=textbook.pk, stock__gte=qty,
                        ).update(stock=F('stock') - qty)
                        if not updated:
                            raise ValueError("Textbook stock changed concurrently — please retry.")
                    success_amount = sale_amount
                    record_payment_transaction(
                        provider='manual',
                        reference=reference,
                        school_id=school.pk,
                        amount=sale_amount,
                        status='completed',
                        payment_type=PaymentTypes.TEXTBOOK,
                        object_id=str(obj.pk),
                        metadata={'payment_method': payment_method, 'textbook': textbook.title, 'quantity': qty},
                    )

                elif payment_type == 'hostel':
                    hostel_fee_id = (request.POST.get('hostel_fee_id') or '').strip()
                    if not hostel_fee_id:
                        messages.error(request, "Select a hostel fee to pay.")
                        return redirect('operations:record_payment')
                    with transaction.atomic():
                        fee = HostelFee.objects.select_for_update().get(pk=hostel_fee_id, school=school)
                        if fee.student_id != student.pk:
                            messages.error(
                                request,
                                "The selected hostel fee does not belong to the selected student.",
                            )
                            return redirect('operations:record_payment')
                        if fee.paid:
                            messages.error(request, "This hostel fee is already fully paid.")
                            return redirect('operations:record_payment')
                        balance = ((fee.amount or Decimal("0")) - (fee.amount_paid or Decimal("0"))).quantize(
                            Decimal("0.01")
                        )
                        if amount_decimal > balance:
                            messages.error(
                                request,
                                f"Amount exceeds remaining hostel balance (GHS {balance}).",
                            )
                            return redirect('operations:record_payment')
                        applied = mark_hostel_fee_completed(
                            fee=fee,
                            reference=reference,
                            paid_amount=amount_decimal,
                            recorded_by=request.user,
                            provider="manual",
                        )
                    if applied <= 0:
                        messages.error(request, "Could not record hostel payment.")
                        return redirect('operations:record_payment')

                messages.success(request, f"{payment_type.title()} payment of GHS {success_amount} recorded.")
                return redirect('operations:payment_dashboard')

            except Textbook.DoesNotExist:
                messages.error(request, "Textbook not found.")
            except HostelFee.DoesNotExist:
                messages.error(request, "Hostel fee not found.")
            except Exception as exc:
                logger.exception("record_payment: failed to record %s cash payment: %s", payment_type, exc)
                messages.error(request, f"Failed to record payment: {exc}")

        elif payment_type == 'school_fee':
            if (redir := require_feature(request, "fee_management", "accounts:dashboard", school=school)):
                return redir
            # ── Legacy school-fee path (fee_id + student_id via hidden fields) ──
            student_id = request.POST.get('school_fee_student_id')
            fee_id = request.POST.get('fee_id')
            amount = request.POST.get('school_fee_amount')
            if not (student_id and fee_id and amount):
                messages.error(request, "Please select a student, enter a fee ID, and enter an amount.")
                return redirect('operations:record_payment')
            try:
                student = Student.objects.get(id=student_id, school=school)
                amount_decimal = Decimal(str(amount)).quantize(Decimal('0.01'))
                if amount_decimal <= 0:
                    messages.error(request, "Amount must be positive")
                    return redirect('operations:record_payment')
                with transaction.atomic():
                    fee = (
                        Fee.objects.select_for_update()
                        .filter(
                            id=fee_id,
                            student=student,
                            school=school,
                            deleted_at__isnull=True,
                            is_active=True,
                        )
                        .first()
                    )
                    if not fee:
                        messages.error(request, "Fee not found, or it is inactive/archived.")
                        return redirect('operations:record_payment')
                    balance = (
                        (fee.amount or Decimal("0")) - (fee.amount_paid or Decimal("0"))
                    ).quantize(Decimal("0.01"))
                    if amount_decimal > balance:
                        messages.error(
                            request,
                            f"Amount exceeds remaining fee balance (GHS {balance}).",
                        )
                        return redirect('operations:record_payment')
                    fp = FeePayment.objects.create(
                        fee=fee,
                        amount=amount_decimal,
                        payment_method=payment_method,
                        status="completed",
                    )
                    Fee.objects.filter(pk=fee.pk).update(amount_paid=F("amount_paid") + amount_decimal)
                fee.refresh_from_db()
                fee.save()
                ref = f"CASH_FEE_{fee.pk}_{fp.pk}"
                record_payment_transaction(
                    provider='manual',
                    reference=ref,
                    school_id=school.pk,
                    amount=amount_decimal,
                    status='completed',
                    payment_type=PaymentTypes.SCHOOL_FEE_MANUAL,
                    object_id=str(fee.pk),
                    metadata={'payment_method': payment_method, 'fee_payment_id': fp.pk},
                )
                try:
                    from finance.services.school_funds import record_fee_collected

                    record_fee_collected(
                        school_id=school.pk,
                        amount=amount_decimal,
                        reference=ref,
                        description=f"Manual school fee (fee #{fee.pk})",
                        currency=getattr(settings, "PAYSTACK_CURRENCY", "GHS"),
                        metadata={
                            "fee_id": fee.pk,
                            "fee_payment_id": fp.pk,
                            "manual": True,
                            "payment_method": payment_method,
                        },
                    )
                except Exception:
                    logger.exception(
                        "record_payment: school_funds ledger failed for manual fee ref=%s (non-fatal)",
                        ref,
                    )
                messages.success(request, f"Payment of GHS {amount} recorded successfully")
                return redirect('operations:student_payment_history', student_id=student.id)
            except Student.DoesNotExist:
                messages.error(request, "Student not found")
            except (ValueError, InvalidOperation, TypeError):
                messages.error(request, "Invalid amount")
        else:
            messages.error(request, "Please select a payment type before submitting.")
            return redirect('operations:record_payment')

    students = Student.objects.filter(school=school, status='active').select_related('user').order_by('user__first_name')
    textbooks = Textbook.objects.filter(school=school, stock__gt=0).order_by('title')
    bus_routes = BusRoute.objects.filter(school=school).order_by('name')
    hostel_fees = (
        HostelFee.objects.filter(school=school, paid=False)
        .select_related('student__user', 'hostel')
        .order_by('-id')[:400]
    )
    unpaid_school_fees = []
    if is_feature_enabled_for_school(school.pk, "fee_management"):
        unpaid_school_fees = list(
            Fee.objects.filter(
                school=school,
                deleted_at__isnull=True,
                is_active=True,
            )
            .filter(amount__gt=F("amount_paid"))
            .select_related("student__user", "term", "fee_structure")
            .order_by("-created_at")[:400]
        )
    context = {
        'students': students,
        'textbooks': textbooks,
        'bus_routes': bus_routes,
        'hostel_fees': hostel_fees,
        'unpaid_school_fees': unpaid_school_fees,
        'show_hostel_payment': is_feature_enabled_for_school(school.pk, 'hostel'),
        'page_title': 'Record Payment',
    }
    return render(request, 'operations/record_payment.html', context)


@student_required
def my_payments(request):
    """Student or parent view of payments (parent: ?student=<pk> selects child)."""
    student = student_for_portal(request)
    if not student:
        messages.error(request, "No student profile is linked to this account.")
        return redirect("home")

    from finance.models import Fee, FeePayment

    portal_children = _portal_children(request.user)

    # Get school fees
    school_fees = Fee.objects.filter(student=student).order_by('-created_at')
    
    # Calculate totals for school fees
    school_fees_total = sum((fee.amount or Decimal("0")) for fee in school_fees)
    school_fees_outstanding = sum((fee.remaining_balance or Decimal("0")) for fee in school_fees)
    
    # Get canteen payments (completed only for the summary card)
    canteen = CanteenPayment.objects.filter(
        student=student,
        payment_status='completed'
    ).order_by('-payment_date')
    canteen_total = sum((p.amount or Decimal("0")) for p in canteen)
    
    # Get bus payments (completed only)
    bus = BusPayment.objects.filter(
        student=student,
        payment_status='completed'
    ).order_by('-payment_date')
    bus_total = sum((p.amount or Decimal("0")) for p in bus)
    
    # Get textbook sales (completed only)
    textbooks = TextbookSale.objects.filter(
        student=student,
        payment_status='completed'
    ).order_by('-id')
    textbook_total = sum((s.amount or Decimal("0")) for s in textbooks)
    
    # Calculate totals
    total_paid = school_fees_total - school_fees_outstanding + canteen_total + bus_total + textbook_total
    total_pending = school_fees_outstanding
    
    # Get student name for template
    student_name = student.user.get_full_name() if student.user else "Student"
    
    # Paginate bus and canteen payments
    from django.core.paginator import Paginator
    bus_payments_paginator = Paginator(bus, 50)
    canteen_payments_paginator = Paginator(canteen, 50)
    
    bus_payments_page_number = request.GET.get('bus_payments_page')
    canteen_payments_page_number = request.GET.get('canteen_payments_page')
    
    bus_payments_page_obj = bus_payments_paginator.get_page(bus_payments_page_number)
    canteen_payments_page_obj = canteen_payments_paginator.get_page(canteen_payments_page_number)
    
    context = {
        'school_fees': school_fees,
        'school_fees_total': school_fees_total,
        'school_fees_outstanding': school_fees_outstanding,
        'canteen': canteen_payments_page_obj,
        'canteen_total': canteen_total,
        'bus': bus_payments_page_obj,
        'bus_total': bus_total,
        'textbooks': textbooks,
        'textbook_total': textbook_total,
        'total_paid': total_paid,
        'total_pending': total_pending,
        'student_name': student_name,
        'page_title': 'My Payments',
        'portal_children': portal_children,
        'portal_student': student,
        'paystack_public_key': getattr(settings, 'PAYSTACK_PUBLIC_KEY', ''),
        'bus_payments_page_obj': bus_payments_page_obj,
        'canteen_payments_page_obj': canteen_payments_page_obj,
    }
    return render(request, 'operations/my_payments.html', context)


@login_required
def generate_receipt(request, payment_type, payment_id):
    """Generate receipt for a payment."""
    from finance.models import Fee, FeePayment
    
    if payment_type == 'school_fee':
        try:
            payment = FeePayment.objects.get(id=payment_id)
            fee = payment.fee
            student = fee.student
            amount = float(payment.amount)
            date = payment.created_at
            description = f"School Fees - {fee.amount} GHS"
        except FeePayment.DoesNotExist:
            messages.error(request, "Payment not found")
            return redirect('operations:payment_dashboard')
    
    elif payment_type == 'canteen':
        try:
            payment = CanteenPayment.objects.get(id=payment_id)
            student = payment.student
            amount = float(payment.amount)
            date = payment.payment_date
            description = payment.description or "Canteen Purchase"
        except CanteenPayment.DoesNotExist:
            messages.error(request, "Payment not found")
            return redirect('operations:payment_dashboard')
    
    elif payment_type == 'bus':
        try:
            payment = BusPayment.objects.get(id=payment_id)
            student = payment.student
            amount = float(payment.amount)
            date = payment.payment_date
            description = f"Bus Transport - {payment.route.name if payment.route else 'Transport'}"
        except BusPayment.DoesNotExist:
            messages.error(request, "Payment not found")
            return redirect('operations:payment_dashboard')
    
    elif payment_type == 'textbook':
        try:
            payment = TextbookSale.objects.get(id=payment_id)
            student = payment.student
            amount = float(payment.amount)
            date = payment.sale_date
            description = f"Textbook - {payment.textbook.title if payment.textbook else 'Textbook'}"
        except TextbookSale.DoesNotExist:
            messages.error(request, "Payment not found")
            return redirect('operations:payment_dashboard')
    
    else:
        messages.error(request, "Invalid payment type")
        return redirect('operations:payment_dashboard')
    
    sid = student.school_id
    _receipt_feat = {
        "school_fee": "fee_management",
        "canteen": "canteen",
        "bus": "bus_transport",
        "textbook": "textbooks",
    }.get(payment_type)
    if _receipt_feat and not is_feature_enabled_for_school(sid, _receipt_feat):
        messages.error(request, "This feature is disabled for your school.")
        return redirect("operations:payment_dashboard")

    if not user_can_access_student_payment(request.user, student):
        messages.error(request, "Access denied")
        return redirect("operations:my_payments")
    
    # Convert date to datetime for template date formatting compatibility (fixes TypeError with H:i format)
    from datetime import datetime, time
    if not isinstance(date, datetime):
        date = datetime.combine(date, time.min)
    
    # Create mock payment object for template compatibility
    payment = type('DummyPayment', (object,), {
        'id': payment_id,
        'paid_at': date,
        'created_at': date,
        'amount': amount,
        'description': description,
        'fee_type': payment_type,
        'status': 'paid',
        'student': student,
        'method': 'online',
        'reference': None,
        'period_label': None,
        'balance_before': None,
        'balance_after': None,
    })()
    
    school = getattr(request.user, 'school', None) or (student.school if student else None)
    context = {
        'payment': payment,
        'student': student,
        'amount': amount,
        'date': date,
        'description': description,
        'payment_type': payment_type,
        'school': school,
        'has_pdf': False,
        'page_title': 'Payment Receipt',
    }
    return render(request, 'operations/receipt.html', context)


@require_POST
@login_required
def initiate_online_payment(request):
    """Initiate Paystack for school fees (JSON). Matches finance:pay net/gross and pending FeePayment."""
    from decimal import Decimal
    from finance.paystack_service import compute_paystack_gross_from_net

    if not getattr(settings, "PAYSTACK_SECRET_KEY", ""):
        return JsonResponse({"success": False, "error": "Online payments are unavailable."}, status=503)

    fee_id = request.POST.get("fee_id")
    if not fee_id:
        return JsonResponse({"success": False, "error": "Missing fee_id"}, status=400)

    fee_qs = Fee.objects.select_related("student", "school").filter(pk=fee_id)
    user_school = getattr(request.user, "school", None)
    if user_school and not request.user.is_superuser:
        fee_qs = fee_qs.filter(school=user_school)
    fee = fee_qs.first()
    if not fee:
        return JsonResponse({"success": False, "error": "Fee not found"}, status=404)
    if fee.school_id and (
        not is_feature_enabled_for_school(fee.school_id, "online_payments")
        or not is_feature_enabled_for_school(fee.school_id, "fee_management")
    ):
        return JsonResponse(
            {"success": False, "error": "Online school fee payments are not enabled for this school."},
            status=403,
        )
    if not user_can_access_student_payment(request.user, fee.student):
        return JsonResponse({"success": False, "error": "Forbidden"}, status=403)

    if fee.school and not fee.school.is_payout_setup_active:
        return JsonResponse({"success": False, "error": "Online fee payments are not available for this school. The school must complete payout setup first."}, status=403)

    remaining = fee.remaining_balance
    if remaining <= 0:
        return JsonResponse({"success": False, "error": "Fee already paid"}, status=400)

    amount_str = request.POST.get("amount")
    if amount_str:
        try:
            amount = Decimal(str(amount_str))
            if amount <= 0:
                amount = remaining
            elif amount > remaining:
                amount = remaining
        except (ValueError, TypeError):
            amount = remaining
    else:
        amount = remaining

    amount_net, amount_gross = compute_paystack_gross_from_net(amount)
    charge_amount = float(amount_gross)

    stu = fee.student
    su = stu.user if stu else None
    pu = stu.parent if stu else None
    email = (
        (su.email if su and su.email else None)
        or (pu.email if pu and pu.email else None)
        or (request.user.email if request.user.email else None)
        or f"noreply+{fee.id}@mastex.app"
    )

    reference = f"SCHOOL_FEE_{fee.id}_{uuid.uuid4().hex[:8].upper()}"
    callback_url = request.build_absolute_uri(
        reverse("finance:paystack_callback", kwargs={"fee_id": fee.id})
    )

    school_subaccount = None
    if fee.school and fee.school.is_payout_setup_active:
        school_subaccount = fee.school.paystack_subaccount_code

    pending_payment = FeePayment.objects.create(
        fee=fee,
        amount=amount_net,
        gross_amount=amount_gross,
        paystack_reference=reference,
        status="pending",
    )

    currency = getattr(settings, "PAYSTACK_CURRENCY", "GHS")
    result = paystack_service.initialize_payment(
        email=email,
        amount=charge_amount,
        callback_url=callback_url,
        reference=reference,
        metadata={
            "fee_id": fee.id,
            "payment_id": pending_payment.id,
            "payment_type": "school_fee",
            "student_name": str(stu),
            "school_name": fee.school.name if fee.school else "",
            "school_id": fee.school.id if fee.school else None,
            "amount_net": float(amount_net),
            "amount_gross": float(amount_gross),
        },
        subaccount=school_subaccount,
        currency=currency,
    )

    if result.get("status") and result.get("data", {}).get("authorization_url"):
        nxt = safe_internal_redirect_path(request.POST.get("next"))
        if nxt:
            request.session[FEE_PAYSTACK_RETURN_SESSION_KEY] = nxt
        return JsonResponse(
            {
                "success": True,
                "authorization_url": result["data"]["authorization_url"],
                "reference": reference,
            }
        )

    pending_payment.status = "failed"
    pending_payment.save()
    return JsonResponse(
        {
            "success": False,
            "error": result.get("message", "Payment initialization failed"),
        }
    )


@login_required
def paystack_callback(request, fee_id):
    """Legacy portal callback – delegate to finance handler to keep logic consistent."""
    from finance import views as finance_views

    return finance_views.paystack_callback(request, fee_id)


@csrf_exempt
@require_POST
def paystack_webhook(request):
    """
    Legacy URL: /operations/payments/paystack/webhook/

    Delegates to ``finance.views.paystack_webhook`` so behaviour matches
    ``/finance/paystack-webhook/`` (HMAC verified with ``PAYSTACK_SECRET_KEY``,
    or ``PAYSTACK_WEBHOOK_SECRET`` if set),
    atomic school-fee completion (net amount, pending row, select_for_update),
    and safer textbook stock updates under lock.
    """
    from finance import views as finance_views

    return finance_views.paystack_webhook(request)


@login_required
def send_payment_reminder(request):
    """Send payment reminder to parents/students via SMS."""
    from services.sms_service import SMSService
    
    school = getattr(request.user, 'school', None)
    if not school:
        messages.error(request, "School not found")
        return redirect('accounts:dashboard')

    if (redir := require_feature(request, "fee_management", "accounts:dashboard", school=school)):
        return redir
    if (redir := require_feature(request, "messaging", "accounts:dashboard", school=school)):
        return redir
    
    if request.method == 'POST':
        student_ids = request.POST.getlist('student_ids')
        
        if not student_ids:
            messages.error(request, "No students selected")
            return redirect('operations:payment_dashboard')
        
        from django.core.cache import cache

        from finance.models import Fee

        sent_count = 0
        skipped_throttle = 0
        reminder_cooldown = 3 * 24 * 3600  # 3 days per student per school

        for student_id in student_ids:
            try:
                student = Student.objects.get(id=student_id, school=school)
                fees = Fee.objects.filter(student=student, paid=False)

                if not fees.exists():
                    continue

                total_pending = sum((f.remaining_balance or Decimal("0")) for f in fees)

                parent_phone = None
                if student.parent and student.parent.phone:
                    parent_phone = student.parent.phone

                if parent_phone:
                    throttle_key = f"fee_reminder_sms:{school.pk}:{student.pk}"
                    if cache.get(throttle_key):
                        skipped_throttle += 1
                        continue

                    sms_message = (
                        f"Dear Parent/Guardian of {student.user.get_full_name()}, this is a reminder that "
                        f"there are pending fees of GHS {total_pending} for the current term. "
                        f"Please make payments at your earliest convenience to avoid disruption. "
                        f"Best regards, {school.name}"
                    )

                    try:
                        SMSService.send_sms(parent_phone, sms_message, school.name)
                        cache.set(throttle_key, 1, reminder_cooldown)
                        sent_count += 1
                    except Exception:
                        pass

            except Student.DoesNotExist:
                continue

        if sent_count:
            messages.success(request, f"Reminder SMS sent for {sent_count} student(s).")
        if skipped_throttle:
            messages.info(
                request,
                f"Skipped {skipped_throttle} student(s): a reminder was already sent in the last 3 days.",
            )
        if not sent_count and not skipped_throttle:
            messages.warning(request, "No reminders sent (no parent phone or no unpaid fees).")

        return redirect('operations:payment_dashboard')
    
    # Get students with pending fees
    pending_fees = Fee.objects.filter(school=school, paid=False).select_related('student')
    students_with_pending = Student.objects.filter(
        id__in=pending_fees.values_list('student_id', flat=True).distinct()
    ).order_by('full_name')
    
    context = {
        'students': students_with_pending,
        'page_title': 'Send Payment Reminder',
    }
    return render(request, 'operations/payment_dashboard.html', context)


@login_required
@require_POST
def cancel_pending_payment(request):
    """Cancel a pending canteen/bus/textbook/hostel payment if the user may act for that student."""
    try:
        purchase_id = request.POST.get('purchase_id')
        payment_type = request.POST.get('payment_type')

        if not purchase_id or not payment_type:
            return JsonResponse({'success': False, 'error': 'Missing purchase_id or payment_type'}, status=400)

        if payment_type == 'canteen':
            try:
                payment = CanteenPayment.objects.select_related('student').get(
                    id=purchase_id, payment_status='pending'
                )
            except CanteenPayment.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Canteen payment not found'}, status=404)
            if not user_can_access_student_payment(request.user, payment.student):
                return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)
            payment.delete()
            return JsonResponse({'success': True, 'message': 'Pending payment cancelled successfully'})

        if payment_type == 'bus':
            try:
                payment = BusPayment.objects.select_related('student').get(
                    id=purchase_id, payment_status='pending'
                )
            except BusPayment.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Bus payment not found'}, status=404)
            if not user_can_access_student_payment(request.user, payment.student):
                return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)
            payment.delete()
            return JsonResponse({'success': True, 'message': 'Pending payment cancelled successfully'})

        if payment_type == 'textbook':
            try:
                payment = TextbookSale.objects.select_related('student').get(
                    id=purchase_id, payment_status='pending'
                )
            except TextbookSale.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Textbook payment not found'}, status=404)
            if not user_can_access_student_payment(request.user, payment.student):
                return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)
            payment.delete()
            return JsonResponse({'success': True, 'message': 'Pending payment cancelled successfully'})

        if payment_type == 'hostel':
            try:
                fee = HostelFee.objects.select_related('student').get(
                    id=purchase_id, payment_status='pending'
                )
            except HostelFee.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Hostel payment not found'}, status=404)
            if not user_can_access_student_payment(request.user, fee.student):
                return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)
            fee.payment_status = 'cancelled'
            fee.save(update_fields=['payment_status'])
            return JsonResponse({'success': True, 'message': 'Pending payment cancelled successfully'})

        return JsonResponse({'success': False, 'error': f'Invalid payment type: {payment_type}'}, status=400)

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
