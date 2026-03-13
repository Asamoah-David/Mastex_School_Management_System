import uuid
import json
import requests
from django.conf import settings
from django.http import HttpResponse, Http404
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages

from django.contrib.auth.decorators import login_required
from accounts.permissions import is_school_admin, user_can_manage_school

from .models import Fee, FeeStructure
from .flutterwave_service import initialize_payment
from accounts.models import User
from messaging.utils import send_sms


def pay_with_flutterwave(request, fee_id):
    """
    Initialize Flutterwave payment for a fee.
    This view now fails gracefully instead of raising 500 errors when
    configuration or Flutterwave responses are invalid.
    """
    fee = get_object_or_404(Fee, id=fee_id)

    # Ensure Flutterwave secret/public keys are configured
    if not settings.FLW_PUBLIC_KEY or not settings.FLW_SECRET_KEY:
        messages.error(
            request,
            "Online payments are not configured yet. Please contact the administrator.",
        )
        # Redirect back to a safe page (student detail or a generic page)
        return redirect(request.META.get("HTTP_REFERER", "/"))

    tx_ref = str(uuid.uuid4())
    fee.flutterwave_tx_ref = tx_ref
    fee.save()

    # Build a proper callback URL for the current environment
    callback_url = request.build_absolute_uri(
        reverse("finance:flutterwave_callback")
    )

    try:
        response = initialize_payment(
            amount=str(fee.amount),
            email=fee.student.user.email,
            tx_ref=tx_ref,
            redirect_url=callback_url,
        )
        # Defensive check on Flutterwave response structure
        payment_link = response.get("data", {}).get("link")
        if not payment_link:
            raise ValueError("No payment link returned from Flutterwave.")
    except Exception as exc:
        messages.error(
            request,
            "Could not initialize payment at this time. Please try again later.",
        )
        return redirect(request.META.get("HTTP_REFERER", "/"))

    return redirect(payment_link)

def retry_failed_payments():
    """
    Retry all unpaid fees that have a Flutterwave transaction reference
    """
    failed_fees = Fee.objects.filter(paid=False, flutterwave_tx_ref__isnull=False)
    for fee in failed_fees:
        # Generate new transaction reference
        tx_ref = str(uuid.uuid4())
        fee.flutterwave_tx_ref = tx_ref
        fee.save()
        # Re-initiate payment
        # Best-effort retry – ignore individual failures to avoid crashing the job
        try:
            initialize_payment(
                amount=str(fee.amount),
                email=fee.student.user.email,
                tx_ref=tx_ref,
                redirect_url="",  # Webhook will still confirm payment
            )
        except Exception:
            continue
    return len(failed_fees)

def notify_admin_unpaid_fees():
    """
    Notify all admin users of unpaid fees
    """
    unpaid_fees = Fee.objects.filter(paid=False)
    admins = User.objects.filter(role="admin")
    for admin in admins:
        message = f"There are {unpaid_fees.count()} unpaid fees pending in the system."
        if admin.phone:
            send_sms(admin.phone, message)
    return unpaid_fees.count()


@login_required
def fee_list(request):
    """
    Simple fee management view for school admins.

    - School admins / admins see only their school's fees.
    - Platform superusers can see all fees across schools.
    - Allows marking individual fees as paid when parents pay offline.
    """
    user = request.user
    school = getattr(user, "school", None)

    if not school and not user.is_superuser:
        # Non-superusers must be attached to a school to manage fees
        messages.error(request, "You are not attached to any school.")
        return redirect("accounts:dashboard")

    if not (user.is_superuser or user_can_manage_school(user)):
        messages.error(request, "You do not have permission to manage fees.")
        return redirect("accounts:dashboard")

    # Handle mark-as-paid action
    if request.method == "POST":
        fee_id = request.POST.get("fee_id")
        action = request.POST.get("action")
        if fee_id and action == "mark_paid":
            qs = Fee.objects.all()
            if not user.is_superuser and school:
                qs = qs.filter(school=school)
            fee = qs.filter(id=fee_id).first()
            if fee:
                fee.paid = True
                fee.save(update_fields=["paid"])
                messages.success(request, "Fee marked as paid.")
        return redirect("finance:fee_list")

    # List unpaid fees for this school (or all schools for superuser)
    fees_qs = Fee.objects.filter(paid=False).select_related("student", "student__user", "school")
    if not user.is_superuser and school:
        fees_qs = fees_qs.filter(school=school)

    fees = fees_qs.order_by("student__school__name", "student__class_name", "student__admission_number")

    return render(
        request,
        "finance/fee_list.html",
        {"fees": fees, "school": school},
    )

def flutterwave_callback(request):
    """
    Handle Flutterwave payment callback.
    Previously, unexpected response structures from Flutterwave could raise
    KeyError/TypeError and cause 500 errors; this now fails gracefully.
    """
    transaction_id = request.GET.get("transaction_id")
    if not transaction_id:
        return HttpResponse("Missing transaction id", status=400)

    if not settings.FLW_SECRET_KEY:
        return HttpResponse("Payment verification is not configured.", status=500)

    headers = {"Authorization": f"Bearer {settings.FLW_SECRET_KEY}"}

    try:
        response = requests.get(
            f"https://api.flutterwave.com/v3/transactions/{transaction_id}/verify",
            headers=headers,
            timeout=15,
        )
        response.raise_for_status()
        result = response.json()
    except Exception:
        return HttpResponse("Could not verify payment.", status=502)

    try:
        if result.get("status") == "success":
            data = result.get("data", {})
            tx_ref = data.get("tx_ref")
            amount = data.get("amount")
            fee = Fee.objects.filter(flutterwave_tx_ref=tx_ref).first()
            if fee and amount is not None and float(amount) == float(fee.amount):
                fee.paid = True
                fee.save()
                return HttpResponse("Payment successful")
    except Exception:
        # Any parsing / casting issues should not crash the view
        pass

    return HttpResponse("Payment failed", status=400)

@csrf_exempt
def flutterwave_webhook(request):
    """
    Handle Flutterwave webhook.
    This endpoint is intentionally very defensive to avoid 500s from malformed
    or repeated webhooks.
    """
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    if payload.get("event") == "charge.completed":
        data = payload.get("data", {})
        if data.get("status") == "successful":
            tx_ref = data.get("tx_ref")
            if tx_ref:
                fee = Fee.objects.filter(flutterwave_tx_ref=tx_ref).first()
                if fee:
                    fee.paid = True
                    fee.save()
    return HttpResponse(status=200)


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