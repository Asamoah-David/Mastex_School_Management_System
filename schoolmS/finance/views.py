import uuid
from django.shortcuts import redirect, render
from django.http import HttpResponse
from .models import Fee
from .flutterwave_service import initialize_payment
from django.conf import settings
import requests
from django.views.decorators.csrf import csrf_exempt
import json
from accounts.models import User
from messaging.utils import send_sms

def pay_with_flutterwave(request, fee_id):
    """
    Initialize Flutterwave payment for a fee
    """
    fee = Fee.objects.get(id=fee_id)
    tx_ref = str(uuid.uuid4())
    fee.flutterwave_tx_ref = tx_ref
    fee.save()

    response = initialize_payment(
        amount=str(fee.amount),
        email=fee.student.user.email,
        tx_ref=tx_ref,
        redirect_url="https://yourdomain.com/finance/flutterwave-callback/"
    )
    payment_link = response["data"]["link"]
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
        initialize_payment(
            amount=str(fee.amount),
            email=fee.student.user.email,
            tx_ref=tx_ref,
            redirect_url="https://yourdomain.com/finance/flutterwave-callback/"
        )
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

def flutterwave_callback(request):
    """
    Handle Flutterwave payment callback
    """
    transaction_id = request.GET.get("transaction_id")
    headers = {"Authorization": f"Bearer {settings.FLW_SECRET_KEY}"}
    response = requests.get(f"https://api.flutterwave.com/v3/transactions/{transaction_id}/verify", headers=headers)
    result = response.json()

    if result["status"] == "success":
        tx_ref = result["data"]["tx_ref"]
        amount = result["data"]["amount"]
        fee = Fee.objects.filter(flutterwave_tx_ref=tx_ref).first()
        if fee and float(amount) == float(fee.amount):
            fee.paid = True
            fee.save()
            return HttpResponse("Payment successful")
    return HttpResponse("Payment failed")

@csrf_exempt
def flutterwave_webhook(request):
    """
    Handle Flutterwave webhook
    """
    payload = json.loads(request.body)
    if payload.get("event") == "charge.completed":
        data = payload["data"]
        if data["status"] == "successful":
            tx_ref = data["tx_ref"]
            fee = Fee.objects.filter(flutterwave_tx_ref=tx_ref).first()
            if fee:
                fee.paid = True
                fee.save()
    return HttpResponse(status=200)       