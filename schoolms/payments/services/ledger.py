from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from django.conf import settings


class PaymentTypes:
    SCHOOL_FEE = "school_fee"
    SCHOOL_FEE_MANUAL = "school_fee_manual"
    SCHOOL_FEE_OFFLINE = "school_fee_offline"
    CANTEEN = "canteen"
    BUS = "bus"
    TEXTBOOK = "textbook"
    HOSTEL = "hostel"


def record_payment_transaction(
    *,
    provider: str = "paystack",
    reference: str,
    school_id: Optional[int],
    amount: Any,
    status: str,
    payment_type: str,
    object_id: str = "",
    metadata: Optional[dict] = None,
) -> None:
    if not reference:
        return

    provider = (provider or "").strip().lower() or provider
    status = (status or "").strip().lower() or status
    if status not in ("pending", "completed", "failed"):
        return

    if payment_type == "fee":
        payment_type = PaymentTypes.SCHOOL_FEE

    from finance.models import PaymentTransaction

    amt = amount
    if not isinstance(amt, Decimal):
        try:
            amt = Decimal(str(amt or 0))
        except Exception:
            amt = Decimal("0")

    if status == "failed":
        try:
            if PaymentTransaction.objects.filter(reference=reference, status="completed").exists():
                return
        except Exception:
            return

    try:
        PaymentTransaction.objects.update_or_create(
            reference=reference,
            defaults={
                "provider": provider,
                "school_id": school_id,
                "amount": amt,
                "currency": getattr(settings, "PAYSTACK_CURRENCY", "GHS"),
                "status": status,
                "payment_type": payment_type,
                "object_id": object_id or "",
                "metadata": metadata or {},
            },
        )
    except Exception:
        return
