import uuid
import json
import requests
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.utils import timezone

from django.contrib.auth.decorators import login_required
from accounts.permissions import is_school_admin, user_can_manage_school

from .models import Fee, FeeStructure, FeePayment
from .paystack_service import paystack_service
from accounts.models import User
from messaging.utils import send_sms
from schools.models import School
from django.db import models
import logging
logger = logging.getLogger(__name__)


def is_paystack_configured():
    """Check if Paystack is properly configured."""
    return bool(settings.PAYSTACK_SECRET_KEY)


def pay_with_paystack(request, fee_id):
    """
    Initialize Paystack payment for a fee.
    Supports partial payments - parent can pay any amount.
    Payment goes directly to school's subaccount if configured.
    Creates a pending payment record for tracking.
    """
    # Check if Paystack is configured
    if not is_paystack_configured():
        messages.error(request, "Online payments are currently unavailable. Please contact the school for payment options.")
        return redirect(request.META.get("HTTP_REFERER", "/"))
    
    fee = get_object_or_404(Fee, id=fee_id)
    
    # Check remaining balance
    remaining = fee.remaining_balance
    if remaining <= 0:
        messages.error(request, "This fee has already been fully paid.")
        return redirect(request.META.get("HTTP_REFERER", "/"))
    
    # Get payment amount from form (for partial payments)
    amount = request.GET.get("amount")
    if amount:
        try:
            amount = float(amount)
            if amount <= 0:
                amount = remaining
            elif amount > remaining:
                amount = remaining
        except (ValueError, TypeError):
            amount = remaining
    else:
        amount = remaining
    
    # Get parent's email
    email = fee.student.user.email if fee.student.user else "parent@example.com"
    
    # Build callback URL
    callback_url = request.build_absolute_uri(
        reverse("finance:paystack_callback", kwargs={"fee_id": fee_id})
    )
    
    # Create a unique reference for this payment
    reference = f"SCHOOL_FEE_{fee_id}_{uuid.uuid4().hex[:8].upper()}"
    
    # Get school's subaccount if configured
    school_subaccount = None
    if fee.school and fee.school.paystack_subaccount_code:
        school_subaccount = fee.school.paystack_subaccount_code
    
    # Create pending payment record for tracking
    from .models import FeePayment
    pending_payment = FeePayment.objects.create(
        fee=fee,
        amount=amount,
        paystack_reference=reference,
        status='pending'
    )
    logger.info(f"Created pending payment record: payment_id={pending_payment.id}, reference={reference}")
    
    # Initialize payment with Paystack
    response = paystack_service.initialize_payment(
        email=email,
        amount=amount,
        callback_url=callback_url,
        reference=reference,
        metadata={
            "fee_id": fee_id,
            "payment_id": pending_payment.id,
            "payment_type": "school_fee",
            "student_name": str(fee.student),
            "school_name": fee.school.name if fee.school else "",
            "school_id": fee.school.id if fee.school else None,
        },
        subaccount=school_subaccount  # Pass school's subaccount for direct payment
    )
    
    if response.get("status") and response.get("data", {}).get("authorization_url"):
        # Store reference in session for verification
        request.session[f"paystack_ref_{fee_id}"] = reference
        request.session[f"paystack_payment_id_{fee_id}"] = pending_payment.id
        return redirect(response["data"]["authorization_url"])
    else:
        # Mark payment as failed if initialization failed
        pending_payment.status = 'failed'
        pending_payment.save()
        error_msg = response.get("message", "Could not initialize payment. Please try again.")
        messages.error(request, error_msg)
        return redirect(request.META.get("HTTP_REFERER", "/"))


def pay_with_paystack_custom_amount(request, fee_id):
    """
    Allow parent to specify custom payment amount.
    Payment goes directly to school's subaccount if configured.
    """
    # Check if Paystack is configured
    if not is_paystack_configured():
        messages.error(request, "Online payments are currently unavailable. Please contact the school for payment options.")
        return redirect(request.META.get("HTTP_REFERER", "/"))
    
    fee = get_object_or_404(Fee, id=fee_id)
    
    if request.method == "POST":
        amount_str = request.POST.get("amount", "")
        try:
            amount = float(amount_str)
            if amount <= 0:
                messages.error(request, "Amount must be greater than 0.")
                return redirect(request.META.get("HTTP_REFERER", "/"))
            
            remaining = fee.remaining_balance
            if amount > remaining:
                messages.warning(request, f"Amount exceeds remaining balance of GHS {remaining}. Paying GHS {remaining} instead.")
                amount = remaining
            
            # Get parent's email
            email = fee.student.user.email if fee.student.user else "parent@example.com"
            
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
                amount=amount,
                paystack_reference=reference,
                status='pending'
            )
            logger.info(f"Created pending payment record for custom amount: payment_id={pending_payment.id}, reference={reference}")
            
            # Initialize payment
            response = paystack_service.initialize_payment(
                email=email,
                amount=amount,
                callback_url=callback_url,
                reference=reference,
                metadata={
                    "fee_id": fee_id,
                    "payment_id": pending_payment.id,
                    "payment_type": "school_fee",
                    "student_name": str(fee.student),
                    "school_name": fee.school.name if fee.school else "",
                    "school_id": fee.school.id if fee.school else None,
                },
                subaccount=school_subaccount
            )
            
            if response.get("status") and response.get("data", {}).get("authorization_url"):
                request.session[f"paystack_ref_{fee_id}"] = reference
                request.session[f"paystack_payment_id_{fee_id}"] = pending_payment.id
                request.session[f"paystack_amount_{fee_id}"] = amount
                return redirect(response["data"]["authorization_url"])
            else:
                # Mark payment as failed if initialization failed
                pending_payment.status = 'failed'
                pending_payment.save()
                error_msg = response.get("message", "Could not initialize payment.")
                messages.error(request, error_msg)
                return redirect(request.META.get("HTTP_REFERER", "/"))
            
        except (ValueError, TypeError):
            messages.error(request, "Invalid amount entered.")
    
    return redirect(request.META.get("HTTP_REFERER", "/"))


def paystack_callback(request, fee_id):
    """
    Handle Paystack payment callback.
    Verify payment and update fee accordingly.
    """
    reference = request.GET.get("reference")
    
    if not reference:
        messages.error(request, "Payment reference not found.")
        return redirect("home")
    
    # Get stored amount if available
    amount = request.session.pop(f"paystack_amount_{fee_id}", None)
    
    # Verify payment with Paystack
    response = paystack_service.verify_payment(reference)
    
    if response.get("status") and response.get("data", {}).get("status") == "success":
        data = response["data"]
        paid_amount = float(data.get("amount", 0)) / 100  # Convert from kobo
        
        # If we don't have the amount from session, use verified amount
        if not amount:
            amount = paid_amount
        else:
            amount = float(amount)
        
        # Update the fee
        try:
            fee = Fee.objects.get(id=fee_id)
            
            # Create payment record
            payment = FeePayment.objects.create(
                fee=fee,
                amount=amount,
                paystack_payment_id=data.get("id"),
                paystack_reference=reference,
                payment_method=data.get("authorization", {}).get("channel", "card"),
                status="completed"
            )
            
            # Update fee's amount_paid
            fee.amount_paid = float(fee.amount_paid) + amount
            fee.paystack_payment_id = data.get("id")
            fee.paystack_reference = reference
            
            # Update fee status to 'paid' if fully paid
            if fee.amount_paid >= fee.amount:
                fee.status = 'paid'
            
            fee.save()
            
            # Send SMS notification to parent
            try:
                from fees.services.admin_unpaid_notification import notify_parent_fee_paid
                student = fee.student
                if student.parent and student.parent.phone:
                    notify_parent_fee_paid(student, amount)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to send payment SMS: {e}")
            
            messages.success(request, f"Payment of GHS {amount} received successfully!")
            return redirect("finance:parent_fee_list")
            
        except Fee.DoesNotExist:
            messages.error(request, "Fee record not found.")
    
    else:
        error_msg = response.get("message", "Payment verification failed.")
        messages.error(request, f"Payment was not successful: {error_msg}")
    
    return redirect("finance:parent_fee_list")


@csrf_exempt
def paystack_webhook(request):
    """
    Handle Paystack webhook for payment notifications.
    This ensures payments are recorded even if the user closes the browser
    before being redirected back to the site.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    if request.method != "POST":
        return HttpResponse(status=405)
    
    # Verify webhook signature
    signature = request.headers.get("x-paystack-signature")
    if signature and settings.PAYSTACK_WEBHOOK_SECRET:
        body = request.body
        if not paystack_service.verify_webhook_signature(body, signature, settings.PAYSTACK_WEBHOOK_SECRET):
            logger.warning("Invalid Paystack webhook signature")
            return HttpResponse("Invalid signature", status=403)
    
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in webhook payload")
        return HttpResponse(status=400)
    
    event = payload.get("event")
    logger.info(f"Paystack webhook received: event={event}")
    
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
                payment_id = metadata.get("payment_id")  # Our FeePayment record ID
                if fee_id:
                    try:
                        fee = Fee.objects.get(id=fee_id)
                        amount = float(data.get("amount", 0)) / 100
                        
                        # Check if payment already exists to avoid duplicates
                        existing = FeePayment.objects.filter(paystack_reference=reference).exists()
                        if not existing:
                            # If we have a pending payment ID, update it; otherwise create new
                            if payment_id:
                                try:
                                    payment = FeePayment.objects.get(id=payment_id)
                                    payment.status = "completed"
                                    payment.paystack_payment_id = data.get("id")
                                    payment.payment_method = data.get("authorization", {}).get("channel", "card")
                                    payment.save()
                                    logger.info(f"Updated pending payment to completed: payment_id={payment_id}")
                                except FeePayment.DoesNotExist:
                                    # Create new payment record
                                    payment = FeePayment.objects.create(
                                        fee=fee,
                                        amount=amount,
                                        paystack_payment_id=data.get("id"),
                                        paystack_reference=reference,
                                        payment_method=data.get("authorization", {}).get("channel", "card"),
                                        status="completed"
                                    )
                            else:
                                payment = FeePayment.objects.create(
                                    fee=fee,
                                    amount=amount,
                                    paystack_payment_id=data.get("id"),
                                    paystack_reference=reference,
                                    payment_method=data.get("authorization", {}).get("channel", "card"),
                                    status="completed"
                                )
                            
                            fee.amount_paid = float(fee.amount_paid) + amount
                            fee.paystack_payment_id = data.get("id")
                            fee.paystack_reference = reference
                            fee.save()
                            logger.info(f"School fee payment recorded: fee_id={fee_id}, amount={amount}")
                        else:
                            logger.info(f"Payment already processed: reference={reference}")
                    except Fee.DoesNotExist:
                        logger.error(f"Fee not found: fee_id={fee_id}")
            
            # Handle Canteen Payments
            elif payment_type == "canteen":
                payment_id = metadata.get("payment_id")
                if payment_id:
                    try:
                        from operations.models import CanteenPayment
                        payment = CanteenPayment.objects.get(id=payment_id)
                        if payment.payment_status != 'completed':
                            payment.payment_status = 'completed'
                            from django.utils import timezone
                            payment.payment_date = timezone.now().date()
                            payment.save()
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
                        payment = BusPayment.objects.get(id=payment_id)
                        if payment.payment_status != 'completed':
                            payment.payment_status = 'completed'
                            payment.paid = True
                            from django.utils import timezone
                            payment.payment_date = timezone.now().date()
                            payment.save()
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
                        from operations.models import TextbookSale
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
            
            # Handle Hostel Payments
            elif payment_type == "hostel":
                payment_id = metadata.get("payment_id")
                if payment_id:
                    try:
                        from operations.models import HostelFee
                        fee = HostelFee.objects.get(id=payment_id)
                        if fee.payment_status != 'completed':
                            fee.payment_status = 'completed'
                            fee.paid = True
                            from django.utils import timezone
                            fee.payment_date = timezone.now().date()
                            fee.save()
                            logger.info(f"Hostel payment completed: fee_id={payment_id}")
                        else:
                            logger.info(f"Hostel payment already completed: fee_id={payment_id}")
                    except HostelFee.DoesNotExist:
                        logger.error(f"Hostel fee not found: fee_id={payment_id}")
    
    return HttpResponse(status=200)



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
                    fee.amount_paid = fee.amount
                    fee.save()
                    messages.success(request, "Fee marked as fully paid.")
                elif action == "mark_partially_paid":
                    partial_amount = request.POST.get("partial_amount")
                    if partial_amount:
                        try:
                            amount = float(partial_amount)
                            fee.amount_paid = float(fee.amount_paid) + amount
                            fee.save()
                            messages.success(request, f"Added GHS {amount} to payment.")
                        except (ValueError, TypeError):
                            messages.error(request, "Invalid amount.")
                elif action == "record_offline":
                    offline_amount = request.POST.get("offline_amount", str(fee.remaining_balance))
                    try:
                        amount = float(offline_amount)
                        fee.amount_paid = float(fee.amount_paid) + amount
                        fee.save()
                        # Create payment record
                        FeePayment.objects.create(
                            fee=fee,
                            amount=amount,
                            payment_method="offline",
                            status="completed"
                        )
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

    return render(request, "finance/fee_list.html", {"fees": fees, "school": school})


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
    if not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect("accounts:school_dashboard")
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        try:
            amount = float(request.POST.get("amount", 0))
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
    if not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect("accounts:school_dashboard")
    
    structure = get_object_or_404(FeeStructure, pk=pk, school=school)
    
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        try:
            amount = float(request.POST.get("amount", 0))
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
    if not (request.user.is_superuser or is_school_admin(request.user)):
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
    if not (request.user.is_superuser or is_school_admin(request.user)):
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
        # Check if fee already exists for this student
        existing = Fee.objects.filter(school=school, student=student).first()
        
        if not existing:
            Fee.objects.create(
                school=school,
                student=student,
                amount=structure.amount
            )
            created_count += 1
        else:
            skipped_count += 1
    
    messages.success(request, f"Generated fees for {created_count} students. {skipped_count} skipped (already have fees).")
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
    
    # Get subscription amount from school
    amount = float(school.subscription_amount) if school.subscription_amount else 1500
    
    # Get admin's email
    email = request.user.email or "admin@school.com"
    
    # Build callback URL
    callback_url = request.build_absolute_uri(reverse("finance:subscription_callback"))
    
    # Create a unique reference
    reference = f"SCHOOL_SUB_{school.id}_{uuid.uuid4().hex[:8].upper()}"
    
    # Initialize payment with Paystack
    response = paystack_service.initialize_payment(
        email=email,
        amount=amount,
        callback_url=callback_url,
        reference=reference,
        metadata={
            "school_id": school.id,
            "school_name": school.name,
            "type": "subscription",
        }
    )
    
    if response.get("status") and response.get("data", {}).get("authorization_url"):
        # Store reference in session
        request.session["paystack_sub_ref"] = reference
        request.session["paystack_sub_school_id"] = school.id
        return redirect(response["data"]["authorization_url"])
    else:
        error_msg = response.get("message", "Could not initialize payment. Please try again.")
        messages.error(request, error_msg)
        return redirect("finance:subscription")


def subscription_callback(request):
    """
    Handle Paystack subscription payment callback.
    """
    reference = request.GET.get("reference")
    
    if not reference:
        messages.error(request, "Payment reference not found.")
        return redirect("finance:subscription")
    
    # Verify payment with Paystack
    response = paystack_service.verify_payment(reference)
    
    if response.get("status") and response.get("data", {}).get("status") == "success":
        data = response["data"]
        
        # Get school ID from session
        school_id = request.session.pop("paystack_sub_school_id", None)
        
        if school_id:
            try:
                school = School.objects.get(id=school_id)
                
                # Extend subscription by 1 month
                from django.utils import timezone
                new_end_date = timezone.now() + timezone.timedelta(days=30)
                
                # If already expired or no end date, set new dates
                if not school.subscription_end_date or school.subscription_end_date < timezone.now():
                    school.subscription_start_date = timezone.now()
                
                school.subscription_end_date = new_end_date
                school.subscription_status = "active"
                school.save()
                
                messages.success(request, f"Subscription renewed successfully! Valid until {new_end_date.strftime('%Y-%m-%d')}")
                
            except School.DoesNotExist:
                messages.error(request, "School not found.")
        else:
            messages.error(request, "School information not found.")
    else:
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
    Notify all admin users of unpaid fees.
    """
    unpaid_fees = Fee.objects.filter(amount_paid__lt=models.F('amount'))
    admins = User.objects.filter(role="admin")
    for admin in admins:
        message = f"There are {unpaid_fees.count()} unpaid/partial fees pending in the system."
        if admin.phone:
            send_sms(admin.phone, message)
    return unpaid_fees.count()


# ============ Parent Portal Views ============

@login_required
def parent_fee_list(request):
    """
    View for parents to see their children's fees and make payments.
    """
    user = request.user
    
    # Get all students linked to this user (as parent)
    from students.models import Student
    students = Student.objects.filter(parent=user)
    
    if not students.exists():
        messages.info(request, "No students linked to your account.")
        return render(request, "finance/parent_fee_list.html", {"fees": [], "students": []})
    
    # Get all fees for these students
    fees = Fee.objects.filter(
        student__in=students
    ).select_related("student", "student__user", "school").order_by("-created_at")
    
    # Check if Paystack is configured
    paystack_available = is_paystack_configured()
    
    return render(request, "finance/parent_fee_list.html", {
        "fees": fees,
        "students": students,
        "paystack_available": paystack_available
    })


def payment_success(request):
    """
    Show payment success page after successful payment.
    """
    return render(request, "finance/payment_success.html")


def check_payment_status(request):
    """
    Allow users to check payment status using their payment reference.
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
    
    # Order by most recent first
    payments = payments_qs.order_by("-created_at")[:500]  # Limit to 500 most recent
    
    # Calculate totals
    total_amount = sum(p.amount for p in payments if p.status == "completed")
    total_count = payments.count()
    
    return render(request, "finance/payment_history_list.html", {
        "payments": payments,
        "total_amount": total_amount,
        "total_count": total_count,
        "school": school,
        "filter_status": filter_status,
        "search": search,
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

    payment = get_object_or_404(FeePayment, pk=pk)
    
    # Check permissions
    if not user.is_superuser and school:
        if payment.fee.school != school:
            messages.error(request, "You don't have permission to delete this payment.")
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


# ============ Subscription Cron Endpoint (for Railway/external cron services) ============

def run_subscription_check(request):
    """
    Endpoint for external cron services (like cron-job.org) to trigger subscription checks.
    Requires a secret key for security.
    
    Usage: GET /finance/run-subscription-check/?key=YOUR_SECRET_KEY
    """
    import os
    from django.conf import settings
    
    # Get the secret key from request or environment
    provided_key = request.GET.get("key", "")
    expected_key = getattr(settings, 'CRON_SECRET_KEY', os.environ.get('CRON_SECRET_KEY', ''))
    
    # If no key is configured, allow the request (for development)
    if expected_key and provided_key != expected_key:
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
