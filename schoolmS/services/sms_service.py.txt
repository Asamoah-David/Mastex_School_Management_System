import requests
from django.conf import settings


class SMSService:

    @staticmethod
    def send_sms(phone, message):

        url = settings.MNOTIFY_URL

        payload = {
            "recipient": phone,
            "sender": settings.MNOTIFY_SENDER_ID,
            "message": message,
            "key": settings.MNOTIFY_API_KEY
        }

        try:
            response = requests.post(url, data=payload)

            if response.status_code == 200:
                return True

            return False

        except Exception as e:
            print("SMS Error:", str(e))
            return False