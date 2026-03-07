from services.sms_service import SMSService


def send_sms(to, message):
    """
    Convenience wrapper used by other apps for sending SMS.
    Delegates to the central SMSService implementation.
    """
    return SMSService.send_sms(to, message)


def send_sms_notification(to, message):
    """
    Backwards-compatible alias; prefer send_sms going forward.
    """
    return SMSService.send_sms(to, message)