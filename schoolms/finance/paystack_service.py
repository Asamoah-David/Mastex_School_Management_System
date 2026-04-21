"""
Paystack Payment Service for School Fees
Handles payment initialization, verification, and webhook processing
"""
from __future__ import annotations

import hashlib
import hmac
from decimal import Decimal, ROUND_UP

import requests
from django.conf import settings


def pass_processing_fee_to_payer() -> bool:
    """When True, customer pays a uplift so settlement approximates full net to school/platform."""
    return getattr(settings, "PAYSTACK_PASS_FEE_TO_PAYER", True)


def processing_fee_percent_decimal() -> Decimal:
    """Estimated Paystack % deducted from settlement; used only for gross-up (tune per Paystack pricing)."""
    return Decimal(str(getattr(settings, "PAYSTACK_PROCESSING_FEE_PERCENT", 1.95)))


def compute_paystack_gross_from_net(net: Decimal) -> tuple[Decimal, Decimal]:
    """
    Return (net, gross) amounts in major currency units.
    If pass-through is off, gross == net.
    Gross is rounded up to 2 dp so the school-side net is not under-funded vs estimate.
    """
    net = Decimal(str(net)).quantize(Decimal("0.01"))
    if not pass_processing_fee_to_payer():
        return net, net
    p = processing_fee_percent_decimal()
    if p <= 0:
        return net, net
    denom = Decimal("1") - (p / Decimal("100"))
    if denom <= 0:
        return net, net
    gross = (net / denom).quantize(Decimal("0.01"), rounding=ROUND_UP)
    if gross < net:
        gross = net
    return net, gross


class PaystackService:
    """Paystack API integration for school fee payments."""
    
    def __init__(self):
        self.secret_key = settings.PAYSTACK_SECRET_KEY
        self.public_key = settings.PAYSTACK_PUBLIC_KEY
        self.base_url = "https://api.paystack.co"
        self.platform_fee_percent = getattr(settings, 'PAYSTACK_PLATFORM_FEE_PERCENT', 0)
        self.currency = getattr(settings, 'PAYSTACK_CURRENCY', 'GHS')
    
    def _get_headers(self):
        """Get headers for Paystack API requests."""
        return {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json"
        }
    
    def initialize_payment(self, email, amount, callback_url, reference=None, metadata=None, subaccount=None, split_code=None, channels=None, currency=None):
        """
        Initialize a Paystack payment.
        
        Args:
            email: Customer's email address
            amount: Amount in GHS (will be converted to kobo)
            callback_url: URL to redirect after payment
            reference: Unique transaction reference
            metadata: Additional data to pass
            subaccount: Paystack subaccount code for direct payment to school
            split_code: Paystack split code for payment splitting
            channels: List of payment channels (e.g., ['card'], ['mobile_money'], ['bank'])
            currency: Currency code (e.g., 'GHS', 'NGN'). Defaults to settings.PAYSTACK_CURRENCY
            
        Returns:
            dict with status, authorization_url, reference
        """
        if not reference:
            import uuid
            reference = f"SCHOOL_FEE_{uuid.uuid4().hex[:12].upper()}"
        
        # Use provided currency or fall back to default
        currency_code = currency if currency else self.currency
        
        data = {
            "email": email,
            "amount": int(amount * 100),  # Convert to kobo
            "reference": reference,
            "callback_url": callback_url,
            "currency": currency_code,
            "metadata": metadata or {}
        }
        
        # Add subaccount for direct payment to school
        if subaccount:
            data["subaccount"] = subaccount
            data["bearer_type"] = "account"
        
        # Add split code for payment splitting
        if split_code:
            data["split_code"] = split_code
        
        # Add channels for specific payment methods (card, mobile_money, bank)
        if channels:
            data["channels"] = channels
        
        try:
            response = requests.post(
                f"{self.base_url}/transaction/initialize",
                json=data,
                headers=self._get_headers(),
                timeout=30
            )
            return response.json()
        except Exception as e:
            return {"status": False, "message": str(e)}
    
    def verify_payment(self, reference):
        """
        Verify a Paystack payment by reference.
        
        Args:
            reference: Transaction reference
            
        Returns:
            dict with payment status and details
        """
        try:
            response = requests.get(
                f"{self.base_url}/transaction/verify/{reference}",
                headers=self._get_headers(),
                timeout=30
            )
            return response.json()
        except Exception as e:
            return {"status": False, "message": str(e)}
    
    def get_payment_details(self, reference):
        """
        Get detailed payment information.
        
        Args:
            reference: Transaction reference
            
        Returns:
            dict with payment details
        """
        try:
            response = requests.get(
                f"{self.base_url}/transaction/{reference}",
                headers=self._get_headers(),
                timeout=30
            )
            return response.json()
        except Exception as e:
            return {"status": False, "message": str(e)}
    
    def list_transactions(self, per_page=50, page=1):
        """
        List all transactions.
        
        Args:
            per_page: Number of transactions per page
            page: Page number
            
        Returns:
            dict with transactions list
        """
        try:
            response = requests.get(
                f"{self.base_url}/transaction",
                headers=self._get_headers(),
                params={"perPage": per_page, "page": page},
                timeout=30
            )
            return response.json()
        except Exception as e:
            return {"status": False, "message": str(e)}
    
    def charge_authorization(self, email, amount, authorization_code, reference=None):
        """
        Charge a customer using saved authorization.
        
        Args:
            email: Customer's email
            amount: Amount in GHS
            authorization_code: Saved authorization code
            reference: Unique reference
            
        Returns:
            dict with charge status
        """
        if not reference:
            import uuid
            reference = f"CHARGE_{uuid.uuid4().hex[:12].upper()}"
        
        data = {
            "email": email,
            "amount": int(amount * 100),
            "authorization_code": authorization_code,
            "reference": reference,
            "currency": self.currency
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/charge_authorization",
                json=data,
                headers=self._get_headers(),
                timeout=30
            )
            return response.json()
        except Exception as e:
            return {"status": False, "message": str(e)}
    
    @staticmethod
    def verify_webhook_signature(request_body, signature, secret_key):
        """
        Verify Paystack webhook signature.
        
        Args:
            request_body: Raw request body
            signature: Paystack signature from headers
            secret_key: Paystack API secret key (same key used for HMAC webhook verification)
            
        Returns:
            bool indicating if signature is valid
        """
        expected_signature = hmac.HMAC(
            secret_key.encode('utf-8'),
            request_body,
            hashlib.sha512
        ).hexdigest()
        return hmac.compare_digest(expected_signature, signature)

    def list_banks(self, *, country: str = "ghana", currency: str | None = None):
        """List Paystack-supported banks (for building the bank-code dropdown)."""
        params = {"country": country, "perPage": 100}
        if currency:
            params["currency"] = currency
        try:
            response = requests.get(
                f"{self.base_url}/bank",
                params=params,
                headers=self._get_headers(),
                timeout=30,
            )
            return response.json()
        except Exception as e:
            return {"status": False, "message": str(e)}

    def create_subaccount(
        self,
        *,
        business_name: str,
        settlement_bank: str,
        account_number: str,
        percentage_charge: float = 0.0,
        primary_contact_email: str | None = None,
        primary_contact_name: str | None = None,
        primary_contact_phone: str | None = None,
        metadata: dict | None = None,
    ):
        """Create a Paystack subaccount for a school. `settlement_bank` is the Paystack bank code."""
        body = {
            "business_name": (business_name or "").strip()[:200],
            "settlement_bank": str(settlement_bank).strip(),
            "account_number": str(account_number).strip(),
            "percentage_charge": float(percentage_charge or 0),
        }
        if primary_contact_email:
            body["primary_contact_email"] = primary_contact_email.strip()[:200]
        if primary_contact_name:
            body["primary_contact_name"] = primary_contact_name.strip()[:200]
        if primary_contact_phone:
            body["primary_contact_phone"] = primary_contact_phone.strip()[:30]
        if metadata:
            body["metadata"] = metadata
        try:
            response = requests.post(
                f"{self.base_url}/subaccount",
                json=body,
                headers=self._get_headers(),
                timeout=45,
            )
            return response.json()
        except Exception as e:
            return {"status": False, "message": str(e)}

    def create_transfer_recipient(
        self,
        *,
        recipient_type: str,
        name: str,
        account_number: str,
        bank_code: str,
        currency: str | None = None,
    ):
        """
        Create a Paystack transfer recipient (mobile_money or nuban for Ghana).
        See https://paystack.com/docs/api/#transfer-recipient
        """
        currency_code = currency or self.currency
        body = {
            "type": recipient_type,
            "name": name[:100],
            "account_number": str(account_number).strip(),
            "bank_code": str(bank_code).strip(),
            "currency": currency_code,
        }
        try:
            response = requests.post(
                f"{self.base_url}/transferrecipient",
                json=body,
                headers=self._get_headers(),
                timeout=45,
            )
            return response.json()
        except Exception as e:
            return {"status": False, "message": str(e)}

    def initiate_transfer(
        self,
        *,
        amount_major: Decimal,
        recipient_code: str,
        reason: str,
        reference: str,
        currency: str | None = None,
        metadata: dict | None = None,
    ):
        """
        Queue a transfer from Paystack merchant balance.
        amount_major: e.g. Decimal('100.50') GHS → sent as pesewas.
        """
        currency_code = currency or self.currency
        major = Decimal(str(amount_major)).quantize(Decimal("0.01"))
        amount_minor = int(major * 100)
        body = {
            "source": "balance",
            "amount": amount_minor,
            "recipient": recipient_code,
            "reason": (reason or "Staff payroll")[:110],
            "reference": reference[:99],
            "currency": currency_code,
        }
        if metadata:
            body["metadata"] = metadata
        try:
            response = requests.post(
                f"{self.base_url}/transfer",
                json=body,
                headers=self._get_headers(),
                timeout=45,
            )
            return response.json()
        except Exception as e:
            return {"status": False, "message": str(e)}


# Singleton instance
paystack_service = PaystackService()
