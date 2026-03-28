"""
Custom Email Backend that uses SendGrid REST API
This replaces SMTP and works on Railway without blocked ports.
"""
import logging
import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)


class SendGridEmailBackend(BaseEmailBackend):
    """SendGrid REST API email backend."""

    def send_messages(self, messages):
        """Send all messages using SendGrid API."""
        # Use EMAIL_HOST_PASSWORD which is already set in Railway
        api_key = getattr(settings, 'EMAIL_HOST_PASSWORD', None)
        
        logger.info(f"SendGrid backend: API key present: {bool(api_key)}")
        
        # Fall back to SMTP if no SendGrid API key
        if not api_key or api_key == "":
            logger.warning("No SendGrid API key, falling back to SMTP")
            return self._fallback_smtp(messages)
        
        num_sent = 0
        for message in messages:
            try:
                self._send_sendgrid(message, api_key)
                num_sent += 1
                logger.info(f"Email sent successfully to {message.to}")
            except Exception as e:
                logger.error(f"Failed to send email: {e}")
                raise
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
        
        logger.info(f"Sending email to {to_emails} via SendGrid")
        
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
        
        logger.info(f"SendGrid request: {data}")
        
        resp = requests.post(url, json=data, headers=headers, timeout=30)
        
        logger.info(f"SendGrid response status: {resp.status_code}")
        
        if resp.status_code not in [200, 201, 202]:
            raise Exception(f"SendGrid error: {resp.status_code} - {resp.text}")

    def _fallback_smtp(self, messages):
        """Fallback to SMTP if SendGrid not configured."""
        from django.core.mail.backends.smtp import EmailBackend
        backend = EmailBackend()
        return backend.send_messages(messages)
