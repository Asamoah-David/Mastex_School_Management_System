"""
Payment Tracking Views - Canteen, Bus, Textbook, School Fees
Provides comprehensive payment tracking with date filters and reporting.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, F
from django.utils import timezone
from django.http import JsonResponse
from datetime import datetime, timedelta
from decimal import Decimal

from accounts.decorators import admin_required, role_required
from schools.models import School
from students.models import Student
from operations.models import CanteenPayment, BusPayment, TextbookSale
from finance.models import Fee, FeePayment
from finance.paystack_service import paystack_service


@login_required
@role_required('admin', 'accountant')
def payment_dashboard(request):
    """Admin payment dashboard with all payment types and filters"""
    school = request.user.school
    
    # Get date filter from query params
    date_filter = request.GET.get('date_filter', 'today')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    payment_type = request.GET.get('payment_type', 'all')
    
    today = timezone.now().date()
    
    # Calculate date ranges
    if date_filter == 'today':
        start = today
        end = today
    elif date_filter == 'week':
        start = today - timedelta(days=today.weekday())
        end = today
    elif date_filter == 'month':
        start = today.replace(day=1)
        end = today
    elif date_filter == 'term':
        # Get current term start (assuming term starts in January, May, September)
        month = today.month
        if month <= 4:
            start = today.replace(month=1, day=1)
        elif month <= 8:
            start = today.replace(month=5, day=1)
        else:
            start = today.replace(month=9, day=1)
        end = today
    elif start_date and end_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        except:
            start = today
            end = today
    else:
        start = today
        end = today
    
    # School Fees Summary
    school_fees = []
    if payment_type in ['all', 'school_fees']:
        school_fees = Fee.objects.filter(school=school).select_related('student', 'student__user')
        
        # Calculate totals
        total_school_fees = school_fees.aggregate(
            total=Sum('amount'),
            paid=Sum('amount', filter=Q(feeperpayment__status='completed'))
        )
        
        # Filter by date
        school_fees = school_fees.annotate(
            paid_amount=Sum('feeperpayment__amount', filter=Q(feeperpayment__status='completed')),
            last_payment_date=Max('feeperpayment__created_at', filter=Q(feeperpayment__status='completed'))
        ).filter(
            Q(last_payment_date__range=[start, end]) | Q(last_payment_date__isnull=True)
        )
    
    # Canteen Payments Summary
    canteen_payments = []
    if payment_type in ['all', 'canteen']:
        canteen_payments = CanteenPayment.objects.filter(
            school=school,
            payment_date__range=[start, end]
        ).select_related('student', 'student__user')
        
        canteen_total = canteen_payments.aggregate(
            total=Sum('amount'),
            count=Count('id')
        )
    
    # Bus Payments Summary
    bus_payments = []
    if payment_type in ['all', 'bus']:
        bus_payments = BusPayment.objects.filter(
            school=school,
            payment_date__range=[start, end]
        ).select_related('student', 'student__user', 'route')
        
        bus_total = bus_payments.aggregate(
            total=Sum('amount'),
            count=Count('id')
        )
        
        # Group by payment status
        bus_paid = bus_payments.filter(paid=True).count()
        bus_unpaid = bus_payments.filter(paid=False).count()
    
    # Textbook Sales Summary
    textbook_sales = []
    if payment_type in ['all', 'textbook']:
        textbook_sales = TextbookSale.objects.filter(
            school=school,
            sale_date__range=[start, end]
        ).select_related('student', 'student__user', 'textbook')
        
        textbook_total = textbook_sales.aggregate(
            total=Sum('amount'),
            count=Count('id')
        )
    
    # Outstanding payments - students with unpaid fees
    outstanding_students = Student.objects.filter(school=school).annotate(
        total_fees=Sum('fee__amount'),
        total_paid=Sum('fee__feeperpayment__amount', filter=Q(fee__feeperpayment__status='completed'))
    ).filter(
        total_fees__gt=F('total_paid')
    ).select_related('user')[:50]
    
    # Recent payments across all categories
    recent_payments = []
    
    # Get recent school fee payments
    recent_school_fees = FeePayment.objects.filter(
        fee__school=school,
        status='completed',
        created_at__date__range=[start, end]
    ).select_related('fee__student', 'fee__student__user')[:20]
    
    for payment in recent_school_fees:
        recent_payments.append({
            'date': payment.created_at,
            'student': payment.fee.student,
            'type': 'School Fees',
            'amount': payment.amount,
            'term': payment.fee.term
        })
    
    # Get recent canteen payments
    for payment in canteen_payments[:10]:
        recent_payments.append({
            'date': payment.payment_date,
            'student': payment.student,
            'type': 'Canteen',
            'amount': payment.amount,
            'description': payment.description
        })
    
    # Sort by date
    recent_payments.sort(key=lambda x: x['date'], reverse=True)
    recent_payments = recent_payments[:20]
    
    context = {
        'date_filter': date_filter,
        'start_date': start,
        'end_date': end,
        'payment_type': payment_type,
        # School Fees
        'school_fees': school_fees,
        'total_school_fees': total_school_fees.get('total') or 0,
        # Canteen
        'canteen_payments': canteen_payments,
        'canteen_total': canteen_total.get('total') or 0,
        'canteen_count': canteen_total.get('count') or 0,
        # Bus
        'bus_payments': bus_payments,
        'bus_total': bus_total.get('total') or 0,
        'bus_count': bus_total.get('count') or 0,
        'bus_paid': bus_paid if payment_type in ['all', 'bus'] else 0,
        'bus_unpaid': bus_unpaid if payment_type in ['all', 'bus'] else 0,
        # Textbooks
        'textbook_sales': textbook_sales,
        'textbook_total': textbook_total.get('total') or 0,
        'textbook_count': textbook_total.get('count') or 0,
        # Summary
        'outstanding_students': outstanding_students,
        'recent_payments': recent_payments,
    }
    
    return render(request, 'operations/payment_dashboard.html', context)


@login_required
@role_required('admin', 'accountant')
def student_payment_history(request, student_id):
    """View complete payment history for a specific student"""
    school = request.user.school
    student = get_object_or_404(Student, id=student_id, school=school)
    
    # Get all payments
    canteen = CanteenPayment.objects.filter(student=student).order_by('-payment_date')
    bus = BusPayment.objects.filter(student=student).order_by('-id')
    textbooks = TextbookSale.objects.filter(student=student).order_by('-sale_date')
    school_fees = Fee.objects.filter(student=student).prefetch_related('feeperpayment_set')
    
    # Calculate totals
    canteen_total = canteen.aggregate(total=Sum('amount'))['total'] or 0
    bus_total = bus.filter(paid=True).aggregate(total=Sum('amount'))['total'] or 0
    textbook_total = textbooks.aggregate(total=Sum('amount'))['total'] or 0
    school_fees_total = school_fees.aggregate(total=Sum('amount'))['total'] or 0
    
    # Outstanding balance
    school_fees_paid = FeePayment.objects.filter(
        fee__student=student,
        status='completed'
    ).aggregate(total=Sum('amount'))['total'] or 0
    school_fees_outstanding = school_fees_total - school_fees_paid
    
    context = {
        'student': student,
        'canteen': canteen,
        'canteen_total': canteen_total,
        'bus': bus,
        'bus_total': bus_total,
        'textbooks': textbooks,
        'textbook_total': textbook_total,
        'school_fees': school_fees,
        'school_fees_total': school_fees_total,
        'school_fees_paid': school_fees_paid,
        'school_fees_outstanding': school_fees_outstanding,
        'overall_total': canteen_total + bus_total + textbook_total + school_fees_paid,
    }
    
    return render(request, 'operations/student_payment_history.html', context)


@login_required
@role_required('admin', 'accountant')
def record_payment(request):
    """Record a payment manually"""
    school = request.user.school
    
    if request.method == 'POST':
        payment_type = request.POST.get('payment_type')
        student_id = request.POST.get('student')
        amount = Decimal(request.POST.get('amount', 0))
        description = request.POST.get('description', '')
        
        try:
            student = Student.objects.get(id=student_id, school=school)
        except Student.DoesNotExist:
            messages.error(request, 'Student not found')
            return redirect('operations:record_payment')
        
        if payment_type == 'canteen':
            CanteenPayment.objects.create(
                school=school,
                student=student,
                amount=amount,
                description=description,
                recorded_by=request.user
            )
            messages.success(request, f'Canteen payment of {amount} recorded for {student}')
        
        elif payment_type == 'bus':
            term = request.POST.get('term', '')
            BusPayment.objects.create(
                school=school,
                student=student,
                amount=amount,
                term_period=term,
                paid=True,
                payment_date=timezone.now().date()
            )
            messages.success(request, f'Bus payment of {amount} recorded for {student}')
        
        elif payment_type == 'textbook':
            # Get textbook
            textbook_id = request.POST.get('textbook')
            quantity = int(request.POST.get('quantity', 1))
            if textbook_id:
                from operations.models import Textbook
                textbook = Textbook.objects.get(id=textbook_id, school=school)
                total = textbook.price * quantity
                TextbookSale.objects.create(
                    school=school,
                    student=student,
                    textbook=textbook,
                    quantity=quantity,
                    amount=total,
                    recorded_by=request.user
                )
                messages.success(request, f'Textbook sale of {total} recorded for {student}')
        
        return redirect('operations:payment_dashboard')
    
    # Get students for dropdown
    students = Student.objects.filter(school=school).select_related('user').order_by('user__last_name')
    
    context = {
        'students': students,
    }
    
    return render(request, 'operations/record_payment.html', context)


@login_required
@role_required('parent', 'student')
def my_payments(request):
    """Parent/Student view of their payments"""
    user = request.user
    
    if user.role == 'student':
        # Get student's own payments
        try:
            student = Student.objects.get(user=user)
            canteen = CanteenPayment.objects.filter(student=student).order_by('-payment_date')[:50]
            bus = BusPayment.objects.filter(student=student).order_by('-id')
            textbooks = TextbookSale.objects.filter(student=student).order_by('-sale_date')[:50]
            school_fees = Fee.objects.filter(student=student).prefetch_related('feeperpayment_set')
            student_name = user.get_full_name()
        except Student.DoesNotExist:
            messages.error(request, 'Student profile not found')
            return redirect('students:student_detail')
    else:
        # Parent - get payments for their children
        children = Student.objects.filter(user__parent_user=user).select_related('user')
        child_ids = children.values_list('id', flat=True)
        
        canteen = CanteenPayment.objects.filter(student_id__in=child_ids).order_by('-payment_date')[:50]
        bus = BusPayment.objects.filter(student_id__in=child_ids).order_by('-id')
        textbooks = TextbookSale.objects.filter(student_id__in=child_ids).order_by('-sale_date')[:50]
        school_fees = Fee.objects.filter(student_id__in=child_ids).prefetch_related('feeperpayment_set')
        student_name = f"Children's"
    
    # Calculate totals
    canteen_total = canteen.aggregate(total=Sum('amount'))['total'] or 0
    bus_total = bus.filter(paid=True).aggregate(total=Sum('amount'))['total'] or 0
    textbook_total = textbooks.aggregate(total=Sum('amount'))['total'] or 0
    school_fees_total = school_fees.aggregate(total=Sum('amount'))['total'] or 0
    
    # Outstanding
    school_fees_paid = FeePayment.objects.filter(
        fee__student_id__in=child_ids if user.role == 'parent' else [student.id],
        status='completed'
    ).aggregate(total=Sum('amount'))['total'] or 0
    school_fees_outstanding = school_fees_total - school_fees_paid
    
    context = {
        'student_name': student_name,
        'canteen': canteen,
        'canteen_total': canteen_total,
        'bus': bus,
        'bus_total': bus_total,
        'textbooks': textbooks,
        'textbook_total': textbook_total,
        'school_fees': school_fees,
        'school_fees_total': school_fees_total,
        'school_fees_paid': school_fees_paid,
        'school_fees_outstanding': school_fees_outstanding,
        'overall_total': canteen_total + bus_total + textbook_total + school_fees_paid,
    }
    
    return render(request, 'operations/my_payments.html', context)


@login_required
@role_required('admin', 'accountant')
def generate_receipt(request, payment_type, payment_id):
    """Generate a receipt for a payment"""
    school = request.user.school
    
    if payment_type == 'canteen':
        payment = get_object_or_404(CanteenPayment, id=payment_id, school=school)
        receipt_data = {
            'type': 'Canteen Purchase',
            'date': payment.payment_date,
            'student': payment.student,
            'amount': payment.amount,
            'description': f"Canteen: {payment.description}" if payment.description else "Canteen Purchase",
            'receipt_number': f"CN-{payment.id:06d}",
        }
    elif payment_type == 'bus':
        payment = get_object_or_404(BusPayment, id=payment_id, school=school)
        receipt_data = {
            'type': 'Bus Fee',
            'date': payment.payment_date or timezone.now().date(),
            'student': payment.student,
            'amount': payment.amount,
            'description': f"Bus Route: {payment.route.name} - {payment.term_period}" if payment.route else f"Bus Fee - {payment.term_period}",
            'receipt_number': f"BUS-{payment.id:06d}",
        }
    elif payment_type == 'textbook':
        payment = get_object_or_404(TextbookSale, id=payment_id, school=school)
        receipt_data = {
            'type': 'Textbook Purchase',
            'date': payment.sale_date,
            'student': payment.student,
            'amount': payment.amount,
            'description': f"{payment.textbook.title} x{payment.quantity}",
            'receipt_number': f"TB-{payment.id:06d}",
        }
    elif payment_type == 'school_fees':
        payment = get_object_or_404(FeePayment, id=payment_id)
        receipt_data = {
            'type': 'School Fees',
            'date': payment.created_at.date(),
            'student': payment.fee.student,
            'amount': payment.amount,
            'description': f"School Fees - {payment.fee.term}",
            'receipt_number': f"SF-{payment.id:06d}",
        }
    else:
        messages.error(request, 'Invalid payment type')
        return redirect('operations:payment_dashboard')
    
    receipt_data['school'] = school
    receipt_data['collected_by'] = request.user.get_full_name()
    
    return render(request, 'operations/receipt.html', receipt_data)


# Import Max for aggregate
from django.db.models import Max


# ==================== ONLINE PAYMENT INTEGRATION ====================

@login_required
def initiate_online_payment(request):
    """Initiate Paystack payment for school fees - uses school subaccount"""
    user = request.user
    
    if request.method == 'POST':
        fee_id = request.POST.get('fee_id')
        amount = request.POST.get('amount')
        
        if not fee_id or not amount:
            return JsonResponse({'status': 'error', 'message': 'Missing fee or amount'})
        
        try:
            fee = Fee.objects.get(id=fee_id)
            amount = Decimal(amount)
            
            # Get student's parent email for payment
            if user.role == 'student':
                email = user.email or f"{user.username}@school.local"
            else:
                email = user.email or f"{user.username}@school.local"
            
            # Generate callback URL
            callback_url = request.build_absolute_uri(
                f"/operations/payments/paystack/callback/?fee_id={fee_id}"
            )
            
            # Get school's subaccount for direct payment to school
            school_subaccount = None
            if fee.school and fee.school.paystack_subaccount_code:
                school_subaccount = fee.school.paystack_subaccount_code
            
            # Initialize Paystack payment
            metadata = {
                'fee_id': fee.id,
                'student_id': fee.student.id,
                'user_id': user.id,
                'school_id': fee.school.id if fee.school else None,
                'school_name': fee.school.name if fee.school else '',
                'payment_type': 'school_fees'
            }
            
            result = paystack_service.initialize_payment(
                email=email,
                amount=float(amount),
                callback_url=callback_url,
                reference=f"SF_{fee.id}_{user.id}_{int(timezone.now().timestamp())}",
                metadata=metadata,
                subaccount=school_subaccount  # Pass school subaccount for direct payment
            )
            
            if result.get('status'):
                return JsonResponse({
                    'status': 'success',
                    'authorization_url': result['data']['authorization_url'],
                    'reference': result['data']['reference']
                })
            else:
                return JsonResponse({
                    'status': 'error',
                    'message': result.get('message', 'Payment initialization failed')
                })
                
        except Fee.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Fee not found'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request'})


@login_required
def paystack_callback(request):
    """Handle Paystack payment callback"""
    reference = request.GET.get('reference')
    fee_id = request.GET.get('fee_id')
    
    if not reference:
        messages.error(request, 'Payment reference not found')
        return redirect('operations:my_payments')
    
    try:
        # Verify payment with Paystack
        result = paystack_service.verify_payment(reference)
        
        if result.get('status') and result['data']['status'] == 'success':
            # Payment successful - record it
            fee = Fee.objects.get(id=fee_id)
            
            # Get or create payment record
            payment, created = FeePayment.objects.get_or_create(
                fee=fee,
                transaction_ref=reference,
                defaults={
                    'amount': Decimal(result['data']['amount']) / 100,
                    'status': 'completed',
                    'payment_method': 'paystack',
                    'paid_by': request.user
                }
            )
            
            if created:
                messages.success(request, f'Payment of {payment.amount} confirmed! Receipt sent to your email.')
                
                # Send SMS notification
                try:
                    from messaging.utils import send_sms
                    student = fee.student
                    if student.parent and student.parent.phone:
                        msg = f"Payment confirmed! {fee.term}: GHS {payment.amount}. Ref: {reference}"
                        send_sms(student.parent.phone, msg)
                except:
                    pass
            else:
                messages.info(request, 'Payment already recorded')
        else:
            messages.error(request, 'Payment verification failed. Please contact support.')
            
    except Fee.DoesNotExist:
        messages.error(request, 'Fee record not found')
    except Exception as e:
        messages.error(request, f'Error processing payment: {str(e)}')
    
    return redirect('operations:my_payments')


@login_required
def paystack_webhook(request):
    """Handle Paystack webhook for payment notifications"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error'}, status=400)
    
    # Verify webhook signature
    signature = request.headers.get('x-paystack-signature')
    if not signature:
        return JsonResponse({'status': 'error', 'message': 'Missing signature'}, status=400)
    
    # Get raw body for signature verification
    body = request.body
    
    if not paystack_service.verify_webhook_signature(
        body, 
        signature, 
        settings.PAYSTACK_WEBHOOK_SECRET
    ):
        return JsonResponse({'status': 'error', 'message': 'Invalid signature'}, status=400)
    
    try:
        import json
        data = json.loads(body)
        
        event = data.get('event')
        
        if event == 'charge.success':
            payment_data = data['data']
            metadata = payment_data.get('metadata', {})
            
            fee_id = metadata.get('fee_id')
            
            if fee_id:
                try:
                    fee = Fee.objects.get(id=fee_id)
                    
                    # Check if already recorded
                    if not FeePayment.objects.filter(transaction_ref=payment_data['reference']).exists():
                        payment = FeePayment.objects.create(
                            fee=fee,
                            transaction_ref=payment_data['reference'],
                            amount=Decimal(payment_data['amount']) / 100,
                            status='completed',
                            payment_method='paystack'
                        )
                        
                        # Send email receipt
                        try:
                            from messaging.email_utils import send_email
                            student = fee.student
                            if student.parent and student.parent.email:
                                send_email(
                                    student.parent.email,
                                    f"Payment Confirmation - {fee.term}",
                                    f"Payment of GHS {payment.amount} for {student.user.get_full_name()} ({fee.term}) confirmed. Reference: {payment.transaction_ref}"
                                )
                        except:
                            pass
                            
                except Fee.DoesNotExist:
                    pass
        
        return JsonResponse({'status': 'success'})
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# ==================== SMS/EMAIL NOTIFICATIONS ====================

@login_required
def send_payment_reminder(request):
    """Send payment reminder SMS to parent"""
    from django.http import JsonResponse
    
    if request.method == 'POST':
        student_id = request.POST.get('student_id')
        
        try:
            student = Student.objects.get(id=student_id)
            
            if student.parent and student.parent.phone:
                from messaging.utils import send_sms
                
                # Calculate outstanding amount
                total_fees = student.fee_set.aggregate(total=Sum('amount'))['total'] or 0
                total_paid = FeePayment.objects.filter(
                    fee__student=student,
                    status='completed'
                ).aggregate(total=Sum('amount'))['total'] or 0
                outstanding = total_fees - total_paid
                
                if outstanding > 0:
                    msg = f"Reminder: Outstanding school fees of GHS {outstanding:.2f} for {student.user.get_full_name()}. Please pay promptly. - {student.school.name}"
                    send_sms(student.parent.phone, msg)
                    return JsonResponse({'status': 'success', 'message': 'Reminder sent'})
                else:
                    return JsonResponse({'status': 'error', 'message': 'No outstanding fees'})
            else:
                return JsonResponse({'status': 'error', 'message': 'No parent phone number'})
                
        except Student.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Student not found'})
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request'})
