import requests
from django.conf import settings


class SMSService:
    @staticmethod
    def send_sms(to, message):
        url = "https://api.mnotify.com/api/sms/quick"
        headers = {
            "Authorization": f"Bearer {settings.MNOTIFY_API_KEY}",
            "Content-Type": "application/json",
        }
        data = {
            "recipient": [to],
            "sender": settings.MNOTIFY_SENDER_ID,
            "message": message,
            "is_schedule": False,
        }
        resp = requests.post(url, json=data, headers=headers, timeout=30)
        if resp.status_code != 200:
            # log or raise as appropriate
            raise RuntimeError(f"MNotify error: {resp.text}")
        return resp.json()


# Convenience function for backward compatibility
def send_sms(to, message):
    """Send SMS to a recipient."""
    return SMSService.send_sms(to, message)
