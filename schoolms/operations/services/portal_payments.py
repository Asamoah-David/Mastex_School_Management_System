from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from payments.services.ledger import PaymentTypes, record_payment_transaction

logger = logging.getLogger(__name__)


def _currency() -> str:
    return getattr(settings, "PAYSTACK_CURRENCY", "GHS")


def _record_to_school_ledger(*, school_id, amount, reference, description, metadata=None):
    """Write to school funds ledger.

    When called inside a ``transaction.atomic()`` block (the normal path for
    all ``mark_*_completed`` functions), any failure will propagate and roll
    back the enclosing transaction — keeping the payment record and ledger
    in sync.  The exception is still logged for observability.
    """
    from finance.services.school_funds import record_fee_collected

    record_fee_collected(
        school_id=school_id,
        amount=amount,
        reference=reference,
        description=description,
        currency=_currency(),
        metadata=metadata,
    )


def mark_canteen_payment_completed(*, payment, reference: str | None) -> None:
    with transaction.atomic():
        payment.payment_status = "completed"
        payment.payment_date = timezone.now().date()
        if reference and not payment.payment_reference:
            payment.payment_reference = reference
        payment.save(update_fields=["payment_status", "payment_date", "payment_reference"])
        if reference:
            record_payment_transaction(
                reference=reference,
                school_id=payment.school_id,
                amount=payment.amount or Decimal("0"),
                status="completed",
                payment_type=PaymentTypes.CANTEEN,
                object_id=str(payment.pk),
                metadata={"canteen_payment_id": payment.pk},
            )
            _record_to_school_ledger(
                school_id=payment.school_id,
                amount=payment.amount or Decimal("0"),
                reference=reference,
                description=f"Canteen payment #{payment.pk}",
                metadata={"canteen_payment_id": payment.pk},
            )


def mark_canteen_payment_failed(*, payment, reference: str | None) -> None:
    payment.payment_status = "failed"
    payment.save(update_fields=["payment_status"])
    if reference:
        record_payment_transaction(
            reference=reference,
            school_id=payment.school_id,
            amount=payment.amount or Decimal("0"),
            status="failed",
            payment_type=PaymentTypes.CANTEEN,
            object_id=str(payment.pk),
            metadata={"canteen_payment_id": payment.pk},
        )


def mark_bus_payment_completed(*, payment, reference: str | None) -> None:
    with transaction.atomic():
        payment.payment_status = "completed"
        payment.paid = True
        payment.payment_date = timezone.now().date()
        if reference and not payment.payment_reference:
            payment.payment_reference = reference
        payment.save(update_fields=["payment_status", "paid", "payment_date", "payment_reference"])
        if reference:
            record_payment_transaction(
                reference=reference,
                school_id=payment.school_id,
                amount=payment.amount or Decimal("0"),
                status="completed",
                payment_type=PaymentTypes.BUS,
                object_id=str(payment.pk),
                metadata={"bus_payment_id": payment.pk},
            )
            _record_to_school_ledger(
                school_id=payment.school_id,
                amount=payment.amount or Decimal("0"),
                reference=reference,
                description=f"Bus payment #{payment.pk}",
                metadata={"bus_payment_id": payment.pk},
            )


def mark_bus_payment_failed(*, payment, reference: str | None) -> None:
    payment.payment_status = "failed"
    payment.save(update_fields=["payment_status"])
    if reference:
        record_payment_transaction(
            reference=reference,
            school_id=payment.school_id,
            amount=payment.amount or Decimal("0"),
            status="failed",
            payment_type=PaymentTypes.BUS,
            object_id=str(payment.pk),
            metadata={"bus_payment_id": payment.pk},
        )


def mark_textbook_sale_completed(*, sale, reference: str | None) -> None:
    with transaction.atomic():
        sale.payment_status = "completed"
        if reference and not sale.payment_reference:
            sale.payment_reference = reference
        sale.save(update_fields=["payment_status", "payment_reference"])
        if reference:
            record_payment_transaction(
                reference=reference,
                school_id=sale.school_id,
                amount=sale.amount or Decimal("0"),
                status="completed",
                payment_type=PaymentTypes.TEXTBOOK,
                object_id=str(sale.pk),
                metadata={"textbook_sale_id": sale.pk},
            )
            _record_to_school_ledger(
                school_id=sale.school_id,
                amount=sale.amount or Decimal("0"),
                reference=reference,
                description=f"Textbook sale #{sale.pk}",
                metadata={"textbook_sale_id": sale.pk},
            )


def mark_textbook_sale_failed(*, sale, reference: str | None) -> None:
    sale.payment_status = "failed"
    sale.save(update_fields=["payment_status"])
    if reference:
        record_payment_transaction(
            reference=reference,
            school_id=sale.school_id,
            amount=sale.amount or Decimal("0"),
            status="failed",
            payment_type=PaymentTypes.TEXTBOOK,
            object_id=str(sale.pk),
            metadata={"textbook_sale_id": sale.pk},
        )


def mark_hostel_fee_completed(*, fee, reference: str | None, paid_amount: Decimal | None = None) -> Decimal:
    """Apply a hostel payment atomically and mirror it to ledgers."""

    def _normalize_amount(value) -> Decimal:
        try:
            return Decimal(str(value))
        except (TypeError, InvalidOperation):
            return Decimal("0")

    requested = paid_amount
    if requested is None:
        # Fall back to remaining balance (or total) when amount is not provided (e.g., webhook)
        requested = getattr(fee, "balance", None)
        if requested in (None, ""):
            requested = fee.amount

    amount_to_apply = _normalize_amount(requested)
    if amount_to_apply <= Decimal("0"):
        return Decimal("0")

    amount_to_apply = amount_to_apply.quantize(Decimal("0.01"))

    with transaction.atomic():
        added = fee.add_payment(amount=amount_to_apply, payment_reference=reference)
        if not added:
            return Decimal("0")

        if reference:
            metadata = {"hostel_fee_id": fee.pk}
            if not fee.paid:
                metadata["partial"] = True

            record_payment_transaction(
                reference=reference,
                school_id=fee.school_id,
                amount=amount_to_apply,
                status="completed",
                payment_type=PaymentTypes.HOSTEL,
                object_id=str(fee.pk),
                metadata=metadata,
            )
            _record_to_school_ledger(
                school_id=fee.school_id,
                amount=amount_to_apply,
                reference=reference,
                description=f"Hostel fee #{fee.pk}",
                metadata=metadata,
            )

    return amount_to_apply


def mark_hostel_fee_failed(*, fee, reference: str | None) -> None:
    fee.payment_status = "failed"
    fee.save(update_fields=["payment_status"])
    if reference:
        record_payment_transaction(
            reference=reference,
            school_id=fee.school_id,
            amount=fee.amount or Decimal("0"),
            status="failed",
            payment_type=PaymentTypes.HOSTEL,
            object_id=str(fee.pk),
            metadata={"hostel_fee_id": fee.pk},
        )
