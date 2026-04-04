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


from students.models import Student
from schools.models import School
from .models import CanteenItem, CanteenPayment, BusRoute, BusPayment, Textbook, TextbookSale, HostelFee
from finance.paystack_service import paystack_service
from finance.models import Fee, FeePayment


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
    """Get the school for the current user."""
    if hasattr(request.user, 'school'):
        return request.user.school
    student = _get_user_student(request)
    if student:
        return student.school
    return None


def _get_parent_email(student, request):
    """Get parent's email for a student."""
    if student.parent and student.parent.email:
        return student.parent.email
    return None


# ==================== CANTEEN PAYMENTS ====================

@student_required
def canteen_my(request):
    """Student view to browse and purchase canteen items."""
    student = _get_user_student(request)
    if not student:
        return redirect('accounts:login')
    
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
    context = {
        'items': items,
        'my_payments': my_payments,
        'pending_payments': pending_payments,
        'page_title': 'Canteen',
        'paystack_public_key': getattr(settings, 'PAYSTACK_PUBLIC_KEY', ''),
    }
    return render(request, 'operations/canteen_my.html', context)


@require_POST
def canteen_initiate_payment(request):
    """Initiate Paystack payment for canteen items."""
    student = _get_user_student(request)
    if not student:
        return JsonResponse({'success': False, 'error': 'Student not found'}, status=400)
    
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
    
    # Build callback URL
    callback_url = request.build_absolute_uri(reverse('operations:canteen_payment_verify'))
    
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
        payment.save()
        return JsonResponse({
            'success': True,
            'authorization_url': result['data']['authorization_url'],
            'reference': reference,
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
    reference = request.GET.get('reference')
    
    if not reference:
        messages.error(request, "Invalid payment reference")
        return redirect('operations:canteen_my')
    
    # Verify with Paystack
    result = paystack_service.verify_payment(reference)
    
    try:
        payment = CanteenPayment.objects.get(payment_reference=reference)
        
        if result.get('status') and result['data']['status'] == 'success':
            payment.payment_status = 'completed'
            payment.save()
            messages.success(request, "Payment successful! Your order has been placed.")
        else:
            payment.payment_status = 'failed'
            payment.save()
            messages.error(request, "Payment failed. Please try again.")
            
    except CanteenPayment.DoesNotExist:
        messages.error(request, "Payment record not found")
    
    return redirect('operations:canteen_my')


# ==================== BUS/TRANSPORT PAYMENTS ====================

@student_required
def bus_my(request):
    """Student view to see bus routes and make payments."""
    student = _get_user_student(request)
    if not student:
        return redirect('accounts:login')
    
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
    context = {
        'routes': routes,
        'my_payments': my_payments,
        'pending_payments': pending_payments,
        'page_title': 'Transport',
        'paystack_public_key': getattr(settings, 'PAYSTACK_PUBLIC_KEY', ''),
    }
    return render(request, 'operations/bus_my.html', context)


@require_POST
def bus_initiate_payment(request):
    """Initiate Paystack payment for bus/transport."""
    student = _get_user_student(request)
    if not student:
        return JsonResponse({'success': False, 'error': 'Student not found'}, status=400)
    
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
            'reference': reference
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
    reference = request.GET.get('reference')
    
    if not reference:
        messages.error(request, "Invalid payment reference")
        return redirect('operations:bus_my')
    
    result = paystack_service.verify_payment(reference)
    
    try:
        payment = BusPayment.objects.get(payment_reference=reference)
        
        if result.get('status') and result['data']['status'] == 'success':
            payment.payment_status = 'completed'
            payment.paid = True
            payment.payment_date = timezone.now().date()
            payment.save()
            messages.success(request, "Payment successful! Your bus pass is now active.")
        else:
            payment.payment_status = 'failed'
            payment.save()
            messages.error(request, "Payment failed. Please try again.")
            
    except BusPayment.DoesNotExist:
        messages.error(request, "Payment record not found")
    
    return redirect('operations:bus_my')


# ==================== TEXTBOOK PAYMENTS ====================

@student_required
def textbook_my(request):
    """Student view to browse and purchase textbooks."""
    student = _get_user_student(request)
    if not student:
        return redirect('accounts:login')
    
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
    context = {
        'textbooks': textbooks,
        'my_purchases': my_purchases,
        'pending_purchases': pending_purchases,
        'page_title': 'Textbooks',
        'paystack_public_key': getattr(settings, 'PAYSTACK_PUBLIC_KEY', ''),
    }
    return render(request, 'operations/textbook_my.html', context)


@require_POST
def textbook_initiate_payment(request):
    """Initiate Paystack payment for textbooks."""
    student = _get_user_student(request)
    if not student:
        return JsonResponse({'success': False, 'error': 'Student not found'}, status=400)
    
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
    
    # Build callback URL
    callback_url = request.build_absolute_uri(reverse('operations:textbook_payment_verify'))
    
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
        return JsonResponse({
            'success': True,
            'authorization_url': result['data']['authorization_url'],
            'reference': reference
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
    reference = request.GET.get('reference')
    
    if not reference:
        messages.error(request, "Invalid payment reference")
        return redirect('operations:textbook_my')
    
    result = paystack_service.verify_payment(reference)
    
    try:
        sale = TextbookSale.objects.get(payment_reference=reference)
        
        if result.get('status') and result['data']['status'] == 'success':
            sale.payment_status = 'completed'
            sale.save()
            # Reduce stock
            sale.textbook.stock -= sale.quantity
            sale.textbook.save()
            messages.success(request, "Payment successful! Your textbook(s) have been reserved.")
        else:
            sale.payment_status = 'failed'
            sale.save()
            messages.error(request, "Payment failed. Please try again.")
            
    except TextbookSale.DoesNotExist:
        messages.error(request, "Payment record not found")
    
    return redirect('operations:textbook_my')


# ==================== HOSTEL FEE PAYMENTS ====================

@student_required
def hostel_my(request):
    """Student view to see hostel fees and make payments."""
    student = _get_user_student(request)
    if not student:
        return redirect('accounts:login')
    
    school = student.school
    
    # Get student's hostel fee records
    from operations.models import HostelAssignment
    assignments = HostelAssignment.objects.filter(
        student=student,
        is_active=True
    ).select_related('hostel')
    
    # Get all pending hostel fees for this student
    hostel_fees = HostelFee.objects.filter(
        student=student
    ).select_related('hostel')[:20]
    
    # Get pending payments
    pending_fees = HostelFee.objects.filter(
        student=student,
        payment_status='pending'
    )
    
    from django.conf import settings
    context = {
        'assignments': assignments,
        'hostel_fees': hostel_fees,
        'pending_fees': pending_fees,
        'page_title': 'Hostel',
        'paystack_public_key': getattr(settings, 'PAYSTACK_PUBLIC_KEY', ''),
    }
    return render(request, 'operations/hostel_my.html', context)


@require_POST
def hostel_initiate_payment(request):
    """Initiate Paystack payment for hostel fees."""
    student = _get_user_student(request)
    if not student:
        return JsonResponse({'success': False, 'error': 'Student not found'}, status=400)
    
    fee_id = request.POST.get('fee_id')
    
    try:
        fee = HostelFee.objects.get(id=fee_id, student=student)
    except HostelFee.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Fee not found'}, status=404)
    
    if fee.payment_status == 'completed':
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
    
    # Build callback URL
    callback_url = request.build_absolute_uri(reverse('operations:hostel_payment_verify'))
    
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
            'reference': reference
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
    reference = request.GET.get('reference')
    
    if not reference:
        messages.error(request, "Invalid payment reference")
        return redirect('operations:hostel_my')
    
    result = paystack_service.verify_payment(reference)
    
    try:
        fee = HostelFee.objects.get(payment_reference=reference)
        
        if result.get('status') and result['data']['status'] == 'success':
            fee.payment_status = 'completed'
            fee.paid = True
            fee.payment_date = timezone.now().date()
            fee.save()
            messages.success(request, "Payment successful! Your hostel fee is now cleared.")
        else:
            fee.payment_status = 'failed'
            fee.save()
            messages.error(request, "Payment failed. Please try again.")
            
    except HostelFee.DoesNotExist:
        messages.error(request, "Payment record not found")
    
    return redirect('operations:hostel_my')


# ==================== GENERAL PAYMENT DASHBOARD ====================

@login_required
def payment_dashboard(request):
    """Admin dashboard showing all payments across the system."""
    school = getattr(request.user, 'school', None)
    if not school:
        messages.error(request, "School not found")
        return redirect('dashboard')
    
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
    
    # Get other payments (canteen, bus, textbook)
    canteen_payments = CanteenPayment.objects.filter(school=school, payment_status='completed')
    bus_payments = BusPayment.objects.filter(school=school, payment_status='completed')
    textbook_sales = TextbookSale.objects.filter(school=school, payment_status='completed')
    
    # Calculate totals by type
    if payment_type == 'all' or payment_type == 'school_fees':
        school_fees_total = total_collected
    else:
        school_fees_total = 0
    
    if payment_type == 'all' or payment_type == 'canteen':
        canteen_total = sum(float(p.amount) for p in canteen_payments)
    else:
        canteen_total = 0
    
    if payment_type == 'all' or payment_type == 'bus':
        bus_total = sum(float(p.amount) for p in bus_payments)
    else:
        bus_total = 0
    
    if payment_type == 'all' or payment_type == 'textbook':
        textbook_total = sum(float(s.amount) for s in textbook_sales)
    else:
        textbook_total = 0
    
    # Recent payments
    recent_fee_payments = fees[:20]
    
    context = {
        'fees': recent_fee_payments,
        'total_fees': total_fees,
        'paid_fees': paid_fees,
        'pending_fees': pending_fees,
        'total_amount': total_amount,
        'total_collected': total_collected,
        'canteen_total': canteen_total,
        'bus_total': bus_total,
        'textbook_total': textbook_total,
        'school_fees_total': school_fees_total,
        'date_filter': date_filter,
        'payment_type': payment_type,
        'start_date': start_date,
        'end_date': end_date,
        'page_title': 'Payment Dashboard',
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
        return redirect('dashboard')
    
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
    students = Student.objects.filter(school=school, is_active=True).order_by('full_name')
    
    context = {
        'students': students,
        'page_title': 'Record Payment',
    }
    return render(request, 'operations/record_payment.html', context)


@student_required
def my_payments(request):
    """Student view of their own payments."""
    student = _get_user_student(request)
    if not student:
        return redirect('accounts:login')
    
    from finance.models import Fee, FeePayment
    
    # Get school fees
    fees = Fee.objects.filter(student=student).order_by('-created_at')
    
    # Get all payment records
    all_payments = []
    
    # Fee payments
    for fee in fees:
        fee_payments = FeePayment.objects.filter(fee=fee).order_by('-created_at')
        for payment in fee_payments:
            all_payments.append({
                'type': 'school_fee',
                'description': f"School Fees",
                'amount': float(payment.amount),
                'status': payment.status,
                'date': payment.created_at,
            })
    
    # Canteen payments - use payment_date since created_at doesn't exist
    canteen_payments = CanteenPayment.objects.filter(
        student=student
    ).order_by('-payment_date')
    for payment in canteen_payments:
        all_payments.append({
            'type': 'canteen',
            'description': payment.description or "Canteen",
            'amount': float(payment.amount),
            'status': payment.payment_status,
            'date': payment.payment_date,
        })
    
    # Bus payments - use payment_date since created_at doesn't exist
    bus_payments = BusPayment.objects.filter(
        student=student
    ).order_by('-payment_date')
    for payment in bus_payments:
        all_payments.append({
            'type': 'bus',
            'description': f"Bus - {payment.route.name if payment.route else 'Transport'}",
            'amount': float(payment.amount),
            'status': payment.payment_status,
            'date': payment.payment_date,
        })
    
    # Textbook sales - use sale_date instead of created_at
    textbook_sales = TextbookSale.objects.filter(
        student=student
    ).order_by('-id')
    for sale in textbook_sales:
        all_payments.append({
            'type': 'textbook',
            'description': f"Textbook - {sale.textbook.title if sale.textbook else 'Textbook'}",
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
        'payments': all_payments,
        'fees': fees,
        'total_paid': total_paid,
        'total_pending': total_pending,
        'page_title': 'My Payments',
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
    
    # Verify access
    school = getattr(request.user, 'school', None)
    if school and student.school != school:
        messages.error(request, "Access denied")
        return redirect('operations:payment_dashboard')
    
    if request.user.role == 'student' and request.user.student != student:
        messages.error(request, "Access denied")
        return redirect('operations:my_payments')
    
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
    """Initiate Paystack payment for school fees."""
    from finance.models import Fee
    
    school = getattr(request.user, 'school', None)
    if not school:
        return JsonResponse({'success': False, 'error': 'School not found'}, status=400)
    
    fee_id = request.POST.get('fee_id')
    
    try:
        fee = Fee.objects.get(id=fee_id, school=school)
    except Fee.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Fee not found'}, status=404)
    
    remaining = fee.remaining_balance
    if remaining <= 0:
        return JsonResponse({'success': False, 'error': 'Fee already paid'}, status=400)
    
    student = fee.student
    
    # Get parent email using helper function
    parent_email = _get_parent_email(student, request)
    
    if not parent_email and request.user.email:
        parent_email = request.user.email
    
    # Generate unique reference
    reference = f"FEE_{uuid.uuid4().hex[:12].upper()}"
    
    # Build callback URL
    callback_url = request.build_absolute_uri(reverse('operations:paystack_callback', args=[fee.id]))
    
    metadata = {
        'payment_type': 'school_fee',
        'fee_id': str(fee.id),
        'student_name': student.user.get_full_name(),
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
        amount=remaining,
        callback_url=callback_url,
        reference=reference,
        metadata=metadata,
        subaccount=school_subaccount,
        currency=currency
    )
    
    if result.get('status'):
        # Update fee with reference
        fee.paystack_reference = reference
        fee.save()
        
        return JsonResponse({
            'success': True,
            'authorization_url': result['data']['authorization_url'],
            'reference': reference
        })
    else:
        return JsonResponse({
            'success': False,
            'error': result.get('message', 'Payment initialization failed')
        })


def paystack_callback(request, fee_id):
    """Handle Paystack payment callback for school fees."""
    from finance.models import Fee, FeePayment
    
    reference = request.GET.get('reference')
    
    if not reference:
        messages.error(request, "Invalid payment reference")
        return redirect('students:fees_list')
    
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
            fee.save()
            
            messages.success(request, "Payment successful!")
        else:
            messages.error(request, "Payment failed. Please try again.")
            
    except Fee.DoesNotExist:
        messages.error(request, "Fee record not found")
    
    return redirect('students:fees_list')


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
    
    logger = logging.getLogger(__name__)
    
    try:
        # Get raw request body
        body = request.body
        data = json.loads(body)
        
        event = data.get('event')
        logger.info(f"Paystack webhook received: event={event}")
        
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
        return redirect('dashboard')
    
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


@csrf_exempt
def cancel_pending_payment(request):
    """API endpoint to cancel/delete pending payments"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Only POST method allowed'}, status=405)
    
    try:
        purchase_id = request.POST.get('purchase_id')
        payment_type = request.POST.get('payment_type')  # canteen, bus, textbook
        
        if not purchase_id or not payment_type:
            return JsonResponse({'success': False, 'error': 'Missing purchase_id or payment_type'}, status=400)
        
        # Import models here to avoid circular imports
        from .models import CanteenPayment, BusPayment, TextbookSale
        
        deleted = False
        
        if payment_type == 'canteen':
            try:
                payment = CanteenPayment.objects.get(id=purchase_id, payment_status='pending')
                payment.delete()
                deleted = True
            except CanteenPayment.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Canteen payment not found'}, status=404)
        
        elif payment_type == 'bus':
            try:
                payment = BusPayment.objects.get(id=purchase_id, payment_status='pending')
                payment.delete()
                deleted = True
            except BusPayment.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Bus payment not found'}, status=404)
        
        elif payment_type == 'textbook':
            try:
                payment = TextbookSale.objects.get(id=purchase_id, payment_status='pending')
                payment.delete()
                deleted = True
            except TextbookSale.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Textbook payment not found'}, status=404)
        
        elif payment_type == 'hostel':
            try:
                payment = HostelFee.objects.get(id=purchase_id, payment_status='pending')
                payment.payment_status = 'cancelled'
                payment.save()
                deleted = True
            except HostelFee.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Hostel payment not found'}, status=404)
        
        else:
            return JsonResponse({'success': False, 'error': f'Invalid payment type: {payment_type}'}, status=400)
        
        if deleted:
            return JsonResponse({'success': True, 'message': 'Pending payment cancelled successfully'})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
    
    return JsonResponse({'success': False, 'error': 'Unknown error'}, status=500)
