from __future__ import annotations

from decimal import Decimal

from django.utils import timezone

from payments.services.ledger import PaymentTypes, record_payment_transaction


def mark_canteen_payment_completed(*, payment, reference: str | None) -> None:
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


def mark_hostel_fee_completed(*, fee, reference: str | None) -> None:
    from operations.models import HostelFeePayment

    fee.payment_status = "completed"
    fee.paid = True
    fee.payment_date = timezone.now().date()
    fee.amount_paid = fee.amount
    if reference and not fee.payment_reference:
        fee.payment_reference = reference
    if fee.payment_history is None:
        fee.payment_history = []
    if reference and not any((entry or {}).get("reference") == reference for entry in fee.payment_history):
        fee.payment_history.append(
            {
                "amount": str(fee.amount or Decimal("0")),
                "date": str(fee.payment_date),
                "reference": reference,
            }
        )
    fee.save(update_fields=["payment_status", "paid", "payment_date", "amount_paid", "payment_reference", "payment_history"])

    if reference:
        HostelFeePayment.objects.get_or_create(
            payment_reference=reference,
            defaults={
                "hostel_fee": fee,
                "amount": fee.amount or Decimal("0"),
                "recorded_by": None,
            },
        )
    else:
        HostelFeePayment.objects.create(
            hostel_fee=fee,
            amount=fee.amount or Decimal("0"),
            recorded_by=None,
        )

    if reference:
        record_payment_transaction(
            reference=reference,
            school_id=fee.school_id,
            amount=fee.amount or Decimal("0"),
            status="completed",
            payment_type=PaymentTypes.HOSTEL,
            object_id=str(fee.pk),
            metadata={"hostel_fee_id": fee.pk},
        )


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
