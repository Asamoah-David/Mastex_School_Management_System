from django.core.management.base import BaseCommand
from finance.views import retry_failed_payments, notify_admin_unpaid_fees

class Command(BaseCommand):
    help = "Retry failed Flutterwave payments and notify admins of unpaid fees"

    def handle(self, *args, **kwargs):
        retried_count = retry_failed_payments()
        self.stdout.write(f"Retried {retried_count} failed payments.")

        unpaid_count = notify_admin_unpaid_fees()
        self.stdout.write(f"Notified admins about {unpaid_count} unpaid fees.")