"""
Custom Email Backend that uses SendGrid REST API
This replaces SMTP and works on Railway without blocked ports.
"""
import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.utils import EMAIL_ADDRESS_HEADERS


class SendGridEmailBackend(BaseEmailBackend):
    """SendGrid REST API email backend."""

    def send_messages(self, messages):
        """Send all messages using SendGrid API."""
        sendgrid_key = getattr(settings, 'SENDGRID_API_KEY', None)
        
        # Fall back to SMTP if no SendGrid API key
        if not sendgrid_key or sendgrid_key == "":
            return self._fallback_smtp(messages)
        
        num_sent = 0
        for message in messages:
            self._send_sendgrid(message, sendgrid_key)
            num_sent += 1
        return num_sent

    def _send_sendgrid(self, message, api_key):
        """Send a single message via SendGrid REST API."""
        from_email = message.from_email or getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        
        if not from_email:
            raise ValueError("No from email configured")
        
        # Handle multiple recipients
        to_emails = message.to
        if not to_emails:
            return
        
        # Build the request
        url = "https://api.sendgrid.com/v3/mail/send"
        
        # Simple text content
        body = message.body
        if message.content_subtype == 'html':
            content_type = "text/html"
        else:
            content_type = "text/plain"
        
        # Build personalizations
        personalizations = []
        for to_email in to_emails:
            personalizations.append({"email": to_email})
        
        data = {
            "personalizations": personalizations,
            "from": {"email": from_email},
            "subject": message.subject,
            "content": [
                {"type": content_type, "value": body}
            ]
        }
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        resp = requests.post(url, json=data, headers=headers, timeout=30)
        
        if resp.status_code not in [200, 201, 202]:
            raise Exception(f"SendGrid error: {resp.status_code} - {resp.text}")

    def _fallback_smtp(self, messages):
        """Fallback to SMTP if SendGrid not configured."""
        from django.core.mail.backends.smtp import EmailBackend
        backend = EmailBackend()
        return backend.send_messages(messages)