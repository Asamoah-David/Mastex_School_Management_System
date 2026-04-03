"""
Payment Views for Canteen, Bus, Textbooks, and Hostel with Paystack Integration
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.conf import settings
import uuid

from accounts.decorators import login_required, parent_required, student_required


from students.models import Student
from schools.models import School
from .models import CanteenItem, CanteenPayment, BusRoute, BusPayment, Textbook, TextbookSale, HostelFee
from finance.paystack_service import paystack_service


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
    ).select_related('item')[:20]
    
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
    
    # Get parent email for payment
    parent_email = ""
    if request.user.role == 'parent':
        parent_email = request.user.email
    elif student.parent_email:
        parent_email = student.parent_email
    
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
        'student_name': student.full_name
    }
    
    result = paystack_service.initialize_payment(
        email=parent_email or student.user.email,
        amount=total_amount,
        callback_url=callback_url,
        reference=reference,
        metadata=metadata
    )
    
    if result.get('status'):
        payment.save()
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
    
    # Get parent email
    parent_email = ""
    if request.user.role == 'parent':
        parent_email = request.user.email
    elif student.parent_email:
        parent_email = student.parent_email
    
    if not parent_email and request.user.email:
        parent_email = request.user.email
    
    # Build callback URL
    callback_url = request.build_absolute_uri(reverse('operations:bus_payment_verify'))
    
    metadata = {
        'payment_type': 'bus',
        'payment_id': str(payment.id),
        'route_name': route.name,
        'term': term,
        'student_name': student.full_name
    }
    
    result = paystack_service.initialize_payment(
        email=parent_email or student.user.email,
        amount=amount,
        callback_url=callback_url,
        reference=reference,
        metadata=metadata
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
    ).select_related('textbook')[:20]
    
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
    
    # Get parent email
    parent_email = ""
    if request.user.role == 'parent':
        parent_email = request.user.email
    elif student.parent_email:
        parent_email = student.parent_email
    
    if not parent_email and request.user.email:
        parent_email = request.user.email
    
    # Build callback URL
    callback_url = request.build_absolute_uri(reverse('operations:textbook_payment_verify'))
    
    metadata = {
        'payment_type': 'textbook',
        'payment_id': str(sale.id),
        'textbook_title': textbook.title,
        'quantity': quantity,
        'student_name': student.full_name
    }
    
    result = paystack_service.initialize_payment(
        email=parent_email or student.user.email,
        amount=total_amount,
        callback_url=callback_url,
        reference=reference,
        metadata=metadata
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
    
    # Get parent email
    parent_email = ""
    if request.user.role == 'parent':
        parent_email = request.user.email
    elif student.parent_email:
        parent_email = student.parent_email
    
    if not parent_email and request.user.email:
        parent_email = request.user.email
    
    # Build callback URL
    callback_url = request.build_absolute_uri(reverse('operations:hostel_payment_verify'))
    
    metadata = {
        'payment_type': 'hostel',
        'payment_id': str(fee.id),
        'hostel_name': fee.hostel.name,
        'term': fee.term,
        'student_name': student.full_name
    }
    
    result = paystack_service.initialize_payment(
        email=parent_email or student.user.email,
        amount=amount,
        callback_url=callback_url,
        reference=reference,
        metadata=metadata
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