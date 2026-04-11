"""
Payment Views for Canteen, Bus, Textbooks, and Hostel with Paystack Integration
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.conf import settings
import uuid

from accounts.decorators import login_required, parent_required, student_required
from accounts.permissions import user_can_manage_school

from students.models import Student
from schools.models import School
from .models import CanteenItem, CanteenPayment, BusRoute, BusPayment, Textbook, TextbookSale, HostelFee
from finance.paystack_service import paystack_service
from finance.models import Fee, FeePayment
from core.utils import FEE_PAYSTACK_RETURN_SESSION_KEY, safe_internal_redirect_path


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
    """Students linked to a parent user (stable ordering)."""
    if getattr(user, "role", None) != "parent":
        return []
    return list(
        user.children.select_related("user", "school").order_by("class_name", "admission_number")
    )


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
    if role == "parent" and student.parent_id == user.id:
        return True
    school = getattr(user, "school", None)
    if school and student.school_id == school.id:
        if user_can_manage_school(user):
            return True
    return False


# ==================== CANTEEN PAYMENTS ====================

@student_required
def canteen_my(request):
    """Student view to browse and purchase canteen items."""
    student = student_for_portal(request)
    if not student:
        messages.error(request, "No student profile is linked to this account.")
        return redirect("home")

    school = student.school

    # Get available canteen items
    items = CanteenItem.objects.filter(school=school, is_available=True)

    # Get student's payment history (only completed payments)
    my_payments = CanteenPayment.objects.filter(
        student=student,
        payment_status='completed'
    )[:20]

    # Get pending payments
    pending_payments = CanteenPayment.objects.filter(
        student=student,
        payment_status='pending'
    )

    from django.conf import settings
    portal_children = _portal_children(request.user)
    context = {
        'items': items,
        'my_payments': my_payments,
        'pending_payments': pending_payments,
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
    
    item_id = request.POST.get('item_id')
    quantity = int(request.POST.get('quantity', 1))
    payment_method = request.POST.get('payment_method', 'card')
    
    try:
        item = CanteenItem.objects.get(id=item_id, school=student.school, is_available=True)
    except CanteenItem.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Item not found'}, status=404)
    
    total_amount = float(item.price) * quantity
    
    # Create pending payment record
    payment = CanteenPayment.objects.create(
        school=student.school,
        student=student,
        amount=total_amount,
        description=f"{item.name} x{quantity}",
        payment_status='pending'
    )
    
    # Generate unique reference
    reference = f"CANTEEN_{uuid.uuid4().hex[:12].upper()}"
    payment.payment_reference = reference
    payment.save()
    
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
    if school and hasattr(school, 'paystack_subaccount_code') and school.paystack_subaccount_code:
        school_subaccount = school.paystack_subaccount_code
    
    # Get currency from settings
    from django.conf import settings
    currency = getattr(settings, 'PAYSTACK_CURRENCY', 'GHS')
    
    result = paystack_service.initialize_payment(
        email=parent_email or student.user.email,
        amount=total_amount,
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
        payment.payment_status = 'failed'
        payment.save()
        return JsonResponse({
            'success': False,
            'error': result.get('message', 'Payment initialization failed')
        })


def canteen_payment_verify(request):
    """Verify Paystack payment for canteen."""
    # First try to find by payment_id from query parameter (most reliable)
    payment_id = request.GET.get('payment_id')
    
    if payment_id:
        try:
            payment = CanteenPayment.objects.get(id=payment_id)
            if payment.payment_status == 'completed':
                messages.info(request, "Payment already confirmed.")
                return redirect('operations:canteen_my')
        except CanteenPayment.DoesNotExist:
            pass
    
    reference = request.GET.get('reference')
    result = paystack_service.verify_payment(reference) if reference else None
    
    payment = None
    
    # Try to find by payment_id
    if payment_id:
        try:
            payment = CanteenPayment.objects.get(id=payment_id)
        except CanteenPayment.DoesNotExist:
            pass
    
    # Fallback: try to find by payment_reference
    if not payment and reference:
        try:
            payment = CanteenPayment.objects.get(payment_reference=reference)
        except CanteenPayment.DoesNotExist:
            pass
    
    if payment:
        if result and result.get('status') and result['data']['status'] == 'success':
            payment.payment_status = 'completed'
            payment.save()
            messages.success(request, "Payment successful! Your order has been placed.")
        else:
            payment.payment_status = 'failed'
            payment.save()
            messages.error(request, "Payment failed. Please try again.")
    else:
        messages.error(request, "Payment record not found")
    
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

    # Get all bus routes with fees
    routes = BusRoute.objects.filter(school=school)

    # Get student's payment records
    my_payments = BusPayment.objects.filter(
        student=student,
        payment_status='completed'
    ).select_related('route')[:20]

    # Get pending payments
    pending_payments = BusPayment.objects.filter(
        student=student,
        payment_status='pending'
    )

    from django.conf import settings
    portal_children = _portal_children(request.user)
    context = {
        'routes': routes,
        'my_payments': my_payments,
        'pending_payments': pending_payments,
        'page_title': 'Transport',
        'paystack_public_key': getattr(settings, 'PAYSTACK_PUBLIC_KEY', ''),
        'portal_children': portal_children,
        'portal_student': student,
        'mode': 'parent' if getattr(request.user, 'role', None) == 'parent' else 'student',
        'children': portal_children,
    }
    return render(request, 'operations/bus_my.html', context)


@login_required
@require_POST
def bus_initiate_payment(request):
    """Initiate Paystack payment for bus/transport."""
    student, err = authorized_student_for_payment_post(request)
    if err:
        return err
    
    route_id = request.POST.get('route_id')
    term = request.POST.get('term', f'Term {timezone.now().year}')
    payment_method = request.POST.get('payment_method', 'card')
    
    try:
        route = BusRoute.objects.get(id=route_id, school=student.school)
    except BusRoute.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Route not found'}, status=404)
    
    # Check if already paid for this term
    existing = BusPayment.objects.filter(
        student=student,
        route=route,
        term_period=term,
        payment_status='completed'
    ).exists()
    
    if existing:
        return JsonResponse({'success': False, 'error': 'Already paid for this term'}, status=400)
    amount = float(route.fee_per_term)
    
    # Create pending payment record
    payment = BusPayment.objects.create(
        school=student.school,
        student=student,
        route=route,
        amount=amount,
        term_period=term,
        payment_status='pending'
    )
    
    # Generate unique reference
    reference = f"BUS_{uuid.uuid4().hex[:12].upper()}"
    payment.payment_reference = reference
    payment.save()
    
    # Get parent email using helper function
    parent_email = _get_parent_email(student, request)
    
    if not parent_email and request.user.email:
        parent_email = request.user.email
    
    # Build callback URL
    callback_url = request.build_absolute_uri(reverse('operations:bus_payment_verify'))
    
    metadata = {
        'payment_type': 'bus',
        'payment_id': str(payment.id),
        'route_name': route.name,
        'term': term,
        'student_name': student.user.get_full_name()
    }
    
    # Get school's subaccount if configured
    school = student.school
    school_subaccount = None
    if school and hasattr(school, 'paystack_subaccount_code') and school.paystack_subaccount_code:
        school_subaccount = school.paystack_subaccount_code
    
    # Get currency from settings
    from django.conf import settings
    currency = getattr(settings, 'PAYSTACK_CURRENCY', 'GHS')
    
    # Build callback URL with payment_id as query parameter for reliable lookup
    callback_url = request.build_absolute_uri(
        reverse('operations:bus_payment_verify') + f"?payment_id={payment.id}"
    )
    
    result = paystack_service.initialize_payment(
        email=parent_email or student.user.email,
        amount=amount,
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
        })
    else:
        payment.payment_status = 'failed'
        payment.save()
        return JsonResponse({
            'success': False,
            'error': result.get('message', 'Payment initialization failed')
        })


def bus_payment_verify(request):
    """Verify Paystack payment for bus."""
    # First try to find by payment_id from query parameter (most reliable)
    payment_id = request.GET.get('payment_id')
    
    if payment_id:
        try:
            payment = BusPayment.objects.get(id=payment_id)
            if payment.payment_status == 'completed':
                messages.info(request, "Payment already confirmed.")
                return redirect('operations:bus_my')
        except BusPayment.DoesNotExist:
            pass
    
    reference = request.GET.get('reference')
    result = paystack_service.verify_payment(reference) if reference else None
    
    payment = None
    
    # Try to find by payment_id
    if payment_id:
        try:
            payment = BusPayment.objects.get(id=payment_id)
        except BusPayment.DoesNotExist:
            pass
    
    # Fallback: try to find by payment_reference
    if not payment and reference:
        try:
            payment = BusPayment.objects.get(payment_reference=reference)
        except BusPayment.DoesNotExist:
            pass
    
    if payment:
        if result and result.get('status') and result['data']['status'] == 'success':
            payment.payment_status = 'completed'
            payment.paid = True
            payment.payment_date = timezone.now().date()
            payment.save()
            messages.success(request, "Payment successful! Your bus pass is now active.")
        else:
            payment.payment_status = 'failed'
            payment.save()
            messages.error(request, "Payment failed. Please try again.")
    else:
        messages.error(request, "Payment record not found")
    
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

    # Get available textbooks
    textbooks = Textbook.objects.filter(school=school, stock__gt=0)

    # Get student's purchase history
    my_purchases = TextbookSale.objects.filter(
        student=student,
        payment_status='completed'
    )[:20]

    # Get pending purchases
    pending_purchases = TextbookSale.objects.filter(
        student=student,
        payment_status='pending'
    )

    from django.conf import settings
    portal_children = _portal_children(request.user)
    context = {
        'textbooks': textbooks,
        'my_purchases': my_purchases,
        'pending_purchases': pending_purchases,
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
    
    textbook_id = request.POST.get('textbook_id')
    quantity = int(request.POST.get('quantity', 1))
    
    try:
        textbook = Textbook.objects.get(id=textbook_id, school=student.school, stock__gte=quantity)
    except Textbook.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Textbook not found or insufficient stock'}, status=404)
    
    total_amount = float(textbook.price) * quantity
    
    # Create pending sale record
    sale = TextbookSale.objects.create(
        school=student.school,
        student=student,
        textbook=textbook,
        quantity=quantity,
        amount=total_amount,
        payment_status='pending'
    )
    
    # Generate unique reference
    reference = f"TEXTBOOK_{uuid.uuid4().hex[:12].upper()}"
    sale.payment_reference = reference
    sale.save()
    
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
    if school and hasattr(school, 'paystack_subaccount_code') and school.paystack_subaccount_code:
        school_subaccount = school.paystack_subaccount_code
    
    # Get currency from settings
    from django.conf import settings
    currency = getattr(settings, 'PAYSTACK_CURRENCY', 'GHS')
    
    result = paystack_service.initialize_payment(
        email=parent_email or student.user.email,
        amount=total_amount,
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
        sale.payment_status = 'failed'
        sale.save()
        return JsonResponse({
            'success': False,
            'error': result.get('message', 'Payment initialization failed')
        })


def textbook_payment_verify(request):
    """Verify Paystack payment for textbooks."""
    # First try to find by payment_id from query parameter (most reliable)
    payment_id = request.GET.get('payment_id')
    
    if payment_id:
        try:
            sale = TextbookSale.objects.get(id=payment_id)
            if sale.payment_status == 'completed':
                messages.info(request, "Payment already confirmed.")
                return redirect('operations:textbook_my')
        except TextbookSale.DoesNotExist:
            pass
    
    reference = request.GET.get('reference')
    result = paystack_service.verify_payment(reference) if reference else None
    
    sale = None
    
    # Try to find by payment_id
    if payment_id:
        try:
            sale = TextbookSale.objects.get(id=payment_id)
        except TextbookSale.DoesNotExist:
            pass
    
    # Fallback: try to find by payment_reference
    if not sale and reference:
        try:
            sale = TextbookSale.objects.get(payment_reference=reference)
        except TextbookSale.DoesNotExist:
            pass
    
    if sale:
        if result and result.get('status') and result['data']['status'] == 'success':
            sale.payment_status = 'completed'
            sale.save()
            # Reduce stock
            if sale.textbook:
                sale.textbook.stock -= sale.quantity
                sale.textbook.save()
            messages.success(request, "Payment successful! Your textbook(s) have been reserved.")
        else:
            sale.payment_status = 'failed'
            sale.save()
            messages.error(request, "Payment failed. Please try again.")
    else:
        messages.error(request, "Payment record not found")
    
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

    if fee.payment_status == 'completed' or fee.paid:
        return JsonResponse({'success': False, 'error': 'Already paid'}, status=400)

    amount = float(fee.amount)

    # Generate unique reference
    reference = f"HOSTEL_{uuid.uuid4().hex[:12].upper()}"
    fee.payment_reference = reference
    fee.payment_status = 'pending'
    fee.save()

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
        'student_name': student.user.get_full_name()
    }

    # Get school's subaccount if configured
    school = student.school
    school_subaccount = None
    if school and hasattr(school, 'paystack_subaccount_code') and school.paystack_subaccount_code:
        school_subaccount = school.paystack_subaccount_code
    
    # Get currency from settings
    from django.conf import settings
    currency = getattr(settings, 'PAYSTACK_CURRENCY', 'GHS')
    
    result = paystack_service.initialize_payment(
        email=parent_email or student.user.email,
        amount=amount,
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
            'payment_id': fee.id  # Return payment_id for reliable lookup
        })
    else:
        fee.payment_status = 'failed'
        fee.save()
        return JsonResponse({
            'success': False,
            'error': result.get('message', 'Payment initialization failed')
        })


def hostel_payment_verify(request):
    """Verify Paystack payment for hostel fees."""
    # First try to find by payment_id from query parameter (most reliable)
    payment_id = request.GET.get('payment_id')
    
    if payment_id:
        try:
            fee = HostelFee.objects.get(id=payment_id)
            if fee.payment_status == 'completed':
                messages.info(request, "Payment already confirmed.")
                return redirect('operations:hostel_my')
        except HostelFee.DoesNotExist:
            pass
    
    reference = request.GET.get('reference')
    result = paystack_service.verify_payment(reference) if reference else None
    
    fee = None
    
    # Try to find by payment_id
    if payment_id:
        try:
            fee = HostelFee.objects.get(id=payment_id)
        except HostelFee.DoesNotExist:
            pass
    
    # Fallback: try to find by payment_reference
    if not fee and reference:
        try:
            fee = HostelFee.objects.get(payment_reference=reference)
        except HostelFee.DoesNotExist:
            pass
    
    if fee:
        if result and result.get('status') and result['data']['status'] == 'success':
            fee.payment_status = 'completed'
            fee.paid = True
            fee.payment_date = timezone.now().date()
            fee.save()
            messages.success(request, "Payment successful! Your hostel fee is now cleared.")
        else:
            fee.payment_status = 'failed'
            fee.save()
            messages.error(request, "Payment failed. Please try again.")
    else:
        messages.error(request, "Payment record not found")
    
    return redirect('operations:hostel_my')


# ==================== GENERAL PAYMENT DASHBOARD ====================

@login_required
def payment_dashboard(request):
    """Admin dashboard showing all payments across the system."""
    school = getattr(request.user, 'school', None)
    if not school:
        messages.error(request, "School not found")
        return redirect('accounts:dashboard')
    
    # Get filter parameters
    date_filter = request.GET.get('date_filter', 'all')
    payment_type = request.GET.get('payment_type', 'all')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    # Base queryset for fees
    from finance.models import Fee
    fees = Fee.objects.filter(school=school).select_related('student')
    
    # Filter by date
    if date_filter == 'today':
        from django.utils import timezone
        today = timezone.now().date()
        fees = fees.filter(created_at__date=today)
    elif date_filter == 'week':
        from django.utils import timezone
        week_ago = timezone.now() - timezone.timedelta(days=7)
        fees = fees.filter(created_at__gte=week_ago)
    elif date_filter == 'month':
        from django.utils import timezone
        month_ago = timezone.now() - timezone.timedelta(days=30)
        fees = fees.filter(created_at__gte=month_ago)
    
    if start_date:
        fees = fees.filter(created_at__date__gte=start_date)
    if end_date:
        fees = fees.filter(created_at__date__lte=end_date)
    
    # Get payment counts
    total_fees = fees.count()
    paid_fees = fees.filter(paid=True).count()
    pending_fees = total_fees - paid_fees
    
    # Get amounts
    total_amount = sum(float(f.amount) for f in fees)
    total_collected = sum(float(f.amount_paid) for f in fees)
    
    # Get other payments (canteen, bus, textbook) with date filtering
    canteen_payments = CanteenPayment.objects.filter(school=school).select_related('student', 'student__user', 'recorded_by')
    bus_payments = BusPayment.objects.filter(school=school).select_related('student', 'student__user', 'route')
    textbook_sales = TextbookSale.objects.filter(school=school).select_related('student', 'student__user', 'textbook')
    hostel_fees = HostelFee.objects.filter(school=school).select_related('student', 'student__user')
    
    # Apply date filtering to other payments
    from django.utils import timezone
    if date_filter == 'today':
        today = timezone.now().date()
        canteen_payments = canteen_payments.filter(payment_date=today)
        bus_payments = bus_payments.filter(payment_date=today)
        textbook_sales = textbook_sales.filter(sale_date=today)
        hostel_fees = hostel_fees.filter(payment_date=today)
    elif date_filter == 'week':
        week_ago = timezone.now() - timezone.timedelta(days=7)
        canteen_payments = canteen_payments.filter(payment_date__gte=week_ago)
        bus_payments = bus_payments.filter(payment_date__gte=week_ago)
        textbook_sales = textbook_sales.filter(sale_date__gte=week_ago)
        hostel_fees = hostel_fees.filter(payment_date__gte=week_ago)
    elif date_filter == 'month':
        month_ago = timezone.now() - timezone.timedelta(days=30)
        canteen_payments = canteen_payments.filter(payment_date__gte=month_ago)
        bus_payments = bus_payments.filter(payment_date__gte=month_ago)
        textbook_sales = textbook_sales.filter(sale_date__gte=month_ago)
        hostel_fees = hostel_fees.filter(payment_date__gte=month_ago)
    
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
    canteen_total_all = sum(float(p.amount) for p in canteen_payments.filter(payment_status='completed'))
    bus_total_all = sum(float(p.amount) for p in bus_payments.filter(paid=True))
    textbook_total_all = sum(float(s.amount) for s in textbook_sales.filter(payment_status='completed'))
    hostel_total_all = sum(float(f.amount) for f in hostel_fees.filter(paid=True))
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
                'date': f.created_at,
                'type': 'School Fee',
                'amount': float(f.amount_paid),
                'description': f.term or 'School Fee',
            })
    
    if payment_type in ['all', 'canteen']:
        for p in canteen_filtered:
            recent_payments.append({
                'student': p.student,
                'date': p.payment_date,
                'type': 'Canteen',
                'amount': float(p.amount),
                'description': p.description,
                'id': p.id,
            })
    
    if payment_type in ['all', 'bus']:
        for p in bus_filtered:
            recent_payments.append({
                'student': p.student,
                'date': p.payment_date,
                'type': 'Bus',
                'amount': float(p.amount),
                'description': p.route.name if p.route else 'Bus Fee',
                'id': p.id,
            })
    
    if payment_type in ['all', 'textbook']:
        for s in textbook_filtered:
            recent_payments.append({
                'student': s.student,
                'date': s.sale_date,
                'type': 'Textbook',
                'amount': float(s.amount),
                'description': s.textbook.title if s.textbook else 'Textbook',
                'id': s.id,
            })
    
    if payment_type in ['all', 'hostel']:
        for h in hostel_filtered:
            recent_payments.append({
                'student': h.student,
                'date': h.payment_date,
                'type': 'Hostel',
                'amount': float(h.amount),
                'description': f"Hostel Fee - {h.term}" if h.term else 'Hostel Fee',
                'id': h.id,
            })
    
    # Sort by date descending
    recent_payments.sort(key=lambda x: x['date'] if x['date'] else timezone.now(), reverse=True)
    recent_payments = recent_payments[:50]  # Limit to 50 most recent
    
    # Count variables for template
    canteen_count = canteen_filtered.count()
    bus_count = bus_filtered.count()
    bus_paid = bus_filtered.count()
    bus_unpaid = bus_payments.filter(paid=False).count()
    textbook_count = textbook_filtered.count()
    
    context = {
        'fees': school_fees_filtered[:20],
        'school_fees': school_fees_filtered[:20],
        'canteen_payments': canteen_filtered,
        'bus_payments': bus_payments,
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
        'outstanding_students': [],
    }
    return render(request, 'operations/payment_dashboard.html', context)


@login_required
def student_payment_history(request, student_id):
    """View payment history for a specific student."""
    from finance.models import Fee, FeePayment
    
    student = get_object_or_404(Student, id=student_id)
    school = getattr(request.user, 'school', None)
    
    if school and student.school != school:
        messages.error(request, "Student not found")
        return redirect('operations:payment_dashboard')
    
    # Get all fees for student
    fees = Fee.objects.filter(student=student).order_by('-created_at')
    
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
    canteen_payments = CanteenPayment.objects.filter(student=student).order_by('-created_at')
    for payment in canteen_payments:
        all_payments.append({
            'type': 'canteen',
            'payment': payment,
            'amount': float(payment.amount),
            'status': payment.payment_status,
            'date': payment.created_at,
        })
    
    # Get bus payments
    bus_payments = BusPayment.objects.filter(student=student).order_by('-created_at')
    for payment in bus_payments:
        all_payments.append({
            'type': 'bus',
            'payment': payment,
            'amount': float(payment.amount),
            'status': payment.payment_status,
            'date': payment.created_at,
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
    
    # Sort by date (handle None dates)
    all_payments.sort(key=lambda x: x['date'] or timezone.now().date(), reverse=True)
    
    # Calculate totals
    total_paid = sum(p['amount'] for p in all_payments if p['status'] == 'completed')
    total_pending = sum(p['amount'] for p in all_payments if p['status'] == 'pending')
    
    context = {
        'student': student,
        'payments': all_payments,
        'fees': fees,
        'total_paid': total_paid,
        'total_pending': total_pending,
        'page_title': f'Payment History - {student.user.get_full_name()}',
    }
    return render(request, 'operations/student_payment_history.html', context)


@login_required
def record_payment(request):
    """Manually record a payment for a student."""
    from finance.models import Fee, FeePayment
    
    school = getattr(request.user, 'school', None)
    if not school:
        messages.error(request, "School not found")
        return redirect('accounts:dashboard')
    
    if request.method == 'POST':
        student_id = request.POST.get('student_id')
        fee_id = request.POST.get('fee_id')
        amount = request.POST.get('amount')
        payment_method = request.POST.get('payment_method', 'cash')
        
        try:
            student = Student.objects.get(id=student_id, school=school)
            fee = Fee.objects.get(id=fee_id, student=student)
            
            amount_decimal = float(amount)
            
            if amount_decimal <= 0:
                messages.error(request, "Amount must be positive")
                return redirect('operations:record_payment')
            
            # Create payment record
            payment = FeePayment.objects.create(
                fee=fee,
                amount=amount_decimal,
                payment_method=payment_method,
                status='completed'
            )
            
            # Update fee
            fee.amount_paid += amount_decimal
            fee.save()
            
            messages.success(request, f"Payment of GHS {amount} recorded successfully")
            return redirect('operations:student_payment_history', student_id=student.id)
            
        except (Student.DoesNotExist, Fee.DoesNotExist) as e:
            messages.error(request, "Student or fee not found")
        except ValueError:
            messages.error(request, "Invalid amount")
    
    # Get students for dropdown
    students = Student.objects.filter(school=school, status='active').select_related('user').order_by('user__first_name')
    
    context = {
        'students': students,
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
    school_fees_total = sum(float(fee.amount) for fee in school_fees)
    school_fees_outstanding = sum(float(fee.remaining_balance) for fee in school_fees)
    
    # Get canteen payments (completed only for the summary card)
    canteen = CanteenPayment.objects.filter(
        student=student,
        payment_status='completed'
    ).order_by('-payment_date')
    canteen_total = sum(float(p.amount) for p in canteen)
    
    # Get bus payments (completed only)
    bus = BusPayment.objects.filter(
        student=student,
        payment_status='completed'
    ).order_by('-payment_date')
    bus_total = sum(float(p.amount) for p in bus)
    
    # Get textbook sales (completed only)
    textbooks = TextbookSale.objects.filter(
        student=student,
        payment_status='completed'
    ).order_by('-id')
    textbook_total = sum(float(s.amount) for s in textbooks)
    
    # Calculate totals
    total_paid = school_fees_total - school_fees_outstanding + canteen_total + bus_total + textbook_total
    total_pending = school_fees_outstanding
    
    # Get student name for template
    student_name = student.user.get_full_name() if student.user else "Student"
    
    context = {
        'school_fees': school_fees,
        'school_fees_total': school_fees_total,
        'school_fees_outstanding': school_fees_outstanding,
        'canteen': canteen,
        'canteen_total': canteen_total,
        'bus': bus,
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
    
    if not user_can_access_student_payment(request.user, student):
        messages.error(request, "Access denied")
        return redirect("operations:my_payments")
    
    context = {
        'student': student,
        'amount': amount,
        'date': date,
        'description': description,
        'payment_type': payment_type,
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

    fee = get_object_or_404(Fee, id=fee_id)
    if not user_can_access_student_payment(request.user, fee.student):
        return JsonResponse({"success": False, "error": "Forbidden"}, status=403)

    remaining = float(fee.remaining_balance)
    if remaining <= 0:
        return JsonResponse({"success": False, "error": "Fee already paid"}, status=400)

    amount_str = request.POST.get("amount")
    if amount_str:
        try:
            amount = float(amount_str)
            if amount <= 0:
                amount = remaining
            elif amount > remaining:
                amount = remaining
        except (ValueError, TypeError):
            amount = remaining
    else:
        amount = remaining

    amount_net, amount_gross = compute_paystack_gross_from_net(Decimal(str(amount)))
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
    if fee.school and fee.school.paystack_subaccount_code:
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
    """Handle Paystack payment callback for school fees."""
    from finance.models import Fee, FeePayment
    
    reference = request.GET.get('reference')
    
    if not reference:
        messages.error(request, "Invalid payment reference")
        return redirect('operations:my_payments')
    
    # Verify with Paystack
    result = paystack_service.verify_payment(reference)
    
    try:
        fee = Fee.objects.get(id=fee_id)
        
        if result.get('status') and result['data']['status'] == 'success':
            # Create payment record
            amount = float(result['data']['amount']) / 100  # Paystack returns kobo
            
            payment = FeePayment.objects.create(
                fee=fee,
                amount=amount,
                paystack_reference=reference,
                payment_method='card',
                status='completed'
            )
            
            # Update fee
            fee.amount_paid += amount
            fee.paystack_reference = reference
            
            # Check if fee is fully paid
            if fee.amount_paid >= fee.amount:
                fee.status = 'paid'
            
            fee.save()
            
            messages.success(request, "Payment successful!")
            return redirect('operations:my_payments')
        else:
            messages.error(request, "Payment failed. Please try again.")
            return redirect('operations:my_payments')
            
    except Fee.DoesNotExist:
        messages.error(request, "Fee record not found")
        return redirect('operations:my_payments')


@csrf_exempt
@require_POST
def paystack_webhook(request):
    """
    Handle Paystack webhook for payment notifications.
    This ensures payments are recorded even if the user closes the browser
    before being redirected back to the site.
    """
    import json
    import logging
    from django.conf import settings as _settings

    logger = logging.getLogger(__name__)

    secret = getattr(_settings, "PAYSTACK_WEBHOOK_SECRET", "") or getattr(_settings, "PAYSTACK_SECRET_KEY", "")
    if not secret:
        logger.error("Paystack webhook secret not configured")
        return JsonResponse({"error": "Server misconfigured"}, status=500)

    signature = request.headers.get("X-Paystack-Signature", "")
    if not signature:
        return JsonResponse({"error": "Missing signature"}, status=400)

    from finance.paystack_service import paystack_service
    if not paystack_service.verify_webhook_signature(request.body, signature, secret):
        logger.warning("Paystack webhook: invalid HMAC signature")
        return JsonResponse({"error": "Invalid signature"}, status=403)

    try:
        body = request.body
        data = json.loads(body)
        
        event = data.get('event')
        logger.info("Paystack webhook received: event=%s", event)
        
        if event == 'charge.success':
            # Get payment reference from metadata
            metadata = data.get('metadata', {})
            payment_type = metadata.get('payment_type')
            reference = data.get('data', {}).get('reference')
            
            logger.info(f"Processing payment: type={payment_type}, reference={reference}")
            
            if payment_type == 'school_fee':
                fee_id = metadata.get('fee_id')
                if fee_id:
                    try:
                        fee = Fee.objects.get(id=fee_id)
                        amount = float(data.get('data', {}).get('amount', 0)) / 100
                        
                        # Check if payment already exists to avoid duplicates
                        existing = FeePayment.objects.filter(paystack_reference=reference).exists()
                        if not existing:
                            payment = FeePayment.objects.create(
                                fee=fee,
                                amount=amount,
                                paystack_reference=reference,
                                payment_method='card',
                                status='completed'
                            )
                            
                            fee.amount_paid += amount
                            fee.save()
                            logger.info(f"School fee payment recorded: fee_id={fee_id}, amount={amount}")
                        else:
                            logger.info(f"Payment already processed: reference={reference}")
                            
                    except Fee.DoesNotExist:
                        logger.error(f"Fee not found: fee_id={fee_id}")
            
            elif payment_type == 'canteen':
                payment_id = metadata.get('payment_id')
                if payment_id:
                    try:
                        payment = CanteenPayment.objects.get(id=payment_id)
                        if payment.payment_status != 'completed':
                            payment.payment_status = 'completed'
                            payment.payment_date = timezone.now().date()
                            payment.save()
                            logger.info(f"Canteen payment completed: payment_id={payment_id}")
                        else:
                            logger.info(f"Canteen payment already completed: payment_id={payment_id}")
                    except CanteenPayment.DoesNotExist:
                        logger.error(f"Canteen payment not found: payment_id={payment_id}")
            
            elif payment_type == 'bus':
                payment_id = metadata.get('payment_id')
                if payment_id:
                    try:
                        payment = BusPayment.objects.get(id=payment_id)
                        if payment.payment_status != 'completed':
                            payment.payment_status = 'completed'
                            payment.paid = True
                            payment.payment_date = timezone.now().date()
                            payment.save()
                            logger.info(f"Bus payment completed: payment_id={payment_id}")
                        else:
                            logger.info(f"Bus payment already completed: payment_id={payment_id}")
                    except BusPayment.DoesNotExist:
                        logger.error(f"Bus payment not found: payment_id={payment_id}")
            
            elif payment_type == 'textbook':
                payment_id = metadata.get('payment_id')
                if payment_id:
                    try:
                        sale = TextbookSale.objects.get(id=payment_id)
                        if sale.payment_status != 'completed':
                            sale.payment_status = 'completed'
                            sale.save()
                            # Reduce textbook stock
                            if sale.textbook:
                                sale.textbook.stock -= sale.quantity
                                sale.textbook.save()
                                logger.info(f"Textbook stock reduced: textbook_id={sale.textbook.id}, quantity={sale.quantity}")
                            logger.info(f"Textbook sale completed: sale_id={payment_id}")
                        else:
                            logger.info(f"Textbook sale already completed: sale_id={payment_id}")
                    except TextbookSale.DoesNotExist:
                        logger.error(f"Textbook sale not found: sale_id={payment_id}")
            
            elif payment_type == 'hostel':
                payment_id = metadata.get('payment_id')
                if payment_id:
                    try:
                        fee = HostelFee.objects.get(id=payment_id)
                        if fee.payment_status != 'completed':
                            fee.payment_status = 'completed'
                            fee.paid = True
                            fee.payment_date = timezone.now().date()
                            fee.save()
                            logger.info(f"Hostel payment completed: fee_id={payment_id}")
                        else:
                            logger.info(f"Hostel payment already completed: fee_id={payment_id}")
                    except HostelFee.DoesNotExist:
                        logger.error(f"Hostel fee not found: fee_id={payment_id}")
        
        return JsonResponse({'success': True})
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in webhook: {e}")
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
def send_payment_reminder(request):
    """Send payment reminder to parents/students via SMS."""
    from services.sms_service import SMSService
    
    school = getattr(request.user, 'school', None)
    if not school:
        messages.error(request, "School not found")
        return redirect('accounts:dashboard')
    
    if request.method == 'POST':
        student_ids = request.POST.getlist('student_ids')
        
        if not student_ids:
            messages.error(request, "No students selected")
            return redirect('operations:payment_dashboard')
        
        from finance.models import Fee
        sent_count = 0
        
        for student_id in student_ids:
            try:
                student = Student.objects.get(id=student_id, school=school)
                fees = Fee.objects.filter(student=student, paid=False)
                
                if not fees.exists():
                    continue
                
                total_pending = sum(float(f.remaining_balance) for f in fees)
                
                # Get parent's phone number for SMS
                parent_phone = None
                if student.parent and student.parent.phone:
                    parent_phone = student.parent.phone
                
                if parent_phone:
                    sms_message = f"Dear Parent/Guardian of {student.user.get_full_name()}, this is a reminder that there are pending fees of GHS {total_pending} for the current term. Please make payments at your earliest convenience to avoid disruption. Best regards, {school.name}"
                    
                    try:
                        SMSService.send_sms(parent_phone, sms_message, school.name)
                        sent_count += 1
                    except Exception:
                        pass
                
                messages.success(request, f"Reminder sent for {sent_count} student(s)")
                
            except Student.DoesNotExist:
                continue
        
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
