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


def is_paystack_configured():
    """Check if Paystack is properly configured."""
    return bool(settings.PAYSTACK_SECRET_KEY)


def pay_with_paystack(request, fee_id):
    """
    Initialize Paystack payment for a fee.
    Supports partial payments - parent can pay any amount.
    Payment goes directly to school's subaccount if configured.
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
    
    # Initialize payment with Paystack
    response = paystack_service.initialize_payment(
        email=email,
        amount=amount,
        callback_url=callback_url,
        reference=reference,
        metadata={
            "fee_id": fee_id,
            "student_name": str(fee.student),
            "school_name": fee.school.name if fee.school else "",
            "school_id": fee.school.id if fee.school else None,
        },
        subaccount=school_subaccount,  # Pass school's subaccount for direct payment
        channels=['card', 'mobile_money', 'bank']
    )
    
    if response.get("status") and response.get("data", {}).get("authorization_url"):
        # Store reference in session for verification
        request.session[f"paystack_ref_{fee_id}"] = reference
        return redirect(response["data"]["authorization_url"])
    else:
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
            
            # Initialize payment
            response = paystack_service.initialize_payment(
                email=email,
                amount=amount,
                callback_url=callback_url,
                reference=reference,
                metadata={
                    "fee_id": fee_id,
                    "student_name": str(fee.student),
                    "school_name": fee.school.name if fee.school else "",
                    "school_id": fee.school.id if fee.school else None,
                },
                subaccount=school_subaccount,  # Pass school's subaccount for direct payment
                channels=['card', 'mobile_money', 'bank']
            )
            
            if response.get("status") and response.get("data", {}).get("authorization_url"):
                request.session[f"paystack_ref_{fee_id}"] = reference
                request.session[f"paystack_amount_{fee_id}"] = amount
                return redirect(response["data"]["authorization_url"])
            else:
                error_msg = response.get("message", "Could not initialize payment.")
                messages.error(request, error_msg)
                
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
            return redirect("finance:payment_success")
            
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
    """
    if request.method != "POST":
        return HttpResponse(status=405)
    
    # Verify webhook signature
    signature = request.headers.get("x-paystack-signature")
    if signature and settings.PAYSTACK_WEBHOOK_SECRET:
        body = request.body
        if not paystack_service.verify_webhook_signature(body, signature, settings.PAYSTACK_WEBHOOK_SECRET):
            return HttpResponse("Invalid signature", status=403)
    
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse(status=400)
    
    event = payload.get("event")
    
    if event == "charge.success":
        data = payload.get("data", {})
        reference = data.get("reference")
        
        if reference:
            # Find fee by reference in metadata or payment record
            metadata = data.get("metadata", {})
            fee_id = metadata.get("fee_id")
            
            if fee_id:
                try:
                    fee = Fee.objects.get(id=fee_id)
                    amount = float(data.get("amount", 0)) / 100
                    
                    # Create payment record
                    FeePayment.objects.create(
                        fee=fee,
                        amount=amount,
                        paystack_payment_id=data.get("id"),
                        paystack_reference=reference,
                        payment_method=data.get("authorization", {}).get("channel", "card"),
                        status="completed"
                    )
                    
                    # Update fee
                    fee.amount_paid = float(fee.amount_paid) + amount
                    fee.paystack_payment_id = data.get("id")
                    fee.paystack_reference = reference
                    fee.save()
                    
                except Fee.DoesNotExist:
                    pass
    
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
        },
        channels=['card', 'mobile_money', 'bank']
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
