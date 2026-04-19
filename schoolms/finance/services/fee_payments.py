from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models, transaction

from payments.services.ledger import PaymentTypes, record_payment_transaction


def net_amount_for_school_fee(*, reference: str, fee_id: int, paystack_major_units) -> Decimal:
    from finance.models import FeePayment

    pending = FeePayment.objects.filter(
        paystack_reference=reference, status="pending", fee_id=fee_id
    ).first()
    if pending:
        return pending.amount
    if isinstance(paystack_major_units, Decimal):
        return paystack_major_units
    return Decimal(str(paystack_major_units))


def complete_fee_payment(*, fee_id: int, reference: str, paid_amount, paystack_id, channel: str) -> bool:
    from finance.models import Fee, FeePayment

    with transaction.atomic():
        pending = (
            FeePayment.objects.select_for_update()
            .select_related("fee")
            .filter(paystack_reference=reference, status="pending")
            .order_by("-pk")
            .first()
        )
        if not pending:
            return False

        if pending.fee_id != fee_id:
            return False

        fee = Fee.objects.select_for_update().get(id=fee_id)
        remaining = fee.amount - fee.amount_paid
        if remaining < Decimal("0"):
            remaining = Decimal("0")

        credit = paid_amount
        if not isinstance(credit, Decimal):
            credit = Decimal(str(credit))
        if credit < Decimal("0"):
            credit = Decimal("0")
        if credit > remaining:
            credit = remaining

        pending.status = "completed"
        pending.amount = credit
        pending.paystack_payment_id = paystack_id
        pending.payment_method = channel
        if not pending.receipt_no:
            pending.receipt_no = f"RCP-FEE-{pending.fee_id}-{pending.pk or ''}"[:64]
        pending.save(update_fields=["status", "amount", "paystack_payment_id", "payment_method", "receipt_no"])

        record_payment_transaction(
            reference=reference,
            school_id=pending.fee.school_id,
            amount=credit,
            status="completed",
            payment_type=PaymentTypes.SCHOOL_FEE,
            object_id=str(pending.fee_id),
            metadata={
                "fee_payment_id": pending.pk,
                "paystack_payment_id": paystack_id,
                "channel": channel,
            },
        )

        Fee.objects.filter(id=fee_id).update(amount_paid=models.F("amount_paid") + credit)
        fee.refresh_from_db(fields=["amount_paid"])
        fee.save()
        return True


def currency_code() -> str:
    return getattr(settings, "PAYSTACK_CURRENCY", "GHS")
