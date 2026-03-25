import logging
from services.sms_service import SMSService
from django.conf import settings

logger = logging.getLogger(__name__)


def notify_admin_unpaid_fee(student):
    """
    Send SMS notification to admin when a student has unpaid fees.
    """
    try:
        message = f"""
Mastex SchoolOS Alert

Student: {student.name}
Parent: {student.parent_name}

has unpaid school fees.
"""
        if settings.ADMIN_PHONE:
            SMSService.send_sms(settings.ADMIN_PHONE, message)
            logger.info(f"Unpaid fee notification sent for student: {student.name}")
        else:
            logger.warning("ADMIN_PHONE not configured, skipping notification")
    except Exception as e:
        logger.error(f"Failed to send unpaid fee notification: {e}")


def notify_parent_fee_paid(student, amount):
    """
    Send SMS notification to parent when fee payment is received.
    """
    try:
        if student.parent and student.parent.phone:
            message = f"""
Mastex SchoolOS

Payment received!

Student: {student.name}
Amount: GHS {amount}

Thank you for your payment.
"""
            SMSService.send_sms(student.parent.phone, message)
            logger.info(f"Fee payment notification sent for student: {student.name}")
    except Exception as e:
        logger.error(f"Failed to send fee payment notification: {e}")
