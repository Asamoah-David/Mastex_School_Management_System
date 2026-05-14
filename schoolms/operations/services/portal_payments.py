from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from operations.models.canteen import CanteenPayment
from operations.models.transport import BusPayment
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
    """Settle a Paystack canteen row: align ``amount_paid`` with ``amount`` and mirror to ledgers.

    Idempotent: if already completed with full ``amount_paid``, returns without re-crediting school funds.
    """
    with transaction.atomic():
        cp = CanteenPayment.objects.select_for_update().get(pk=payment.pk)
        full = (cp.amount or Decimal("0")).quantize(Decimal("0.01"))
        paid = (cp.amount_paid or Decimal("0")).quantize(Decimal("0.01"))
        if cp.payment_status == "completed" and paid >= full and full > 0:
            return

        cp.amount_paid = full
        cp.payment_status = "completed"
        cp.payment_date = timezone.now().date()
        if reference and not cp.payment_reference:
            cp.payment_reference = reference
        ref_str = (reference or cp.payment_reference or "").strip()
        hist = list(cp.payment_history or [])
        if ref_str and not any((r.get("reference") or "") == ref_str for r in hist):
            hist.append(
                {
                    "amount": str(full),
                    "date": str(cp.payment_date),
                    "reference": ref_str,
                }
            )
        elif not hist:
            hist.append(
                {
                    "amount": str(full),
                    "date": str(cp.payment_date),
                    "reference": ref_str,
                }
            )
        cp.payment_history = hist
        cp.save(
            update_fields=[
                "amount_paid",
                "payment_status",
                "payment_date",
                "payment_reference",
                "payment_history",
            ]
        )

        if reference:
            record_payment_transaction(
                reference=reference,
                school_id=cp.school_id,
                amount=full,
                status="completed",
                payment_type=PaymentTypes.CANTEEN,
                object_id=str(cp.pk),
                metadata={"canteen_payment_id": cp.pk},
            )
            _record_to_school_ledger(
                school_id=cp.school_id,
                amount=full,
                reference=reference,
                description=f"Canteen payment #{cp.pk}",
                metadata={"canteen_payment_id": cp.pk},
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
    """Complete a bus Paystack payment and align ``amount_paid`` with charged ``amount``.

    Idempotent when already completed with full ``amount_paid`` (avoids duplicate school-fund credits).
    """
    with transaction.atomic():
        bp = BusPayment.objects.select_for_update().get(pk=payment.pk)
        full = (bp.amount or Decimal("0")).quantize(Decimal("0.01"))
        paid = (bp.amount_paid or Decimal("0")).quantize(Decimal("0.01"))
        if bp.payment_status == "completed" and bp.paid and paid >= full and full > 0:
            return

        bp.amount_paid = full
        bp.payment_status = "completed"
        bp.paid = True
        bp.payment_date = timezone.now().date()
        if reference and not bp.payment_reference:
            bp.payment_reference = reference
        ref_str = (reference or bp.payment_reference or "").strip()
        hist = list(bp.payment_history or [])
        if ref_str and not any((r.get("reference") or "") == ref_str for r in hist):
            hist.append(
                {
                    "amount": str(full),
                    "date": str(bp.payment_date),
                    "reference": ref_str,
                }
            )
        elif not hist:
            hist.append(
                {
                    "amount": str(full),
                    "date": str(bp.payment_date),
                    "reference": ref_str,
                }
            )
        bp.payment_history = hist
        bp.save(
            update_fields=[
                "amount_paid",
                "payment_status",
                "paid",
                "payment_date",
                "payment_reference",
                "payment_history",
            ]
        )

        if reference:
            record_payment_transaction(
                reference=reference,
                school_id=bp.school_id,
                amount=full,
                status="completed",
                payment_type=PaymentTypes.BUS,
                object_id=str(bp.pk),
                metadata={"bus_payment_id": bp.pk},
            )
            _record_to_school_ledger(
                school_id=bp.school_id,
                amount=full,
                reference=reference,
                description=f"Bus payment #{bp.pk}",
                metadata={"bus_payment_id": bp.pk},
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


def mark_hostel_fee_completed(
    *,
    fee,
    reference: str | None,
    paid_amount: Decimal | None = None,
    recorded_by=None,
    provider: str = "paystack",
) -> Decimal:
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
        added = fee.add_payment(
            amount=amount_to_apply,
            payment_reference=reference,
            recorded_by=recorded_by,
        )
        if not added:
            return Decimal("0")

        if reference:
            metadata = {"hostel_fee_id": fee.pk}
            if not fee.paid:
                metadata["partial"] = True

            record_payment_transaction(
                provider=provider,
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
