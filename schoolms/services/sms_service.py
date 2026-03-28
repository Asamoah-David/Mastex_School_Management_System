import requests
from django.conf import settings


class SMSService:
    @staticmethod
    def send_sms(to, message):
        # Validate API key is configured
        api_key = settings.MNOTIFY_API_KEY
        if not api_key or api_key == "":
            raise RuntimeError("MNotify API key not configured. Please set MNOTIFY_API_KEY in environment variables.")
        
        # Validate sender ID is configured
        sender_id = settings.MNOTIFY_SENDER_ID
        if not sender_id or sender_id == "":
            raise RuntimeError("MNotify sender ID not configured. Please set MNOTIFY_SENDER_ID in environment variables.")
        
        # Validate recipient phone number
        if not to or to.strip() == "":
            raise RuntimeError("Recipient phone number is required.")
        
        # Clean phone number - remove any spaces or special characters
        phone = ''.join(c for c in str(to) if c.isdigit() or c == '+')
        
        # Check if phone number has at least 10 digits (basic validation)
        if len(phone) < 10:
            raise RuntimeError(f"Invalid phone number format: {to}. Please use international format like +233123456789")
        
        url = "https://api.mnotify.com/api/sms/quick"
        
        # MNotify expects key in JSON body, not Authorization header
        headers = {"Content-Type": "application/json"}
        
        data = {
            "key": api_key,
            "recipient": [phone],
            "sender": sender_id,
            "message": message,
        }
        
        try:
            resp = requests.post(url, json=data, headers=headers, timeout=30)
            
            if resp.status_code == 200:
                result = resp.json()
                if result.get('status') == 'success' or result.get('code') == '2000':
                    return result
                else:
                    raise RuntimeError(f"MNotify SMS failed: {result.get('message', resp.text)}")
            elif resp.status_code == 401:
                raise RuntimeError("MNotify API authentication failed. Check your API key is correct.")
            elif resp.status_code == 403:
                raise RuntimeError("MNotify API access forbidden. Your API key may have expired.")
            else:
                raise RuntimeError(f"MNotify SMS failed: {resp.text}")
        except requests.exceptions.Timeout:
            raise RuntimeError("Connection to MNotify timed out. Please check your network.")
        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(f"Network error: {str(e)}")


# Convenience function for backward compatibility
def send_sms(to, message):
    """Send SMS to a recipient."""
