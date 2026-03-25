from schoolms.services.sms_service import SMSService


def send_fee_reminder(student):

    message = f"""
Reminder:

{student.name} has an outstanding school fee.

Please login to the portal and complete payment.
"""

    SMSService.send_sms(student.parent_phone, message)