"""
Paystack Payment Service for School Fees
Handles payment initialization, verification, and webhook processing
"""
import requests
import hashlib
import hmac
from django.conf import settings
from django.utils import timezone


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
    
    def initialize_payment(self, email, amount, callback_url, reference=None, metadata=None, subaccount=None, split_code=None):
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
            
        Returns:
            dict with status, authorization_url, reference
        """
        if not reference:
            import uuid
            reference = f"SCHOOL_FEE_{uuid.uuid4().hex[:12].upper()}"
        
        data = {
            "email": email,
            "amount": int(amount * 100),  # Convert to kobo
            "reference": reference,
            "callback_url": callback_url,
            "currency": self.currency,
            "metadata": metadata or {}
        }
        
        # Add subaccount for direct payment to school
        if subaccount:
            data["subaccount"] = subaccount
            data["bearer_type"] = "account"
        
        # Add split code for payment splitting
        if split_code:
            data["split_code"] = split_code
        
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
            secret_key: Paystack webhook secret
            
        Returns:
            bool indicating if signature is valid
        """
        expected_signature = hmac.new(
            secret_key.encode('utf-8'),
            request_body,
            hashlib.sha512
        ).hexdigest()
        return hmac.compare_digest(expected_signature, signature)


# Singleton instance
paystack_service = PaystackService()
