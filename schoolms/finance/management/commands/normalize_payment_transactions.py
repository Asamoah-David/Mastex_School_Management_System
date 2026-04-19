from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from finance.models import PaymentTransaction


class Command(BaseCommand):
    help = "Normalize PaymentTransaction fields (provider/payment_type) to canonical values"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would change without writing to the database",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Limit number of rows to update (0 = no limit)",
        )

    def handle(self, *args, **options):
        dry_run = bool(options.get("dry_run"))
        limit = int(options.get("limit") or 0)

        total_candidates = 0
        updated = 0

        qs = PaymentTransaction.objects.all().only("id", "provider", "payment_type")
        if limit > 0:
            qs = qs.order_by("id")[:limit]

        with transaction.atomic():
            for tx in qs:
                total_candidates += 1
                new_provider = (tx.provider or "").strip().lower() or tx.provider
                new_payment_type = (tx.payment_type or "").strip()

                new_status = (tx.status or "").strip().lower() or tx.status
                if new_status in ("complete", "completed"):
                    new_status = "completed"
                elif new_status in ("fail", "failed"):
                    new_status = "failed"
                elif new_status in ("pend", "pending"):
                    new_status = "pending"

                if new_payment_type == "fee":
                    new_payment_type = "school_fee"

                if new_provider != tx.provider or new_payment_type != tx.payment_type or new_status != tx.status:
                    if dry_run:
                        self.stdout.write(
                            f"Would update id={tx.id} provider={tx.provider!r}->{new_provider!r} "
                            f"payment_type={tx.payment_type!r}->{new_payment_type!r} "
                            f"status={tx.status!r}->{new_status!r}"
                        )
                    else:
                        PaymentTransaction.objects.filter(pk=tx.pk).update(
                            provider=new_provider,
                            payment_type=new_payment_type,
                            status=new_status,
                        )
                    updated += 1

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(
            f"Scanned {total_candidates} rows. {'Would update' if dry_run else 'Updated'} {updated} rows."
        )
