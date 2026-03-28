"""
SendGrid Email Service - Uses SendGrid REST API directly
"""
import requests
from django.conf import settings


class SendGridEmail:
    @staticmethod
    def send_email(to_email, subject, message):
        """Send email using SendGrid API."""
        api_key = getattr(settings, 'SENDGRID_API_KEY', None)
        if not api_key or api_key == "":
            raise RuntimeError("SendGrid API key not configured. Please set SENDGRID_API_KEY in environment variables.")
        
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        if not from_email or from_email == "":
            raise RuntimeError("Default from email not configured. Please set DEFAULT_FROM_EMAIL in environment variables.")
        
        if not to_email or '@' not in str(to_email):
            raise RuntimeError(f"Invalid recipient email: {to_email}")
        
        url = "https://api.sendgrid.com/v3/mail/send"
        
        data = {
            "personalizations": [{
                "to": [{"email": to_email}]
            }],
            "from": {"email": from_email},
            "subject": subject,
            "content": [{
                "type": "text/plain",
                "value": message
            }]
        }
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            resp = requests.post(url, json=data, headers=headers, timeout=30)
            
            if resp.status_code in [200, 201, 202]:
                return {"status": "success", "message": "Email sent successfully"}
            elif resp.status_code == 400:
                raise RuntimeError(f"SendGrid error: {resp.text}")
            elif resp.status_code == 401:
                raise RuntimeError("SendGrid API key is invalid.")
            elif resp.status_code == 403:
                raise RuntimeError("SendGrid API access forbidden.")
            else:
                raise RuntimeError(f"SendGrid error: {resp.status_code} - {resp.text}")
        except requests.exceptions.Timeout:
            raise RuntimeError("SendGrid request timed out.")
        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(f"Network error: {str(e)}")


def send_email(to_email, subject, message):
    """Convenience function."""
    return SendGridEmail.send_email(to_email, subject, message)