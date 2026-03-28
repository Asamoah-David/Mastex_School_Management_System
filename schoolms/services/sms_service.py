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
        
        # Try with Bearer prefix first, if that fails try without
        headers_list = [
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            {"Authorization": api_key, "Content-Type": "application/json"},
        ]
        
        data = {
            "recipient": [phone],
            "sender": sender_id,
            "message": message,
            "is_schedule": False,
        }
        
        last_error = None
        for headers in headers_list:
            try:
                resp = requests.post(url, json=data, headers=headers, timeout=30)
                
                # MNotify returns 200 on success, but also check for 'code' in response
                if resp.status_code == 200:
                    result = resp.json()
                    # Check if API indicates success (code 0 or success=True)
                    if result.get('code') == 0 or result.get('success') == True or result.get('status') == 'success':
                        return result
                    # API returned 200 but with error
                    last_error = result.get('message', result.get('error', resp.text))
                    continue
                elif resp.status_code == 401:
                    last_error = "MNotify API authentication failed. Check your API key is correct."
                elif resp.status_code == 403:
                    last_error = "MNotify API access forbidden. Your API key may have expired or been deactivated."
                elif resp.status_code == 429:
                    last_error = "MNotify API rate limit exceeded. Please try again later."
                else:
                    last_error = resp.text
            except requests.exceptions.Timeout:
                last_error = "Connection to MNotify timed out. Please check your network."
            except requests.exceptions.ConnectionError as e:
                last_error = f"Network error connecting to MNotify: {str(e)}. Check if outbound connections are allowed."
            except Exception as e:
                last_error = f"Unexpected error: {str(e)}"
                continue
        
        raise RuntimeError(f"MNotify SMS failed: {last_error}")


# Convenience function for backward compatibility
def send_sms(to, message):
    """Send SMS to a recipient."""
    return SMSService.send_sms(to, message)