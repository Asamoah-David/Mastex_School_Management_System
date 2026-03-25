"""
Django management command to check and update subscription statuses.
Run daily via cron: python manage.py check_subscriptions
"""
from django.core.management.base import BaseCommand
from fees.services.subscription_reminder import run_subscription_checks


class Command(BaseCommand):
    help = 'Check subscriptions and send expiry reminders to schools'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Starting subscription check...'))
        
        result = run_subscription_checks()
        
        self.stdout.write(self.style.SUCCESS(
            f"\nCompleted:\n"
            f"  - Marked {result['expired']} subscriptions as expired\n"
            f"  - Sent {len(result['reminders'])} reminder notifications"
        ))
