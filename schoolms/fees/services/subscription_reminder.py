"""
Subscription Expiry Reminder Service
Sends SMS and Email reminders to schools before their subscription expires.
Run via cron job: python manage.py check_subscriptions
"""
import logging
from datetime import timedelta

logger = logging.getLogger(__name__)
from django.utils import timezone
from schools.models import School
from accounts.models import User
from services.sms_service import send_sms


def send_expiry_reminders():
    """
    Check all schools and send reminders based on days until expiry.
    - 7 days before expiry
    - 3 days before expiry
    - 1 day before expiry
    - On expiry day
    """
    today = timezone.now().date()
    schools_contacted = []
    
    schools = School.objects.filter(
        subscription_status='active',
        is_active=True
    ).exclude(subscription_end_date__isnull=True)
    
    for school in schools:
        if not school.subscription_end_date:
            continue
            
        days_left = (school.subscription_end_date.date() - today).days
        
        # Determine reminder threshold
        should_notify = False
        message = ""
        
        if days_left == 7:
            should_notify = True
            message = f"URGENT: Your {school.name} subscription expires in 7 days. Renew now to avoid interruption. Visit your dashboard to renew."
        elif days_left == 3:
            should_notify = True
            message = f"CRITICAL: {school.name} subscription expires in 3 days! Please renew immediately to maintain access."
        elif days_left == 1:
            should_notify = True
            message = f"FINAL WARNING: {school.name} subscription expires TOMORROW! Renew now to avoid losing access."
        elif days_left == 0:
            should_notify = True
            message = f"EXPIRED: {school.name} subscription has expired. Please renew immediately to regain access."
        
        if should_notify:
            # Get school admins to notify
            admins = User.objects.filter(
                school=school,
                role="school_admin",
            ).exclude(phone__isnull=True).exclude(phone__exact="")
            
            for admin in admins:
                if admin.phone:
                    try:
                        send_sms(admin.phone, message)
                        schools_contacted.append({
                            'school': school.name,
                            'admin': admin.get_full_name() or admin.username,
                            'phone': admin.phone,
                            'days_left': days_left
                        })
                    except Exception:
                        logger.warning("Failed to send subscription reminder SMS", exc_info=True)
            
            # Also send email if configured
            for admin in admins:
                if admin.email:
                    try:
                        from messaging.email_utils import send_email
                        subject = f"Subscription {'Expiring' if days_left > 0 else 'Expired'}: {school.name}"
                        send_email(
                            admin.email,
                            subject,
                            message
                        )
                    except Exception:
                        logger.warning("Failed to send subscription reminder email", exc_info=True)
            if school.email:
                try:
                    from messaging.email_utils import send_email

                    subject = f"Subscription {'Expiring' if days_left > 0 else 'Expired'}: {school.name}"
                    send_email(school.email, subject, message)
                except Exception:
                    logger.warning("Failed to send subscription reminder email to school", exc_info=True)
    
    return schools_contacted


def check_and_update_expired_subscriptions():
    """
    Mark subscriptions expired only after subscription_end_date + grace days.
    """
    from datetime import timedelta

    from core.subscription_access import subscription_grace_days_for_school

    now = timezone.now()
    expired_count = 0
    schools = School.objects.filter(
        subscription_status__in=("active", "trial"),
    ).exclude(subscription_end_date__isnull=True)

    for school in schools:
        end = school.subscription_end_date
        grace = subscription_grace_days_for_school(school)
        if now <= end + timedelta(days=grace):
            continue
        School.objects.filter(pk=school.pk).update(subscription_status="expired")
        expired_count += 1
        logger.info("Marked school subscription as expired (school_id=%s)", school.id)

        admins = User.objects.filter(school=school, role="school_admin").exclude(
            phone__isnull=True
        ).exclude(phone__exact="")

        message = (
            f"NOTICE: Your {school.name} subscription has ended (including any grace period). "
            f"Please renew to continue using the platform."
        )

        for admin in admins:
            if admin.phone:
                try:
                    send_sms(admin.phone, message)
                except Exception:
                    pass
        if school.email:
            try:
                from messaging.email_utils import send_email

                send_email(
                    school.email,
                    f"Subscription ended — {school.name}",
                    message,
                )
            except Exception:
                logger.warning("Failed school subscription expiry email", exc_info=True)

    return expired_count


def run_subscription_checks():
    """
    Main function to run all subscription checks.
    Run daily via cron: python manage.py check_subscriptions
    """
    # 1. Update expired subscriptions
    expired = check_and_update_expired_subscriptions()

    # 2. Send reminders
    reminders_sent = send_expiry_reminders()

    logger.info(
        "Subscription checks complete: expired=%s, reminders_sent=%s",
        expired,
        len(reminders_sent),
    )
    
    return {
        'expired': expired,
        'reminders': reminders_sent
    }
