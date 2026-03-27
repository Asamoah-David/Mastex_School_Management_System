import requests
from django.conf import settings


class SMSService:
    @staticmethod
    def send_sms(to, message):
        url = "https://api.mnotify.com/api/sms/quick"
        api_key = settings.MNOTIFY_API_KEY
        
        # Try with Bearer prefix first, if that fails try without
        headers_list = [
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            {"Authorization": api_key, "Content-Type": "application/json"},
        ]
        
        data = {
            "recipient": [to],
            "sender": settings.MNOTIFY_SENDER_ID,
            "message": message,
            "is_schedule": False,
        }
        
        last_error = None
        for headers in headers_list:
            try:
                resp = requests.post(url, json=data, headers=headers, timeout=30)
                if resp.status_code == 200:
                    return resp.json()
                last_error = resp.text
                # If this format failed, try next format
            except Exception as e:
                last_error = str(e)
                continue
        
        raise RuntimeError(f"MNotify error: {last_error}")


# Convenience function for backward compatibility
def send_sms(to, message):
    """Send SMS to a recipient."""
    return SMSService.send_sms(to, message)
