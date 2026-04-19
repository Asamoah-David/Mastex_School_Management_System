from django.core.management.base import BaseCommand
from django.db.models import Count


class Command(BaseCommand):
    help = "Check for duplicate non-empty payment_reference values before applying unique constraints."

    def handle(self, *args, **options):
        from operations.models import BusPayment, TextbookSale, HostelFee, CanteenPayment
        from finance.models import FeePayment, SubscriptionPayment

        checks = [
            ("BusPayment", BusPayment.objects.exclude(payment_reference__isnull=True).exclude(payment_reference="")),
            ("TextbookSale", TextbookSale.objects.exclude(payment_reference__isnull=True).exclude(payment_reference="")),
            ("HostelFee", HostelFee.objects.exclude(payment_reference__isnull=True).exclude(payment_reference="")),
            ("CanteenPayment", CanteenPayment.objects.exclude(payment_reference__isnull=True).exclude(payment_reference="")),
            ("FeePayment", FeePayment.objects.exclude(paystack_reference__isnull=True).exclude(paystack_reference="")),
            (
                "SubscriptionPayment",
                SubscriptionPayment.objects.exclude(paystack_reference__isnull=True).exclude(paystack_reference=""),
            ),
        ]

        found_any = False
        for label, qs in checks:
            field = "paystack_reference" if label in ("FeePayment", "SubscriptionPayment") else "payment_reference"
            dups = (
                qs.values(field)
                .annotate(c=Count("id"))
                .filter(c__gt=1)
                .order_by("-c")
            )
            if not dups.exists():
                self.stdout.write(self.style.SUCCESS(f"{label}: OK (no duplicate non-empty payment_reference values)"))
                continue

            found_any = True
            self.stdout.write(self.style.ERROR(f"{label}: Found duplicates"))
            for row in dups[:200]:
                ref = row.get(field)
                count = row.get("c")
                self.stdout.write(f"  - {ref!r}: {count} rows")

        if found_any:
            raise SystemExit(2)
