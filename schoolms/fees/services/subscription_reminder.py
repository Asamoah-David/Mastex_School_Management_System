"""
Subscription Expiry Reminder Service
Sends SMS and Email reminders to schools before their subscription expires.
Run via cron job: python manage.py check_subscriptions
"""
from datetime import timedelta
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
                role__in=['admin', 'school_admin']
            ).exclude(phone__isnull=True).exclude(phone__exact='')
            
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
                    except Exception as e:
                        print(f"Failed to send SMS to {admin.phone}: {e}")
            
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
                    except Exception as e:
                        print(f"Failed to send email to {admin.email}: {e}")
    
    return schools_contacted


def check_and_update_expired_subscriptions():
    """
    Automatically update subscription status for expired schools.
    This should run daily via cron job.
    """
    today = timezone.now()
    expired_count = 0
    
    # Find active subscriptions that have passed their end date
    schools = School.objects.filter(
        subscription_status='active',
        subscription_end_date__lt=today
    )
    
    for school in schools:
        school.subscription_status = 'expired'
        school.save(update_fields=['subscription_status'])
        expired_count += 1
        print(f"Marked {school.name} as expired")
        
        # Notify school admins
        admins = User.objects.filter(
            school=school,
            role__in=['admin', 'school_admin']
        ).exclude(phone__isnull=True).exclude(phone__exact='')
        
        message = f"NOTICE: Your {school.name} subscription has expired. Please renew to continue using the platform."
        
        for admin in admins:
            if admin.phone:
                try:
                    send_sms(admin.phone, message)
                except Exception:
                    pass
    
    return expired_count


def run_subscription_checks():
    """
    Main function to run all subscription checks.
    Run daily via cron: python manage.py check_subscriptions
    """
    print("=== Starting Subscription Checks ===")
    
    # 1. Update expired subscriptions
    print("\n[1] Checking for expired subscriptions...")
    expired = check_and_update_expired_subscriptions()
    print(f"    Marked {expired} subscriptions as expired")
    
    # 2. Send reminders
    print("\n[2] Sending expiry reminders...")
    reminders_sent = send_expiry_reminders()
    print(f"    Sent {len(reminders_sent)} reminder notifications")
    
    print("\n=== Subscription Checks Complete ===")
    
    return {
        'expired': expired,
        'reminders': reminders_sent
    }
